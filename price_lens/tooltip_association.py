"""Pixel proofs binding a native description to its inventory source cell."""
from collections import OrderedDict
from dataclasses import dataclass,field
import hashlib

from PySide6.QtCore import QPoint,QRect
from PySide6.QtGui import QImage,QRegion

from .tooltip_source import TitleProof,capture_title
from .tooltip_geometry import verified_frame
from .inventory_pixels import InventoryHeader,same_cell


def association_state(value):
    if value is None:return 'normal'
    if not isinstance(value,dict):return 'rejected'
    state=value.get('state')
    return state if state in ('normal','inventory-primary') else 'rejected'


def _rect(value,image):
    if not isinstance(value,dict):return None
    parts=[value.get(k) for k in ('x','y','width','height')]
    if any(type(v) is not int for v in parts) or parts[2]<=0 or parts[3]<=0:return None
    if any(abs(v)>32768 for v in parts):return None
    rect=QRect(*parts)
    return rect if image.rect().contains(rect) else None


def _fingerprint(image,rect):
    pixels=image.copy(rect).convertToFormat(QImage.Format.Format_RGBA8888)
    return hashlib.blake2b(pixels.constBits(),digest_size=12).digest()


def _point(value):
    if isinstance(value,dict):value=(value.get('x'),value.get('y'))
    if not isinstance(value,(tuple,list)) or len(value)!=2 or any(type(v) is not int for v in value):return None
    return tuple(value)


def _pixels(image,rect):
    patch=image.copy(rect).convertToFormat(QImage.Format.Format_RGBA8888)
    return bytes(patch.constBits())


def _guard_regions(rect,source):
    """Exclude only a header's rounded top corners, never its interior."""
    if (rect.x()!=source.x() or rect.y()!=source.y() or rect.width()!=source.width()
            or not 12<=rect.height()<=source.height()/3):return (rect,)
    corner=max(2,min(6,round(source.width()/207*2)))
    if rect.width()<=corner*2 or rect.height()<=corner:return (rect,)
    return (QRect(rect.x()+corner,rect.y(),rect.width()-corner*2,rect.height()),
            QRect(rect.x(),rect.y()+corner,corner,rect.height()-corner),
            QRect(rect.right()-corner+1,rect.y()+corner,corner,rect.height()-corner))


@dataclass(frozen=True)
class TooltipAssociation:
    token: str
    source: QRect
    slot: QRect
    panel: QRect
    comparison: QRect | None
    source_kind: str
    layout: str
    read_pointer: tuple | None
    cursor: QRect | None
    slot_pixels: bytes
    regions: tuple
    fingerprints: tuple
    title: TitleProof | None = None
    frame_caps: tuple = ()
    header: InventoryHeader | None = None
    _matches_cache: OrderedDict = field(default_factory=OrderedDict,init=False,repr=False,compare=False)

    @classmethod
    def from_result(cls,result,image,pointer=None):
        """Reuse the reader's immutable proof; decode direct legacy readings."""
        if '_tooltip_context' in result:
            proof=result['_tooltip_context']
            return proof if isinstance(proof,cls) else None
        tooltip=result.get('tooltip')
        return cls.read(result.get('tooltipAssociation'),tooltip.get('found') if isinstance(tooltip,dict) else None,image,pointer=pointer)

    @classmethod
    def read(cls,value,found,image,pointer=None,*,exclude=()):
        if association_state(value)!='inventory-primary' or not isinstance(found,dict) or image.isNull():return None
        exclude=tuple(exclude)
        if len(exclude)>64 or any(not isinstance(rect,QRect) for rect in exclude):return None
        token=value.get('token')
        if not isinstance(token,str) or not 1<=len(token)<=512:return None
        source=_rect(value.get('source'),image);slot=_rect(value.get('slot'),image)
        panel=_rect(value.get('panel'),image);name=_rect(found.get('area'),image)
        if source is None or slot is None or panel is None or name is None:return None
        if not source.contains(slot) or not panel.contains(name):return None
        version=value.get('version',1)
        if type(version) is not int or version not in (1,2,3):return None
        comparison=None
        source_kind=value.get('sourceKind','inventory')
        layout=value.get('layout','legacy')
        if source_kind!='inventory':return None
        if version>=2 and layout=='primary-left':
            comparison=_rect(value.get('comparison'),image)
            if comparison is None or layout!='primary-left':return None
            # Native association establishes the horizontal pair's role. An
            # inconsistent IPC rectangle must never turn that into a union or
            # move a comparison's title into the primary panel.
            if panel.right()>=comparison.left() or panel.intersects(comparison):return None
        elif version==3:
            if layout!='single' or value.get('comparison') is not None:return None
        elif version==2 or layout not in ('legacy','primary-left'):return None
        read_pointer=_point(value.get('pointer',pointer))
        cursor=_rect(value.get('cursor'),image) if value.get('cursor') is not None else None
        if version>=2:
            if read_pointer is None or cursor is None or not slot.contains(QPoint(*read_pointer)):return None
            if panel.contains(QPoint(*read_pointer)) or comparison is not None and comparison.contains(QPoint(*read_pointer)):return None
            if not cursor.contains(QPoint(*read_pointer)) or not cursor.intersects(slot):return None
            if cursor.width()>slot.width()*2 or cursor.height()>slot.height()*2:return None
        elif cursor is not None and read_pointer is None:return None
        guards=value.get('guards')
        if not isinstance(guards,list) or not 1<=len(guards)<=12:return None
        caps=();header_proof=None
        if version==3:
            caps=value.get('frameCaps')
            frames=(panel,comparison) if comparison is not None else (panel,)
            if (not isinstance(caps,list) or len(caps)!=len(frames)
                    or any(type(v) is not bool for v in caps) or not any(caps)):return None
            header=QRect(source.x(),source.y(),source.width(),round(45*source.width()/207))
            if not any(_rect(value,image)==header for value in guards):return None
            if any(not verified_frame(image,rect,scale=source.width()/207,cap=cap,exclude=exclude)
                   for rect,cap in zip(frames,caps)):return None
            caps=tuple(caps)
            if 'sourceTab' in value:
                header_proof=InventoryHeader.capture(image,source,value['sourceTab'])
                if header_proof is None:return None
        # A stationary pointer and unchanged equipped title do not prove that
        # the inventory cell still contains the item previously associated.
        # Compare its pixels separately, excluding only the old/new captured
        # cursor footprints. An exact slot hash would flicker on hand motion.
        regions=[name]
        for guard in guards:
            rect=_rect(guard,image)
            if rect is None:return None
            if rect==slot:continue
            if header_proof is not None and rect==QRect(*header_proof.rect):continue
            for part in _guard_regions(rect,source):
                if part not in regions:regions.append(part)
        header_pixels=(header_proof.rect[2]*header_proof.rect[3]) if header_proof is not None else 0
        if slot.width()*slot.height()+sum(rect.width()*rect.height() for rect in regions)+header_pixels>131072:return None
        title=capture_title(image,name,panel=panel,pointer=read_pointer,exclude=exclude)
        if title is None:return None
        return cls(token,source,slot,panel,comparison,source_kind,layout,
                   read_pointer,cursor,_pixels(image,slot),tuple(regions),
                      tuple(_fingerprint(image,r) for r in regions),title,caps,header_proof)

    def contains_pointer(self,pointer):
        pointer=_point(pointer)
        if pointer is None:return False
        point=QPoint(*pointer)
        return self.source.contains(point) and self.slot.contains(point)

    def _slot_matches(self,image,pointer):
        current=_pixels(image,self.slot)
        if self.cursor is None or self.read_pointer is None:return current==self.slot_pixels
        point=_point(pointer)
        if point is None:return False
        local=QRect(0,0,self.slot.width(),self.slot.height())
        before=self.cursor.translated(-self.slot.x(),-self.slot.y())
        after=before.translated(point[0]-self.read_pointer[0],point[1]-self.read_pointer[1])
        visible=QRegion(local).subtracted(QRegion(before)).subtracted(QRegion(after))
        if self.header is not None:
            return same_cell(self.slot_pixels,current,self.slot.width(),self.slot.height(),visible,self.source.width()/207)
        # The rectangular cursor envelope is deliberately conservative. Near
        # a cell edge it can leave a narrow, fully exposed strip below 10% of
        # the cell. Require a scaled 4x4 block's worth of exact visible pixels
        # alongside the independent header/frame/title proofs instead.
        minimum=max(16,round(16*(self.source.width()/207)**2))
        if sum(r.width()*r.height() for r in visible)<minimum:return False
        # Apply the coverage rule even when one animation frame happens to be
        # byte-identical, so a wholly hidden cell cannot alternate authority.
        if current==self.slot_pixels:return True
        stride=self.slot.width()*4
        for rect in visible:
            for row in range(rect.top(),rect.bottom()+1):
                begin=row*stride+rect.left()*4;end=begin+rect.width()*4
                if current[begin:end]!=self.slot_pixels[begin:end]:return False
        return True

    def matches(self,image,pointer,*,exclude=()):
        if not self.contains_pointer(pointer) or image.isNull():return False
        exclude=tuple(exclude)
        if len(exclude)>64 or any(not isinstance(rect,QRect) for rect in exclude):return False
        # Capture owns immutable QImages. Qt changes cacheKey on a pixel edit or
        # detach, so a different capture, pointer or paint mask cannot reuse a
        # previous decision. Bound this to the submitted/current frames' checks.
        key=(image.cacheKey(),_point(pointer),tuple(rect.getRect() for rect in exclude))
        cached=self._matches_cache.get(key)
        if cached is not None:return cached
        result=self._matches_current(image,pointer,exclude)
        self._matches_cache[key]=result
        while len(self._matches_cache)>4:self._matches_cache.popitem(last=False)
        return result

    def _matches_current(self,image,pointer,exclude):
        if any(not image.rect().contains(rect) for rect in
               (self.source,self.slot,self.panel,*((self.comparison,) if self.comparison is not None else ()))):return False
        frames=(self.panel,self.comparison) if self.comparison is not None else (self.panel,)
        return (self._slot_matches(image,pointer)
                and (self.header is None or self.header.matches(image))
                and all(verified_frame(image,rect,scale=self.source.width()/207,cap=cap,exclude=exclude)
                        for rect,cap in zip(frames,self.frame_caps))
                and (self.title.matches(image,panel=self.panel,pointer=pointer,antialias=True,exclude=exclude) if self.title is not None
                     else _fingerprint(image,self.regions[0])==self.fingerprints[0]) and all(
            image.rect().contains(rect) and _fingerprint(image,rect)==proof
            for rect,proof in zip(self.regions[1:],self.fingerprints[1:])))

"""Pixel proofs binding a native description to its inventory source cell."""
from dataclasses import dataclass
import hashlib

from PySide6.QtCore import QPoint,QRect
from PySide6.QtGui import QImage,QRegion


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

    @classmethod
    def from_result(cls,result,image,pointer=None):
        """Reuse the reader's immutable proof; decode direct legacy readings."""
        if '_tooltip_context' in result:
            proof=result['_tooltip_context']
            return proof if isinstance(proof,cls) else None
        return cls.read(result.get('tooltipAssociation'),(result.get('tooltip') or {}).get('found'),image,pointer=pointer)

    @classmethod
    def read(cls,value,found,image,pointer=None):
        if association_state(value)!='inventory-primary' or not isinstance(found,dict) or image.isNull():return None
        token=value.get('token')
        if not isinstance(token,str) or not 1<=len(token)<=512:return None
        source=_rect(value.get('source'),image);slot=_rect(value.get('slot'),image)
        panel=_rect(value.get('panel'),image);name=_rect(found.get('area'),image)
        if source is None or slot is None or panel is None or name is None:return None
        if not source.contains(slot) or not panel.contains(name):return None
        version=value.get('version',1)
        if type(version) is not int or version not in (1,2):return None
        comparison=None
        source_kind=value.get('sourceKind','inventory')
        layout=value.get('layout','legacy')
        if source_kind!='inventory':return None
        if version==2:
            comparison=_rect(value.get('comparison'),image)
            if comparison is None or layout!='primary-left':return None
            # Native association establishes the horizontal pair's role. An
            # inconsistent IPC rectangle must never turn that into a union or
            # move a comparison's title into the primary panel.
            if panel.right()>=comparison.left() or panel.intersects(comparison):return None
        elif layout not in ('legacy','primary-left'):return None
        read_pointer=_point(value.get('pointer',pointer))
        cursor=_rect(value.get('cursor'),image) if value.get('cursor') is not None else None
        if version==2:
            if read_pointer is None or cursor is None or not slot.contains(QPoint(*read_pointer)):return None
            if panel.contains(QPoint(*read_pointer)) or comparison.contains(QPoint(*read_pointer)):return None
            if not cursor.contains(QPoint(*read_pointer)) or not cursor.intersects(slot):return None
            if cursor.width()>slot.width()*2 or cursor.height()>slot.height()*2:return None
        elif cursor is not None and read_pointer is None:return None
        guards=value.get('guards')
        if not isinstance(guards,list) or not 1<=len(guards)<=12:return None
        # A stationary pointer and unchanged equipped title do not prove that
        # the inventory cell still contains the item previously associated.
        # Compare its pixels separately, excluding only the old/new captured
        # cursor footprints. An exact slot hash would flicker on hand motion.
        regions=[name]
        for guard in guards:
            rect=_rect(guard,image)
            if rect is None:return None
            if rect==slot:continue
            if rect not in regions:regions.append(rect)
        if slot.width()*slot.height()+sum(rect.width()*rect.height() for rect in regions)>131072:return None
        return cls(token,source,slot,panel,comparison,source_kind,layout,
                   read_pointer,cursor,_pixels(image,slot),tuple(regions),
                   tuple(_fingerprint(image,r) for r in regions))

    def contains_pointer(self,pointer):
        pointer=_point(pointer)
        if pointer is None:return False
        point=QPoint(*pointer)
        return self.source.contains(point) and self.slot.contains(point)

    def _slot_matches(self,image,pointer):
        current=_pixels(image,self.slot)
        if current==self.slot_pixels:return True
        if self.cursor is None or self.read_pointer is None:return False
        point=_point(pointer)
        if point is None:return False
        local=QRect(0,0,self.slot.width(),self.slot.height())
        before=self.cursor.translated(-self.slot.x(),-self.slot.y())
        after=before.translated(point[0]-self.read_pointer[0],point[1]-self.read_pointer[1])
        visible=QRegion(local).subtracted(QRegion(before)).subtracted(QRegion(after))
        if sum(r.width()*r.height() for r in visible)<max(16,local.width()*local.height()*.10):return False
        stride=self.slot.width()*4
        for rect in visible:
            for row in range(rect.top(),rect.bottom()+1):
                begin=row*stride+rect.left()*4;end=begin+rect.width()*4
                if current[begin:end]!=self.slot_pixels[begin:end]:return False
        return True

    def matches(self,image,pointer):
        if not self.contains_pointer(pointer) or image.isNull():return False
        if any(not image.rect().contains(rect) for rect in
               (self.source,self.slot,self.panel,*((self.comparison,) if self.comparison is not None else ()))):return False
        return self._slot_matches(image,pointer) and all(
            image.rect().contains(rect) and _fingerprint(image,rect)==proof
            for rect,proof in zip(self.regions,self.fingerprints))

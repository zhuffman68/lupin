"""NPC-window proof and exclusion, independent of item rows and active tabs.

Only captured pixels are used. A known window has three states: present,
unknown (temporarily covered/contradictory), or absent. Unknown retains an
exclusion, never an item identity, asking price or player-shop context.
"""
from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import QPoint,QRect
from PySide6.QtGui import QImage

from .pixel_components import colour_components


def _rgb(image):
    image=image.convertToFormat(QImage.Format.Format_RGBA8888)
    rows=np.frombuffer(image.constBits(),np.uint8).reshape(image.height(),image.bytesPerLine())
    return rows[:,:image.width()*4].reshape(image.height(),image.width(),4)[:,:,:3].astype(np.int16)


def _orange(p):
    r,g,b=p[:,:,0],p[:,:,1],p[:,:,2]
    return (r>=190)&(g>=85)&(g<=205)&(b<=115)&(r-g>=35)&(g-b>=20)


def _green(p):
    return (p[:,:,1]>=110)&(p[:,:,0]>=70)&(p[:,:,0]<=210)&(p[:,:,2]<110)&(p[:,:,1]-p[:,:,2]>40)


def _neutral(p):return (p.min(axis=2)>=210)&(p.max(axis=2)-p.min(axis=2)<=40)


def _red(p):
    # Native bevel/antialias colours can darken the third divider scanline.
    return (p[:,:,0]>=100)&(p[:,:,1]<=75)&(p[:,:,2]<=75)&(p[:,:,0]-p[:,:,1]>=75)&(p[:,:,0]-p[:,:,2]>=75)


def _grey(p):return (p.min(axis=2)>=110)&(p.max(axis=2)-p.min(axis=2)<=40)


def _tabs(p):
    neutral=(p.max(axis=2)-p.min(axis=2)<=40)&(p.min(axis=2)>=80)
    pink=(p[:,:,0]>=145)&(p[:,:,0]-p[:,:,1]>=35)&(p[:,:,2]>=35)&(p[:,:,2]<=210)
    return neutral|pink


def _at(anchor,x,y,w,h):
    left,top,s=anchor
    return QRect(left+round(x*s),top+round(y*s),max(1,round(w*s)),max(1,round(h*s)))


def _guards(anchor):
    at=lambda *parts:_at(anchor,*parts)
    return ((at(0,0,66,14),_orange,.45),(at(230,0,66,14),_orange,.45),
        (at(0,-20,66,14),_green,.45),
        (at(206,31,90,2),_neutral,.6),(at(206,41,90,2),_neutral,.6),
        (at(-146,82,444,3),_red,.78),
        (at(-42,-26,98,3),_grey,.6),(at(186,-26,100,3),_grey,.6))


class _Probe:
    def __init__(self,image,roi,exclude):
        self.roi=roi;self.rgb=_rgb(image.copy(roi))
        self.visible=np.ones(self.rgb.shape[:2],dtype=bool)
        for mask in exclude:
            part=roi.intersected(mask)
            if not part.isEmpty():self.visible[part.top()-roi.top():part.bottom()-roi.top()+1,
                part.left()-roi.left():part.right()-roi.left()+1]=False

    def evidence(self,rect,predicate,fraction):
        if not self.roi.contains(rect):return None
        yy=slice(rect.top()-self.roi.top(),rect.bottom()-self.roi.top()+1)
        xx=slice(rect.left()-self.roi.left(),rect.right()-self.roi.left()+1)
        shown=self.visible[yy,xx];count=int(shown.sum())
        if count<max(2,rect.width()*rect.height()*.6):return None
        return int((predicate(self.rgb[yy,xx])&shown).sum())>=count*fraction


@dataclass(frozen=True)
class NpcShop:
    rectangle: QRect
    anchor: tuple
    controls: tuple
    pixels: tuple

    @property
    def lists(self):
        return _at(self.anchor,-154,88,462,244).intersected(self.rectangle)

    def state(self,image,exclude=()):
        if image is None or image.isNull():return 'unknown'
        # Tabs, wallet digits, portraits and both lists are absent from these
        # stable samples. Byte-identical controls take the inexpensive path.
        if all(image.rect().contains(rect) and not any(rect.intersects(mask) for mask in exclude)
               and image.copy(rect).convertToFormat(QImage.Format.Format_RGBA8888)==pixels
               for rect,pixels in zip(self.controls,self.pixels)):return 'present'
        roi=_at(self.anchor,-154,-34,462,122).intersected(image.rect())
        if roi.isEmpty():return 'absent'
        probe=_Probe(image,roi,exclude)
        states=[probe.evidence(*guard) for guard in _guards(self.anchor)]
        positive=sum(value is True for value in states);negative=sum(value is False for value in states)
        if positive==len(states):return 'present'
        # An uncertain header cannot promote known NPC rows to player listings.
        # Multiple exposed contradictions release the old window immediately.
        if negative==0 or negative==1 and positive>=6:return 'unknown'
        return 'absent'

    def matches(self,image,exclude=()):return self.state(image,exclude)=='present'

    def contains(self,pointer):
        return pointer is not None and self.rectangle.contains(QPoint(*pointer))


def find_npc_shop(image,*,exclude=(),near=None):
    """Acquire a complete current control grid from either NPC column.

    A hint is geometry only. Initial proof requires every native guard;
    subsequent unknown states are available only for an already proved window.
    """
    if image is None or image.isNull():return None
    roi=image.rect()
    if isinstance(near,QRect) and not near.isEmpty():
        s=max(.5,min(3,near.width()/199))
        roi=near.adjusted(-round(270*s),-round(165*s),round(330*s),round(35*s)).intersected(roi)
    if roi.isEmpty() or roi.width()*roi.height()>4_000_000:return None
    probe=_Probe(image,roi,exclude);orange=_orange(probe.rgb)&probe.visible
    buttons=[]
    for left,top,right,bottom in colour_components(orange):
        w,h=right-left+1,bottom-top+1
        if 30<=w<=210 and 7<=h<=48 and 2.8<=w/h<=6:
            buttons.append(QRect(roi.x()+left,roi.y()+top,w,h))
    buttons=sorted(buttons,key=lambda rect:(rect.y(),rect.x()))[:128]
    for left in buttons:
        for right in buttons:
            s=(right.x()-left.x())/230
            if not .5<=s<=3 or abs(left.width()-66*s)>3*s or abs(right.width()-66*s)>3*s:continue
            if abs(right.y()-left.y())>3*s or not 10*s<=left.height()<=19*s:continue
            # Components may include a bevel. Locate their native interior in
            # a bounded offset, retaining all independent control/frame checks.
            for dy in sorted(range(-round(3*s),round(3*s)+1),key=abs):
                anchor=(left.x(),left.y()+dy,s)
                if not all(probe.evidence(*guard) is True for guard in _guards(anchor)):continue
                if not all(probe.evidence(_at(anchor,*parts),_tabs,.6) is True
                           for parts in ((-145,63,204,16),(85,63,172,16))):continue
                controls=tuple(guard[0] for guard in _guards(anchor))
                rectangle=_at(anchor,-154,-34,462,376).intersected(image.rect())
                return NpcShop(rectangle,anchor,controls,tuple(image.copy(rect).convertToFormat(QImage.Format.Format_RGBA8888)
                                                             for rect in controls))
    return None


def suppress_npc_rows(result,npc):
    """Filter NPC-owned rows before player context, cards/history or prices."""
    if npc is None:return result
    area=(result.get('shop') or {}).get('area') or {}
    if all(type(area.get(key)) is int for key in ('x','y','width','height')):
        table=QRect(*(area[key] for key in ('x','y','width','height')))
        if npc.rectangle.intersects(table):return {**result,'shop':None,'hover':None}
    return result


def suppress_npc_prices(result,npc,pointer,*,inventory=None):
    """Only a validated ordinary inventory header can bypass NPC exclusion.

    A raw inventory-primary flag is not proof. The caller must validate the
    submitted source/header/slot/title against current pixels first.
    """
    result=suppress_npc_rows(result,npc)
    if npc is None or not npc.contains(pointer):return result
    from .tooltip_association import TooltipAssociation
    independent=(isinstance(inventory,TooltipAssociation) and inventory.header is not None
                 and inventory.contains_pointer(pointer))
    if independent:return result
    return {**result,'hover':None,'tooltip':None,'tooltipAssociation':{'state':'rejected'}}

"""Screen-pixel detection and presentation state for Classic's shop price form."""
from dataclasses import dataclass,field
import time

import numpy as np
from PySide6.QtCore import QRect
from PySide6.QtGui import QImage


def _runs(values,gap=0):
    groups=[]
    for value in values:
        value=int(value)
        if not groups or value>groups[-1][1]+gap+1:groups.append([value,value])
        else:groups[-1][1]=value
    return groups


def _exposed_form_structure(image,rect,exclude):
    """A caption and connected left/bottom frame when our paint hides controls."""
    patch=image.copy(rect).convertToFormat(QImage.Format.Format_RGBA8888)
    rows=np.frombuffer(patch.constBits(),np.uint8).reshape(patch.height(),patch.bytesPerLine())
    rgb=rows[:,:patch.width()*4].reshape(patch.height(),patch.width(),4)[:,:,:3].astype(np.int16)
    visible=np.ones(rgb.shape[:2],dtype=bool);s=rect.width()/232
    for hidden in exclude:
        part=rect.intersected(hidden.adjusted(-1,-1,1,1))
        if not part.isEmpty():visible[part.top()-rect.top():part.bottom()-rect.top()+1,
            part.left()-rect.left():part.right()-rect.left()+1]=False
    def region(x,y,w,h):
        return (slice(round(y*s),round((y+h)*s)),slice(round(x*s),round((x+w)*s)))
    caption=region(6,5,79,13)
    if int(((rgb[caption].max(2)<150)&visible[caption]).sum())<max(12,round(24*s*s)):return False
    left=region(0,18,5,113);bottom=region(6,134,220,5)
    for key,axis in ((left,1),(bottom,0)):
        colors=rgb[key];shown=visible[key]
        known=shown.sum(axis=axis)>=max(2,round(3*s))
        if int(known.sum())<max(12,round(20*s)):return False
        low=np.where(shown[:,:,None],colors,32767).min(axis=axis)
        high=np.where(shown[:,:,None],colors,-32768).max(axis=axis)
        strokes=(high-low).max(axis=1)>=24
        if int((strokes&known).sum())<int(known.sum())*.6:return False
    return True


def _form_controls(image,rect,exclude,inputs,buttons):
    if any(cue is False for cue in buttons):return False
    if not any(cue is True for cue in inputs) and not all(cue is None for cue in inputs):return False
    if any(cue is True for cue in inputs) and all(cue is True for cue in buttons):return True
    # Unknown is permitted only for control pixels covered by known Lupin
    # rectangles, with independent caption and connected native frame evidence.
    return _exposed_form_structure(image,rect,exclude)


def price_entry_dialog(image,shop,exclude=()):
    """Require native form structure and exposed controls or proven own occlusion.

    All evidence comes from exposed pixels beside an independently known shop.
    Opaque Lupin annotations cannot provide or refute the native dialog's cues.
    """
    if image is None or image.isNull() or not isinstance(shop,QRect) or shop.isEmpty():return None
    scale=max(.65,min(2.1,shop.width()/199))
    roi=shop.adjusted(-round(20*scale),-round(65*scale),round(360*scale),round(90*scale)).intersected(image.rect())
    if roi.isEmpty() or roi.width()*roi.height()>1_500_000:return None
    patch=image.copy(roi).convertToFormat(QImage.Format.Format_RGBA8888)
    rgb=np.frombuffer(patch.constBits(),dtype=np.uint8).reshape(patch.height(),patch.bytesPerLine())
    rgb=rgb[:,:patch.width()*4].reshape(patch.height(),patch.width(),4)[:,:,:3].astype(np.int16)
    visible=np.ones(rgb.shape[:2],dtype=bool)
    for hidden in exclude:
        part=roi.intersected(hidden.adjusted(-1,-1,1,1))
        if not part.isEmpty():visible[part.y()-roi.y():part.bottom()-roi.y()+1,part.x()-roi.x():part.right()-roi.x()+1]=False
    r,g,b=rgb[:,:,0],rgb[:,:,1],rgb[:,:,2]
    pink=(r>=150)&(r-g>=35)&(b-g>=15)&(b<=220)&(g>=45)&(g<=165)&visible
    rows=_runs(np.flatnonzero(pink.sum(axis=1)>=max(12,round(20*scale))),gap=max(1,round(2*scale)))
    bands=[]
    for top,bottom in rows:
        height=bottom-top+1
        if not 9*scale<=height<=20*scale:continue
        for left,right in _runs(np.flatnonzero(pink[top:bottom+1].sum(axis=0)>=height*.25),gap=max(1,round(scale))):
            if 45*scale<=right-left+1<=125*scale:bands.append((left,top,right,bottom))
    bands.sort(key=lambda band:(band[1],band[0]))

    def evidence(rect,predicate,minimum=24,fraction=.65,control=False):
        part=rect.intersected(roi)
        if part!=rect:return False
        yy=slice(part.y()-roi.y(),part.bottom()-roi.y()+1)
        xx=slice(part.x()-roi.x(),part.right()-roi.x()+1)
        exposed=visible[yy,xx];count=int(exposed.sum())
        if control and count<max(minimum,rect.width()*rect.height()*.2):return None
        return count>=minimum and int((predicate(rgb[yy,xx])&exposed).sum())>=count*fraction

    neutral=lambda colors:(colors.min(axis=2)>=220)&(colors.max(axis=2)-colors.min(axis=2)<45)
    orange=lambda colors:(colors[:,:,0]>=190)&(colors[:,:,0]-colors[:,:,1]>=25)&(colors[:,:,1]-colors[:,:,2]>=12)
    for first in bands[:24]:
        left,top,_,_=first
        followers=[band for band in bands if abs(band[0]-left)<=3*scale and band[1]>top]
        for second in followers:
            pitch=second[1]-top;s=pitch/20
            if not .65<=s<=2.1 or abs(s-scale)>scale*.12:continue
            third=next((band for band in followers if abs(band[1]-(top+2*pitch))<=2*scale),None)
            if third is None:continue
            rect=QRect(roi.x()+left-round(6*s),roi.y()+top-round(27*s),round(232*s),round(139*s))
            if not image.rect().contains(rect):continue
            def at(x,y,w,h):return QRect(rect.x()+round(x*s),rect.y()+round(y*s),round(w*s),round(h*s))
            if not evidence(at(5,4,220,13),neutral,minimum=round(30*s*s),fraction=.6):continue
            inputs=[evidence(at(118,29+20*i,104,12),neutral,minimum=round(30*s*s),fraction=.75,control=True) for i in range(3)]
            buttons=[evidence(at(x,118,40,12),orange,minimum=round(20*s*s),fraction=.35,control=True) for x in (132,182)]
            if not _form_controls(image,rect,exclude,inputs,buttons):continue
            if not evidence(rect.adjusted(round(4*s),round(4*s),-round(4*s),-round(4*s)),
                            lambda colors:(colors.max(axis=2)>=190)&(colors.max(axis=2)-colors.min(axis=2)<90),
                            minimum=round(180*s*s),fraction=.6):continue
            return rect
    return None


def _known_form_present(image,rect,exclude):
    """Recheck a measured form when a cursor fragments one label's colour run."""
    if image is None or image.isNull() or not image.rect().contains(rect):return False
    s=rect.width()/232
    if not .65<=s<=2.1:return False
    patch=image.copy(rect).convertToFormat(QImage.Format.Format_RGBA8888)
    rows=np.frombuffer(patch.constBits(),dtype=np.uint8).reshape(patch.height(),patch.bytesPerLine())
    rgb=rows[:,:patch.width()*4].reshape(patch.height(),patch.width(),4)[:,:,:3].astype(np.int16)
    visible=np.ones(rgb.shape[:2],dtype=bool)
    for hidden in exclude:
        part=rect.intersected(hidden.adjusted(-1,-1,1,1))
        if not part.isEmpty():visible[part.y()-rect.y():part.bottom()-rect.y()+1,part.x()-rect.x():part.right()-rect.x()+1]=False
    def check(x,y,w,h,predicate,fraction,control=False):
        yy=slice(round(y*s),round((y+h)*s));xx=slice(round(x*s),round((x+w)*s))
        exposed=visible[yy,xx];colors=rgb[yy,xx];count=int(exposed.sum())
        if control and count<max(12,round(20*s*s),exposed.size*.2):return None
        return count>=max(12,round(20*s*s)) and int((predicate(colors)&exposed).sum())>=count*fraction
    pink=lambda a:(a[:,:,0]>=150)&(a[:,:,0]-a[:,:,1]>=35)&(a[:,:,2]-a[:,:,1]>=15)&(a[:,:,2]<=220)
    white=lambda a:(a.min(axis=2)>=220)&(a.max(axis=2)-a.min(axis=2)<45)
    orange=lambda a:(a[:,:,0]>=190)&(a[:,:,0]-a[:,:,1]>=25)&(a[:,:,1]-a[:,:,2]>=12)
    return (check(5,4,220,13,white,.6)
            and all(check(6,27+20*i,108,16,pink,.25) for i in range(3))
            and _form_controls(image,rect,exclude,
                [check(118,29+20*i,104,12,white,.75,control=True) for i in range(3)],
                [check(x,118,40,12,orange,.35,control=True) for x in (132,182)]))


@dataclass
class ShopPriceEntry:
    rectangle: QRect | None = None
    closed_at: float | None = None
    _memo_key: tuple | None = field(default=None,init=False,repr=False)
    _memo_rect: QRect | None = field(default=None,init=False,repr=False)

    @property
    def blocking(self):return self.rectangle is not None or self.closed_at is not None

    def clear(self):self.rectangle=None;self.closed_at=None;self._memo_key=None;self._memo_rect=None

    def peek(self,image,shop,exclude=()):
        """Share one immutable frame's geometry with capture before UI delivery."""
        if image is None or image.isNull() or not isinstance(shop,QRect) or shop.isEmpty():return None
        key=(image.cacheKey(),shop.getRect(),tuple(rect.getRect() for rect in exclude))
        if key!=self._memo_key:
            previous=self.rectangle
            self._memo_rect=(QRect(previous) if previous is not None
                and _known_form_present(image,previous,exclude) else price_entry_dialog(image,shop,exclude))
            self._memo_key=key
        return QRect(self._memo_rect) if self._memo_rect is not None else None

    def observe(self,image,shop,exclude=(),*,now=None):
        before=self.blocking;previous=self.rectangle
        self.rectangle=self.peek(image,shop,exclude)
        if self.rectangle is not None:self.closed_at=None
        elif previous is not None:self.closed_at=time.monotonic() if now is None else now
        return before!=self.blocking or previous!=self.rectangle

    def accept(self,started_at,*,verified=False,closed=False):
        if self.rectangle is not None or self.closed_at is None:return False
        if started_at is None or started_at<self.closed_at or not (verified or closed):return False
        self.closed_at=None
        return True

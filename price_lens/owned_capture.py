"""Exclude Lupin's own paint only where the shared image proves it is present.

Wayland may report (0, 0) for a movable top-level surface. Those coordinates
are hints, not permission to hide an unrelated part of the game from OCR.
"""
from dataclasses import dataclass
import time
import weakref

from PySide6.QtCore import QPoint,QRect,Qt
from PySide6.QtGui import QImage

from .chat_ocr import pixels


@dataclass
class PaintAnchor:
    rect:QRect
    points:object
    colours:object

    @classmethod
    def from_image(cls,image,rect):
        import numpy as np
        if image.isNull():return None
        rgb=pixels(image).astype('int16')
        if rgb.shape[0]<4 or rgb.shape[1]<8 or rgb.shape[0]*rgb.shape[1]>262144:return None
        edge=np.zeros(rgb.shape[:2],dtype=bool)
        edge[:,1:]|=np.max(np.abs(rgb[:,1:]-rgb[:,:-1]),axis=2)>22
        edge[1:]|=np.max(np.abs(rgb[1:]-rgb[:-1]),axis=2)>22
        # Transparent padding cannot establish that an independent surface is
        # on screen. Its opaque painted strokes must provide the proof.
        argb=image.convertToFormat(QImage.Format.Format_RGBA8888)
        alpha=np.frombuffer(bytes(argb.constBits()),dtype='uint8').reshape(argb.height(),argb.bytesPerLine())[:,:argb.width()*4].reshape(argb.height(),argb.width(),4)[:,:,3]
        ys,xs=np.nonzero(edge&(alpha>=250))
        if len(xs)<24 or int(xs.max()-xs.min())<8 or int(ys.max()-ys.min())<3:return None
        chosen=np.linspace(0,len(xs)-1,min(128,len(xs)),dtype=int)
        points=np.column_stack((xs[chosen],ys[chosen]));colours=rgb[ys[chosen],xs[chosen]]
        if float(colours.std(0).max())<12:return None
        return cls(QRect(rect),points,colours)

    def score(self,rgb,origin):
        import numpy as np
        x,y=origin[0]+self.rect.x(),origin[1]+self.rect.y()
        if x<0 or y<0 or x+self.rect.width()>rgb.shape[1] or y+self.rect.height()>rgb.shape[0]:return 0.
        actual=rgb[y+self.points[:,1],x+self.points[:,0]].astype('int16')
        return float((np.max(np.abs(actual-self.colours),axis=1)<=18).mean())


def locate_paint(rgb,anchors,hints=()):
    """Require two separated current paint anchors; never guess a window."""
    import numpy as np
    if len(anchors)<2:return None
    first=anchors[0]
    if not any(abs(a.rect.x()-first.rect.x())+abs(a.rect.y()-first.rect.y())>=24 for a in anchors[1:]):return None
    def score(origin):return min(a.score(rgb,origin) for a in anchors)
    for origin in hints:
        if origin is not None and score(origin)>=.94:return tuple(origin)
    height=rgb.shape[0]-first.rect.height()+1;width=rgb.shape[1]-first.rect.width()+1
    if width<=0 or height<=0 or rgb.shape[0]*rgb.shape[1]>16777216:return None
    matches=np.ones((height,width),dtype=bool)
    # Four widely spaced edge samples bound the full-image search. The complete
    # descriptors of both anchors still verify every surviving candidate.
    for index in np.linspace(0,len(first.points)-1,4,dtype=int):
        x,y=first.points[index]
        sample=rgb[y:y+height,x:x+width].astype('int16')
        matches&=np.max(np.abs(sample-first.colours[index]),axis=2)<=18
        if not matches.any():return None
    ys,xs=np.nonzero(matches)
    if len(xs)>96:return None
    found=[]
    for x,y in zip(xs,ys):
        origin=int(x)-first.rect.x(),int(y)-first.rect.y();value=score(origin)
        if value>=.94:found.append((value,origin))
    if not found:return None
    best=max(found)[1]
    if any(max(abs(p-q) for p,q in zip(origin,best))>2 for _,origin in found):return None
    return best


class OwnedCapture:
    """Two retained surfaces at most in normal use; failed searches are paced."""
    def __init__(self):self.states=weakref.WeakKeyDictionary()

    def rectangle(self,image,widget,anchors,screen):
        if image.isNull() or not widget.isVisible() or widget.isMinimized():return None
        if screen.width()<=0 or screen.height()<=0:return None
        sx,sy=image.width()/screen.width(),image.height()/screen.height()
        width,height=round(widget.width()*sx),round(widget.height()*sy)
        if width<=0 or height<=0 or width*height>16777216:return None
        # Render one client image before scaling/cropping. Rescaling children
        # independently changes fractional-scale glyph advances and backgrounds.
        snapshot=widget.grab().toImage()
        if snapshot.isNull():return None
        if snapshot.width()!=width or snapshot.height()!=height:
            snapshot=snapshot.scaled(width,height,Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.SmoothTransformation)
        descriptors=[]
        for child in anchors:
            if child is None or not child.isVisible():continue
            at=child.mapTo(widget,QPoint());w,h=round(child.width()*sx),round(child.height()*sy)
            if w<8 or h<4:continue
            rect=QRect(round(at.x()*sx),round(at.y()*sy),w,h)
            if not snapshot.rect().contains(rect):continue
            descriptor=PaintAnchor.from_image(snapshot.copy(rect),rect)
            if descriptor is not None:descriptors.append(descriptor)
        if len(descriptors)<2:return None
        if not any(abs(a.rect.x()-descriptors[0].rect.x())+abs(a.rect.y()-descriptors[0].rect.y())>=24 for a in descriptors[1:]):return None
        rgb=pixels(image);point=widget.mapToGlobal(QPoint())-screen.topLeft()
        reported=round(point.x()*sx),round(point.y()*sy)
        key=(image.width(),image.height(),widget.width(),widget.height(),sx,sy)
        state=self.states.get(widget)
        if state is None or state['key']!=key:
            state=dict(key=key,origin=None,next_search=0.);self.states[widget]=state
        hints=[state['origin'],reported]
        # Checking a known origin is cheap and always uses this frame's pixels.
        origin=next((p for p in hints if p is not None and min(a.score(rgb,p) for a in descriptors)>=.94),None)
        now=time.monotonic()
        if origin is None and now>=state['next_search']:
            state['next_search']=now+1.;origin=locate_paint(rgb,descriptors)
        state['origin']=origin
        if origin is None:return None
        rect=QRect(*origin,round(widget.width()*sx),round(widget.height()*sy)).intersected(image.rect())
        return rect if not rect.isEmpty() else None

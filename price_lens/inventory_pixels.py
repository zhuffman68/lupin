"""Native inventory decoration, separated from item and control identity."""
from dataclasses import dataclass
from math import ceil,floor

import numpy as np
from PySide6.QtCore import QRect
from PySide6.QtGui import QImage


def tab_bounds(width,height,tab):
    if type(tab) is not int or not 0<=tab<6 or not 130<=width<=435:return None
    scale=width/207
    # One physical antialias fringe follows the sprite at fractional scaling.
    rect=QRect(floor((6+33*tab)*scale)-1,floor(22*scale)-1,
               ceil((35+33*tab)*scale)-floor((6+33*tab)*scale)+2,
               ceil(41*scale)-floor(22*scale)+2)
    return rect if QRect(0,0,width,height).contains(rect) else None


def same_header(before,after,tab):
    """Only the selected native tab may pulse towards white; its shape stays.

    The pulse multiplies distance from white, including antialiased letters.
    Compare that colour direction with integer-rounding error only, bound the
    gain, allow three RGB units of quantization/resampling error, and retain enough
    visible pink selection. All other controls, text and
    inactive tabs stay exact, apart from the header's tiny rounded corners.
    """
    if before.shape!=after.shape or before.ndim!=3 or before.shape[2]!=3:return False
    height,width,_=before.shape;rect=tab_bounds(width,height,tab)
    if rect is None:return False
    scale=width/207;corner=max(2,min(6,ceil(2*scale)+1))
    strict=np.ones((height,width),dtype=bool)
    strict[:corner,:corner]=False;strict[:corner,-corner:]=False
    strict[rect.top():rect.bottom()+1,rect.left():rect.right()+1]=False
    if not np.array_equal(before[strict],after[strict]):return False
    old=before[rect.top():rect.bottom()+1,rect.left():rect.right()+1].astype(np.int32)
    new=after[rect.top():rect.bottom()+1,rect.left():rect.right()+1].astype(np.int32)
    minimum=max(24,floor(64*scale*scale+.5))
    def selected(rgb):
        r,g,b=rgb[:,:,0],rgb[:,:,1],rgb[:,:,2]
        return int(((r>=180)&(r-g>=8)&(b-g>=4)&(g>=45)&(b>=60)).sum())>=minimum
    if not selected(old) or not selected(new):return False
    a,b=255-old,255-new;ma,mb=a.max(2),b.max(2)
    lo,hi=np.minimum(ma,mb),np.maximum(ma,mb)
    if np.any(np.where(lo==0,hi>2,hi>4*lo)):return False
    error=np.abs(a*mb[:,:,None]-b*ma[:,:,None])
    return bool(np.all(error<=3*(ma+mb)[:,:,None]))


def rgb_pixels(image,rect):
    patch=image.copy(rect).convertToFormat(QImage.Format.Format_RGBA8888)
    data=np.frombuffer(patch.constBits(),np.uint8).reshape(rect.height(),patch.bytesPerLine())
    return data[:,:rect.width()*4].reshape(rect.height(),rect.width(),4)[:,:,:3].copy()


@dataclass(frozen=True)
class InventoryHeader:
    rect: tuple
    tab: int
    pixels: bytes

    @classmethod
    def capture(cls,image,source,tab):
        rect=QRect(source.x(),source.y(),source.width(),floor(45*source.width()/207+.5))
        if not image.rect().contains(rect):return None
        pixels=rgb_pixels(image,rect)
        if not same_header(pixels,pixels,tab):return None
        return cls(rect.getRect(),tab,pixels.tobytes())

    def matches(self,image):
        rect=QRect(*self.rect)
        if not image.rect().contains(rect):return False
        old=np.frombuffer(self.pixels,np.uint8).reshape(rect.height(),rect.width(),3)
        return same_header(old,rgb_pixels(image,rect),self.tab)


def same_cell(before,after,width,height,visible,scale):
    """Exact exposed icon interior; only a gold-to-gold outer rim may animate."""
    old=np.frombuffer(before,np.uint8).reshape(height,width,4)
    new=np.frombuffer(after,np.uint8).reshape(height,width,4)
    exposed=np.zeros((height,width),dtype=bool)
    for rect in visible:exposed[rect.top():rect.bottom()+1,rect.left():rect.right()+1]=True
    rim=max(1,ceil(scale));core=exposed.copy()
    core[:rim]=False;core[-rim:]=False;core[:,:rim]=False;core[:,-rim:]=False
    if int(core.sum())<max(16,floor(16*scale*scale+.5)):return False
    changed=np.any(old!=new,axis=2)&exposed
    if np.any(changed&core):return False
    def gold(rgb):
        rgb=rgb[:,:,:3].astype(np.int32);r,g,b=rgb[:,:,0],rgb[:,:,1],rgb[:,:,2]
        return (r>=225)&(g>=100)&(r>=g)&(b<=80)&(g-b>=70)
    return not np.any(changed&~(gold(old)&gold(new)&(old[:,:,3]==new[:,:,3])))

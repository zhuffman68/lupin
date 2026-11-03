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
    """Keep icon pixels exact while recognizing the native rim and its fringe.

    The top of a newly highlighted cell has a gold scanline one pixel inside
    its blended edge. Prove that scanline in both frames before allowing the
    adjoining highlight pixels; a wider ignored border would hide icon changes.
    """
    old=np.frombuffer(before,np.uint8).reshape(height,width,4)
    new=np.frombuffer(after,np.uint8).reshape(height,width,4)
    exposed=np.zeros((height,width),dtype=bool)
    for rect in visible:exposed[rect.top():rect.bottom()+1,rect.left():rect.right()+1]=True
    def gold(rgb):
        rgb=rgb[:,:,:3].astype(np.int32);r,g,b=rgb[:,:,0],rgb[:,:,1],rgb[:,:,2]
        return (r>=225)&(g>=100)&(r>=g)&(b<=80)&(g-b>=70)
    rim=max(1,ceil(scale));core=exposed.copy()
    core[:rim]=False;core[-rim:]=False;core[:,:rim]=False;core[:,-rim:]=False
    paired_gold=gold(old)&gold(new)
    allowed=paired_gold&~core
    # A native highlight can blend towards the pale cell edge or over the tip
    # of the icon. These colours alone are not evidence: each column/row must
    # also have its own exposed, aligned gold anchor in both captured frames.
    def fringe(rgb):
        rgb=rgb[:,:,:3].astype(np.int32);r,g,b=rgb[:,:,0],rgb[:,:,1],rgb[:,:,2]
        pale=(rgb.min(2)>=220)&(rgb.max(2)-rgb.min(2)<=35)&(r+4>=g)&(g+4>=b)
        return ((r>=24)&(g>=24)&(r+4>=g)&(g>=b+8))|pale
    tones=fringe(old)&fringe(new)
    minimum=max(8,ceil(8*scale))
    depth=min(ceil(2*scale),width//4,height//4)
    for axis in (0,1):
        for reverse in (False,True):
            for offset in range(depth):
                position=(height if axis==0 else width)-1-offset if reverse else offset
                line=paired_gold[position,:] if axis==0 else paired_gold[:,position]
                shown=exposed[position,:] if axis==0 else exposed[:,position]
                anchors=line&shown
                if int(anchors.sum())<minimum or int(anchors.sum())*5<int(shown.sum())*4:continue
                band=(slice(height-1-offset,height) if reverse else slice(0,offset+1)) if axis==0 else (
                      slice(width-1-offset,width) if reverse else slice(0,offset+1))
                if axis==0:
                    qualified=anchors[None,:]&tones[band,:]
                    allowed[band,:]|=qualified;core[band,:]&=~qualified
                else:
                    qualified=anchors[:,None]&tones[:,band]
                    allowed[:,band]|=qualified;core[:,band]&=~qualified
    if int(core.sum())<max(16,floor(16*scale*scale+.5)):return False
    changed=np.any(old!=new,axis=2)&exposed
    return not np.any(changed&~(allowed&(old[:,:,3]==new[:,:,3])))

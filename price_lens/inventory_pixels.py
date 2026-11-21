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


def _white_pulse(old,new,active,fringe):
    if np.array_equal(old,new):return True
    a,b=255-old.astype(np.int32),255-new.astype(np.int32)
    ma,mb=a.max(2),b.max(2)
    lo,hi=np.minimum(ma,mb),np.maximum(ma,mb)
    if np.any(np.where(lo==0,hi>2,hi>(6 if active else 4)*lo)):return False
    changed=np.any(np.abs(a*mb[:,:,None]-b*ma[:,:,None])>3*(ma+mb)[:,:,None],axis=2)
    if changed.any():
        edge=fringe+1
        bright=(old.min(2)>=218)|(new.min(2)>=218)
        inner=changed[edge:-edge,edge:-edge]
        if inner.any() or np.any(changed&~bright):return False
        ar,br=a[changed],b[changed]
        fitted=np.zeros(len(ar),dtype=bool)
        # At the sprite edge the raster mixes white with the stationary
        # header paper (245, 246, 247). Fit only those native endpoints.
        for offset in ((2,2,2),(4,4,3),(6,5,5),(8,7,6),(10,9,8)):
            aa,bb=ar-offset,br-offset
            am,bm=np.abs(aa).max(1),np.abs(bb).max(1)
            fitted|=np.all(np.abs(aa*bm[:,None]-bb*am[:,None])<=3*(am+bm)[:,None],axis=1)
        if not fitted.all():return False
    if active:return True
    # Gray tab ink needs a shared gain; individual gray pixels do not carry
    # colour-direction evidence of letter shape. Check each interior scanline.
    a,b=a[:,fringe:-fringe],b[:,fringe:-fringe]
    sa,sb=a.sum(axis=(1,2))[:,None,None],b.sum(axis=(1,2))[:,None,None]
    return bool(np.all(np.abs(a*sb-b*sa)<=3*(sa+sb)))


def same_header(before,after,tab):
    """Permit native white flashes while preserving the selected tab and UI ink."""
    if before.shape!=after.shape or before.ndim!=3 or before.shape[2]!=3:return False
    height,width,_=before.shape
    if tab_bounds(width,height,tab) is None:return False
    scale=width/207;corner=max(2,min(6,ceil(2*scale)+1))
    strict=np.ones((height,width),dtype=bool)
    strict[:corner,:corner]=False;strict[:corner,-corner:]=False
    minimum=max(24,floor(64*scale*scale+.5))
    def selected(rgb):
        r,g,b=rgb.astype(np.int16).transpose(2,0,1)
        return int(((r>=180)&(r-g>=8)&(b-g>=4)&(b-g<55)&(g>=45)&(b>=60)).sum())>=minimum
    for index in range(6):
        rect=tab_bounds(width,height,index)
        if rect is None:return False
        region=np.s_[rect.top():rect.bottom()+1,rect.left():rect.right()+1]
        strict[region]=False
        old,new=before[region],after[region];active=index==tab
        if selected(old)!=active or selected(new)!=active:return False
        if not _white_pulse(old,new,active,ceil(scale)+1):return False
    return np.array_equal(before[strict],after[strict])


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
        current=rgb_pixels(image,rect)
        return np.array_equal(old,current) or same_header(old,current,self.tab)


def same_cell(before,after,width,height,visible,scale):
    """Keep icon pixels exact while recognizing the native rim and its fringe.

    The top of a newly highlighted cell has a gold scanline one pixel inside
    its blended edge. Require that scanline to align with gold or the native
    bare bevel in the other image before accepting adjoining colour changes.
    """
    old=np.frombuffer(before,np.uint8).reshape(height,width,4)
    new=np.frombuffer(after,np.uint8).reshape(height,width,4)
    exposed=np.zeros((height,width),dtype=bool)
    for rect in visible:exposed[rect.top():rect.bottom()+1,rect.left():rect.right()+1]=True
    core_minimum=max(16,floor(16*scale*scale+.5))
    depth=min(ceil(2*scale),width//4,height//4)
    if depth and before==after and int(exposed[depth:-depth,depth:-depth].sum())>=core_minimum:return True
    def gold(rgb):
        rgb=rgb[:,:,:3].astype(np.int32);r,g,b=rgb[:,:,0],rgb[:,:,1],rgb[:,:,2]
        return (r>=225)&(g>=100)&(r>=g)&(b<=80)&(g-b>=70)
    rim=max(1,ceil(scale));core=exposed.copy()
    core[:rim]=False;core[-rim:]=False;core[:,:rim]=False;core[:,-rim:]=False
    old_gold,new_gold=gold(old),gold(new)
    paired_gold=old_gold&new_gold
    allowed=paired_gold&~core
    # A native highlight can blend towards the pale cell edge or over the tip
    # of the icon. These colours alone are not evidence: each column/row must
    # also have its own exposed, aligned gold anchor in both captured frames.
    def fringe(rgb):
        rgb=rgb[:,:,:3].astype(np.int32);r,g,b=rgb[:,:,0],rgb[:,:,1],rgb[:,:,2]
        pale=(rgb.min(2)>=220)&(rgb.max(2)-rgb.min(2)<=35)&(r+4>=g)&(g+4>=b)
        return ((r>=24)&(g>=24)&(r+4>=g)&(g>=b+8))|pale
    old_fringe,new_fringe=fringe(old),fringe(new)
    def bare_cell(rgb):
        rgb=rgb[:,:,:3].astype(np.int16)
        # A scaled plain bevel can blend the adjacent native colours. Fit
        # the same blend in every channel, with a small raster tolerance.
        palette=np.array(((206,201,190),(225,223,213),(245,246,247)),dtype=np.int16)
        plain=np.zeros(rgb.shape[:2],dtype=bool)
        for left,right in ((0,1),(1,2),(0,2)):
            base=palette[left];direction=palette[right]-base;span=int(direction[0])
            delta=rgb-base;mix=np.clip(delta[:,:,0],0,span)
            plain|=np.all(np.abs(delta*span-mix[:,:,None]*direction)<=4*span,axis=2)
        return plain
    old_bare,new_bare=bare_cell(old),bare_cell(new)
    decorations=((paired_gold,old_fringe&new_fringe,None),
                 (old_bare&new_gold,old_bare&(new_gold|new_fringe),old_bare&new_fringe&~new_gold),
                 (new_bare&old_gold,new_bare&(old_gold|old_fringe),new_bare&old_fringe&~old_gold))
    minimum=max(8,ceil(8*scale))
    for axis in (0,1):
        for reverse in (False,True):
            for offset in range(depth):
                position=(height if axis==0 else width)-1-offset if reverse else offset
                shown=exposed[position,:] if axis==0 else exposed[:,position]
                band=(slice(height-1-offset,height) if reverse else slice(0,offset+1)) if axis==0 else (
                      slice(width-1-offset,width) if reverse else slice(0,offset+1))
                for evidence,tones,soft in decorations:
                    anchors=(evidence[position,:] if axis==0 else evidence[:,position])&shown
                    count=int(anchors.sum())
                    if count<minimum or count*5<int(shown.sum())*4:continue
                    scaled_phase=soft is not None and scale>1
                    if scaled_phase:
                        end_pixels=soft[position,:] if axis==0 else soft[:,position]
                        # The end of a scaled line can blend into the adjacent
                        # background. Only the two outer cell pixels may use
                        # the neighbouring gold anchor for that weaker tint.
                        anchors[0]|=anchors[1]&shown[0]&end_pixels[0]
                        anchors[-1]|=anchors[-2]&shown[-1]&end_pixels[-1]
                    if axis==0:
                        qualified=anchors[None,:]&tones[band,:]
                        allowed[band,:]|=qualified;core[band,:]&=~qualified
                    else:
                        qualified=anchors[:,None]&tones[:,band]
                        allowed[:,band]|=qualified;core[:,band]&=~qualified
                    if scaled_phase:
                        # Raster scaling blends the last gold scanline onto
                        # one adjacent physical pixel. The fringe needs its
                        # own plain counterpart and this same line's anchors.
                        inside=position+(-1 if reverse else 1)
                        edge=(inside,slice(None)) if axis==0 else (slice(None),inside)
                        qualified=anchors&soft[edge]
                        allowed[edge]|=qualified;core[edge]&=~qualified
    if int(core.sum())<core_minimum:return False
    changed=np.any(old!=new,axis=2)&exposed
    return not np.any(changed&~(allowed&(old[:,:,3]==new[:,:,3])))

"""Bounded native row-pixel proofs, independent of capture and item identity."""
from dataclasses import dataclass
import math

import numpy as np
from PySide6.QtCore import QRect
from PySide6.QtGui import QImage


MAX_PIXELS=65_536
MAX_EXCLUSIONS=64
MIN_VISIBLE_PIXELS=32
MIN_VISIBLE_FRACTION=.10


@dataclass(frozen=True)
class RowProof:
    rect: tuple[int,int,int,int]
    rgba: bytes
    pointer: tuple[int,int] | None
    scale: float
    exclude: tuple[tuple[int,int,int,int],...]


def _rect(value):
    if isinstance(value,QRect):return QRect(value)
    if isinstance(value,dict):value=tuple(value.get(key) for key in ('x','y','width','height'))
    if not isinstance(value,(tuple,list)) or len(value)!=4 or any(type(part) is not int for part in value):return None
    if any(not -(2**31)<=part<2**31 for part in value):return None
    if value[0]+value[2]>=2**31 or value[1]+value[3]>=2**31:return None
    try:return QRect(*value)
    except (ValueError,TypeError,OverflowError):return None


def _point(value):
    if value is None:return None
    if not isinstance(value,(tuple,list)) or len(value)!=2 or any(type(part) is not int for part in value):raise ValueError('Invalid pointer')
    return tuple(value)


def _scale(value):
    if isinstance(value,bool):raise ValueError('Invalid scale')
    value=float(value)
    if not math.isfinite(value) or not .25<=value<=4:raise ValueError('Invalid scale')
    return value


def _exclusions(values,rect):
    result=[]
    for index,value in enumerate(values):
        if index>=MAX_EXCLUSIONS:raise ValueError('Too many exclusions')
        area=_rect(value)
        if area is None or area.isEmpty():raise ValueError('Invalid exclusion')
        part=area.intersected(rect)
        if not part.isEmpty():result.append(part.getRect())
    return tuple(result)


def _cursor(pointer,scale):
    if pointer is None:return None
    return QRect(pointer[0]-round(8*scale),pointer[1]-round(8*scale),
                 max(1,round(32*scale)),max(1,round(36*scale)))


def _masks(rect,old_pointer,pointer,scale,old_exclude,exclude):
    hidden=[QRect(*area) for area in (*old_exclude,*exclude)]
    hidden.extend(area for point in (old_pointer,pointer) if (area:=_cursor(point,scale)) is not None)
    return [part for area in hidden if not (part:=area.intersected(rect)).isEmpty()]


def _visible(rect,hidden):
    if not hidden:return None
    visible=np.ones((rect.height(),rect.width()),dtype=bool)
    for part in hidden:
        visible[part.top()-rect.top():part.bottom()-rect.top()+1,
                part.left()-rect.left():part.right()-rect.left()+1]=False
    return visible


def _enough(rect,visible):
    count=rect.width()*rect.height() if visible is None else int(visible.sum())
    return count>=max(MIN_VISIBLE_PIXELS,math.ceil(rect.width()*rect.height()*MIN_VISIBLE_FRACTION))


def _pixels(image,rect):
    patch=image.copy(rect).convertToFormat(QImage.Format.Format_RGBA8888)
    pixels=patch.constBits()
    if patch.bytesPerLine()==patch.width()*4:return bytes(pixels)
    rows=np.frombuffer(pixels,dtype=np.uint8).reshape(patch.height(),patch.bytesPerLine())
    return rows[:,:patch.width()*4].tobytes()


def _band_tint(rgb,visible):
    """Require a broad native blue or selected-orange background, not scenery."""
    count=int(visible.sum())
    if not count:return None
    matches=[]
    for family,base in (('blue',np.array((202,213,223),dtype=np.float32)),
                        ('orange',np.array((251,167,46),dtype=np.float32))):
        gain=(rgb*base).sum(axis=2)/float(base@base)
        palette=visible&(gain>=.45)&(gain<=1.15)&(np.max(np.abs(rgb-gain[:,:,None]*base),axis=2)<=7)
        if int(palette.sum())<count*.45:continue
        tint=np.median(rgb[palette],axis=0)
        if int((palette&(np.max(np.abs(rgb-tint),axis=2)<=1)).sum())<count*.40:continue
        matches.append((family,tint))
    return matches[0] if len(matches)==1 else None


def _selection_equivalent(before,after,visible,scale):
    """Ignore only proved native band recolouring with unchanged glyph coverage.

    The 37-pixel icon column stays exact.  Each changed text-band pixel must
    preserve black-ink coverage under measured blue/orange tints; arbitrary
    palette, icon, name and price changes therefore remain contradictions.
    """
    height,width=before.shape[:2]
    band_width=round(162*scale);gutter=round(2*scale)
    if (abs(width-(round(37*scale)+band_width))>2
            or abs(height-(round(35*scale)+2*gutter))>2):return None
    left=width-band_width;top=gutter;bottom=height-gutter
    native_visible=np.ones((height,width),dtype=bool) if visible is None else visible
    part=native_visible[top:bottom,left:]
    old=before[top:bottom,left:,:3].astype(np.float32)
    new=after[top:bottom,left:,:3].astype(np.float32)
    source=_band_tint(old,part);target=_band_tint(new,part)
    if source is None or target is None or source[0]==target[0]:return None
    blue,orange=(old,new) if source[0]=='blue' else (new,old)
    normal,selected=(source[1],target[1]) if source[0]=='blue' else (target[1],source[1])
    gain=(blue*normal).sum(axis=2)/float(normal@normal)
    same=(gain>=0)&(gain<=1.08)
    # The native blue band has a few bright bevel columns.  Their documented
    # palette spread applies only to almost-uncovered background, never ink.
    error=np.where(gain>=.9,14,1.5)
    same&=np.max(np.abs(blue-gain[:,:,None]*normal),axis=2)<=error
    predicted=np.rint(gain[:,:,None]*selected).clip(0,255)
    same&=np.max(np.abs(orange-predicted),axis=2)<=1
    # Classic recolours its thin rule between name and price separately.  Only
    # this known pair, within the middle native rule strip, is equivalent.
    blue_rule=np.array((222,223,223));orange_rule=np.array((247,192,110))
    rule=((np.all(old==blue_rule,axis=2)&np.all(new==orange_rule,axis=2))
          |(np.all(old==orange_rule,axis=2)&np.all(new==blue_rule,axis=2)))
    rule&=np.abs(np.arange(bottom-top)[:,None]-(bottom-top)/2)<=max(1,round(scale))
    same|=rule
    same&=before[top:bottom,left:,3]==after[top:bottom,left:,3]
    result=np.zeros((height,width),dtype=bool);result[top:bottom,left:]=same
    return result


def capture_proof(image,rect,*,pointer=None,exclude=(),scale=1.0):
    """Capture at most 65,536 native pixels; retain no source-frame reference."""
    area=_rect(rect)
    if (area is None or area.isEmpty() or area.width()*area.height()>MAX_PIXELS
            or not isinstance(image,QImage) or image.isNull() or not image.rect().contains(area)):return None
    try:
        point=_point(pointer);scale=_scale(scale);excluded=_exclusions(exclude,area)
    except (TypeError,ValueError,OverflowError):return None
    visible=_visible(area,_masks(area,point,None,scale,excluded,()))
    if not _enough(area,visible):return None
    return RowProof(area.getRect(),_pixels(image,area),point,scale,excluded)


def proof_state(proof,latest,*,pointer=None,exclude=()):
    """Return same, occluded, changed or unknown from currently exposed pixels.

    Old/current annotation and native-tooltip rectangles, and both cursor
    footprints, cannot supply evidence of native changes.  They also cannot
    establish sameness when fewer than 32 pixels or ten percent remain visible.
    """
    if not isinstance(proof,RowProof):return 'unknown'
    area=_rect(proof.rect)
    if (area is None or area.isEmpty() or area.width()*area.height()>MAX_PIXELS
            or not isinstance(latest,QImage) or latest.isNull() or not latest.rect().contains(area)
            or not isinstance(proof.rgba,bytes) or len(proof.rgba)!=area.width()*area.height()*4):return 'unknown'
    try:
        old_pointer=_point(proof.pointer);point=_point(pointer);scale=_scale(proof.scale)
        old_excluded=_exclusions(proof.exclude,area);excluded=_exclusions(exclude,area)
    except (TypeError,ValueError,OverflowError):return 'unknown'
    hidden=_masks(area,old_pointer,point,scale,old_excluded,excluded)
    visible=_visible(area,hidden)
    if not _enough(area,visible):return 'unknown'
    current=_pixels(latest,area)
    if current==proof.rgba:return 'same'
    before=np.frombuffer(proof.rgba,dtype=np.uint8).reshape(area.height(),area.width(),4)
    after=np.frombuffer(current,dtype=np.uint8).reshape(area.height(),area.width(),4)
    different=np.any(before!=after,axis=2)
    exposed=different if visible is None else different&visible
    if not np.any(exposed):return 'occluded'
    equivalent=_selection_equivalent(before,after,visible,scale)
    if equivalent is None or np.any(exposed&~equivalent):return 'changed'
    # A proved selection transform is unchanged native evidence even beneath a
    # cursor exclusion.  Other masked deltas still cannot establish identity.
    return 'occluded' if visible is not None and np.any(different&~visible&~equivalent) else 'same'

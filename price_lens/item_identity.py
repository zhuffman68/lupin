"""Observation-local item identity from names and cached exact-ID icon pixels.

No requests, disk writes or persistent name bindings occur here. Callers own the
submitted frame and must retain any result only with its verified page/row proof.
"""
from dataclasses import dataclass
import math

import numpy as np
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QImage

from .domain import Item

MAX_CANDIDATES = 8
MAX_ICON_WORK = 8_000_000


@dataclass(frozen=True)
class IdentityResult:
    item: Item | None
    candidates: tuple[Item, ...]
    reason: str
    evidence: str = ''


def observed_item(catalog, row):
    """Resolve a name or root-proved row['_item_id'], never raw item_id fields.

    The caller must scope _item_id to the current submitted frame and page/slot.
    A stale field outside the current name candidates is rejected.
    """
    if not catalog or not isinstance(row, dict):return None
    candidates = catalog.candidates(row.get('name'), row.get('tier'))
    if '_item_id' in row:
        identity = row['_item_id']
        if type(identity) is not int:return None
        item=catalog.by_id.get(identity)
        return item if item in candidates else None
    return candidates[0] if len(candidates) == 1 else None


def shop_icon_rect(row):
    """Bound the native icon immediately left of its 162-pixel name band."""
    try:
        area = row['area']
        if any(type(area[k]) is not int for k in ('x','y','width','height')):return None
        scale = area['width'] / 162.0
        if not .5 <= scale <= 3 or abs(area['height'] - 35*scale) > max(2,2*scale):return None
        return QRect(area['x']-round(37*scale),area['y']-round(2*scale),
                     round(37*scale),area['height']+round(4*scale))
    except (KeyError, TypeError, ValueError):return None


def resolve_shop_item(catalog, row, image=None, thumbnails=None):
    """Return IdentityResult for this submitted row/frame, using cached icons.

    thumbnails is a cached-only callable(game_id) -> QImage, or an object with
    image(game_id). It is never observed/pumped and must not initiate downloads.
    Unique names need no icon. Distinct same-name IDs require exclusive current
    icon evidence; absent, identical, covered or uncertain templates abstain.
    """
    candidates = tuple(catalog.candidates(row.get('name'),row.get('tier'))) if catalog else ()
    if row.get('covered') or row.get('listing_old') or row.get('presentation_held'):
        return IdentityResult(None,candidates,'ambiguous' if candidates else 'unidentified')
    if len(candidates) == 1:return IdentityResult(candidates[0],candidates,'identified','name')
    if not candidates:return IdentityResult(None,(),'unidentified')
    rectangle = shop_icon_rect(row)
    if rectangle is None:return IdentityResult(None,candidates,'ambiguous')
    return resolve_icon(candidates,image,rectangle,thumbnails,scale=row['area']['width']/162.0)


def _rgba(image):
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    return np.frombuffer(bytes(image.constBits()),dtype=np.uint8).reshape(
        image.height(),image.bytesPerLine())[:,:image.width()*4].reshape(image.height(),image.width(),4)


def resolve_icon(candidates, image, icon_rect, thumbnails, *, scale=1.0):
    """Match all candidate cached QImages inside a bounded frame rectangle.

    This conservative comparison uses opaque pixels, allows tiny rendering
    differences and demands a clear margin over every competing exact ID.
    No best-name/nearest-sprite fallback or result cache is used.
    """
    candidates = tuple(candidates)
    unresolved = IdentityResult(None,candidates,'ambiguous' if candidates else 'unidentified')
    if (not 1 <= len(candidates) <= MAX_CANDIDATES
            or len({item.game_id for item in candidates}) != len(candidates)
            or not isinstance(image,QImage) or image.isNull()
            or not isinstance(icon_rect,QRect) or not image.rect().contains(icon_rect)
            or not 8 <= icon_rect.width() <= 144 or not 8 <= icon_rect.height() <= 144
            or not isinstance(scale,(int,float)) or isinstance(scale,bool)
            or not math.isfinite(scale) or not .5 <= scale <= 3):return unresolved
    getter = thumbnails if callable(thumbnails) else getattr(thumbnails,'image',None)
    if not callable(getter):return unresolved
    templates = []
    work = 0
    for item in candidates:
        try:icon = getter(item.game_id)
        except (KeyError,TypeError,ValueError,OSError):return unresolved
        if (not isinstance(icon,QImage) or icon.isNull()
                or not 1 <= icon.width() <= 96 or not 1 <= icon.height() <= 96):return unresolved
        if scale != 1:
            icon = icon.scaled(max(1,round(icon.width()*scale)),max(1,round(icon.height()*scale)),
                               Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.FastTransformation)
        if icon.width()>icon_rect.width() or icon.height()>icon_rect.height():return unresolved
        pixels = _rgba(icon)
        ys,xs = np.nonzero(pixels[:,:,3] >= 250)
        if len(xs)<48:return unresolved
        colours = pixels[ys,xs,:3].astype(np.int16)
        if len(np.unique(colours,axis=0))<6 or np.ptp(colours,axis=0).max()<32:return unresolved
        width,height = icon_rect.width()-icon.width()+1,icon_rect.height()-icon.height()+1
        if width*height>1024:return unresolved
        work += width*height*len(xs)
        if work>MAX_ICON_WORK:return unresolved
        templates.append((item,ys,xs,colours,width,height))
    frame = _rgba(image.copy(icon_rect))[:,:,:3].astype(np.int16)
    scores = []
    for item,ys,xs,colours,width,height in templates:
        offsets_y,offsets_x = np.mgrid[:height,:width]
        offsets_y,offsets_x = offsets_y.ravel(),offsets_x.ravel()
        best = (float('inf'),0.)
        # Bound temporary arrays independently of image size/candidate count.
        for start in range(0,len(offsets_x),16):
            ox,oy = offsets_x[start:start+16],offsets_y[start:start+16]
            delta = np.abs(frame[oy[:,None]+ys,ox[:,None]+xs]-colours)
            means = delta.mean(axis=(1,2))
            close = (delta.max(axis=2)<=8).mean(axis=1)
            for mean,fraction in zip(means,close):
                if (mean,-fraction)<(best[0],-best[1]):best = (float(mean),float(fraction))
        scores.append((item,*best))
    strong = [score for score in scores if score[1]<=1.5 and score[2]>=.995]
    if len(strong)!=1:return unresolved
    winner = strong[0]
    if any(mean<8 or fraction>.9 for item,mean,fraction in scores if item.game_id!=winner[0].game_id):return unresolved
    return IdentityResult(winner[0],candidates,'identified','icon')

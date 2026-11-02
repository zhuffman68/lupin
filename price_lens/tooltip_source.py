"""Bounded title-pixel proofs for native item descriptions, never shop offers.

Only an independently present native panel permits its dark translucent
background to vary. Opaque name strokes retain their positions and colours;
independently bound inventory titles may blend only their antialiased fringe.
Cursor/annotation exclusions never excuse a changed or hidden letter.
"""
from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import QRect
from PySide6.QtGui import QImage

from .shop_source import cursor_rectangle
from .tooltip_geometry import still_present

MAX_TITLE_PIXELS = 65_536
MAX_PANEL_PIXELS = 1_048_576
MAX_EXCLUSIONS = 64


def _rectangle(value):
    if isinstance(value, QRect):
        rect = QRect(value)
    elif isinstance(value, dict):
        parts = tuple(value.get(k) for k in ('x', 'y', 'width', 'height'))
        if any(type(v) is not int for v in parts):return None
        try:rect = QRect(*parts)
        except (TypeError, ValueError, OverflowError):return None
    else:
        return None
    return rect if not rect.isEmpty() else None


def _point(value):
    if value is None:return None
    if not isinstance(value, (tuple, list)) or len(value) != 2 or any(type(v) is not int for v in value):
        raise ValueError('Invalid title pointer')
    if any(abs(v) > 32768 for v in value):raise ValueError('Invalid title pointer')
    return tuple(value)


def _exclusions(values):
    result = []
    for index, value in enumerate(values):
        if index >= MAX_EXCLUSIONS:raise ValueError('Too many title exclusions')
        rect = _rectangle(value)
        if rect is None:raise ValueError('Invalid title exclusion')
        result.append(rect)
    return tuple(result)


def _pixels(image, rect):
    patch = image.copy(rect).convertToFormat(QImage.Format.Format_RGBA8888)
    rows = np.frombuffer(patch.constBits(), dtype=np.uint8).reshape(patch.height(), patch.bytesPerLine())
    return rows[:, :patch.width()*4].copy().tobytes()


def _ink(rgba):
    """Use the native reader's white/coloured title-ink classification."""
    rgb = rgba[:, :, :3].astype(np.int32)
    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    high, low = rgb.max(axis=2), rgb.min(axis=2)
    neutral = (np.abs(r-g) <= 55) & (np.maximum(b-r, 0) < 100)
    light = r*30//100 + g*59//100 + b*11//100
    return (neutral & (light >= 150)) | (~neutral & (high >= 150) & (high-low > 45))


def _same_bound_raster(before,after,old_ink,new_ink):
    """Opaque glyphs stay exact; their blended fringe may reveal scenery.

    Only the inventory association uses this after checking its independent
    source cell/header/frame. Generic and shop titles retain their exact ink
    comparison. Neither an added stroke nor a mask can lend title authority.
    """
    old_rgb,new_rgb=before[:,:,:3],after[:,:,:3]
    old_core=old_ink&(old_rgb.max(axis=2)>=230)
    new_core=new_ink&(new_rgb.max(axis=2)>=230)
    if (int(old_core.sum())<8 or not np.array_equal(old_core,new_core)
            or not np.array_equal(before[old_core],after[old_core])):return False
    # Native antialiasing reaches two physical pixels at the usual 12px title
    # height. Bound its support by the measured title scale, not arbitrary
    # rectangles or a whole-name colour tolerance.
    radius=min(6,max(1,(before.shape[0]+5)//6))
    padded=np.pad(old_core,radius);fringe=np.zeros(old_core.shape,dtype=bool)
    for dy in range(radius*2+1):
        for dx in range(radius*2+1):
            fringe|=padded[dy:dy+old_core.shape[0],dx:dx+old_core.shape[1]]
    changed=(old_ink|new_ink)&np.any(before!=after,axis=2)
    if np.any(changed&~fringe):return False
    # A stroke erased into the native dark body is not antialias blending.
    # Strong/opaque additions, removals, moves and recolours already fail the
    # exact core comparison above, including within cursor/annotation masks.
    return not np.any(changed&(np.minimum(old_rgb.max(axis=2),new_rgb.max(axis=2))<130))


def _enough_visible_ink(rect, ink, exclusions, pointer):
    visible = np.ones(ink.shape, dtype=bool)
    cursor = cursor_rectangle(pointer)
    for hidden in (*exclusions, *((cursor,) if cursor is not None else ())):
        part = rect.intersected(hidden)
        if not part.isEmpty():
            visible[part.top()-rect.top():part.bottom()-rect.top()+1,
                    part.left()-rect.left():part.right()-rect.left()+1] = False
    total = int(ink.sum())
    return int((visible & ink).sum()) >= max(8, total*.5)


@dataclass(frozen=True)
class TitleProof:
    rect: tuple
    rgba: bytes
    panel: tuple | None
    exclude: tuple
    pointer: tuple | None
    semantic: bool

    def matches(self, latest, *, panel=None, exclude=(), pointer=None, antialias=False):
        if not isinstance(latest, QImage) or latest.isNull():return False
        rect = QRect(*self.rect)
        if not latest.rect().contains(rect):return False
        try:
            exclusions = _exclusions(exclude)
            point = _point(pointer)
        except (TypeError, ValueError, OverflowError):return False
        if self.panel is not None:
            expected = QRect(*self.panel)
            supplied = expected if panel is None else _rectangle(panel)
            if supplied != expected or not latest.rect().contains(expected):return False
            if not still_present(latest, expected, exclusions):return False
        elif panel is not None:
            # A later panel cannot retroactively authorize background tolerance.
            return False
        current = _pixels(latest, rect)
        if not self.semantic:return current == self.rgba
        before = np.frombuffer(self.rgba, dtype=np.uint8).reshape(rect.height(), rect.width(), 4)
        after = np.frombuffer(current, dtype=np.uint8).reshape(before.shape)
        old_ink, new_ink = _ink(before), _ink(after)
        same=(np.array_equal(old_ink,new_ink) and np.array_equal(before[old_ink],after[old_ink]))
        if not same and not (antialias and _same_bound_raster(before,after,old_ink,new_ink)):return False
        # Compare all strokes, including masked ones. Masks can reduce usable
        # evidence but can never conceal a suffix change or foreign bright ink.
        return (_enough_visible_ink(rect, old_ink, tuple(QRect(*r) for r in self.exclude), self.pointer)
                and _enough_visible_ink(rect, new_ink, exclusions, point))


def capture_title(image, rect, *, panel=None, exclude=(), pointer=None):
    """Capture an immutable title proof; absent panel proof stays byte-exact."""
    if not isinstance(image, QImage) or image.isNull():return None
    rect = _rectangle(rect)
    if (rect is None or rect.width()*rect.height() > MAX_TITLE_PIXELS
            or not image.rect().contains(rect)):return None
    try:
        exclusions = _exclusions(exclude)
        point = _point(pointer)
    except (TypeError, ValueError, OverflowError):return None
    native = None
    if panel is not None:
        native = _rectangle(panel)
        if (native is None or native.width()*native.height() > MAX_PANEL_PIXELS
                or not image.rect().contains(native) or not native.contains(rect)
                or not still_present(image, native, exclusions)):return None
    rgba = _pixels(image, rect)
    pixels = np.frombuffer(rgba, dtype=np.uint8).reshape(rect.height(), rect.width(), 4)
    ink = _ink(pixels)
    semantic = bool(native is not None and int(ink.sum()) >= 8)
    if semantic and not _enough_visible_ink(rect, ink, exclusions, point):return None
    return TitleProof(rect.getRect(), rgba, native.getRect() if native is not None else None,
                      tuple(r.getRect() for r in exclusions), point, semantic)

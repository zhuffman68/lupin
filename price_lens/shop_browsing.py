"""Short shop-list priority from visible native pixels, without input events.

This state never supplies an item identity or an asking price.  Its epoch only
invalidates observations of an older viewport; covered rows must be read again.
"""
from dataclasses import dataclass
import math
import time
import numpy as np

from PySide6.QtCore import QObject, QRect, QTimer, Qt, Signal
from PySide6.QtGui import QImage, QRegion

from .domain import glyph_key, item_words, unclipped_name


def _rectangle(area):
    if isinstance(area, QRect):
        return QRect(area)
    try:
        return QRect(*(int(area[k]) for k in ('x', 'y', 'width', 'height')))
    except (KeyError, TypeError, ValueError):
        return None


def _hidden(tooltip, exclude):
    return tuple(QRect(rect) for rect in (*exclude, *((tooltip,) if tooltip is not None else ())))


@dataclass
class _RowProof:
    identity: object
    rectangle: QRect
    pixels: QImage
    exclude: tuple


class ShopBrowsing(QObject):
    """One bounded deadline per proven native viewport transition.

    ``observe_frame`` accepts an exposed scrollbar-thumb movement immediately.
    ``observe_rows`` is the fallback for fresh, exact row identities whose native
    name ink also changed.  Both return True only when they advance ``epoch``.
    ``pending`` means an advanced viewport has not supplied fresh usable rows.
    The changed signal wakes presentation at expiry; it does not extend it.
    """
    changed = Signal()
    SECONDS = 1.5
    ROW_LIMIT = 24

    def __init__(self, identity=None, parent=None):
        super().__init__(parent)
        self.resolve_identity = identity
        self.epoch = 0
        self.pending = False
        self.priority_until = 0.0
        self.area = None
        self.thumb = None
        self.frame = QImage()
        self.exclusions = ()
        self.rows = {}
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self._expire)

    def reset(self):
        self.epoch += 1
        self.pending = False
        self.priority_until = 0.0
        self.area = None
        self.thumb = None
        self.frame = QImage()
        self.exclusions = ()
        self.rows = {}
        self.timer.stop()

    def active(self, now=None):
        now = time.monotonic() if now is None else now
        return bool(self.priority_until and now < self.priority_until)

    def _expire(self):
        remaining = self.priority_until - time.monotonic()
        if remaining > 0:
            self.timer.start(max(1, math.ceil(remaining * 1000)))
            return
        if self.priority_until:
            self.timer.stop()
            self.priority_until = 0.0
            self.changed.emit()

    def _advance(self, now):
        self.epoch += 1
        self.pending = True
        self.rows = {}
        self.priority_until = now + self.SECONDS
        self.timer.start(math.ceil(self.SECONDS * 1000))

    @staticmethod
    def _rim_patch(image, area):
        rect=QRect(area.x(),area.y()-6,area.width(),4)
        return image.copy(rect) if image.rect().contains(rect) else QImage()

    @staticmethod
    def _same_rim(before, previous, after, area, old_exclude, exclude):
        """A moved shop compares in list-local coordinates, not screen space."""
        if before.isNull() or previous is None:
            return False
        old = QRect(previous.x(), previous.y() - 6, previous.width(), 4)
        current = QRect(area.x(), area.y() - 6, area.width(), 4)
        if old.size() != current.size() or before.size()!=old.size() or not after.rect().contains(current):
            return False
        visible = QRegion(QRect(0, 0, old.width(), old.height()))
        for rect in old_exclude:
            visible = visible.subtracted(QRegion(rect.translated(-old.topLeft())))
        for rect in exclude:
            visible = visible.subtracted(QRegion(rect.translated(-current.topLeft())))
        if sum(part.width() * part.height() for part in visible) < old.width():
            return False
        return all(before.copy(part) == after.copy(part.translated(current.topLeft()))
                   for part in visible)

    @staticmethod
    def scrollbar_thumb(image, area, *, tooltip=None, exclude=()):
        """Locate Classic's blue thumb inside its exposed neutral native rail.

        Missing/covered pixels are unknown, never a thumb at a different place.
        The arrow buttons are excluded, and both blue body and neutral rail are
        required so a dark description or our own labels cannot act as a thumb.
        """
        area = _rectangle(area)
        if area is None or image is None or image.isNull() or area.width() < 80:
            return None
        scale = area.width() / 199.0
        rail = QRect(area.right() + max(2, round(3 * scale)), area.top() + round(14 * scale),
                     max(6, round(14 * scale)), area.height() - round(28 * scale))
        if rail.height() < 24 or not image.rect().contains(rail):
            return None
        # Convert only this narrow native rail.  Per-pixel QColor/contains calls
        # otherwise multiply work by every annotation exclusion at capture FPS.
        patch=image.copy(rail).convertToFormat(QImage.Format.Format_RGBA8888)
        rgba=np.frombuffer(patch.constBits(),dtype=np.uint8).reshape(patch.height(),patch.bytesPerLine())
        rgb=rgba[:,:patch.width()*4].reshape(patch.height(),patch.width(),4)[:,:,:3].astype(np.int16)
        visible=np.ones((patch.height(),patch.width()),dtype=bool)
        for hidden in _hidden(tooltip,exclude):
            part=rail.intersected(hidden)
            if not part.isEmpty():
                visible[part.top()-rail.top():part.bottom()-rail.top()+1,
                        part.left()-rail.left():part.right()-rail.left()+1]=False
        r,g,b=rgb[:,:,0],rgb[:,:,1],rgb[:,:,2]
        blue=((r<200)&(g-r>=10)&(b-g>=10)&visible).sum(axis=1)
        brightest=rgb.max(axis=2);darkest=rgb.min(axis=2)
        neutral=((brightest>=150)&(brightest-darkest<=12)&visible).sum(axis=1)
        counts=visible.sum(axis=1);valid=counts>=max(4,rail.width()//2)
        blue_row=valid&(blue>=np.maximum(3,np.ceil(counts*.4)))
        blue_rows=(np.flatnonzero(blue_row)+rail.top()).tolist()
        neutral_rows=int((valid&~blue_row&(neutral>=np.ceil(counts*.6))).sum())
        if neutral_rows < max(8, round(8 * scale)) or not blue_rows:
            return None
        runs = []
        first = last = blue_rows[0]
        for y in blue_rows[1:]:
            if y - last > 2:
                runs.append((first, last));first = y
            last = y
        runs.append((first, last))
        minimum = max(6, round(6 * scale))
        runs = [(a, b) for a, b in runs if b - a + 1 >= minimum]
        if len(runs) != 1:
            return None
        first, last = runs[0]
        return (first - area.top(), last - first + 1)

    def observe_frame(self, image, area, *, tooltip=None, exclude=(), now=None):
        now = time.monotonic() if now is None else now
        area = _rectangle(area)
        if area is None or image is None or image.isNull():
            return False
        hidden = _hidden(tooltip, exclude)
        thumb = self.scrollbar_thumb(image, area, tooltip=tooltip, exclude=exclude)
        changed = False
        compatible = self.area is not None and abs(self.area.width() - area.width()) <= 3 and abs(self.area.height() - area.height()) <= 3
        rim = compatible and self._same_rim(self.frame, self.area, image, area, self.exclusions, hidden)
        if rim and thumb is not None and self.thumb is not None:
            changed = abs(thumb[0] - self.thumb[0]) >= 2 and abs(thumb[1] - self.thumb[1]) <= 2
            if changed:
                self._advance(now)
        # An occluded sample cannot replace the last proven native thumb.  Nor
        # can a foreign pane rebase the rim and establish itself on the next tick.
        if self.area is None or rim:
            self.area = QRect(area)
            self.frame = self._rim_patch(image,area)
            self.exclusions = hidden
            if thumb is not None:
                self.thumb = thumb
        return changed

    def _identity(self, row):
        if self.resolve_identity:
            return self.resolve_identity(row)
        return (glyph_key(item_words(unclipped_name(row.get('name') or ''))).rstrip(': '), row.get('tier'))

    @staticmethod
    def _ink_changed(old, image, rect, hidden):
        if old.rectangle.size() != rect.size():
            return False
        visible = QRegion(QRect(0, 0, rect.width(), max(8, rect.height() // 2)))
        for masked in old.exclude:
            visible = visible.subtracted(QRegion(masked.translated(-old.rectangle.topLeft())))
        for masked in hidden:
            visible = visible.subtracted(QRegion(masked.translated(-rect.topLeft())))
        count = changed = 0
        for part in visible:
            for y in range(part.top(), part.bottom() + 1):
                for x in range(part.left(), part.right() + 1):
                    before = old.pixels.pixelColor(x, y)
                    after = image.pixelColor(rect.x() + x, rect.y() + y)
                    a = max(before.red(), before.green(), before.blue()) < 90
                    b = max(after.red(), after.green(), after.blue()) < 90
                    changed += a != b
                    count += 1
        return count >= max(40, rect.width() * rect.height() // 8) and changed >= max(6, count * .025)

    def observe_rows(self, rows, image, *, area=None, tooltip=None, exclude=(), now=None, latest=None):
        """Accept fresh native row proof; retained/hidden rows never seed a page.

        Pass the canonical ID resolver at construction.  ``latest`` optionally
        rejects a row whose exposed native pixels changed during OCR.  Callers
        must also reject results submitted under an older browsing epoch.
        """
        now = time.monotonic() if now is None else now
        area = _rectangle(area) if area is not None else self.area
        if area is None or image is None or image.isNull():
            return False
        hidden = _hidden(tooltip, exclude)
        proofs = {}
        for row in rows:
            if not isinstance(row, dict) or any(row.get(key) for key in ('covered', 'retained', 'reference_only', 'listing_old', 'presentation_held')):
                continue
            if not row.get('name') or not row.get('price'):
                continue
            identity = self._identity(row)
            rect = _rectangle(row.get('area'))
            if identity is None or rect is None or not image.rect().contains(rect):
                continue
            if any(rect.intersects(mask) for mask in hidden):
                continue
            if latest is not None and (not latest.rect().contains(rect) or latest.copy(rect) != image.copy(rect)):
                continue
            slot = tuple(rect.translated(-area.topLeft()).getRect())
            proofs[slot] = _RowProof(identity, QRect(rect), image.copy(rect), hidden)
        compatible = self.area is not None and abs(self.area.width() - area.width()) <= 3
        changed = bool(not self.pending and compatible and any(
            slot in self.rows and self.rows[slot].identity != proof.identity
            and self._ink_changed(self.rows[slot], image, proof.rectangle, hidden)
            for slot, proof in proofs.items()))
        if changed:
            self._advance(now)
        # A fresh clean list may establish geometry after a drag, or recover an
        # unknown thumb.  Row order, OCR-only corrections and quote changes do
        # not advance the viewport or restart its deadline.
        if proofs:
            self.area = QRect(area)
            self.frame = self._rim_patch(image,area)
            self.exclusions = hidden
            thumb = self.scrollbar_thumb(image, area, tooltip=tooltip, exclude=exclude)
            if thumb is not None:
                self.thumb = thumb
            elif changed:
                # Rows proved this viewport while its thumb was hidden.  Its
                # eventual reveal only seeds a baseline, not another scroll.
                self.thumb = None
            for slot,proof in proofs.items():
                self.rows.pop(slot,None);self.rows[slot]=proof
            while len(self.rows)>self.ROW_LIMIT:self.rows.pop(next(iter(self.rows)))
            self.pending = False
        return changed

"""OS screen sharing only. No process discovery, game APIs, hooks or input APIs."""
from pathlib import Path
from collections import deque
import hashlib
import os
import tempfile
import time
import sys

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal, QRect, QPoint, Qt
from PySide6.QtGui import QImage
import json
from .stream import StreamClient, screen_pixels
from .platform_paths import reader_binary
from .capture_platform import uses_system_picker
from .tracking_identity import name_proof
from .tooltip_association import TooltipAssociation,association_state
from .pickup_capture import PickupWorker
from .shop_browsing import ShopBrowsing
from .reader_request import SubmittedRequest
from .reader_metrics import ReaderMetrics
from .npc_shop import find_npc_shop,suppress_npc_rows,suppress_npc_prices
from .shop_source import cursor_rectangle


class PixelReader(QObject):
    reading = Signal(dict)
    status = Signal(str)
    image_ready = Signal(QImage)
    area_changed = Signal()
    experience = Signal(dict)
    pickup_status = Signal(str)
    shop_viewport_changed = Signal()
    npc_shop_changed = Signal(object)

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.root = Path(root)
        self.temp = tempfile.TemporaryDirectory(prefix="classic-price-lens-", dir=os.environ.get("XDG_RUNTIME_DIR"))
        self.image = QImage()
        self.last_frame = 0.0
        self.image_sequence = 0
        self.submitted_sequence = -1
        self.latest_latency_ms = None
        self.metrics = ReaderMetrics()
        diagnostics=os.environ.get('LUPIN_READER_DIAGNOSTICS')
        if diagnostics:
            self.diagnostics_timer=QTimer(self)
            self.diagnostics_timer.setInterval(2000)
            self.diagnostics_timer.timeout.connect(lambda:self.metrics.write(diagnostics))
            self.diagnostics_timer.start()
        self._experience_enabled = False
        self.pickups_enabled = True
        self.tracking_epoch = 0
        self.tracking_frame_at = 0.0
        self.tracking_identity_area = None
        self.pickup_worker = None
        self.pickup_covered_at = 0
        self.manual_game_area = None
        self.manual_game_guards = []
        self.manual_game_footer = None
        self.prices_enabled = True
        self.last_experience = 0.0
        self.last_price_epoch = None
        self.last_map_read = 0.0
        self.last_pickup = self.last_pickup_frame = 0.0
        self.exclude_regions = lambda: []
        self.annotation_regions = lambda: []
        self.writer_regions = lambda: []
        self.timings = deque(maxlen=240)
        self.last_metrics = 0
        self.shop_rect = None
        self.shop_fingerprint = None
        self.tooltip_enabled = False
        self.pointer = None
        self.last_pointer = None
        self.tooltip_rect = None
        self.tooltip_fingerprint = None
        self.tooltip_association = None
        self.tooltip_title_proof = None
        self.tooltip_retry_requested = False
        self.tooltip_retry_key = None
        self.tooltip_retry_at = 0.0
        self.roi_clean = True
        self.shop_context = None
        self.npc_shop = None
        self.npc_shop_state = 'absent'
        self.shop_context_provider = lambda:self.shop_context
        self.shop_name_recovery_needed = lambda pointer:True
        self.shop_browsing = ShopBrowsing(parent=self)
        self.shop_tooltip_bounds = None
        self.shop_exclusions = lambda: []
        self.crop = None
        self.auto_enabled = True
        self.live_source = False
        self.game_area = None
        self.game_guards = []
        self.game_footer = None
        self.submitted_request = None
        self.active_request = None
        self.next_area_search = 0.0
        self.last_geometry_check = 0.0
        self.last_locator_check = 0.0
        self.paused = False
        self.generation = 0
        self.rescan_requested = False
        self.buffer = b""
        self.kde_screen = None
        self.kde_desktop = None
        self.stream = StreamClient(root, self)
        self.stream.frame.connect(self.on_stream_frame)
        self.stream.status.connect(self.status)
        self.process = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("RAYON_NUM_THREADS", "2")
        env.insert("OMP_NUM_THREADS", "2")
        env.insert("RTEN_NUM_THREADS", "1")
        self.process.setProcessEnvironment(env)
        self.process.readyReadStandardOutput.connect(self.on_output)
        self.process.readyReadStandardError.connect(self.on_stderr)
        self.process.errorOccurred.connect(lambda error: self.status.emit("Reader could not start; run ./setup.sh"))
        self.process.finished.connect(self.on_finished)
        self.process.start(str(reader_binary(self.root)))
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.scan)
        self.timer.start()
        self.screenshot = QProcess(self)
        self.screenshot.finished.connect(self.on_screenshot)
        self.screenshot.errorOccurred.connect(lambda error: self.status.emit("KDE screen capture failed"))
        self.screenshot_timer = QTimer(self)
        self.screenshot_timer.setInterval(300)
        self.screenshot_timer.timeout.connect(self.take_screenshot)

    def start(self, screen, desktop):
        self.generation += 1
        self.paused = False
        self.live_source = True
        self.reset_area()
        self.timer.start()
        self.screenshot_timer.stop()
        self.shop_rect = self.shop_fingerprint = None
        self.shop_context = None
        self.tooltip_rect = self.tooltip_fingerprint = None
        self.tooltip_association = None
        self.status.emit("Choose a monitor or full workspace in the system sharing dialog"
                         if uses_system_picker() else "Capturing the selected display")
        self.stream.start(screen, desktop)

    @property
    def pending(self):return self.active_request is not None

    @property
    def pending_since(self):
        request=self.active_request or self.submitted_request
        return request.started_at if request is not None else 0.0

    @property
    def submitted_image(self):
        return self.submitted_request.frame if self.submitted_request is not None else QImage()

    @property
    def using_roi(self):
        return bool(self.submitted_request is not None and self.submitted_request.using_roi)

    def submit(self,payload,*,mode,now=None,analysis_rect=None,using_roi=False,local_roi=False):
        """Bind response authority and timeout to the pixels actually sent."""
        started=time.monotonic() if now is None else now
        request=SubmittedRequest(mode,self.image,self.pointer,self.image_sequence,self.generation,started,
            shop_epoch=self.shop_browsing.epoch if mode=='prices' else None,
            tracking_epoch=self.tracking_epoch if mode in ('experience','tracking-location') else None,
            crop=self.crop.getRect() if self.crop is not None else None,
            analysis_rect=analysis_rect.getRect() if analysis_rect is not None else None,
            using_roi=using_roi,local_roi=local_roi,locate_game=bool(payload.get('auto_game')),
            annotations=tuple(tuple(rect[key] for key in ('x','y','width','height'))
                              for rect in payload.get('annotations',[])[:64]))
        self.active_request=self.submitted_request=request
        metrics=getattr(self,'metrics',None)
        if metrics is not None:metrics.record(mode.replace('-', '_')+'.submitted',
                            age_ms=max(0,(started-getattr(self,'last_frame',started))*1000))
        if mode=='prices':
            self.last_pointer=request.pointer
            self.last_price_epoch=request.shop_epoch
            payload['shop_epoch']=request.shop_epoch
            payload['capture_generation']=request.generation
        # EXP shares the transport but must not consume the pending price frame.
        if mode!='experience':self.submitted_sequence=request.sequence
        self.process.write((json.dumps(payload)+'\n').encode())

    def pause(self, keep_stream=False):
        self.generation += 1
        self.paused = True
        self.timer.stop()
        self.screenshot_timer.stop()
        self.shop_browsing.reset()
        if keep_stream:
            self.stream.set_paused(True)
        else:
            self.stream.stop()

    def start_kde(self, screen, desktop):
        self.pause()
        self.paused = False
        self.live_source = True
        self.reset_area()
        self.timer.start()
        self.shop_rect = self.shop_fingerprint = None
        self.kde_screen = screen
        self.kde_desktop = desktop
        self.screenshot_timer.start()
        self.status.emit("KDE screenshot fallback • continuous, one capture at a time")
        self.take_screenshot()

    def take_screenshot(self):
        if self.screenshot.state() != QProcess.ProcessState.NotRunning:
            return
        path = str(Path(self.temp.name) / "desktop.bmp")
        self.screenshot.start("spectacle", ["-b", "-n", "-f", "-o", path])

    def on_screenshot(self, code, status):
        if code or not self.screenshot_timer.isActive():
            return
        path = Path(self.temp.name) / "desktop.bmp"
        image = QImage(str(path))
        if image.isNull():
            self.status.emit("KDE returned an empty screenshot")
            return
        self.image = screen_pixels(image, self.kde_screen, self.kde_desktop)
        self.validate_area()
        path.unlink(missing_ok=True)
        self.last_frame = time.monotonic()
        self.mark_tracking_frame()
        self.image_sequence += 1
        self.observe_shop_frame()
        self.image_ready.emit(self.image)
        self.scan()

    def on_stream_frame(self, image, captured_at):
        if self.paused:
            return
        if not image.isNull():
            self.last_frame = captured_at
            self.image = image
            self.validate_area()
            self.mark_tracking_frame()
            self.image_sequence += 1
            self.observe_shop_frame()
            self.image_ready.emit(self.image)
            self.scan()

    def observe_shop_frame(self):
        """A new captured viewport invalidates old OCR before it can draw."""
        if getattr(self,'npc_shop',None) is not None:
            source=self.image.copy(self.crop) if self.crop else self.image
            self.update_npc_shop(source,exclude=self.annotation_regions())
        context=self.current_shop_context()
        if not self.live_source or self.paused or not self.prices_enabled or context is None:
            return
        source = self.image.copy(self.crop) if self.crop else self.image
        pointer=self.pointer
        if pointer is not None and self.crop:pointer=(pointer[0]-self.crop.x(),pointer[1]-self.crop.y())
        if self.shop_browsing.observe_frame(source, context,
                tooltip=self.shop_tooltip_bounds, exclude=self.shop_exclusions(), pointer=pointer):
            self.shop_fingerprint = None
            self.shop_viewport_changed.emit()

    def update_npc_shop(self,image,*,exclude=(),candidate=None):
        """Revalidate stable controls; uncertain NPC ownership stays excluded.

        Discovery belongs to submitted OCR results, not a full-frame scan on
        every capture. This path only samples an already measured header.
        """
        before=self.npc_shop.rectangle if self.npc_shop is not None else None
        npc=self.npc_shop
        point=self.pointer
        if point is not None and self.crop:point=(point[0]-self.crop.x(),point[1]-self.crop.y())
        scale=(npc or candidate).anchor[2] if npc is not None or candidate is not None else 1
        cursor=cursor_rectangle(point,scale)
        exclude=(*exclude,*((cursor,) if cursor is not None else ()))
        state=npc.state(image,exclude) if npc is not None else 'absent'
        if state=='absent' and candidate is not None:
            npc=candidate;state=npc.state(image,exclude)
        if state=='absent':npc=None
        self.npc_shop=npc;self.npc_shop_state=state
        after=npc.rectangle if npc is not None else None
        if after is not None and self.shop_context is not None and after.intersects(self.shop_context):
            self.shop_context=None
        if before!=after:
            # The capture-only fingerprint must not outlive its NPC window.
            self.shop_rect=self.shop_fingerprint=None
            self.npc_shop_changed.emit(after)
        return npc

    def current_shop_context(self):
        provider=getattr(self,'shop_context_provider',None)
        return provider() if callable(provider) else self.shop_context

    def load_image(self, path):
        self.pause()
        self.paused = False
        self.live_source = False
        self.reset_area()
        self.timer.start()
        self.image = QImage(str(path))
        if self.image.isNull():
            self.status.emit("Could not open screenshot")
            return
        self.crop = None
        self.shop_rect = self.shop_fingerprint = None
        self.last_frame = time.monotonic()
        self.image_sequence += 1
        self.image_ready.emit(self.image)
        self.status.emit("Screenshot mode • saved image, not a live capture")
        self.scan()

    @property
    def auto_active(self):
        return self.auto_enabled and self.live_source and self.crop is None

    @property
    def experience_enabled(self):
        return self._experience_enabled

    @experience_enabled.setter
    def experience_enabled(self, enabled):
        self._experience_enabled=bool(enabled)
        worker=getattr(self,'pickup_worker',None)
        if not enabled and worker is not None:
            worker.close()
            self.pickup_worker=None

    @property
    def tracking_area(self):
        return self.game_area if self.auto_active else self.manual_game_area

    @property
    def tracking_ready(self):
        guards = self.game_guards if self.auto_active else self.manual_game_guards
        return bool(self.live_source and not self.paused and self.tracking_area is not None
                    and guards and 0 <= time.monotonic() - self.tracking_frame_at < 1.5)

    def mark_tracking_frame(self):
        area = self.tracking_area
        guards = self.game_guards if self.auto_active else self.manual_game_guards
        if area is not None and guards:
            self.tracking_frame_at = self.last_frame

    def reset_area(self):
        self.game_area = None
        self.game_guards = []
        self.game_footer = None
        self.manual_game_area = None
        self.manual_game_guards = []
        self.manual_game_footer = None
        self.tracking_frame_at = 0.0
        self.tracking_identity_area = None
        self.pickup_covered_at = 0
        if self.pickup_worker is not None:
            self.pickup_worker.invalidate()
        self.next_area_search = 0
        self.shop_rect = self.shop_fingerprint = self.shop_context = None
        self.npc_shop = None
        self.npc_shop_state = 'absent'
        self.shop_tooltip_bounds = None
        self.shop_browsing.reset()
        self.tooltip_rect = self.tooltip_fingerprint = None
        self.tooltip_association = None
        self.tooltip_title_proof = None
        self.last_experience = self.last_map_read = self.last_pickup = self.last_pickup_frame = 0
        self.area_changed.emit()

    def set_auto_area(self, enabled):
        self.auto_enabled = enabled
        if enabled:
            self.crop = None
        self.generation += 1
        self.reset_area()
        self.image_sequence += 1
        self.scan()

    def set_crop(self, area):
        self.generation += 1
        self.crop = area
        self.reset_area()
        self.image_sequence += 1
        self.scan()

    @staticmethod
    def fingerprint(image, area):
        # constBits() borrows storage; retain the QImage until hashing completes.
        patch = image.copy(area)
        return hashlib.blake2b(patch.constBits(), digest_size=8).digest()

    def validate_area(self):
        if self.auto_active and self.game_area and any(
                not self.guard_matches(self.image, area, digest) for area, digest in self.game_guards):
            # Discard results from the old position before drawing another label.
            self.generation += 1
            self.reset_area()
        elif self.manual_game_area is not None and any(
                not self.guard_matches(self.image, area, digest)
                for area, digest in self.manual_game_guards):
            self.generation += 1
            self.reset_area()

    @staticmethod
    def guard_signature(image, area):
        if image.isNull() or not image.rect().contains(area):return None
        patch=image.copy(area).scaled(16,16,Qt.AspectRatioMode.IgnoreAspectRatio,
             Qt.TransformationMode.SmoothTransformation).convertToFormat(QImage.Format.Format_Grayscale8)
        return bytes(patch.constBits())

    @classmethod
    def guard_matches(cls,image,area,reference):
        current=cls.guard_signature(image,area)
        if current is None or reference is None:return False
        gain=sum(current)/max(1,sum(reference))
        if not .80<=gain<=1.20:return False
        return sum(abs(a-b*gain) for a,b in zip(current,reference))/len(current)<8

    def scan(self):
        if self.paused:
            return
        now = time.monotonic()
        if not self.experience_enabled and self.pickup_worker is not None:
            self.pickup_worker.close()
            self.pickup_worker = None
        if (self.experience_enabled and self.pickups_enabled and self.tracking_ready
                and now-self.last_pickup >= .2 and self.last_frame > self.last_pickup_frame):
            self.scan_pickups(now)
        if self.pending:
            if now > self.active_request.deadline_at:
                self.process.kill()
                self.status.emit("Screen reader timed out; restart the app")
            return
        if self.image.isNull() or self.process.state() != QProcess.ProcessState.Running:
            return
        if (self.live_source and self.crop is not None and
                (self.manual_game_area is None or now-self.last_locator_check >= 1)
                and now >= self.next_area_search):
            self.scan_location(now, tracking_only=True)
            return
        exp_due = (self.experience_enabled and self.live_source and now-self.last_frame < 3
                and now-self.last_experience >= 1
                and self.tracking_ready)
        if self.image_sequence == self.submitted_sequence:
            if exp_due:self.scan_experience(now)
            return
        if self.auto_active and self.game_area is None and time.monotonic() < self.next_area_search:
            return
        if not self.prices_enabled:
            if self.auto_active and (self.game_area is None or now-self.last_locator_check>=1):
                self.scan_location(now)
            elif exp_due:self.scan_experience(now)
            else:self.submitted_sequence=self.image_sequence
            return
        force_rescan = self.rescan_requested
        image = self.image.copy(self.crop) if self.crop else self.image
        pointer = self.pointer
        if pointer and self.crop:
            pointer = (pointer[0] - self.crop.x(), pointer[1] - self.crop.y())
        context=self.current_shop_context()
        npc=getattr(self,'npc_shop',None)
        in_shop = pointer_in_shop(pointer, context)
        hover_check = self.tooltip_enabled and pointer is not None and not in_shop
        if self.auto_active:
            hover_check = bool(hover_check and self.game_area and self.game_area.contains(QPoint(*pointer)))
        tooltip_same = False
        if (hover_check and not self.tooltip_retry_requested and self.tooltip_rect and self.pointer==self.last_pointer
                and (self.tooltip_fingerprint is not None or getattr(self,'tooltip_association',None) is not None
                     or getattr(self,'tooltip_title_proof',None) is not None)):
            if self.tooltip_association is not None:
                tooltip_same=self.tooltip_association.matches(image,pointer,exclude=self.annotation_regions())
            elif getattr(self,'tooltip_title_proof',None) is not None:
                tooltip_same=self.tooltip_title_proof.matches(image,pointer=pointer)
            else:tooltip_same=self.fingerprint(image,self.tooltip_rect)==self.tooltip_fingerprint
        if self.shop_rect and self.shop_fingerprint is not None:
            patch = image.copy(context or self.shop_rect)
            fingerprint = hashlib.blake2b(patch.constBits(), digest_size=8).digest()
            # Native pane closure/source changes request their own rescan.
            # An unchanged stationary shop need not repeat description OCR
            # five times a second merely because the pointer remains inside it.
            shop_hover_due = (in_shop or bool(npc and npc.contains(pointer))) and self.pointer != self.last_pointer
            if (not force_rescan and fingerprint == self.shop_fingerprint and not shop_hover_due and (not hover_check or tooltip_same)
                    and (not self.auto_active or now-self.last_locator_check<1.0)):
                self.submitted_sequence = self.image_sequence
                if exp_due:self.scan_experience(now)
                return
        elif not force_rescan and self.shop_rect is None and tooltip_same:
            self.submitted_sequence = self.image_sequence
            if exp_due:self.scan_experience(now)
            return
        if not force_rescan and self.shop_rect is None and time.monotonic() - self.pending_since < 0.2:
            return
        # Give a newly opened/scrolled page one prompt slot, with an absolute
        # EXP-service bound. There is still only one primary in-flight request.
        browsing=getattr(self,'shop_browsing',None)
        fresh_shop=(force_rescan or self.shop_rect is None or browsing is not None
                    and browsing.epoch!=getattr(self,'last_price_epoch',None))
        if exp_due and now-self.last_experience>=1.6 and (not fresh_shop or now-self.last_experience>=2.5):
            self.scan_experience(now)
            return
        origin = {"x": 0, "y": 0}
        using_roi = bool(self.shop_rect and self.roi_clean and not hover_check and not force_rescan)
        local_roi=bool(self.auto_active and using_roi and self.game_area
                                   and now-self.last_locator_check<1.0)
        if using_roi:
            region = (context or self.shop_rect).adjusted(-16, -16, 16, 16).intersected(image.rect())
            if not self.auto_active or local_roi:
                origin = {"x": region.x(), "y": region.y()}
                image = image.copy(region)
        if self.auto_active and not local_roi:self.last_locator_check=now
        image = image.convertToFormat(QImage.Format.Format_RGBA8888)
        path = Path(self.temp.name) / "frame.rgba"
        path.write_bytes(image.constBits())
        self.rescan_requested = False
        started=time.monotonic()
        self.last_geometry_check = started
        request = {"path": str(path), "at_ms": int(self.last_frame * 1000),
                   "pointer": {"x": pointer[0], "y": pointer[1]} if pointer is not None else None,
                   "tooltip": bool(hover_check),
                   "tooltip_retry": bool(hover_check and self.tooltip_retry_requested),
                   "origin": origin,
                   "auto_game": self.auto_active and not local_roi,
                   "roi": {"x": region.x(), "y": region.y(), "width": region.width(), "height": region.height()} if self.auto_active and using_roi and not local_roi else None,
                   "width": image.width(), "height": image.height()}
        needs_name=getattr(self,'shop_name_recovery_needed',lambda point:True)
        request['shop_area']=(dict(zip(('x','y','width','height'),context.getRect()))
                               if context is not None else None)
        request['shop_recovery']=bool(context is not None and needs_name(pointer))
        request['progressive_shop']=bool(context is not None and not hover_check)
        crop_origin=self.crop.topLeft() if self.crop else QPoint()
        source_region=self.crop.intersected(self.image.rect()) if self.crop else self.image.rect()
        request['exclude']=[dict(zip(('x','y','width','height'),rect.intersected(source_region).translated(-crop_origin).getRect()))
                            for rect in self.writer_regions()[:8] if rect.intersects(source_region)]
        request['annotations']=[dict(zip(('x','y','width','height'),rect.getRect()))
                                for rect in self.annotation_regions()[:64] if not rect.isEmpty()]
        self.tooltip_retry_requested = False
        self.submit(request,mode='prices',now=started,using_roi=using_roi,local_roi=local_roi)

    def request_rescan(self,*,preserve_shop_cache=False):
        """Queue newest pixels without changing an active request's deadline."""
        if not preserve_shop_cache:self.shop_fingerprint = None
        self.rescan_requested = True
        self.image_sequence += 1
        QTimer.singleShot(0,self.scan)

    def retry_tooltip(self, key):
        now=time.monotonic()
        if key is None or key==self.tooltip_retry_key or now-self.tooltip_retry_at<.5:return
        self.tooltip_retry_key=key;self.tooltip_retry_at=now
        self.tooltip_retry_requested=True;self.image_sequence+=1
        QTimer.singleShot(0,self.scan)

    def scan_location(self,now,tracking_only=False):
        source = self.image.copy(self.crop) if tracking_only and self.crop else self.image
        image=source.convertToFormat(QImage.Format.Format_RGBA8888)
        path=Path(self.temp.name)/'location.rgba';path.write_bytes(image.constBits())
        self.last_locator_check=now
        self.submit({'path':str(path),'at_ms':int(self.last_frame*1000),
             'auto_game':True,'locate_only':True,'width':image.width(),'height':image.height()},
             mode='tracking-location' if tracking_only else 'location',now=now,
             analysis_rect=self.crop if tracking_only else None)

    def scan_experience(self, now):
        # Reuse this capture and this OCR process. Map search is infrequent;
        # ordinary EXP samples transport only the bottom 256 pixels.
        area = self.tracking_area
        if area is None or not self.tracking_ready:
            return
        area = area.intersected(self.image.rect())
        read_map = now-self.last_map_read >= 5
        if not read_map:
            area = QRect(area.x(), max(area.y(), area.bottom()+1-256), area.width(), min(256, area.height()))
        image = self.image.copy(area).convertToFormat(QImage.Format.Format_RGBA8888)
        if image.isNull():
            return
        path = Path(self.temp.name)/"experience.rgba"
        path.write_bytes(image.constBits())
        self.last_experience = now
        if read_map:
            self.last_map_read = now
        request = {"path":str(path),"width":image.width(),"height":image.height(),
                   "at_ms":int(self.last_frame*1000),"experience_only":True,"read_map":read_map,
                   "origin":{"x":area.x(),"y":area.y()}}
        self.submit(request,mode='experience',now=now,analysis_rect=area)

    @staticmethod
    def pickup_area(game):
        """Keep the footer and our bottom-left tracking cards outside the ROI."""
        width=min(640,max(180,round(game.width()*.48)))
        height=min(300,max(40,round(game.height()*.32)))
        footer=min(64,max(28,round(game.height()*.08)))
        return QRect(game.right()+1-width,max(game.y(),game.bottom()+1-footer-height),width,height).intersected(game)

    def scan_pickups(self,now):
        game=self.tracking_area
        if game is None or not self.tracking_ready or not self.pickups_enabled:return
        area=self.pickup_area(game).intersected(self.image.rect())
        if any(area.intersects(region) for region in self.exclude_regions()):
            self.metrics.record('pickup.covered')
            self.pickup_status.emit('covered')
            self.last_pickup=now;self.last_pickup_frame=self.last_frame
            self.pickup_covered_at=int(self.last_frame*1000)
            if self.pickup_worker is not None:self.pickup_worker.invalidate()
            self.experience.emit({'atMs':int(self.last_frame*1000),'pickupsRead':True,
                                  'trackingEpoch':self.tracking_epoch,
                                  'pickups':{'valid':False,'covered':True,'lines':[]}})
            return
        if self.pickup_worker is not None and self.pickup_worker.pending:return
        image=self.image.copy(area).convertToFormat(QImage.Format.Format_RGBA8888)
        if image.isNull():return
        if self.pickup_worker is None:
            self.pickup_worker=PickupWorker(self.root,self.temp.name,self)
            self.pickup_worker.result.connect(self.on_pickup_result)
            self.pickup_worker.issue.connect(self.on_pickup_issue)
        identity_proof=name_proof(self.image,self.tracking_identity_area,QPoint())
        if self.pickup_worker.submit(image,self.last_frame,self.generation,self.tracking_epoch,identity_proof):
            self.metrics.record('pickup.submitted',age_ms=max(0,(now-self.last_frame)*1000))
            self.last_pickup=now;self.last_pickup_frame=self.last_frame

    def on_pickup_issue(self, reason):
        self.metrics.record('pickup.'+reason)
        self.pickup_status.emit(reason)

    def on_pickup_result(self,result):
        age=time.monotonic()*1000-result.get('atMs',0)
        if not (self.tracking_ready and self.experience_enabled and self.pickups_enabled):reason='inactive'
        elif result.get('captureGeneration')!=self.generation:reason='old_capture'
        elif result.get('trackingEpoch')!=self.tracking_epoch:reason='old_session'
        elif result.get('atMs',0)<=self.pickup_covered_at:reason='covered_frame'
        elif not 0<=age<1500:reason='late_frame'
        else:reason='delivered'
        self.metrics.record('pickup.'+reason,age_ms=age)
        if reason=='delivered':self.experience.emit(result)
        elif reason=='late_frame':self.pickup_status.emit(reason)

    def accept_tracking_location(self,result,request):
        origin=QPoint(*request.analysis_origin)
        area=result.get('gameArea')
        guards=[QRect(*(rect[k] for k in ('x','y','width','height'))).translated(origin)
                for rect in result.get('gameGuards') or []]
        fingerprints=[(rect,self.guard_signature(request.frame,rect)) for rect in guards]
        if area and fingerprints and all(self.guard_matches(self.image,rect,digest) for rect,digest in fingerprints):
            selected=QRect(*(area[k] for k in ('x','y','width','height'))).translated(origin)
            if self.crop is None or not self.crop.contains(selected):
                selected=None
        else:
            selected=None
        changed=selected!=self.manual_game_area
        self.manual_game_area=selected
        self.manual_game_guards=fingerprints if selected is not None else []
        footer=result.get('gameFooter')
        self.manual_game_footer=(QRect(*(footer[k] for k in ('x','y','width','height')))
            .translated(origin).intersected(selected)
            if selected is not None and isinstance(footer,dict) else None)
        if selected is None:
            self.next_area_search=time.monotonic()+.4
            self.tracking_frame_at=0.0
        else:self.mark_tracking_frame()
        if changed:self.area_changed.emit()

    def on_output(self):
        self.buffer += bytes(self.process.readAllStandardOutput())
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            request=self.active_request
            self.active_request=None
            if request is None:continue
            metrics=getattr(self,'metrics',None)
            try:
                result = json.loads(line)
                partial=request.mode=='prices' and result.get('shopPartial') is True
                if partial:self.active_request=request
                if metrics is not None:metrics.record(request.mode.replace('-', '_')+('.partial' if partial else '.returned'),
                    duration_ms=(time.monotonic()-request.started_at)*1000)
                if metrics is not None and request.mode=='prices':
                    metrics.record('prices.capture_age',age_ms=time.monotonic()*1000-result.get('atMs',0))
                    if result.get('shopCached') is True:metrics.record('prices.cache_hit')
                    for key,event in (('shopMs','prices.native_shop'),('componentMs','prices.native_components'),('tooltipMs','prices.native_tooltip')):
                        metrics.record(event,duration_ms=(result.get('readerStages') or {}).get(key))
                if self.paused or request.generation != self.generation:
                    continue
                if result.get("error"):
                    self.status.emit("Reader: " + result["error"])
                else:
                    if request.mode=='tracking-location':
                        if request.tracking_epoch==self.tracking_epoch:self.accept_tracking_location(result,request)
                        continue
                    if request.mode=='experience':
                        if (self.experience_enabled and self.tracking_ready
                                and request.tracking_epoch==self.tracking_epoch
                                and 0<=time.monotonic()*1000-result.get("atMs",0) < 1500):
                            experience=result.get('experience')
                            if isinstance(experience,dict):
                                experience['nameProof']=name_proof(request.analysis_image(),experience.get('area'),QPoint(*request.analysis_origin))
                                if experience['nameProof'] is not None:self.tracking_identity_area=experience.get('area')
                            result['trackingEpoch']=request.tracking_epoch
                            self.experience.emit(result)
                        continue
                    if request.locate_game:
                        area = result.get("gameArea")
                        guards = [QRect(r["x"], r["y"], r["width"], r["height"]) for r in result.get("gameGuards") or []]
                        fingerprints = [(r, self.guard_signature(request.frame, r)) for r in guards]
                        if area and (not fingerprints or any(not self.guard_matches(self.image, r, digest) for r, digest in fingerprints)):
                            self.reset_area()
                            continue
                        selected = QRect(area["x"], area["y"], area["width"], area["height"]) if area else None
                        changed = selected != self.game_area
                        self.game_area, self.game_guards = selected, fingerprints
                        self.mark_tracking_frame()
                        footer=result.get('gameFooter')
                        self.game_footer=(QRect(*(footer[k] for k in ('x','y','width','height'))).intersected(selected)
                                          if selected is not None and isinstance(footer,dict) else None)
                        if selected is None:
                            self.next_area_search = time.monotonic() + 0.4
                        if changed:
                            self.area_changed.emit()
                    if request.mode=='location':continue
                    # Classify from the immutable submission before publishing
                    # rows, including replies submitted under an older epoch.
                    source=request.source_image();current=self.image.copy(self.crop) if self.crop else self.image
                    masks=tuple(QRect(*rect) for rect in request.annotations)
                    native_area=(result.get('shop') or {}).get('area') or {}
                    near=(QRect(*(native_area[key] for key in ('x','y','width','height')))
                        if all(type(native_area.get(key)) is int for key in ('x','y','width','height')) else None)
                    read_point=request.pointer;current_point=self.pointer
                    if request.crop:
                        if read_point is not None:read_point=(read_point[0]-request.crop[0],read_point[1]-request.crop[1])
                        if current_point is not None:current_point=(current_point[0]-request.crop[0],current_point[1]-request.crop[1])
                    source_npc=self.npc_shop
                    cursor=cursor_rectangle(read_point,source_npc.anchor[2] if source_npc is not None else
                        max(.5,min(3,near.width()/199)) if near is not None else 1)
                    masks=(*masks,*((cursor,) if cursor is not None else ()))
                    if source_npc is None or source_npc.state(source,masks)=='absent':
                        generic=result.get('tooltip')
                        # An inventory-only reply must still prove its header,
                        # cell and title below. With no shop rows to classify,
                        # its flag need not trigger another full-frame search.
                        possible=near is not None or (isinstance(generic,dict) and generic.get('found')
                            and association_state(result.get('tooltipAssociation'))!='inventory-primary')
                        source_npc=find_npc_shop(source,near=near,exclude=masks) if possible else None
                    current_npc=self.update_npc_shop(current,exclude=self.annotation_regions(),candidate=source_npc)
                    raw_shop_hover=bool(result.get('hover'))
                    result=suppress_npc_rows(suppress_npc_rows(result,source_npc),current_npc)
                    if current_npc is not None:result['_npc_shop_area']=current_npc.rectangle.getRect()
                    stale_shop = request.shop_epoch != self.shop_browsing.epoch
                    result['shopViewportEpoch'] = request.shop_epoch
                    result['_submitted_request']=request
                    if stale_shop:
                        # An unrelated shop scroll cannot invalidate a freshly
                        # proved inventory cell/title in this same submission.
                        # Retire only shop authority; the newest page's caches
                        # must not be replaced or cleared by this late reply.
                        shop_hover=raw_shop_hover
                        result.update(_shop_stale=True,shop=None,hover=None)
                        self.request_rescan(preserve_shop_cache=True)
                        if shop_hover and association_state(result.get('tooltipAssociation'))=='normal':
                            # Removing an obsolete hover field must not turn its
                            # shop description into an inventory reference.
                            continue
                        independent=result.get('tooltip')
                        if (not (isinstance(independent,dict) and isinstance(independent.get('found'),dict))
                                and association_state(result.get('tooltipAssociation'))!='rejected'):
                            # A shop-only miss must not retire an independent
                            # tooltip already established from newer pixels.
                            continue
                    else:
                        area = (result.get("shop") or {}).get("area")
                        rows = (result.get("shop") or {}).get("rows") or []
                        clean = all(row.get("covered") or row.get("name") and (row.get("price") or row.get('nameOnly')) for row in rows)
                        if request.using_roi and area and not clean:
                            # A slightly moved shop can still be found inside the old
                            # crop while the tail of each price is clipped. Read the
                            # full current frame next. Independently complete rows
                            # can publish now; one incomplete neighbour cannot
                            # freeze every old label until that retry completes.
                            self.request_rescan()
                        self.roi_clean = bool(clean)
                        if request.using_roi and area is None and self.npc_shop is None and (not self.auto_active or self.game_area):
                            # A moved/closed shop triggers an immediate full search
                            # in the same captured frame, not another polling delay.
                            self.request_rescan()
                        self.shop_rect = QRect(area["x"], area["y"], area["width"], area["height"]) if area else None
                        # Only accepted player rows establish hover routing.
                        # The separate NPC rectangle below is capture-only.
                        if self.shop_rect and rows:
                            if self.shop_context is None or abs(self.shop_context.x() - self.shop_rect.x()) > 4 or not self.shop_context.intersects(self.shop_rect):
                                self.shop_context = self.shop_rect
                            else:
                                self.shop_context = self.shop_context.united(self.shop_rect)
                        else:
                            self.shop_context = None
                        if self.shop_rect is None and self.npc_shop is not None:
                            # Cache only the NPC lists, away from character/NPC
                            # animations. This is a capture optimization, never
                            # a player-shop routing context or a price source.
                            self.shop_rect=self.npc_shop.lists
                        if self.shop_rect:
                            source = request.source_image()
                            # Compare later frames with the frame actually recognised.
                            # New captures arriving during OCR must not disable caching.
                            self.shop_fingerprint = self.fingerprint(source, self.current_shop_context() or self.shop_rect)
                        else:
                            self.shop_fingerprint = None
                    tooltip = (result.get("tooltip") or {})
                    found = tooltip.get("found") if isinstance(tooltip, dict) else None
                    association=result.get('tooltipAssociation');state=association_state(association)
                    proof=None
                    if state=='inventory-primary':
                        source=request.source_image()
                        current=self.image.copy(self.crop) if self.crop else self.image
                        read_point=request.pointer;current_point=self.pointer
                        if self.crop:
                            if read_point is not None:read_point=(read_point[0]-self.crop.x(),read_point[1]-self.crop.y())
                            if current_point is not None:current_point=(current_point[0]-self.crop.x(),current_point[1]-self.crop.y())
                        proof=TooltipAssociation.read(association,found,source,pointer=read_point,
                            exclude=tuple(QRect(*rect) for rect in request.annotations))
                        if proof is None or not proof.contains_pointer(read_point) or not proof.matches(
                                current,current_point,exclude=self.annotation_regions()):state='rejected'
                    if state=='rejected':result['tooltipAssociation']={'state':'rejected'}
                    for npc,point in ((source_npc,read_point),(current_npc,current_point)):
                        result=suppress_npc_prices(result,npc,point,inventory=proof if state=='inventory-primary' else None)
                    tooltip=result.get('tooltip') or {}
                    found=tooltip.get('found') if isinstance(tooltip,dict) else None
                    state=association_state(result.get('tooltipAssociation'))
                    if state=='rejected':
                        result['tooltipAssociation']={'state':'rejected'}
                        result['tooltip']={**(tooltip if isinstance(tooltip,dict) else {}),'found':None}
                        found=None;proof=None
                    self.tooltip_association=proof
                    result['_tooltip_context']=proof
                    tooltip_area = found.get("area") if found else None
                    self.tooltip_rect = QRect(tooltip_area["x"], tooltip_area["y"], tooltip_area["width"], tooltip_area["height"]) if tooltip_area else None
                    if self.tooltip_rect and (proof is not None or self.image_sequence == self.submitted_sequence):
                        source = request.source_image()
                        self.tooltip_fingerprint = self.fingerprint(source, self.tooltip_rect)
                    else:
                        self.tooltip_fingerprint = None
                    self.latest_latency_ms = time.monotonic() * 1000 - result["atMs"]
                    self.timings.append({"capture_to_read_ms": round(self.latest_latency_ms, 1),
                                         "ocr_ms": round(result.get("ocrMs", 0), 1),
                                         "rows": len((result.get("shop") or {}).get("rows", []))})
                    result["pointerAtRead"] = list(request.pointer) if request.pointer is not None else None
                    self.reading.emit(result)
                    metrics = os.environ.get("CLASSIC_LENS_METRICS")
                    if metrics and time.monotonic() - self.last_metrics > 1:
                        Path(metrics).write_text(json.dumps(list(self.timings), indent=2) + "\n")
                        self.last_metrics = time.monotonic()
            except (ValueError, TypeError) as error:
                self.status.emit(f"Reader returned an invalid result: {error}")
        if self.image_sequence != self.submitted_sequence:
            QTimer.singleShot(0, self.scan)

    def on_stderr(self):
        # Keep the stream drained; no game pixels or OCR strings are sent anywhere.
        message = bytes(self.process.readAllStandardError()).decode(errors="replace")
        if message.strip():
            self.status.emit("Reader: " + message[-300:].strip())

    def on_finished(self, code, status):
        self.active_request = None
        if code:
            self.status.emit(f"Screen reader stopped ({code}); restart the app")

    def close(self, keep_stream=False):
        self.paused=True
        if hasattr(self,'diagnostics_timer'):self.diagnostics_timer.stop()
        self.timer.stop()
        self.screenshot_timer.stop()
        if self.pickup_worker is not None:
            self.pickup_worker.close()
            self.pickup_worker=None
        if self.screenshot.state() != QProcess.ProcessState.NotRunning:
            self.screenshot.kill()
            self.screenshot.waitForFinished(1000)
        self.stream.stop(keep_session=keep_stream)
        self.process.closeWriteChannel()
        if not self.process.waitForFinished(1500):
            self.process.kill()
            self.process.waitForFinished(1000)
        self.temp.cleanup()


def pointer_in_shop(pointer, shop_context):
    return bool(pointer is not None and shop_context is not None and shop_context.contains(QPoint(*pointer)))

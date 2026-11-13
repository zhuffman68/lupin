"""Our independent annotation helper, with versioned startup and bounded recovery."""
import json
import os
from pathlib import Path
import sys
import time

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

from . import __version__
from .desktop_environment import recovered_environment
from .platform_paths import cache_directory
from .updates import atomic_json


class Overlay(QObject):
    pointer = Signal(int, int)
    writer_event = Signal(dict)
    writer_lost = Signal()
    status = Signal(str)
    painted = Signal(dict)

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.root = Path(root)
        self.process = QProcess(self)
        self.buffer = b''
        self.last_state = None
        self.sent_state = None
        self.presentation_id=0;self.capture_at=0;self.last_capture_considered=0;self.pending_capture_at=0
        self.diagnostics=bool(os.environ.get('LUPIN_READER_DIAGNOSTICS'))
        self.state_pending = False
        self.state_timer=QTimer(self);self.state_timer.setSingleShot(True)
        self.state_timer.timeout.connect(self.flush_labels)
        self.process.bytesWritten.connect(lambda *_:self.schedule_labels())
        self.writer_state = None
        self.last_error = ''
        self.layout_boxes = []
        self.ready = False
        self.closed = False
        self.retries = 0
        self.loss_handled = False
        self.failure_reason = ''
        self.retry_timer = QTimer(self)
        self.retry_timer.setSingleShot(True)
        self.retry_timer.timeout.connect(self.start)
        self.startup_timer = QTimer(self)
        self.startup_timer.setSingleShot(True)
        self.startup_timer.setInterval(4000)
        self.startup_timer.timeout.connect(self.startup_timed_out)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.readyReadStandardError.connect(self.read_error)
        self.process.started.connect(self.flush_state)
        self.process.finished.connect(self.writer_disconnected)
        self.process.errorOccurred.connect(self.process_error)
        self.process.setWorkingDirectory(str(self.root))
        self.start()

    def start(self):
        if self.closed or self.process.state() != QProcess.ProcessState.NotRunning:
            return
        self.ready = False
        self.sent_state=None
        self.loss_handled = False
        self.failure_reason = ''
        self.buffer = b''
        self.last_error = ''
        environment = QProcessEnvironment.systemEnvironment()
        for key, value in recovered_environment().items():
            environment.insert(key, value)
        # Position only our independent canvas through XWayland. No game
        # window handles, parenting, hooks or input synthesis are involved.
        if (sys.platform.startswith('linux') and os.environ.get('WAYLAND_DISPLAY')
                and os.environ.get('DISPLAY') and os.environ.get('QT_QPA_PLATFORM') != 'offscreen'):
            environment.insert('QT_QPA_PLATFORM', 'xcb')
        self.process.setProcessEnvironment(environment)
        self.startup_timer.start()
        self.process.start(sys.executable, ['-B', '-m', 'price_lens.annotations'])

    def read_error(self):
        self.last_error = (self.last_error + bytes(self.process.readAllStandardError()).decode(errors='replace'))[-3000:]

    def record_failure(self, reason, code=None):
        # No stderr, captured text, draft or personal path is persisted.
        try:
            atomic_json(cache_directory() / 'overlay-startup.json', dict(
                at=time.time(), version=__version__, reason=reason,
                exit_code=code, retries=self.retries,
            ))
        except OSError:
            pass

    def process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.failure_reason = 'start-failed'
            self.writer_disconnected()

    def startup_timed_out(self):
        if self.closed or self.ready:
            return
        self.failure_reason = 'startup-timeout'
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()
        else:
            self.writer_disconnected()

    def writer_disconnected(self, code=None, *_):
        if self.loss_handled:
            return
        self.loss_handled = True
        self.ready = False
        self.layout_boxes = []
        self.writer_state = None
        self.startup_timer.stop()
        self.writer_lost.emit()
        if self.closed:
            return
        self.read_error()
        reason = self.failure_reason or ('display-authentication' if 'Authorization required' in self.last_error else 'unexpected-exit')
        self.record_failure(reason, code if type(code) is int else None)
        if self.retries < 2:
            self.retry_timer.start(500 * 2 ** self.retries)
            self.retries += 1
            self.status.emit('Restoring overlay labels…')
        else:
            self.status.emit('Overlay labels could not start. Retry overlays or restart Lupin from the application launcher.')

    def retry(self):
        if self.closed or self.process.state() != QProcess.ProcessState.NotRunning:
            return
        self.retry_timer.stop()
        self.retries = 0
        self.status.emit('Restoring overlay labels…')
        self.start()

    def flush_state(self):
        self.state_pending=self.last_state is not None
        self.flush_labels()
        if self.writer_state is not None and self.writer_available:
            if self.writer_state.get('operation') == 'open':
                self.allow_writer_foreground()
            self.process.write((json.dumps({'writer': self.writer_state}, ensure_ascii=False) + '\n').encode('utf-8'))

    def allow_writer_foreground(self):
        if sys.platform == 'win32' and self.process.processId():
            import ctypes
            try:
                ctypes.windll.user32.AllowSetForegroundWindow(int(self.process.processId()))
            except (AttributeError, OSError):
                pass

    @property
    def writer_available(self):
        return self.ready and self.process.state() == QProcess.ProcessState.Running

    @property
    def recovering(self):
        return not self.closed and not self.ready and (self.retry_timer.isActive() or self.startup_timer.isActive())

    def update_writer(self, state):
        self.writer_state = state
        if self.writer_available:
            if state.get('operation') == 'open':
                self.allow_writer_foreground()
            self.process.write((json.dumps({'writer': state}, ensure_ascii=False) + '\n').encode('utf-8'))

    def read_output(self):
        self.buffer += bytes(self.process.readAllStandardOutput())
        if len(self.buffer) > 131072:
            self.buffer = b''
            return
        while b'\n' in self.buffer:
            line, self.buffer = self.buffer.split(b'\n', 1)
            try:
                report = json.loads(line)
                if not isinstance(report, dict):
                    continue
                if report.get('ready') is True:
                    if report.get('version') != __version__:
                        self.failure_reason = 'version-mismatch'
                        self.process.kill()
                        return
                    self.ready = True
                    self.startup_timer.stop()
                    self.status.emit('')
                if isinstance(report.get('writer'), dict):
                    self.writer_event.emit(report['writer'])
                painted=report.get('painted')
                if isinstance(painted,dict) and type(painted.get('id')) is int and 0<painted['id']<=self.presentation_id:
                    self.painted.emit(painted)
                if isinstance(report.get('layout'), list):
                    self.layout_boxes = report['layout'][:48]
                point = report.get('pointer')
                if (isinstance(point, list) and len(point) == 2
                        and all(type(value) is int for value in point)):
                    self.pointer.emit(*point)
            except (ValueError, TypeError):
                pass

    def update(self, geometry, rows, hover_enabled=False):
        state = dict(geometry=geometry, rows=rows, hover_enabled=hover_enabled,
                               reduce_motion=getattr(self, 'reduce_motion', False),
                               shop_viewport_epoch=getattr(self, 'shop_viewport_epoch', 0),
                               shop_viewport_pending=getattr(self, 'shop_viewport_pending', False))
        new_capture=self.capture_at if self.capture_at!=self.last_capture_considered else 0
        self.last_capture_considered=self.capture_at
        if state==self.last_state:return
        if new_capture:self.pending_capture_at=new_capture
        self.last_state=state
        self.state_pending=True
        # First useful annotations need not wait for the control panel's card
        # layout. Repeated state is suppressed; a busy pipe retains only latest.
        if self.process.state()==QProcess.ProcessState.Running and not self.process.bytesToWrite():self.flush_labels()
        else:self.schedule_labels()

    def schedule_labels(self):
        if (not self.closed and self.state_pending and not self.state_timer.isActive()
                and self.process.state()==QProcess.ProcessState.Running and not self.process.bytesToWrite()):
            self.state_timer.start(0)

    def flush_labels(self):
        if (not self.state_pending or self.process.state()!=QProcess.ProcessState.Running
                or self.process.bytesToWrite()):return
        self.state_timer.stop();self.state_pending=False
        if self.last_state==self.sent_state:return
        self.presentation_id+=1;state=self.last_state
        if self.diagnostics:
            state=dict(state,trace=dict(id=self.presentation_id,sent_at=time.monotonic(),captured_at=self.pending_capture_at))
        self.process.write((json.dumps(state,separators=(',',':'))+'\n').encode())
        self.sent_state=self.last_state
        self.pending_capture_at=0

    def close(self):
        if self.closed:return
        self.closed = True
        self.ready = False
        self.retry_timer.stop()
        self.startup_timer.stop()
        self.state_timer.stop()
        if self.process.state() == QProcess.ProcessState.NotRunning:
            return
        # Close the input stream directly: the helper retires its own surfaces
        # at EOF. Do not queue an otherwise deferred state during shutdown.
        from .process_lifecycle import retire_process
        retire_process(self.process,1000)

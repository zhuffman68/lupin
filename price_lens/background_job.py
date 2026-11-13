"""One running job and one replaceable pending job; results return to Qt."""
from concurrent.futures import CancelledError, ThreadPoolExecutor
from dataclasses import dataclass

from PySide6.QtCore import QObject, Qt, Signal

from .http_json import RequestToken


@dataclass(frozen=True)
class JobResult:
    generation: int
    value: object = None
    error: Exception | None = None


class LatestJob(QObject):
    completed = Signal(object)
    _finished = Signal(object)

    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=name)
        self.generation = 0
        self.closed = False
        self.active = None
        self.pending = None
        self.future = None
        self._finished.connect(self._finish, Qt.ConnectionType.QueuedConnection)

    def submit(self, work):
        if self.closed:
            return None
        self.generation += 1
        if self.active:
            self.active[2].cancel()
        if self.pending:
            self.pending[2].cancel()
        job = (self.generation, work, RequestToken())
        if self.future is None:
            self._start(job)
        else:
            self.pending = job
        return self.generation

    def _start(self, job):
        self.active = job
        generation, work, token = job
        def run():
            try:
                token.check()
                value = work(token)
                token.check()
                return JobResult(generation, value)
            except Exception as error:
                return JobResult(generation, error=error)
        self.future = self.pool.submit(run)
        self.future.add_done_callback(lambda future: self._finished.emit(future.result()) if not self.closed else None)

    def _finish(self, result):
        self.future = None
        self.active = None
        if self.closed:
            return
        if result.generation == self.generation and not isinstance(result.error, CancelledError):
            self.completed.emit(result)
        pending, self.pending = self.pending, None
        if pending and self.future is None:
            self._start(pending)

    def cancel(self):
        self.generation += 1
        if self.active:
            self.active[2].cancel()
        if self.pending:
            self.pending[2].cancel()
        self.pending = None

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.cancel()
        self.pool.shutdown(wait=False, cancel_futures=True)

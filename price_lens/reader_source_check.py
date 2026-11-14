"""One bounded, asynchronous native-control check for an immutable reader reply."""
from PySide6.QtCore import QObject,Signal

from .background_job import LatestJob


class ReaderSourceCheck(QObject):
    finished=Signal()

    def __init__(self,parent=None):
        super().__init__(parent)
        self.work=LatestJob('lupin-source-check',self)
        self.work.completed.connect(self.complete)
        self.pending=None;self.ready=None

    @property
    def busy(self):return self.pending is not None

    def submit(self,request,line,check):
        if self.busy:raise RuntimeError('A reader source check is already pending')
        self.ready=None;self.pending=(request,line)
        self.work.submit(check)

    def complete(self,result):
        pending,self.pending=self.pending,None
        if pending is None:return
        self.ready=(*pending,result)
        self.finished.emit()

    def take(self,request,line):
        ready,self.ready=self.ready,None
        return ready[2] if ready is not None and ready[0] is request and ready[1]==line else None

    def cancel(self):
        was_pending=self.busy
        self.pending=self.ready=None;self.work.cancel()
        # Release the saved reply through the ordinary generation/pause checks.
        if was_pending:self.finished.emit()

    def close(self):
        self.pending=self.ready=None;self.work.close()

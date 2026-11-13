"""Lazy, bounded recovery for Lupin's own native OCR process."""
from PySide6.QtCore import QObject,QProcess,QProcessEnvironment,QTimer,Signal

from .process_lifecycle import retire_process


class ReaderProcess(QObject):
    lost=Signal(str)

    def __init__(self,binary,parent=None):
        super().__init__(parent);self.binary=str(binary)
        self.process=QProcess(self)
        self.process.setProgram(self.binary)
        environment=QProcessEnvironment.systemEnvironment()
        for key,value in (('RAYON_NUM_THREADS','2'),('OMP_NUM_THREADS','2'),('RTEN_NUM_THREADS','1')):environment.insert(key,value)
        self.process.setProcessEnvironment(environment)
        self.closed=self.wanted=self.recovering=False;self.attempts=0
        self.retry=QTimer(self);self.retry.setSingleShot(True);self.retry.timeout.connect(self._start)
        self.idle=QTimer(self);self.idle.setSingleShot(True);self.idle.setInterval(180000)
        self.idle.timeout.connect(self._release_idle)
        self.process.finished.connect(self._exited)
        self.process.errorOccurred.connect(self._error)

    def ensure(self):
        if self.closed:return False
        self.wanted=True;self.idle.stop()
        if self.process.state()==QProcess.ProcessState.Running:return True
        if self.process.state()==QProcess.ProcessState.NotRunning and not self.retry.isActive() and self.attempts<3:self._start()
        return False

    def _start(self):
        if self.closed or not self.wanted:return
        self.recovering=False;self.process.start()

    def restart(self,message):
        if self.closed or self.recovering:return
        self.recovering=True;self.lost.emit(message)
        if self.process.state()!=QProcess.ProcessState.NotRunning:self.process.kill()
        else:self._schedule()

    def _error(self,error):
        if error==QProcess.ProcessError.FailedToStart:self.restart('Screen reader could not start.')

    def _exited(self,*_):
        if self.closed or not self.wanted:return
        if not self.recovering:
            self.recovering=True;self.lost.emit('Screen reader stopped.')
        self._schedule()

    def _schedule(self):
        if self.closed or not self.wanted or self.retry.isActive():return
        self.attempts+=1
        if self.attempts<=3:self.retry.start((100,500,1500)[self.attempts-1])
        else:self.lost.emit('Screen reader unavailable. Pause and resume reading to retry.')

    def accepted(self):
        self.attempts=0;self.recovering=False

    def pause(self):
        self.wanted=False;self.retry.stop();self.attempts=0;self.idle.start()

    def _release_idle(self):
        if not self.wanted and self.process.state()!=QProcess.ProcessState.NotRunning:self.process.kill()

    def close(self):
        self.closed=True;self.retry.stop();self.idle.stop();retire_process(self.process,1500)

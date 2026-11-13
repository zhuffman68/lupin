"""Retire only explicitly owned QProcesses, in parallel without blocking Qt."""
import time

from PySide6.QtCore import QCoreApplication, QProcess, QTimer
from shiboken6 import isValid

_retiring={}
_timer=None


def retire_process(process,grace_ms=200):
    global _timer
    if process is None or not isValid(process):return
    process.blockSignals(True)
    process.setParent(None)
    process.closeWriteChannel()
    if process.state()==QProcess.ProcessState.NotRunning:
        process.deleteLater();return
    _retiring[process]=time.monotonic()+grace_ms/1000
    if _timer is None or not isValid(_timer):
        _timer=QTimer(QCoreApplication.instance());_timer.setInterval(20);_timer.timeout.connect(_poll)
    _timer.start()


def _poll():
    now=time.monotonic()
    for process,deadline in list(_retiring.items()):
        if not isValid(process) or process.state()==QProcess.ProcessState.NotRunning:
            _retiring.pop(process,None)
            if isValid(process):process.deleteLater()
        elif now>=deadline:process.kill()
    if not _retiring and _timer is not None:_timer.stop()


def drain_retired():
    """After Qt exits, finish the already-parallel shutdown within one budget."""
    grace=time.monotonic()+.25
    for process in list(_retiring):
        if isValid(process):process.waitForFinished(max(0,round((grace-time.monotonic())*1000)))
    for process in list(_retiring):
        if isValid(process) and process.state()!=QProcess.ProcessState.NotRunning:process.kill()
    deadline=time.monotonic()+1
    for process in list(_retiring):
        if isValid(process):process.waitForFinished(max(0,round((deadline-time.monotonic())*1000)))
    _poll()

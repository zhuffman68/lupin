"""Retire only explicitly owned QProcesses, in parallel without blocking Qt."""
import atexit,time

from PySide6.QtCore import QCoreApplication, QProcess, QTimer
from shiboken6 import isValid

_retiring={}
_directories={}
_late_directories=set()
_timer=None


def _schedule():
    global _timer
    if _timer is None or not isValid(_timer):
        _timer=QTimer(QCoreApplication.instance());_timer.setInterval(20);_timer.timeout.connect(_poll)
    _timer.start()


def retire_process(process,grace_ms=200):
    if process is None or not isValid(process):return
    process.blockSignals(True)
    process.setParent(None)
    process.closeWriteChannel()
    if process.state()==QProcess.ProcessState.NotRunning:
        process.deleteLater();return
    _retiring[process]=time.monotonic()+grace_ms/1000
    _schedule()


def _clean_directory(directory):
    try:directory.cleanup()
    except OSError:
        # Keep the owned TemporaryDirectory alive for another final-drain/exit
        # attempt. A transient Windows file lock must not break GUI shutdown
        # or create an indefinitely polling cleanup timer.
        _late_directories.add(directory)
    else:_late_directories.discard(directory)


def retire_directory(directory,processes):
    """Keep temporary files until all explicitly supplied writers have exited."""
    _directories[directory]=tuple(process for process in processes if process is not None)
    _poll()
    if _retiring or _directories:_schedule()


def _drain_directories():
    for directory in list(_late_directories):_clean_directory(directory)


atexit.register(_drain_directories)


def _poll():
    now=time.monotonic()
    for process,deadline in list(_retiring.items()):
        if not isValid(process) or process.state()==QProcess.ProcessState.NotRunning:
            _retiring.pop(process,None)
            if isValid(process):process.deleteLater()
        elif now>=deadline:process.kill()
    for directory,processes in list(_directories.items()):
        if any(isValid(process) and process.state()!=QProcess.ProcessState.NotRunning for process in processes):continue
        _directories.pop(directory,None);_clean_directory(directory)
    if not _retiring and not _directories and _timer is not None and isValid(_timer):_timer.stop()


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
    _drain_directories()

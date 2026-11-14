"""Owned subprocesses release their temporary files before final cleanup."""
from pathlib import Path
import sys,tempfile,time,unittest
from PySide6.QtCore import QCoreApplication,QEvent,QProcess,QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid
from price_lens.process_lifecycle import retire_directory,retire_process,drain_retired
from price_lens.capture import PixelReader


class TemporaryProcessFilesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):self.processes=[]

    def tearDown(self):
        for process in self.processes:retire_process(process,0)
        drain_retired();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.app.processEvents()

    def child(self,directory,*,gate=False):
        process=QProcess();self.processes.append(process)
        process.setWorkingDirectory(directory.name)
        script="import pathlib,sys,time; f=open('held.txt','a'); print('ready',flush=True); sys.stdin.readline(); "
        if gate:script+="\nwhile not pathlib.Path('release').exists(): time.sleep(.01)\n"
        script+="\nf.close()\n"
        process.start(sys.executable,['-B','-c',script])
        self.assertTrue(process.waitForStarted(15000))
        self.assertTrue(process.waitForReadyRead(15000));self.assertIn(b'ready',bytes(process.readAllStandardOutput()))
        return process

    def until(self,predicate):
        deadline=time.monotonic()+15
        while not predicate() and time.monotonic()<deadline:QTest.qWait(5)
        self.assertTrue(predicate())

    def test_directory_stays_until_every_writer_exits_and_gui_remains_live(self):
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        first=self.child(directory);last=self.child(directory,gate=True)
        retire_process(first,20000);retire_process(last,20000)
        retire_directory(directory,[first,last])
        self.assertTrue(Path(directory.name).exists())
        heartbeats=[];QTimer.singleShot(0,lambda:heartbeats.append(True))
        self.until(lambda:bool(heartbeats) and (not isValid(first) or first.state()==QProcess.ProcessState.NotRunning))
        self.assertTrue(Path(directory.name).exists());self.assertEqual(last.state(),QProcess.ProcessState.Running)
        (Path(directory.name)/'release').touch();self.until(lambda:not Path(directory.name).exists())

    def test_reader_keeps_an_already_retiring_pickup_writer_until_it_exits(self):
        reader=PixelReader(Path(__file__).resolve().parents[1]);reader.timer.stop();self.addCleanup(reader.close)
        writer=self.child(reader.temp,gate=True)
        reader.temp_writers.append(writer);retire_process(writer,20000)
        path=Path(reader.temp.name);reader.close();reader.close()
        self.assertTrue(path.exists())
        (path/'release').touch();self.until(lambda:not path.exists())

    def test_stopped_writers_cleanup_immediately_and_transient_locks_retry_at_drain(self):
        directory=tempfile.TemporaryDirectory();retire_directory(directory,[])
        self.assertFalse(Path(directory.name).exists())
        class Locked:
            calls=0
            def cleanup(self):
                self.calls+=1
                if self.calls==1:raise PermissionError('controlled fixture lock')
        locked=Locked();retire_directory(locked,[]);self.assertEqual(locked.calls,1)
        drain_retired();self.assertEqual(locked.calls,2)

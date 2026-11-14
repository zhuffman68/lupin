"""Own annotation IPC and temporary helper failures, without capture or game input."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import tempfile
import textwrap
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication,QEvent,QProcess,Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QWidget
from shiboken6 import isValid
from price_lens import __version__
from price_lens.annotations import AnnotationWindow
from price_lens.overlay import Overlay

ROOT=Path(__file__).resolve().parents[1]
READY="print(json.dumps({'ready':True,'version':VERSION}),flush=True)\n"
READ_LOOP="""
for line in sys.stdin:
    try:
        state=json.loads(line)
        if 'rows' in state:
            print(json.dumps({'layout':[[1,2,20,10]] if state['rows'] else []}),flush=True)
    except ValueError:
        pass
"""


class FixtureProcess(QProcess):
    """Embedded Windows Python intentionally ignores cwd in its normal _pth.

    Add only our controlled temporary helper directory for these subprocess
    fixtures; production helpers keep their ordinary module launch unchanged.
    """
    def start(self,program,arguments,mode=QProcess.OpenModeFlag.ReadWrite):
        if arguments==['-B','-m','price_lens.annotations']:
            bootstrap="import os,runpy,sys;sys.path.insert(0,os.getcwd());runpy.run_module('price_lens.annotations',run_name='__main__')"
            arguments=['-B','-c',bootstrap]
        super().start(program,arguments,mode)


class OverlayRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen');cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.path=Path(self.folder.name)
        self.stack=ExitStack();self.stack.enter_context(patch('price_lens.overlay.cache_directory',return_value=self.path/'cache'))
        self.stack.enter_context(patch('price_lens.overlay.recovered_environment',return_value={}))
        self.overlays=[];self.messages=[];self.retry_delays=[]

    def tearDown(self):
        for overlay in self.overlays:overlay.close();overlay.deleteLater()
        from price_lens.process_lifecycle import drain_retired
        drain_retired()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.app.processEvents()
        self.stack.close();self.folder.cleanup()

    def helper(self,body):
        package=self.path/'helper'/'price_lens';package.mkdir(parents=True,exist_ok=True)
        (package/'__init__.py').write_text('__version__ = '+repr(__version__)+'\n')
        prefix='import json,sys\nfrom pathlib import Path\nVERSION='+repr(__version__)+'\n'
        (package/'annotations.py').write_text(prefix+textwrap.dedent(body))
        return package.parent

    def start(self,root,*,timeout_ms=4000,fast_retry=True):
        with patch('price_lens.overlay.QProcess',QProcess if Path(root)==ROOT else FixtureProcess):
            overlay=Overlay(root)
        self.overlays.append(overlay);overlay.startup_timer.setInterval(timeout_ms)
        def status(message):
            self.messages.append(message)
            if overlay.retry_timer.isActive():
                self.retry_delays.append(overlay.retry_timer.interval())
                if fast_retry:overlay.retry_timer.start(1)
        overlay.status.connect(status)
        # On Windows a nonexistent executable can fail synchronously inside the
        # constructor, before this listener exists. Observe its already-scheduled
        # first retry exactly once, then continue through the real Qt signals.
        if overlay.retry_timer.isActive():status('Restoring overlay labels…')
        return overlay

    def wait(self,predicate,timeout=4000):
        deadline=time.monotonic()+timeout/1000
        while not predicate() and time.monotonic()<deadline:QTest.qWait(10)
        self.assertTrue(predicate(),self.messages)

    def attempts(self):
        path=self.path/'helper'/'price_lens'/'attempts.txt'
        # The subprocess can be between opening and writing this tiny fixture.
        return int(path.read_text() or 0) if path.exists() else 0

    def failure(self):
        return json.loads((self.path/'cache'/'overlay-startup.json').read_text())

    def test_real_current_annotation_helper_acknowledges_version_and_layout(self):
        overlay=self.start(ROOT)
        self.assertFalse(overlay.ready);self.assertFalse(overlay.writer_available)
        self.wait(lambda:overlay.ready)
        self.assertTrue(overlay.writer_available)
        overlay.update([0,0,800,600],[dict(x=30,y=30,name='Fixture item',text='FM 1,000',key='fixture')])
        self.wait(lambda:bool(overlay.layout_boxes))
        self.assertTrue(all(len(box)==4 for box in overlay.layout_boxes))
        overlay.update([0,0,800,600],[])
        self.wait(lambda:not overlay.layout_boxes)
        self.assertFalse((self.path/'cache'/'overlay-startup.json').exists())
        overlay.close();self.assertFalse(overlay.ready)
        self.wait(lambda:not isValid(overlay.process) or overlay.process.state()==QProcess.ProcessState.NotRunning)

    def test_two_automatic_retries_then_manual_retry_restores_own_helper(self):
        root=self.helper("""
            counter=Path(__file__).with_name('attempts.txt')
            n=int(counter.read_text())+1 if counter.exists() else 1
            counter.write_text(str(n))
            print('SENSITIVE_CHAT_DRAFT /private/location '+('x'*4000),file=sys.stderr,flush=True)
            raise SystemExit(9)
        """)
        overlay=self.start(root,timeout_ms=15000)
        # Three sequential fixture launches each have their own bounded startup
        # deadline. Keep OS/Python cold start separate from the explicit exit
        # being injected. Production and real-canvas startup limits are unchanged.
        self.wait(lambda:self.attempts()==3 and overlay.process.state()==QProcess.ProcessState.NotRunning and not overlay.retry_timer.isActive(),timeout=45000)
        QTest.qWait(80);self.assertEqual(self.attempts(),3);self.assertFalse(overlay.ready)
        self.assertEqual(self.retry_delays,[500,1000])
        data=self.failure();self.assertEqual(data['reason'],'unexpected-exit');self.assertEqual(data['exit_code'],9)
        self.assertEqual(data['retries'],2);self.assertEqual(set(data),{'at','version','reason','exit_code','retries'})
        self.assertNotIn('SENSITIVE',(self.path/'cache'/'overlay-startup.json').read_text());self.assertLessEqual(len(overlay.last_error),3000)
        self.assertIn('could not start',self.messages[-1])
        self.helper("""
counter=Path(__file__).with_name('attempts.txt');counter.write_text(str(int(counter.read_text())+1))
"""+READY+READ_LOOP)
        overlay.retry();self.wait(lambda:overlay.ready,timeout=15000)
        self.assertEqual(self.attempts(),4);self.assertEqual(overlay.retries,0);self.assertTrue(overlay.writer_available)

    def test_busy_pipe_keeps_only_latest_state_and_does_not_resend_identical_rows(self):
        overlay=self.start(self.helper(READY+READ_LOOP));self.wait(lambda:overlay.ready)
        with patch.object(overlay.process,'bytesToWrite',return_value=4096) as queued,patch.object(overlay.process,'write') as write:
            for text in ('First','Obsolete','Latest'):
                overlay.update([0,0,800,600],[dict(name='Fixture',text=text,x=1,y=2,key='own')])
            write.assert_not_called();self.assertTrue(overlay.state_pending)
            queued.return_value=0;overlay.flush_labels()
            self.assertEqual(write.call_count,1)
            self.assertEqual(json.loads(bytes(write.call_args.args[0]))['rows'][0]['text'],'Latest')
            overlay.update([0,0,800,600],[dict(name='Fixture',text='Latest',x=1,y=2,key='own')])
            self.assertEqual(write.call_count,1);self.assertFalse(overlay.state_pending)

    def test_numeric_paint_acknowledgement_comes_from_real_canvas(self):
        overlay=self.start(ROOT);self.wait(lambda:overlay.ready)
        overlay.diagnostics=True;overlay.capture_at=time.monotonic();reports=[];overlay.painted.connect(reports.append)
        overlay.update([0,0,800,600],[dict(name='Fixture',text='1,000',x=30,y=30,key='own')])
        self.wait(lambda:bool(reports))
        report=reports[-1];self.assertEqual(report['id'],overlay.presentation_id)
        self.assertEqual(report['captured_at'],overlay.capture_at)
        self.assertGreaterEqual(report['painted_at'],report['sent_at'])
        self.assertNotIn('Fixture',json.dumps(report))

    def test_unchanged_prices_stay_visible_and_stopped_authorization_still_expires(self):
        overlay=self.start(self.helper(READY+READ_LOOP));self.wait(lambda:overlay.ready)
        canvas=AnnotationWindow(start_listener=False);clock=[100.0];messages=[]
        def deliver(data):
            messages.append(json.loads(bytes(data)));canvas.read_command(bytes(data));return len(data)
        try:
            overlay.reduce_motion=True
            rows=[dict(x=30,y=30,name='Fixture',text='1,000',key='own',kind='shop')]
            with patch('price_lens.overlay.time.monotonic',side_effect=lambda:clock[0]),\
                    patch.object(overlay.process,'bytesToWrite',return_value=0),\
                    patch.object(overlay.process,'write',side_effect=deliver):
                overlay.update([0,0,800,600],rows);active=canvas.rows[0]
                for second in range(1,9):
                    clock[0]=100.0+second
                    overlay.update([0,0,800,600],rows);canvas.expire()
                    self.assertTrue(canvas.isVisible());self.assertIs(canvas.rows[0],active)
                self.assertEqual(sum('rows' in m for m in messages),1)
                self.assertTrue(all(m=={'heartbeat':True} for m in messages[1:]))
                self.assertEqual(overlay.presentation_id,1)
                clock[0]+=6;canvas.expire();self.assertFalse(canvas.isVisible())
                overlay.update([0,0,800,600],rows);self.assertTrue(canvas.isVisible())
                overlay.update([0,0,800,600],[]);self.assertFalse(canvas.isVisible())
                clock[0]+=2;overlay.update([0,0,800,600],[]);self.assertFalse(canvas.isVisible())
        finally:
            canvas.close();canvas.deleteLater()

    def test_transient_exit_replays_only_saved_annotation_state_to_new_helper(self):
        root=self.helper("""
counter=Path(__file__).with_name('attempts.txt');n=int(counter.read_text())+1 if counter.exists() else 1;counter.write_text(str(n))
if n==1:raise SystemExit(7)
"""+READY+READ_LOOP)
        overlay=self.start(root,timeout_ms=15000);overlay.update([0,0,800,600],[dict(name='Own fixture',text='100',x=1,y=2,key='own')])
        self.wait(lambda:overlay.ready and bool(overlay.layout_boxes),timeout=30000)
        self.assertEqual(self.attempts(),2);self.assertEqual(overlay.layout_boxes,[[1,2,20,10]])
        self.assertEqual(overlay.retries,1);self.assertEqual(self.messages[-1],'')

    def test_wrong_version_never_becomes_ready_and_recovery_is_bounded(self):
        overlay=self.start(self.helper("VERSION='wrong-version'\n"+READY+READ_LOOP),timeout_ms=15000)
        self.wait(lambda:overlay.retries==2 and not overlay.retry_timer.isActive() and overlay.process.state()==QProcess.ProcessState.NotRunning,timeout=45000)
        self.assertFalse(overlay.ready);self.assertFalse(overlay.writer_available)
        self.assertEqual(self.failure()['reason'],'version-mismatch')

    def test_silent_helper_times_out_without_a_false_success(self):
        overlay=self.start(self.helper('import time\ntime.sleep(10)\n'),timeout_ms=80)
        self.wait(lambda:overlay.retries==2 and not overlay.retry_timer.isActive() and overlay.process.state()==QProcess.ProcessState.NotRunning)
        self.assertFalse(overlay.ready);self.assertEqual(self.failure()['reason'],'startup-timeout')

    def test_close_cancels_scheduled_retries_and_manual_retry_is_ignored(self):
        overlay=self.start(self.helper('raise SystemExit(4)\n'),fast_retry=False)
        self.wait(lambda:overlay.retry_timer.isActive())
        overlay.close();self.assertFalse(overlay.retry_timer.isActive());self.assertFalse(overlay.startup_timer.isActive())
        QTest.qWait(550);overlay.retry();QTest.qWait(50)
        self.wait(lambda:not isValid(overlay.process) or overlay.process.state()==QProcess.ProcessState.NotRunning);self.assertFalse(overlay.ready)

    def test_failed_to_start_is_bounded_and_records_only_a_fixed_reason(self):
        root=self.helper(READY+READ_LOOP)
        with patch('price_lens.overlay.sys.executable',str(self.path/'missing-fixture-python')):
            overlay=self.start(root)
            self.wait(lambda:overlay.retries==2 and not overlay.retry_timer.isActive() and overlay.process.state()==QProcess.ProcessState.NotRunning)
        self.assertFalse(overlay.ready);self.assertEqual(self.retry_delays,[500,1000])
        self.assertEqual(self.failure()['reason'],'start-failed')
        self.assertNotIn('missing-fixture-python',(self.path/'cache'/'overlay-startup.json').read_text())

    def test_malformed_reports_do_not_replace_versioned_ready_proof(self):
        body="print('not json',flush=True)\nprint('[]',flush=True)\nprint(json.dumps({'ready':1,'version':VERSION}),flush=True)\n"+READY+READ_LOOP
        overlay=self.start(self.helper(body));self.wait(lambda:overlay.ready)
        self.assertEqual(overlay.retries,0);self.assertFalse((self.path/'cache'/'overlay-startup.json').exists())

    def test_canvas_stays_hidden_when_empty_and_never_grabs_input(self):
        canvas=AnnotationWindow(start_listener=False)
        try:
            self.assertFalse(canvas.isVisible());self.assertIsNone(canvas.writer.window)
            for flag in (Qt.WindowType.WindowTransparentForInput,Qt.WindowType.WindowDoesNotAcceptFocus):self.assertTrue(canvas.windowFlags()&flag)
            self.assertTrue(canvas.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))
            self.assertTrue(canvas.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating))
            canvas.read_command(json.dumps(dict(geometry=[0,0,800,600],reduce_motion=True,rows=[dict(x=20,y=20,name='Own fixture',text='100',key='own')])).encode())
            self.assertTrue(canvas.isVisible());self.assertIsNone(canvas.writer.window)
            self.assertIsNone(QWidget.keyboardGrabber());self.assertIsNone(QWidget.mouseGrabber())
            canvas.read_command(json.dumps(dict(geometry=[0,0,800,600],reduce_motion=True,rows=[])).encode())
            self.assertFalse(canvas.isVisible());self.assertIsNone(canvas.writer.window)
        finally:canvas.close();canvas.deleteLater()


if __name__=='__main__':unittest.main()

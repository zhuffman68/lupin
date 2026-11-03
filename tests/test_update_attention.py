"""Exercise update reminder pixels/lifecycle; direct runs use a private desktop."""
import os
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from PySide6.QtCore import QAbstractAnimation,QCoreApplication,QEvent,Qt
from PySide6.QtGui import QColor,QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QVBoxLayout,QWidget
from shiboken6 import isValid

from price_lens.update_attention import UpdateSettingsButton
import test_ui_context as ui_context
from test_updates import offer


class PaintProbe(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.paints=[];self.layouts=0

    def event(self,event):
        if event.type()==QEvent.Type.LayoutRequest:self.layouts+=1
        return super().event(event)

    def paintEvent(self,event):
        self.paints.append(event.region().boundingRect())
        painter=QPainter(self);painter.fillRect(event.rect(),QColor('#171c25'))


class UpdateAttentionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.app.setProperty('reduceMotion',False)
        self.window=PaintProbe();self.window.resize(420,280)
        layout=QVBoxLayout(self.window)
        self.button=UpdateSettingsButton(self.window);self.button.setObjectName('ghost')
        self.button.setStyleSheet('QPushButton {background:transparent;border:1px solid transparent;'
            'border-radius:7px;color:#b4c0d0;padding:5px 8px;min-height:16px;font-size:12px;}')
        layout.addWidget(self.button,0,Qt.AlignmentFlag.AlignRight)
        self.sibling=PaintProbe();layout.addWidget(self.sibling,1)
        self.window.show();self.app.processEvents()

    def tearDown(self):
        if isValid(self.window):self.window.close();self.window.deleteLater()
        self.app.setProperty('reduceMotion',False)
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.app.processEvents()

    def running(self):return self.button.animation.state()==QAbstractAnimation.State.Running

    def test_reminder_repeats_past_two_passes_and_status_refresh_does_not_restart_it(self):
        self.assertFalse(self.running())
        self.button.set_update_available(True);self.assertTrue(self.running())
        self.button.animation.setCurrentTime(4200)
        self.assertEqual(self.button.animation.currentLoop(),2)
        self.assertAlmostEqual(self.button.progress,.625)
        self.button.set_update_available({'manifest':{'version':'2.0.0'}})
        self.assertEqual(self.button.animation.currentTime(),4200)
        self.assertEqual(self.button.text(),'Settings · update')
        self.button.set_update_available(False)
        self.assertFalse(self.running());self.assertEqual(self.button.progress,0.0)
        self.assertEqual(self.button.text(),'Settings')

    def test_gold_rim_pulse_and_shimmer_render_and_reduced_motion_keeps_a_static_cue(self):
        self.button.set_update_available(True);self.app.processEvents()
        frames=[]
        for timestamp in (0,400,800,1200):
            self.button.animation.setCurrentTime(timestamp)
            frames.append(self.button.grab().toImage())
        self.assertEqual(len({bytes(frame.constBits()) for frame in frames}),4)
        # A gold rim stays present between sweeps; the shimmer travels inside it.
        for frame in frames:
            rim=frame.pixelColor(1,frame.height()//2)
            self.assertGreater(rim.red(),rim.blue())
        self.app.setProperty('reduceMotion',True);self.button.sync_motion()
        self.assertFalse(self.running());self.assertEqual(self.button.text(),'Settings · update')
        still=self.button.grab().toImage();QTest.qWait(50)
        self.assertEqual(still,self.button.grab().toImage())
        self.button.set_update_available(False)
        self.assertNotEqual(still,self.button.grab().toImage())

    def test_hidden_minimized_and_reduced_buttons_stop_frame_delivery_and_resume_when_visible(self):
        frames=[];self.button.animation.valueChanged.connect(frames.append)
        self.button.set_update_available(True);QTest.qWait(45)
        self.assertGreater(len(frames),1)
        for hide,show in ((self.window.hide,self.window.show),
                          (self.window.showMinimized,self.window.showNormal),
                          (self.button.hide,self.button.show)):
            hide();self.app.processEvents();self.assertFalse(self.running())
            count=len(frames);QTest.qWait(50);self.assertEqual(len(frames),count)
            show();self.app.processEvents();self.assertTrue(self.running())
        self.app.setProperty('reduceMotion',True);self.button.sync_motion()
        count=len(frames);QTest.qWait(50);self.assertEqual(len(frames),count)
        self.app.setProperty('reduceMotion',False);self.button.sync_motion()
        self.assertTrue(self.running())

    def test_an_update_found_while_hidden_or_reduced_does_not_start_a_deferred_animation(self):
        self.window.hide();self.button.set_update_available(True)
        self.assertFalse(self.running())
        self.app.setProperty('reduceMotion',True)
        self.window.show();self.app.processEvents();self.assertFalse(self.running())
        self.button.set_update_available(False)
        self.app.setProperty('reduceMotion',False);self.button.sync_motion()
        self.assertFalse(self.running())

    def test_animation_repaints_only_the_button_without_layout_or_sibling_paints(self):
        self.button.set_update_available(True);self.app.processEvents();self.app.processEvents()
        self.window.paints.clear();self.sibling.paints.clear();self.window.layouts=0
        geometry=self.button.geometry();sibling_geometry=self.sibling.geometry()
        for timestamp in (250,600,1100):
            self.button.animation.setCurrentTime(timestamp);self.app.processEvents()
        self.assertEqual(self.window.layouts,0);self.assertEqual(self.sibling.paints,[])
        self.assertEqual(self.button.geometry(),geometry)
        self.assertEqual(self.sibling.geometry(),sibling_geometry)
        for region in self.window.paints:self.assertTrue(geometry.contains(region),region)

    def test_destroying_the_owner_destroys_the_loop_and_stops_frame_delivery(self):
        frames=[];self.button.animation.valueChanged.connect(frames.append)
        self.button.set_update_available(True);QTest.qWait(25)
        animation=self.button.animation
        self.window.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.assertFalse(isValid(animation));self.assertFalse(isValid(self.button))
        count=len(frames);QTest.qWait(50);self.assertEqual(len(frames),count)


class UpdateAttentionUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):ui_context.ContextUiTests.setUpClass.__func__(cls)

    def setUp(self):ui_context.ContextUiTests.setUp(self)

    def tearDown(self):
        ui_context.ContextUiTests.tearDown(self);self.app.setProperty('reduceMotion',False)

    def test_service_updates_and_reduce_motion_control_the_real_settings_button(self):
        window=self.window;window.show();self.app.processEvents()
        button=window.settings_button
        self.assertIsInstance(button,UpdateSettingsButton)
        self.assertFalse(button.update_available)
        window.updates.offer=offer();window.updates.changed.emit()
        self.assertTrue(button.update_available)
        self.assertEqual(button.animation.state(),QAbstractAnimation.State.Running)
        button.animation.setCurrentTime(600);window.updates.changed.emit()
        self.assertEqual(button.animation.currentTime(),600)
        window.set_reduce_motion(True)
        self.assertEqual(button.animation.state(),QAbstractAnimation.State.Stopped)
        self.assertEqual(button.text(),'Settings · update')
        window.set_reduce_motion(False)
        self.assertEqual(button.animation.state(),QAbstractAnimation.State.Running)
        window.updates.offer=None;window.updates.changed.emit()
        self.assertEqual(button.animation.state(),QAbstractAnimation.State.Stopped)
        self.assertEqual(button.text(),'Settings')


if __name__=='__main__':
    from scripts.qa_common import qa_entrypoint
    qa_entrypoint(lambda:unittest.main(),__file__)

"""Drive only Lupin-owned viewports, with no capture or global input filter."""
import unittest

from PySide6.QtCore import QCoreApplication,QEvent,QPoint,QPointF,Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QAbstractItemView,QScrollArea,QWidget

from price_lens.smooth_scroll import SmoothListWidget,SmoothScrollArea


class SmoothScrollTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.views=[];self.app.setProperty('reduceMotion',False)

    def tearDown(self):
        for view in self.views:view.close();view.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.app.setProperty('reduceMotion',False)

    def view(self,kind=SmoothScrollArea):
        view=kind();view.resize(300,220);body=QWidget();body.setMinimumHeight(4000)
        view.setWidgetResizable(True);view.setWidget(body);self.views.append(view);view.show()
        self.app.processEvents();view.verticalScrollBar().setSingleStep(20)
        return view

    def wheel(self,view,angle=-120,*,pixel=0,inverted=False,phase=Qt.ScrollPhase.NoScrollPhase,modifiers=Qt.KeyboardModifier.NoModifier):
        viewport=view.viewport();point=viewport.rect().center()
        event=QWheelEvent(QPointF(point),QPointF(viewport.mapToGlobal(point)),QPoint(0,pixel),QPoint(0,angle),
            Qt.MouseButton.NoButton,modifiers,phase,inverted)
        QApplication.sendEvent(viewport,event)
        return event

    def test_wheel_moves_in_frames_then_stops_at_the_native_distance(self):
        smooth=self.view();native=self.view(QScrollArea)
        self.wheel(native);self.wheel(smooth)
        self.assertEqual(smooth.verticalScrollBar().value(),0)
        QTest.qWait(45)
        self.assertGreater(smooth.verticalScrollBar().value(),0)
        self.assertLess(smooth.verticalScrollBar().value(),native.verticalScrollBar().value())
        QTest.qWait(140)
        self.assertEqual(smooth.verticalScrollBar().value(),native.verticalScrollBar().value())
        self.assertEqual(smooth.smooth_wheel.animation.state(),smooth.smooth_wheel.animation.State.Stopped)

    def test_repeated_wheel_notches_accumulate_without_a_long_queue(self):
        smooth=self.view();native=self.view(QScrollArea)
        for _ in range(4):self.wheel(smooth);self.wheel(native);QTest.qWait(15)
        QTest.qWait(155)
        self.assertEqual(smooth.verticalScrollBar().value(),native.verticalScrollBar().value())
        self.wheel(smooth,120);QTest.qWait(155)
        self.assertLess(smooth.verticalScrollBar().value(),native.verticalScrollBar().value())

    def test_natural_wheel_direction_matches_qt_and_bounds_are_clamped(self):
        smooth=self.view();native=self.view(QScrollArea)
        for view in (smooth,native):view.verticalScrollBar().setValue(300);self.wheel(view,120,inverted=True)
        QTest.qWait(155)
        self.assertEqual(smooth.verticalScrollBar().value(),native.verticalScrollBar().value())
        bar=smooth.verticalScrollBar();bar.setValue(bar.maximum()-3);self.wheel(smooth)
        QTest.qWait(155);self.assertEqual(bar.value(),bar.maximum())
        event=self.wheel(smooth);self.assertFalse(event.isAccepted())

    def test_trackpad_pixels_and_gesture_phases_keep_native_movement(self):
        smooth=self.view();native=self.view(QScrollArea)
        for kwargs in ({'pixel':-13,'phase':Qt.ScrollPhase.ScrollUpdate},{'phase':Qt.ScrollPhase.ScrollUpdate}):
            for view in (smooth,native):view.verticalScrollBar().setValue(500);self.wheel(view,**kwargs)
            self.assertEqual(smooth.verticalScrollBar().value(),native.verticalScrollBar().value())
            self.assertEqual(smooth.smooth_wheel.animation.state(),smooth.smooth_wheel.animation.State.Stopped)

    def test_reduce_motion_is_immediate_and_programmatic_scroll_takes_over(self):
        smooth=self.view();self.app.setProperty('reduceMotion',True);self.wheel(smooth)
        bar=smooth.verticalScrollBar();self.assertGreater(bar.value(),0)
        self.assertEqual(smooth.smooth_wheel.animation.state(),smooth.smooth_wheel.animation.State.Stopped)
        self.app.setProperty('reduceMotion',False);self.wheel(smooth);QTest.qWait(30)
        bar.setValue(800);QTest.qWait(155);self.assertEqual(bar.value(),800)
        self.wheel(smooth);bar.sliderPressed.emit();value=bar.value();QTest.qWait(155)
        self.assertEqual(bar.value(),value)

    def test_hidden_view_stops_animation_and_lists_use_pixel_scrolling(self):
        smooth=self.view();self.wheel(smooth);QTest.qWait(30);smooth.hide()
        value=smooth.verticalScrollBar().value();QTest.qWait(155)
        self.assertEqual(smooth.verticalScrollBar().value(),value)
        self.assertEqual(smooth.smooth_wheel.animation.state(),smooth.smooth_wheel.animation.State.Stopped)
        listing=SmoothListWidget();self.views.append(listing)
        self.assertEqual(listing.verticalScrollMode(),QAbstractItemView.ScrollMode.ScrollPerPixel)


if __name__=='__main__':unittest.main()

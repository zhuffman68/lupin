"""Check rendered frames, live updates and released transient slide resources."""
import unittest
from PySide6.QtCore import QPoint,QRect,Qt,QCoreApplication,QEvent
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QWidget,QVBoxLayout,QLineEdit,QCheckBox
from price_lens.motion import AnimatedTabs,MotionLabel,RollingLabel
from price_lens.slide_surface import invalidate_surface


class Page(QWidget):
    def __init__(self,text):
        super().__init__();self.paints=0
        layout=QVBoxLayout(self);self.caption=MotionLabel(text)
        self.caption.setFixedSize(220,30);self.caption.setProperty('quietUpdates',True)
        layout.addWidget(self.caption);layout.addStretch()

    def paintEvent(self,event):self.paints+=1;super().paintEvent(event)


class SlideSurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.app.setProperty('reduceMotion',False)
        self.tabs=AnimatedTabs();self.tabs.resize(460,400)
        self.pages=[Page('First 10'),Page('Second 20'),Page('Third 30')]
        for index,page in enumerate(self.pages):self.tabs.addTab(page,str(index))
        self.tabs.show();self.app.processEvents()

    def tearDown(self):
        self.tabs.close();self.tabs.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def start(self,index=1):
        self.tabs.setCurrentIndex(index);self.tabs.animation.pause();self.tabs.animation.setCurrentTime(70)
        self.app.processEvents();self.tabs.surface.grab()

    def test_frames_reuse_pages_and_do_not_repaint_every_label_tree(self):
        self.start();self.tabs.surface.dirty.clear()
        before=[page.paints for page in self.pages]
        for clock in range(80,220,10):
            self.tabs.animation.setCurrentTime(clock);self.app.processEvents()
        counts=[page.paints-old for page,old in zip(self.pages,before)]
        self.assertLessEqual(sum(counts),2,counts)
        self.assertTrue(self.tabs.sliding);self.assertIsNotNone(self.tabs.surface)

    def test_partial_text_refresh_matches_the_actual_page_pixels(self):
        self.start();page=self.pages[1];surface=self.tabs.surface
        page.caption.setText('Changed 42')
        rect=QRect(page.caption.mapTo(page,QPoint()),page.caption.size())
        surface.capture(1,rect)
        self.assertEqual(surface.pictures[1].toImage(),page.grab().toImage())

    def test_a_live_number_roll_is_visible_in_the_cached_slide(self):
        value=RollingLabel('100');self.pages[1].layout().insertWidget(1,value)
        self.start();value.setText('101');value.animation.pause();value.animation.setCurrentTime(80)
        self.assertTrue(self.tabs.surface.dirty)
        self.tabs.surface.grab()
        self.assertEqual(self.tabs.surface.pictures[1].toImage(),self.pages[1].grab().toImage())

    def test_retargeting_keeps_the_visible_fraction_and_releases_idle_surfaces(self):
        self.start();fraction=self.tabs.scroll;surface=self.tabs.surface
        self.tabs.setCurrentIndex(2);self.tabs.animation.pause()
        self.assertAlmostEqual(self.tabs.scroll,fraction)
        self.assertIs(self.tabs.surface,surface)
        self.tabs.animation.resume();self.tabs.animation.setCurrentTime(260)
        self.assertIsNone(self.tabs.surface);self.assertFalse(surface.pictures);self.assertFalse(surface.nodes)
        self.assertTrue(self.tabs.stack.layout().isEnabled())
        self.assertFalse(any(getattr(page.caption,'_motion_surfaces',()) for page in self.pages))

    def test_native_controls_and_separate_dirty_regions_remain_live(self):
        page=self.pages[1];entry=QLineEdit('Before');check=QCheckBox('Enabled')
        page.layout().insertWidget(1,entry);page.layout().insertWidget(2,check)
        self.start();surface=self.tabs.surface;surface.dirty.clear()
        entry.setText('After');check.setChecked(True)
        self.assertTrue(surface.dirty)
        self.app.processEvents();surface.grab()
        self.assertEqual(surface.pictures[1].toImage(),page.grab().toImage())
        # Partial rolling updates retain disjoint regions rather than repainting
        # the otherwise unchanged area between distant fields.
        surface.dirty.clear()
        invalidate_surface(page.caption,QRect(0,0,10,10))
        invalidate_surface(check,QRect(0,0,10,10))
        region=surface.dirty[1]
        self.assertGreater(region.rectCount(),1)
        surface.capture(1,region)
        self.assertEqual(surface.pictures[1].toImage(),page.grab().toImage())

    def test_native_stack_does_not_hide_a_departing_page_before_capture(self):
        value=RollingLabel('100');self.pages[0].layout().insertWidget(1,value)
        self.app.processEvents()
        value.setText('101');value.animation.pause();value.animation.setCurrentTime(50)
        self.assertLess(value.roll.progress,1)
        self.start()
        self.assertLess(value.roll.progress,1)
        self.assertTrue(self.pages[0].isVisible())
        self.tabs.finish_slide()
        self.assertFalse(self.pages[0].isVisible())
        self.assertEqual(value.roll.progress,1)

    def test_control_tab_keeps_native_keyboard_navigation(self):
        self.pages[0].caption.setFocus()
        QTest.keyClick(self.pages[0].caption,Qt.Key.Key_Tab,Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.tabs.currentIndex(),1)
        QTest.keyClick(self.pages[1].caption,Qt.Key.Key_Backtab,
                       Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(self.tabs.currentIndex(),0)

    def test_departing_page_keeps_its_pixels_through_changes_and_child_hiding(self):
        self.start();surface=self.tabs.surface;before=surface.pictures[0].toImage()
        self.pages[0].caption.setText('Changed while departing');self.pages[0].caption.hide()
        self.pages[0].layout().addWidget(MotionLabel('New layout'))
        for clock in (100,150,210):
            self.tabs.animation.setCurrentTime(clock);self.app.processEvents();surface.grab()
            self.assertEqual(surface.pictures[0].toImage(),before)
        self.pages[1].caption.setText('Incoming remains live');surface.grab()
        self.assertEqual(surface.pictures[1].toImage(),self.pages[1].grab().toImage())

    def test_departure_capture_contains_the_visible_page_before_paint_is_disabled(self):
        before=self.pages[0].grab().toImage()
        self.start()
        self.assertEqual(self.tabs.surface.pictures[0].toImage(),before)

    def test_reversing_a_slide_promotes_the_target_to_its_current_live_data(self):
        self.start();surface=self.tabs.surface
        self.pages[0].caption.setText('Latest data')
        self.tabs.setCurrentIndex(0);self.tabs.animation.pause();self.app.processEvents();surface.grab()
        self.assertNotIn(0,surface.frozen);self.assertIn(1,surface.frozen)
        self.assertEqual(surface.pictures[0].toImage(),self.pages[0].grab().toImage())


if __name__=='__main__':unittest.main()

"""Selected and automatically read item cards resize through real intermediate frames."""
import unittest
from unittest.mock import patch
from PySide6.QtCore import QPoint
from PySide6.QtGui import QImage,QColor
from PySide6.QtTest import QTest
import test_ui_context as fixture


class ItemResizeMotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.ContextUiTests.setUpClass.__func__(cls)

    def setUp(self):
        fixture.ContextUiTests.setUp(self)
        self.app.setProperty('reduceMotion',False)
        self.window.resize(520,840);self.window.show();self.app.processEvents()

    def tearDown(self):fixture.ContextUiTests.tearDown(self)

    def selected(self):
        p=self.window.search_panel;p.query.setText('Example');p.choose_first();self.app.processEvents()
        card=p.price_view;card.tabs.finish_height();card.tabs.finish_slide();self.window.price_content.finish()
        self.app.processEvents();QTest.qWait(60);return card

    def test_selected_card_grows_and_shrinks_without_reflowing_the_target_page(self):
        card=self.selected();tabs=card.tabs;small=tabs.height();header_y=card.item_name.mapTo(card,QPoint()).y()
        tabs.setCurrentIndex(1);tabs.animation.pause();tabs.height_animation.pause()
        self.assertTrue(tabs.resizing);self.assertEqual(tabs.height(),small)
        target=tabs.target_height;self.assertGreater(target,small)
        page_size=tabs.currentWidget().size();heights=[]
        for ms in range(0,221,20):
            tabs.animation.setCurrentTime(min(ms,210));tabs.height_animation.setCurrentTime(ms);self.app.processEvents()
            heights.append(tabs.height())
            self.assertEqual(tabs.currentWidget().size(),page_size)
            self.assertGreaterEqual(tabs.stack.height(),page_size.height())
            self.assertEqual(card.item_name.mapTo(card,QPoint()).y(),header_y)
        self.assertEqual(heights,sorted(heights));self.assertGreater(len(set(heights)),5)
        tabs.finish_height();tabs.finish_slide();self.app.processEvents()
        self.assertEqual(tabs.height(),target)
        tabs.setCurrentIndex(0);tabs.animation.pause();tabs.height_animation.pause()
        self.assertEqual(tabs.height(),target)
        tabs.height_animation.setCurrentTime(110);self.app.processEvents()
        self.assertGreater(tabs.height(),small);self.assertLess(tabs.height(),target)
        tabs.finish_height();tabs.finish_slide()
        self.assertEqual(tabs.height(),small)

    def test_resize_retargets_from_the_visible_height_and_reduced_motion_is_immediate(self):
        card=self.selected();tabs=card.tabs;small=tabs.height()
        tabs.setCurrentIndex(1);tabs.animation.pause();tabs.height_animation.pause();tabs.height_animation.setCurrentTime(100)
        middle=tabs.height();tabs.setCurrentIndex(0);tabs.animation.pause();tabs.height_animation.pause()
        self.assertEqual(tabs.height(),middle);self.assertEqual(tabs.height_animation.startValue(),middle)
        tabs.finish_height();tabs.finish_slide()
        self.app.setProperty('reduceMotion',True);tabs.setCurrentIndex(1);self.app.processEvents()
        self.assertFalse(tabs.resizing);self.assertEqual(tabs.height(),tabs.target_height)
        self.assertEqual(tabs.height_animation.state(),tabs.height_animation.State.Stopped)

    def test_automatic_card_follows_one_resize_clock_without_a_late_height_jump(self):
        w=self.window;w.on_reading(fixture.ContextUiTests.reading(self,False));self.app.processEvents()
        card=next(card for key,card in w.card_views.items() if key[0] is True)
        w.card_area.finish();card.tabs.finish_height();self.app.processEvents();w.card_area.finish()
        tabs=card.tabs;old_tab=tabs.height();old_area=w.card_area.height()
        tabs.setCurrentIndex(1);tabs.animation.pause();tabs.height_animation.pause()
        for ms in (0,40,80,120,160,200):
            tabs.height_animation.setCurrentTime(ms);self.app.processEvents()
            self.assertEqual(w.card_area.height()-old_area,tabs.height()-old_tab)
            self.assertEqual(w.card_area.animation.state(),w.card_area.animation.State.Stopped)
        tabs.finish_height();tabs.finish_slide();self.app.processEvents()
        self.assertEqual(w.card_area.height()-old_area,tabs.height()-old_tab)

    def test_return_before_the_first_height_tick_cancels_the_obsolete_growth(self):
        card=self.selected();tabs=card.tabs;small=tabs.height()
        tabs.setCurrentIndex(1);tabs.animation.pause();tabs.height_animation.pause()
        self.assertTrue(tabs.resizing);self.assertEqual(tabs.height(),small)
        tabs.setCurrentIndex(0);tabs.animation.pause();self.app.processEvents()
        self.assertFalse(tabs.resizing);self.assertEqual(tabs.height(),small)
        self.assertEqual(tabs.target_height,small)
        tabs.finish_slide()
        self.assertEqual(tabs.height(),small)
        self.assertEqual(tabs.currentWidget().size(),tabs.stack.size())

    def test_opening_keeps_a_cached_thumbnail_in_the_full_card_reveal(self):
        image=QImage(16,16,QImage.Format.Format_ARGB32);image.fill(QColor('orange'))
        w=self.window;p=w.search_panel
        with patch.object(w.thumbnails,'image',return_value=image):
            p.query.setText('Example');p.choose_first()
        card=p.price_view
        self.assertEqual(card.thumbnail.alpha,1)
        self.assertEqual(card.thumbnail.animation.state(),card.thumbnail.animation.State.Stopped)
        self.assertIsNotNone(w.price_content.outgoing)
        self.assertEqual(w.price_content.animation.duration(),130)


if __name__=='__main__':unittest.main()

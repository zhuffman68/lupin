"""The retained item summary stays live without repainting through tab motion."""
from dataclasses import replace
import unittest
import numpy as np
from PySide6.QtCore import QObject,QEvent,QPoint,QRect,QCoreApplication,Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from price_lens.slide_surface import invalidate_surface
import test_item_card_reuse as fixture


class PaintCount(QObject):
    def __init__(self,parent):super().__init__(parent);self.count=0
    def eventFilter(self,widget,event):
        if event.type()==QEvent.Type.Paint:self.count+=1
        return False


class ItemSummaryMotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.ItemCardReuseTests.setUpClass.__func__(cls)

    def setUp(self):
        fixture.ItemCardReuseTests.setUp(self)
        w=self.window;w.resize(520,840)
        w.search_panel.select_observed(w.catalog.by_id[101],dict(name='First Hat'))
        w.search_panel.quote=w.quotes[101];w.search_panel.render();w.update_price_layout()
        self.app.processEvents();self.card=w.search_panel.price_view;self.summary=self.card.summary_card
        self.card.tabs.finish_slide();self.card.tabs.finish_height();w.price_content.finish()
        self.app.processEvents();QTest.qWait(60);self.app.processEvents()
        self.app.setProperty('reduceMotion',False)

    def tearDown(self):fixture.ItemCardReuseTests.tearDown(self)

    def begin(self,index=2):
        tabs=self.card.tabs;tabs.setCurrentIndex(index)
        tabs.animation.pause();tabs.height_animation.pause();self.app.processEvents()
        self.assertIsNotNone(self.summary.summary_surface)
        return tabs

    def pixels(self,widget,rect=None):
        image=widget.grab().toImage().convertToFormat(QImage.Format.Format_RGBA8888)
        if rect is not None:
            scale=image.devicePixelRatio();image=image.copy(round(rect.x()*scale),round(rect.y()*scale),
                round(rect.width()*scale),round(rect.height()*scale))
        raw=np.frombuffer(image.constBits(),dtype=np.uint8).reshape(image.height(),image.bytesPerLine())
        return raw[:,:image.width()*4].reshape(image.height(),image.width(),4).copy()

    def test_summary_pixels_remain_steady_during_growth_and_shrink(self):
        summary=self.summary;tabs=self.card.tabs
        top=summary.mapTo(self.window,QPoint());height=tabs.mapTo(summary,QPoint()).y()
        rect=QRect(top.x(),top.y(),summary.width(),height);before=self.pixels(self.window,rect)
        for destination in (2,0):
            self.begin(destination)
            for ms in (0,55,110,180):
                tabs.animation.setCurrentTime(ms)
                if tabs.resizing:tabs.height_animation.setCurrentTime(ms)
                self.app.processEvents()
                after=self.pixels(self.window,rect)
                # A premultiplied icon edge can round one channel differently
                # when composited; text positions/opacity must remain intact.
                self.assertLessEqual(np.abs(before.astype(int)-after.astype(int)).max(),1)
            tabs.finish_height();tabs.finish_slide();self.app.processEvents()
            self.assertIsNone(summary.summary_surface)
        self.assertEqual(tabs.animation.duration(),220);self.assertEqual(tabs.height_animation.duration(),220)

    def test_tab_resizing_does_not_repaint_the_unchanged_summary_every_frame(self):
        counter=PaintCount(self.window);self.summary.fields['name'].installEventFilter(counter)
        self.card.tabs.setCurrentIndex(2);QTest.qWait(280)
        self.assertLessEqual(counter.count,6)
        self.assertIsNone(self.summary.summary_surface)

    def test_a_quote_update_remains_visible_while_the_summary_surface_is_active(self):
        self.begin();surface=self.summary.summary_surface;part=self.summary.price_column
        crop=QRect(part.pos()-surface.pos(),part.size());before=self.pixels(surface,crop)
        quote=replace(self.window.quotes[101],price=54321)
        self.window.search_panel.accept_quote(101,quote)
        label=self.summary.fields['market'];label.animation.pause();label.animation.setCurrentTime(160)
        invalidate_surface(label);self.app.processEvents()
        self.assertIs(self.summary.summary_surface,surface)
        after=self.pixels(surface,crop)
        surface.hide()
        live=self.pixels(self.window,QRect(part.mapTo(self.window,QPoint()),part.size()))
        surface.show()
        self.assertFalse(np.array_equal(before,after))
        self.assertLessEqual(np.abs(after.astype(int)-live.astype(int)).max(),1)
        self.assertIn('54,321',label.text())

    def test_hidden_and_reduced_motion_cards_release_surfaces_and_observers(self):
        self.begin();surface=self.summary.summary_surface;name=self.summary.fields['name']
        self.assertTrue(getattr(name,'_motion_surfaces',()))
        self.app.setProperty('reduceMotion',True)
        self.card.tabs.move_pages(self.card.tabs.scroll)
        self.card.tabs.finish_height()
        self.assertIsNone(self.summary.summary_surface);self.assertTrue(surface.closed)
        self.assertFalse(any(ref() is surface for ref in getattr(name,'_motion_surfaces',())))
        self.app.setProperty('reduceMotion',False);self.begin(0)
        self.summary.hide();self.app.processEvents()
        self.assertIsNone(self.summary.summary_surface)
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def test_the_transient_surface_never_takes_mouse_input(self):
        self.begin()
        self.assertTrue(self.summary.summary_surface.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))
        item=self.summary.watch_button.item
        self.summary.watch_button.click();self.app.processEvents()
        self.assertIn(item.game_id,self.window.watchlist.ids)

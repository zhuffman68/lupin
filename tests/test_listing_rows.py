"""Large sighting replies stay bounded to visible painting and retain their data."""
from types import SimpleNamespace
import unittest

from PySide6.QtCore import Qt,QPointF
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication,QScrollArea,QWidget
from price_lens.listing_rows import ListingRow,ListingRows


class ListingRowsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.reduced=self.app.property('reduceMotion');self.app.setProperty('reduceMotion',False)

    def tearDown(self):self.app.setProperty('reduceMotion',self.reduced)

    def view(self,*,visible=True):
        area=QScrollArea();area.setWidgetResizable(True);area.resize(410,180)
        view=ListingRows();area.setWidget(view)
        def close():area.close();area.deleteLater();self.app.processEvents()
        self.addCleanup(close)
        if visible:area.show();self.app.processEvents()
        return area,view

    def rows(self,count=3):
        rows=[ListingRow(SimpleNamespace(seller=f'Seller {i}',place=f'CH 1 · FM {i+1}',
            location=f'Channel 1, FM {i+1}',price=15000+i*1000,quantity=1,stock=2,last_seen=1000)) for i in range(count)]
        for row in rows:row.update_age(1060)
        return rows

    def test_loaded_sightings_fade_and_lift_without_resizing_the_scroll_content(self):
        area,view=self.view();rows=self.rows();view.set_rows(rows)
        self.assertEqual(view.animation.duration(),220);self.assertTrue(view.revealing)
        view.animation.pause();view.animation.setCurrentTime(0)
        height=view.height();initial=view.grab().toImage()
        self.assertEqual(view.alpha,0);self.assertEqual(view.lift,8)
        view.animation.setCurrentTime(110);middle=view.grab().toImage()
        self.assertGreater(view.alpha,0);self.assertLess(view.alpha,1)
        self.assertGreater(view.lift,0);self.assertLess(view.lift,8)
        view.animation.setCurrentTime(220);final=view.grab().toImage()
        self.assertEqual(view.alpha,1);self.assertEqual(view.lift,0)
        self.assertNotEqual(initial,middle);self.assertNotEqual(middle,final)
        self.assertEqual(view.height(),height);self.assertIs(view.rows,rows)
        self.assertFalse(view.findChildren(QWidget));self.assertLessEqual(view.last_painted_count,3)

    def test_first_hidden_result_waits_until_show_and_cached_reopening_does_not_replay(self):
        area,view=self.view(visible=False);view.set_rows(self.rows())
        self.assertTrue(view.pending_reveal);self.assertEqual(view.animation.state(),view.animation.State.Stopped)
        area.show();self.app.processEvents()
        self.assertFalse(view.pending_reveal);self.assertTrue(view.revealing)
        self.assertEqual(view.animation.state(),view.animation.State.Running)
        area.hide();self.app.processEvents()
        self.assertEqual(view.animation.state(),view.animation.State.Stopped)
        self.assertEqual(view.alpha,1);self.assertEqual(view.lift,0)
        area.show();self.app.processEvents()
        self.assertEqual(view.animation.state(),view.animation.State.Stopped)

    def test_reduced_motion_and_pointer_hit_testing_follow_the_visible_rows(self):
        area,view=self.view();view.set_rows(self.rows())
        view.animation.pause();view.animation.setCurrentTime(0)
        def move(y):
            point=QPointF(10,y)
            event=QMouseEvent(QMouseEvent.Type.MouseMove,point,point,point,Qt.MouseButton.NoButton,Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier)
            self.app.sendEvent(view,event)
        move(3);self.assertEqual(view.toolTip(),'')
        move(12);self.assertEqual(view.toolTip(),'Channel 1, FM 1')
        self.app.setProperty('reduceMotion',True);view.advance(.5)
        self.assertEqual(view.animation.state(),view.animation.State.Stopped)
        self.assertEqual(view.alpha,1);self.assertEqual(view.lift,0)
        view.set_rows(self.rows(2));self.assertEqual(view.alpha,1)
        self.assertEqual(view.animation.state(),view.animation.State.Stopped)

    def test_hundred_sightings_paint_only_visible_rows_and_scroll_to_the_last(self):
        area=QScrollArea();area.setWidgetResizable(True);area.resize(410,180)
        view=ListingRows();area.setWidget(view)
        rows=[ListingRow(SimpleNamespace(seller=f'Seller {i}',place=f'CH 1 · FM {i%22+1}',
            location=f'Channel 1, FM {i%22+1}',price=123456+i,quantity=1,stock=2,last_seen=1000)) for i in range(100)]
        for row in rows:row.update_age(1060)
        try:
            view.set_rows(rows);area.show();self.app.processEvents();area.grab()
            self.assertLessEqual(view.last_painted_count,5)
            self.assertFalse(view.findChildren(QWidget))
            self.assertGreater(area.verticalScrollBar().maximum(),5000)
            area.verticalScrollBar().setValue(area.verticalScrollBar().maximum());self.app.processEvents();area.grab()
            self.assertLessEqual(view.last_painted_count,5)
            self.assertEqual(view.rows[-1].listing.seller,'Seller 99')
            old_height=view.height();view.refresh_ages(1061)
            self.assertEqual(view.height(),old_height)
        finally:area.close();area.deleteLater();self.app.processEvents()

    def test_visible_age_digits_keep_rolling_without_one_animation_per_sighting(self):
        area=QScrollArea();area.setWidgetResizable(True);area.resize(410,180)
        view=ListingRows();area.setWidget(view)
        row=ListingRow(SimpleNamespace(seller='Seller',place='CH 1 · FM 1',location='FM 1',
            price=10000,quantity=1,stock=None,last_seen=1000));row.update_age(1060)
        try:
            view.set_rows([row]);area.show();self.app.processEvents()
            view.refresh_ages(1120);view.digits.pause();view.digits.setCurrentTime(80)
            self.assertTrue(view.rolling);self.assertGreater(row.roll.progress,0);self.assertLess(row.roll.progress,1)
            held=row.roll.progress;view.refresh_ages(1120)
            self.assertEqual(row.roll.progress,held)
            area.hide();self.app.processEvents()
            self.assertEqual(row.roll.progress,1);self.assertFalse(view.rolling)
        finally:area.close();area.deleteLater();self.app.processEvents()


if __name__=='__main__':unittest.main()

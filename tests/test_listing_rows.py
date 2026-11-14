"""Large sighting replies stay bounded to visible painting and retain their data."""
from types import SimpleNamespace
import unittest

from PySide6.QtWidgets import QApplication,QScrollArea,QWidget
from price_lens.listing_rows import ListingRow,ListingRows


class ListingRowsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.reduced=self.app.property('reduceMotion');self.app.setProperty('reduceMotion',False)

    def tearDown(self):self.app.setProperty('reduceMotion',self.reduced)

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

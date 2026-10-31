"""Production Prices integration with generated icons and isolated UI fixtures."""
import time
import unittest

from PySide6.QtCore import QPoint,QRect
from PySide6.QtGui import QColor,QImage,QPainter

import test_ui_context as fixtures
from price_lens.domain import Catalog,Quote


class ShopIdentityUiTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.ContextUiTests.setUpClass.__func__)
    setUp = fixtures.ContextUiTests.setUp
    tearDown = fixtures.ContextUiTests.tearDown
    reading = fixtures.ContextUiTests.reading
    prepare_shop_description = fixtures.ContextUiTests.prepare_shop_description

    @staticmethod
    def icon(blue):
        image=QImage(24,25,QImage.Format.Format_RGBA8888);image.fill(QColor('transparent'))
        for y in range(2,23):
            for x in range(2,22):
                image.setPixelColor(x,y,QColor(30+x*3,50+y*4,180 if blue else 35))
        return image

    def blue_moon(self,*,both_images=True):
        w=self.window
        w.on_catalog(Catalog({'items':[
            dict(id=1041078,name='Blue Moon',category='Equipment',sub_category='Top',gender='female'),
            dict(id=1032011,name='Blue Moon',category='Equipment',sub_category='Earring')]}))
        images={1041078:self.icon(True)}
        if both_images:images[1032011]=self.icon(False)
        w.thumbnails.image=lambda identity:images.get(identity,QImage())
        painter=QPainter(w.reader.image);painter.drawImage(QPoint(306,223),images[1041078]);painter.end()
        result=self.reading(shop_hover=True)
        result['shop']['rows'][0].update(name='Blue Moon',tier='chaos',
            area=dict(x=340,y=220,width=162,height=35))
        now=time.time()
        w.quotes[1032011]=Quote(1032011,28888,now,now,20,'MesoWatch','https://meso.watch/','24h')
        w.service.requests.clear()
        return result,images

    def test_shop_top_never_receives_same_name_earring_quote(self):
        result,_=self.blue_moon();w=self.window;w.on_reading(result)
        self.assertEqual(w.rows[0]['_item_id'],1041078)
        self.assertEqual(w.service.visible,[1041078])
        self.assertNotIn(1032011,w.service.requests)
        self.assertNotIn('28,888',' '.join(row['text'] for row in w.overlay.rows))
        self.assertIsNone(w.catalog.resolve('Blue Moon'))

    def test_missing_competitor_image_stays_ambiguous_then_resolves_current_pixels(self):
        result,images=self.blue_moon(both_images=False);w=self.window;w.on_reading(result)
        self.assertNotIn('_item_id',w.rows[0])
        self.assertEqual(w.service.visible,[])
        self.assertTrue(any(row['text']=='FM • item ambiguous' for row in w.overlay.rows))
        images[1032011]=self.icon(False)
        w.on_shop_thumbnail(1032011)
        self.assertEqual(w.rows[0]['_item_id'],1041078)
        self.assertEqual(w.service.visible,[1041078])

    def test_delayed_thumbnail_cannot_identify_a_changed_row(self):
        result,images=self.blue_moon(both_images=False);w=self.window;w.on_reading(result)
        painter=QPainter(w.reader.image);painter.fillRect(340,220,162,35,QColor('red'));painter.end()
        images[1032011]=self.icon(False);w.on_shop_thumbnail(1032011)
        self.assertNotIn('_item_id',w.rows[0])
        self.assertEqual(w.service.visible,[])

    def test_delayed_thumbnail_can_identify_unchanged_icon_after_native_selection_recoloring(self):
        from PySide6.QtCore import QRect
        from test_shop_source import ShopSourceTests
        w=self.window;w.reader.image.fill(QColor('#cad5df'))
        result,images=self.blue_moon(both_images=False);w.on_reading(result)
        self.assertNotIn('_item_id',w.rows[0])
        w.reader.image=ShopSourceTests.selected(w.reader.image,QRect(340,220,162,35))
        images[1032011]=self.icon(False);w.on_shop_thumbnail(1032011)
        self.assertEqual(w.rows[0]['_item_id'],1041078)
        self.assertEqual(w.service.visible,[1041078])

    def test_browsing_priority_suppresses_focus_and_clone_then_revalidates_hover(self):
        w=self.window;self.prepare_shop_description()
        self.assertIsNotNone(w.shop_description)
        self.assertTrue(any(row.get('source_shop_key') for row in w.overlay.rows))
        w.shop_browsing.priority_until=time.monotonic()+1.5;w.render()
        self.assertFalse(any(row.get('source_shop_key') for row in w.overlay.rows))
        shops=[row for row in w.overlay.rows if row.get('kind')=='shop']
        self.assertTrue(shops);self.assertTrue(all(row['browsing_priority'] for row in shops))
        self.assertTrue(all(not record[2] for record in w.screen_card_structure))
        w.shop_browsing.priority_until=0;w.on_shop_browsing_changed()
        self.assertTrue(any(row.get('source_shop_key') for row in w.overlay.rows))
        self.assertTrue(w.screen_card_structure[0][2])

    def test_old_viewport_read_cannot_restore_cleared_shop_prices(self):
        w=self.window;result=self.reading(shop_hover=True);w.on_reading(result)
        self.assertTrue(w.rows)
        previous=w.shop_browsing.epoch
        w.shop_browsing.epoch+=1;w.shop_browsing.pending=True;w.on_shop_viewport_changed()
        self.assertEqual(w.rows,[]);self.assertEqual(w.shop_rows.rows,{})
        self.assertFalse(any(row.get('kind')=='shop' or row.get('source_shop_key') for row in w.overlay.rows))
        result['shopViewportEpoch']=previous;w.on_reading(result)
        self.assertEqual(w.rows,[])
        result['shopViewportEpoch']=w.shop_browsing.epoch;w.on_reading(result)
        self.assertTrue(w.rows);self.assertFalse(w.shop_browsing.pending)

    def test_idle_variant_failure_is_explicit_without_fictitious_check(self):
        w=self.window;w.service.lookup_reason=lambda item:'variant-mismatch'
        w.on_reading(self.reading(shop_hover=True))
        shops=[row for row in w.overlay.rows if row.get('kind')=='shop']
        self.assertEqual(shops[0]['text'],'FM • item variant unverified')
        self.assertNotIn('checking',' '.join(row['text'] for row in shops))

    def test_native_orange_selection_keeps_the_offer_without_starting_browsing(self):
        result,_=self.blue_moon();w=self.window
        def band(color):
            painter=QPainter(w.reader.image)
            painter.fillRect(QRect(340,220,162,35),QColor(color))
            painter.fillRect(QRect(350,224,110,7),QColor('black'))
            painter.fillRect(QRect(350,242,60,7),QColor('black'));painter.end()
        band('#cad5df');w.on_reading(result);epoch=w.shop_browsing.epoch
        band('#fba72e');w.reader.last_frame=time.monotonic();w.on_image(w.reader.image)
        self.assertEqual(w.rows[0]['_item_id'],1041078)
        self.assertEqual(w.rows[0]['price'],dict(quantity=1,mesos=100))
        self.assertEqual(w.shop_browsing.epoch,epoch)
        self.assertFalse(w.shop_browsing.active())

    def test_unknown_new_panel_cannot_establish_a_scroll_from_changed_row_pixels(self):
        result,_=self.blue_moon();w=self.window;w.on_reading(result)
        epoch=w.shop_browsing.epoch
        painter=QPainter(w.reader.image)
        painter.fillRect(QRect(360,210,130,150),QColor('#464b78'));painter.end()
        w.reader.last_frame=time.monotonic();w.on_image(w.reader.image)
        self.assertEqual(w.rows,[])
        self.assertEqual(w.shop_browsing.epoch,epoch)
        self.assertFalse(w.shop_browsing.active())


if __name__=='__main__':unittest.main()

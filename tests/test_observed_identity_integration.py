"""Observation identity remains tied to the current frame and shared status."""
import time
from types import SimpleNamespace
import unittest

from PySide6.QtCore import QPoint,QRect
from PySide6.QtGui import QColor,QPainter

import test_shop_ui_identity as shop_fixtures
import test_ui_context as fixtures
from price_lens.domain import Quote


class ObservedIdentityIntegrationTests(unittest.TestCase):
    setUpClass=classmethod(fixtures.ContextUiTests.setUpClass.__func__)
    setUp=fixtures.ContextUiTests.setUp
    tearDown=fixtures.ContextUiTests.tearDown
    reading=fixtures.ContextUiTests.reading
    icon=staticmethod(shop_fixtures.ShopIdentityUiTests.icon)
    blue_moon=shop_fixtures.ShopIdentityUiTests.blue_moon

    def test_new_icon_during_ocr_cannot_publish_submitted_frames_old_identity(self):
        result,images=self.blue_moon();w=self.window
        w.reader.submitted_image=w.reader.image.copy()
        painter=QPainter(w.reader.image)
        painter.fillRect(QRect(303,218,37,39),QColor('#171c25'))
        painter.drawImage(QPoint(306,223),images[1032011]);painter.end()
        result['shopViewportEpoch']=w.shop_browsing.epoch
        w.on_reading(result)
        self.assertFalse(any((item:=w.item_for(row)) and item.game_id==1041078 for row in w.rows),
                         'Current pixels show earrings, but an old submitted-frame top ID was published')

    def test_changed_listing_pixels_during_ocr_cannot_publish_old_asking_price(self):
        result,_=self.blue_moon();w=self.window
        w.reader.submitted_image=w.reader.image.copy()
        painter=QPainter(w.reader.image);painter.fillRect(QRect(340,220,162,35),QColor('red'));painter.end()
        result['shopViewportEpoch']=w.shop_browsing.epoch
        w.on_reading(result)
        self.assertFalse(any(row.get('price')=={'quantity':1,'mesos':100} for row in w.rows),
                         'The asking price belongs to pixels that changed before OCR completed')

    def test_new_current_frame_cannot_keep_same_name_old_icon_identity(self):
        result,images=self.blue_moon();w=self.window;w.on_reading(result)
        self.assertEqual(w.rows[0]['_item_id'],1041078)
        painter=QPainter(w.reader.image)
        painter.fillRect(QRect(303,218,37,39),QColor('#171c25'))
        painter.drawImage(QPoint(306,223),images[1032011]);painter.end()
        w.reader.last_frame=time.monotonic();w.on_image(w.reader.image)
        self.assertFalse(any((item:=w.item_for(row)) and item.game_id==1041078 for row in w.rows),
                         'An accepted old identity outlived the current icon pixels without a scrollbar change')

    def test_lost_shop_container_retires_live_offer_without_inventing_scroll(self):
        result,_=self.blue_moon();w=self.window;w.on_reading(result)
        epoch=w.shop_browsing.epoch
        self.assertTrue(w.shop_rows.rows)
        painter=QPainter(w.reader.image)
        painter.fillRect(QRect(290,190,275,325),QColor('#445566'));painter.end()
        w.reader.last_frame=time.monotonic();w.on_image(w.reader.image)
        self.assertFalse(any(row.get('price') for row in w.rows),
                         'A vanished shop container retained a live asking price')
        self.assertEqual(w.shop_browsing.epoch,epoch)
        self.assertTrue(w.shop_rows.rows,'Losing the visible container must preserve bounded recovery data')

    def test_old_cursor_occlusion_cannot_restore_a_changed_same_name_item_offer(self):
        result,images=self.blue_moon();w=self.window;w.reader.pointer=(315,230)
        result['pointerAtRead']=[315,230];w.on_reading(result)
        self.assertEqual(w.rows[0]['_item_id'],1041078)
        w.reader.submitted_image=w.reader.image.copy()
        painter=QPainter(w.reader.image)
        painter.fillRect(QRect(303,218,37,39),QColor('#171c25'))
        painter.drawImage(QPoint(306,223),images[1032011]);painter.end()
        w.reader.pointer=(580,600)
        # Only the icon changes, inside the previous cursor footprint. The
        # exposed name/price band alone cannot restore the old exact-ID offer.
        w.on_reading(result)
        self.assertFalse(any(row.get('_item_id')==1041078 and row.get('price') for row in w.rows),
                         'Name-band recovery restored an offer whose full item source was not current')

    def test_snapshot_update_does_not_reassign_a_current_icon_identity(self):
        result,_=self.blue_moon();w=self.window;w.on_reading(result)
        now=time.time()
        # The real PriceService delivers this explicit negative reference when
        # the top first enters visible demand; the fixture service only records.
        w.quotes[1041078]=Quote(1041078,None,now-1,None,0,'MesoWatch','','no data')
        w.service.snapshot=SimpleNamespace(meta={'checked_at':now,'published_at':now},rows={})
        w.service.reference=lambda item:Quote(item.game_id,None,now,None,0,'MesoWatch','','no data')
        w.service.lookup_reason=lambda item:'no-sales'
        w.on_price_state()
        self.assertEqual(w.rows[0]['_item_id'],1041078)
        self.assertEqual(w.quote_for(w.item_for(w.rows[0])).game_id,1041078)
        self.assertIsNone(w.quote_for(w.item_for(w.rows[0])).price)
        self.assertEqual(w.catalog.resolve('Blue Moon'),None)

    def test_recent_items_receive_context_id_without_converting_uncertainty_to_earrings(self):
        result,_=self.blue_moon();w=self.window;w.on_reading(result)
        self.assertIn(1041078,w.recent_items.entries)
        self.assertNotIn(1032011,w.recent_items.entries)
        self.assertEqual(w.recent_items.entries[1041078]['price'],{'quantity':1,'mesos':100})
        painter=QPainter(w.reader.image);painter.fillRect(QRect(303,218,37,39),QColor('red'));painter.end()
        w.on_reading(result)
        self.assertIsNone(w.item_for(w.rows[0]))
        self.assertNotIn(1032011,w.recent_items.entries)
        self.assertEqual(w.recent_items.entries[1041078]['price'],{'quantity':1,'mesos':100})

    def test_reason_only_service_update_reaches_existing_screen_card(self):
        w=self.window;current={'reason':'missing'}
        w.service.lookup_reason=lambda item:current['reason']
        w.on_reading(self.reading(shop_hover=True))
        card=next(card for card in w.card_views.values() if hasattr(card,'fields'))
        self.assertEqual(card.fields['status'].text(),'No market reference')
        current['reason']='variant-mismatch';w.on_price_state()
        self.assertTrue(any(row['text']=='FM • item variant unverified' for row in w.overlay.rows))
        self.assertEqual(card.fields['status'].text(),'Item variant unverified')


if __name__=='__main__':unittest.main()

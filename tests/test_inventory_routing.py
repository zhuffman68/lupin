"""Shop geometry cannot veto an independent inventory source in front of it."""
import json
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication,QEvent,QRect
from PySide6.QtGui import QColor,QImage
from PySide6.QtWidgets import QApplication

from price_lens.capture import PixelReader
from price_lens.inventory_probe import InventoryAbsence

ROOT=Path(__file__).resolve().parents[1]


class InventoryRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.reader=PixelReader(ROOT);self.reader.timer.stop();self.reader.auto_enabled=False
        self.reader.reader_process.ensure();self.assertTrue(self.reader.process.waitForStarted(3000))
        self.reader.image=QImage(900,700,QImage.Format.Format_RGBA8888);self.reader.image.fill(QColor('#24384b'))
        self.reader.tooltip_enabled=True;self.reader.pointer=(420,260)
        self.reader.shop_rect=self.reader.shop_context=QRect(350,200,199,350)
        self.reader.roi_clean=True;self.reader.last_frame=time.monotonic();self.reader.image_sequence=1

    def tearDown(self):
        self.reader.close();self.reader.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.app.processEvents()

    def request(self):
        with patch.object(self.reader.process,'write') as write:
            self.reader.scan()
        self.assertTrue(write.called,'Expected a fresh reader request')
        return json.loads(bytes(write.call_args.args[0]))

    def test_pointer_over_shop_rectangle_still_probes_for_a_front_inventory(self):
        request=self.request()
        self.assertTrue(request['tooltip'])
        self.assertTrue(request['inventory_only'])
        self.assertTrue(request['progressive_tooltip'])
        self.assertTrue(request['progressive_shop'])
        self.assertFalse(self.reader.using_roi)
        self.assertEqual(request['width'],900)

    def test_outside_shop_uses_normal_inventory_equipped_and_linked_item_reading(self):
        self.reader.pointer=(210,260)
        request=self.request();self.assertTrue(request['tooltip'])
        self.assertFalse(request.get('inventory_only',False))

    def test_disabled_inventory_reading_keeps_shop_only_requests(self):
        self.reader.tooltip_enabled=False
        request=self.request();self.assertFalse(request['tooltip'])
        self.assertFalse(request.get('inventory_only',False));self.assertTrue(self.reader.using_roi)

    def test_exact_negative_probe_skips_only_unchanged_source_search_pixels(self):
        reader=self.reader;reader.last_pointer=reader.pointer
        reader.shop_fingerprint=reader.fingerprint(reader.image,reader.shop_context)
        area=dict(x=30,y=0,width=600,height=260)
        reader.inventory_absence=InventoryAbsence.capture(dict(absent=True,area=area),reader.image,reader.pointer)
        self.assertIsNotNone(reader.inventory_absence)
        with patch.object(reader.process,'write') as write:reader.scan()
        write.assert_not_called()
        # A source header can be outside the shop table. Its new pixels must
        # invalidate the negative cache even if all shop pixels stay identical.
        reader.image.setPixelColor(310,110,QColor('white'));reader.image_sequence+=1
        request=self.request();self.assertTrue(request['inventory_only'])

    def test_negative_probe_cannot_cache_a_candidate_or_a_different_pointer(self):
        frame=self.reader.image;point=self.reader.pointer
        value=dict(absent=True,area=dict(x=20,y=0,width=600,height=260))
        proof=InventoryAbsence.capture(value,frame,point);self.assertIsNotNone(proof)
        self.assertTrue(proof.matches(QImage(frame),point));self.assertFalse(proof.matches(frame,(421,260)))
        self.assertIsNone(InventoryAbsence.capture({**value,'absent':False},frame,point))
        self.assertIsNone(InventoryAbsence.capture({**value,'area':dict(x=-1,y=0,width=600,height=260)},frame,point))
        self.assertIsNone(InventoryAbsence.capture({**value,'absent':1},frame,point))

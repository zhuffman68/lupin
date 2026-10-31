"""Late shop OCR cannot cross a captured viewport boundary."""
import json
from pathlib import Path
import time
import unittest
from dataclasses import replace
from unittest.mock import PropertyMock,patch

from PySide6.QtWidgets import QApplication

from price_lens.capture import PixelReader
from price_lens.reader_request import SubmittedRequest
from price_lens.platform_paths import reader_binary


ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(reader_binary(ROOT).is_file(),'existing reader binary required; never build in this suite')
class ShopViewportCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.reader=PixelReader(ROOT);self.reader.timer.stop()
        self.addCleanup(self.reader.close)
        self.reader.active_request=self.reader.submitted_request=SubmittedRequest('prices',self.reader.image,None,
            self.reader.image_sequence,self.reader.generation,time.monotonic(),shop_epoch=self.reader.shop_browsing.epoch)
        self.readings=[];self.reader.reading.connect(self.readings.append)

    def deliver(self,**fields):
        self.reader.buffer=json.dumps(dict(atMs=int(time.monotonic()*1000),shop=None,tooltip=None,**fields)).encode()+b'\n'
        self.reader.on_output()

    def test_late_shop_result_is_discarded_after_viewport_changes(self):
        previous=self.reader.image_sequence
        self.reader.shop_browsing.reset()
        self.deliver()
        self.assertEqual(self.readings,[])
        self.assertGreater(self.reader.image_sequence,previous)
        self.assertIsNone(self.reader.shop_fingerprint)

    def test_current_result_carries_its_viewport_epoch(self):
        self.deliver()
        self.assertEqual(len(self.readings),1)
        self.assertEqual(self.readings[0]['shopViewportEpoch'],self.reader.shop_browsing.epoch)

    def test_shop_change_does_not_discard_independent_exp_reply(self):
        self.reader.experience_enabled=True
        self.reader.active_request=replace(self.reader.active_request,mode='experience',shop_epoch=None,
            tracking_epoch=self.reader.tracking_epoch)
        self.reader.shop_browsing.reset()
        results=[];self.reader.experience.connect(results.append)
        with patch.object(PixelReader,'tracking_ready',new_callable=PropertyMock,return_value=True):
            self.deliver(experience={'level':32,'percent':64.0})
        self.assertEqual(len(results),1)
        self.assertEqual(results[0]['experience']['level'],32)
        self.assertEqual(self.readings,[])


if __name__=='__main__':unittest.main()

"""A late shop viewport cannot suppress independently proven inventory pixels."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication,QEvent,QRect
from PySide6.QtGui import QColor,QImage,QPainter
from PySide6.QtWidgets import QApplication

from price_lens.capture import PixelReader
from price_lens.platform_paths import reader_binary
from price_lens.reader_request import SubmittedRequest

ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(reader_binary(ROOT).is_file(),'existing reader binary required; never build in this suite')
class InventoryCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.reader=PixelReader(ROOT);self.reader.timer.stop();self.reader.auto_enabled=False
        self.assertTrue(self.reader.process.waitForStarted(3000))
        self.frame=QImage(800,600,QImage.Format.Format_RGBA8888);self.frame.fill(QColor('#24384b'))
        painter=QPainter(self.frame)
        for x in (60,74,88,104,121):painter.fillRect(x,113,2,6,QColor('white'))
        painter.end()
        reader=self.reader;reader.image=self.frame.copy()
        reader.pointer=reader.last_pointer=(340,190)
        reader.image_sequence=3;reader.submitted_sequence=1
        self.request=SubmittedRequest('prices',self.frame,(340,190),1,reader.generation,time.monotonic(),
            shop_epoch=reader.shop_browsing.epoch)
        reader.shop_browsing._advance()
        reader.shop_rect=QRect(500,300,199,260);reader.shop_context=QRect(498,298,203,264)
        reader.shop_fingerprint=b'current verified page';reader.roi_clean=False
        self.result={'atMs':int(self.request.started_at*1000),
            'shop':{'area':dict(x=400,y=280,width=199,height=260),
                    'rows':[dict(name='Old shop item',price={'quantity':1,'mesos':999},
                                 area=dict(x=437,y=280,width=162,height=35))]},
            'hover':{'tooltip':{'found':{'name':'Old shop item'}}},
            'tooltip':{'found':{'name':'Example Hat','area':dict(x=58,y=111,width=180,height=12)}},
            'tooltipAssociation':{'state':'inventory-primary','token':'context:slot',
                'source':dict(x=300,y=150,width=230,height=300),
                'slot':dict(x=324,y=174,width=36,height=36),
                'panel':dict(x=50,y=100,width=240,height=330),
                'guards':[dict(x=300,y=150,width=230,height=20)]}}
        self.readings=[];reader.reading.connect(self.readings.append)

    def tearDown(self):
        self.reader.close();self.reader.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.app.processEvents()

    def deliver(self,result=None,request=None):
        reader=self.reader;request=self.request if request is None else request
        reader.active_request=reader.submitted_request=request
        message=(json.dumps(self.result if result is None else result)+'\n').encode()
        with patch('price_lens.capture.QTimer.singleShot'),patch.object(reader.process,'readAllStandardOutput',return_value=message):
            reader.on_output()

    def assert_current_shop_untouched(self):
        reader=self.reader
        self.assertEqual(reader.shop_rect,QRect(500,300,199,260))
        self.assertEqual(reader.shop_context,QRect(498,298,203,264))
        self.assertEqual(reader.shop_fingerprint,b'current verified page')
        self.assertFalse(reader.roi_clean)

    def test_old_shop_epoch_keeps_fresh_inventory_proof_and_scrubs_every_old_shop_field(self):
        self.deliver()
        self.assertEqual(len(self.readings),1);result=self.readings[0]
        self.assertTrue(result['_shop_stale']);self.assertIsNone(result['shop']);self.assertIsNone(result['hover'])
        self.assertEqual(result['shopViewportEpoch'],self.request.shop_epoch)
        self.assertNotEqual(result['shopViewportEpoch'],self.reader.shop_browsing.epoch)
        self.assertEqual(result['tooltip']['found']['name'],'Example Hat')
        self.assertIs(result['_submitted_request'],self.request)
        self.assertIs(result['_tooltip_context'],self.reader.tooltip_association)
        self.assertIsNotNone(self.reader.tooltip_fingerprint)
        self.assertEqual(result['pointerAtRead'],[340,190]);self.assertEqual(self.reader.pointer,(340,190))
        self.assertTrue(self.reader.rescan_requested);self.assert_current_shop_untouched()

    def test_changed_inventory_cell_header_or_title_is_still_rejected_with_an_old_shop_epoch(self):
        for point in ((326,176),(310,155),(60,113)):
            with self.subTest(point=point):
                self.reader.image=self.frame.copy();self.reader.image.setPixelColor(*point,QColor('red'))
                self.deliver();result=self.readings[-1]
                self.assertEqual(result['tooltipAssociation']['state'],'rejected')
                self.assertIsNone(result['tooltip']['found']);self.assertIsNone(result['_tooltip_context'])
                self.assertIsNone(self.reader.tooltip_association);self.assertIsNone(self.reader.tooltip_fingerprint)
                self.assert_current_shop_untouched()

    def test_moving_to_another_cell_cannot_keep_the_late_inventory_item(self):
        self.reader.pointer=(376,190);self.deliver()
        self.assertEqual(self.readings[-1]['tooltipAssociation']['state'],'rejected')
        self.assertIsNone(self.readings[-1]['tooltip']['found'])
        self.assertEqual(self.reader.pointer,(376,190));self.assert_current_shop_untouched()

    def test_incomplete_old_shop_roi_does_not_block_independent_inventory_proof(self):
        result=deepcopy(self.result);result['shop']['rows'][0].update(name=None,price=None)
        self.deliver(result,replace(self.request,using_roi=True))
        self.assertEqual(self.readings[-1]['tooltip']['found']['name'],'Example Hat')
        self.assert_current_shop_untouched()

    def test_normal_independent_title_keeps_its_submitted_source_for_ui_validation(self):
        result=deepcopy(self.result);result.update(hover=None,tooltipAssociation={'state':'normal'})
        self.deliver(result)
        self.assertEqual(self.readings[-1]['tooltip']['found']['name'],'Example Hat')
        self.assertIs(self.readings[-1]['_submitted_request'],self.request)
        self.assert_current_shop_untouched()

    def test_scrubbing_old_shop_hover_cannot_promote_its_description_to_inventory(self):
        result=deepcopy(self.result);result['tooltipAssociation']={'state':'normal'}
        self.deliver(result)
        self.assertEqual(self.readings,[]);self.assertTrue(self.reader.rescan_requested)
        self.assert_current_shop_untouched()

    def test_shop_only_miss_cannot_clear_an_existing_inventory_cache(self):
        self.deliver();proof=self.reader.tooltip_association;fingerprint=self.reader.tooltip_fingerprint
        self.readings.clear();result=deepcopy(self.result);result['tooltip']=None;result.pop('tooltipAssociation')
        self.deliver(result)
        self.assertEqual(self.readings,[])
        self.assertIs(self.reader.tooltip_association,proof);self.assertEqual(self.reader.tooltip_fingerprint,fingerprint)
        self.assert_current_shop_untouched()

    def test_explicit_native_rejection_is_not_hidden_by_stale_shop_filtering(self):
        result=deepcopy(self.result);result.update(tooltip=None,tooltipAssociation={'state':'rejected'})
        self.deliver(result)
        self.assertEqual(self.readings[-1]['tooltipAssociation']['state'],'rejected')
        self.assertIsNone(self.readings[-1]['tooltip']['found']);self.assert_current_shop_untouched()

    def test_rescan_preserves_current_shop_and_active_deadline_without_sending_work(self):
        reader=self.reader;reader.active_request=reader.submitted_request=self.request
        before=self.request.deadline_at
        with patch('price_lens.capture.QTimer.singleShot') as queued,patch.object(reader.process,'write') as send:
            reader.request_rescan(preserve_shop_cache=True)
        self.assertIs(reader.active_request,self.request);self.assertEqual(self.request.deadline_at,before)
        self.assertEqual(reader.pending_since,self.request.started_at)
        self.assertTrue(reader.rescan_requested);self.assert_current_shop_untouched()
        queued.assert_called_once_with(0,reader.scan);send.assert_not_called()

    def test_capture_generation_change_still_discards_all_old_source_authority(self):
        self.reader.generation+=1;self.deliver()
        self.assertEqual(self.readings,[]);self.assertIsNone(self.reader.tooltip_association)
        self.assert_current_shop_untouched()


if __name__=='__main__':unittest.main()

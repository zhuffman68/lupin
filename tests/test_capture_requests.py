"""Production request scheduling with mocked transport; no reader or capture."""
from types import MethodType,SimpleNamespace
import unittest
from unittest.mock import Mock,patch

from price_lens.capture import PixelReader
from price_lens.ui import LensWindow
from price_lens.reader_request import SubmittedRequest
from price_lens.price_observations import PriceObservations
from PySide6.QtGui import QImage,QColor


class CaptureRequestTests(unittest.TestCase):
    def pending_reader(self):
        request=SubmittedRequest('prices',QImage(),None,1,0,100,shop_epoch=0)
        reader=SimpleNamespace(paused=False,experience_enabled=False,pickup_worker=None,pending=True,
            pending_since=100.0,process=Mock(),status=SimpleNamespace(emit=Mock()),shop_fingerprint=b'known',
            image_sequence=1,rescan_requested=False,active_request=request)
        reader.scan=MethodType(PixelReader.scan,reader)
        reader.request_rescan=MethodType(PixelReader.request_rescan,reader)
        return reader

    def test_retiring_shop_during_native_ocr_preserves_the_active_timeout(self):
        reader=self.pending_reader()
        window=SimpleNamespace(reader=reader,observations=PriceObservations())
        with patch('price_lens.capture.QTimer.singleShot') as queued,patch('price_lens.capture.time.monotonic',return_value=101):
            LensWindow.retire_shop_source(window)
            reader.scan()
        self.assertEqual(reader.pending_since,100)
        self.assertTrue(reader.pending);self.assertTrue(reader.rescan_requested)
        self.assertEqual(reader.image_sequence,2)
        reader.process.kill.assert_not_called();reader.status.emit.assert_not_called()
        queued.assert_called_once_with(0,reader.scan)

    def test_rescan_requests_do_not_hide_a_real_native_reader_timeout(self):
        reader=self.pending_reader()
        with patch('price_lens.capture.QTimer.singleShot'),patch('price_lens.capture.time.monotonic',return_value=126):
            reader.request_rescan();reader.scan()
        reader.process.kill.assert_called_once_with()
        self.assertIn('timed out',reader.status.emit.call_args.args[0])

    def test_submitted_frame_pointer_context_and_deadline_are_a_single_snapshot(self):
        frame=QImage(30,20,QImage.Format.Format_RGBA8888);frame.fill(QColor('blue'))
        request=SubmittedRequest('prices',frame,(10,12),7,3,100,shop_epoch=8,crop=(2,3,20,10))
        frame.fill(QColor('red'))
        self.assertEqual(request.source_image().pixelColor(0,0),QColor('blue'))
        self.assertEqual(request.pointer,(10,12));self.assertEqual(request.deadline_at,125)
        self.assertEqual((request.sequence,request.generation,request.shop_epoch),(7,3,8))

    def test_tracking_request_carries_its_own_epoch_and_analysis_origin(self):
        frame=QImage(30,20,QImage.Format.Format_RGBA8888);frame.fill(QColor('blue'))
        request=SubmittedRequest('experience',frame,None,7,3,100,tracking_epoch=9,analysis_rect=(4,5,20,10))
        self.assertIsNone(request.shop_epoch);self.assertEqual(request.tracking_epoch,9)
        self.assertEqual(request.analysis_origin,(4,5));self.assertEqual(request.analysis_image().size().toTuple(),(20,10))

    def test_exp_submission_does_not_acknowledge_an_unread_shop_frame(self):
        reader=SimpleNamespace(image=QImage(),pointer=None,image_sequence=7,generation=3,tracking_epoch=9,
            crop=None,shop_browsing=SimpleNamespace(epoch=8),process=Mock(),submitted_sequence=4)
        PixelReader.submit(reader,{},mode='experience',now=100)
        self.assertEqual(reader.submitted_sequence,4)
        self.assertEqual(reader.active_request.sequence,7)
        self.assertEqual(reader.active_request.tracking_epoch,9)

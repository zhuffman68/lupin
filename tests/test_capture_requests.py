"""Production request scheduling with mocked transport; no reader or capture."""
from types import MethodType,SimpleNamespace
import unittest
from unittest.mock import Mock,patch
import tempfile

from price_lens.capture import PixelReader
from price_lens.ui import LensWindow
from price_lens.reader_request import SubmittedRequest
from price_lens.price_observations import PriceObservations
from PySide6.QtGui import QImage,QColor
from PySide6.QtCore import QProcess,QRect


class CaptureRequestTests(unittest.TestCase):
    def scanning_reader(self,*,rescan=False):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        image=QImage(800,600,QImage.Format.Format_RGBA8888);image.fill(QColor('#cad5df'))
        native=QRect(100,150,199,35);full=QRect(100,150,199,260)
        process=Mock();process.state.return_value=QProcess.ProcessState.Running
        reader=SimpleNamespace(paused=False,experience_enabled=False,pickup_worker=None,pending=False,
            image=image,image_sequence=1,submitted_sequence=0,process=process,live_source=False,crop=None,
            auto_active=False,prices_enabled=True,rescan_requested=rescan,pointer=(180,160),
            tooltip_enabled=True,tooltip_retry_requested=False,tooltip_rect=None,tooltip_fingerprint=None,
            shop_rect=native,shop_context=native,shop_context_provider=lambda:full,
            shop_fingerprint=None,roi_clean=True,pending_since=0,last_pointer=(180,160),
            temp=temp,last_frame=100,last_geometry_check=0,writer_regions=lambda:[],annotation_regions=lambda:[],submit=Mock())
        reader.current_shop_context=MethodType(PixelReader.current_shop_context,reader)
        return reader,full

    def test_partial_native_rows_cannot_shrink_the_next_scan_to_one_listing(self):
        reader,area=self.scanning_reader()
        with patch('price_lens.capture.time.monotonic',return_value=100):PixelReader.scan(reader)
        payload=reader.submit.call_args.args[0]
        self.assertEqual((payload['width'],payload['height']),(area.width()+32,area.height()+32))
        self.assertTrue(reader.submit.call_args.kwargs['using_roi'])
        self.assertEqual(payload['shop_area'],dict(zip(('x','y','width','height'),area.getRect())))

    def test_requested_reacquisition_really_reads_the_full_frame(self):
        reader,_=self.scanning_reader(rescan=True)
        with patch('price_lens.capture.time.monotonic',return_value=100):PixelReader.scan(reader)
        payload=reader.submit.call_args.args[0]
        self.assertEqual((payload['width'],payload['height']),(800,600))
        self.assertFalse(reader.submit.call_args.kwargs['using_roi'])

    def test_complete_shop_keeps_geometry_for_cache_without_requesting_recovery(self):
        reader,area=self.scanning_reader();reader.shop_name_recovery_needed=lambda pointer:False
        with patch('price_lens.capture.time.monotonic',return_value=100):PixelReader.scan(reader)
        request=reader.submit.call_args.args[0]
        self.assertEqual(request['shop_area'],dict(zip(('x','y','width','height'),area.getRect())))
        self.assertFalse(request['shop_recovery'])

    def test_unchanged_stationary_shop_does_not_repeat_hover_ocr_on_a_timer(self):
        reader,area=self.scanning_reader()
        reader.shop_fingerprint=PixelReader.fingerprint(reader.image,area)
        with patch('price_lens.capture.time.monotonic',return_value=100):PixelReader.scan(reader)
        reader.submit.assert_not_called()
        self.assertEqual(reader.submitted_sequence,reader.image_sequence)

    def test_stationary_shop_still_scans_when_new_pixels_or_an_explicit_retry_arrive(self):
        for rescan in (False,True):
            reader,area=self.scanning_reader(rescan=rescan)
            reader.shop_fingerprint=b'previous page'
            with patch('price_lens.capture.time.monotonic',return_value=100):PixelReader.scan(reader)
            reader.submit.assert_called_once()

    def test_new_shop_page_gets_one_prompt_slot_without_starving_due_exp(self):
        for age,epoch,expected in ((2.0,2,'prices'),(2.0,1,'experience'),(2.5,2,'experience')):
            with self.subTest(age=age,epoch=epoch):
                reader,_=self.scanning_reader()
                reader.experience_enabled=True;reader.pickups_enabled=False;reader.tracking_ready=True
                reader.live_source=True;reader.last_experience=100-age;reader.scan_experience=Mock()
                reader.shop_browsing=SimpleNamespace(epoch=epoch);reader.last_price_epoch=1
                with patch('price_lens.capture.time.monotonic',return_value=100):PixelReader.scan(reader)
                if expected=='prices':
                    reader.submit.assert_called_once();reader.scan_experience.assert_not_called()
                    self.assertTrue(reader.submit.call_args.args[0]['progressive_shop'])
                else:reader.scan_experience.assert_called_once_with(100);reader.submit.assert_not_called()

    def test_stationary_tooltip_uses_its_native_title_proof_instead_of_repeating_ocr_for_background(self):
        from PySide6.QtGui import QPainter
        from price_lens.tooltip_source import capture_title
        for missing_fingerprint,changed_ink in ((False,False),(False,True),(True,False),(True,True)):
            with self.subTest(missing_fingerprint=missing_fingerprint,changed_ink=changed_ink):
                reader,_=self.scanning_reader();reader.shop_rect=reader.shop_context=None
                reader.shop_context_provider=lambda:None
                reader.pointer=reader.last_pointer=(260,120);reader.tooltip_association=None
                painter=QPainter(reader.image);panel=QRect(100,150,260,230)
                painter.fillRect(panel,QColor('#464b78'));painter.fillRect(145,155,80,6,QColor('white'));painter.end()
                reader.tooltip_rect=QRect(137,150,162,17)
                reader.tooltip_fingerprint=PixelReader.fingerprint(reader.image,reader.tooltip_rect)
                reader.tooltip_title_proof=capture_title(reader.image,reader.tooltip_rect,panel=panel,pointer=reader.pointer)
                self.assertIsNotNone(reader.tooltip_title_proof)
                if missing_fingerprint:
                    # Capture can advance while normal tooltip OCR is pending.
                    # The GUI's validated semantic proof remains authoritative
                    # after that result deliberately omits its raw fingerprint.
                    reader.tooltip_fingerprint=None
                reader.image.setPixelColor(160 if changed_ink else 280,155,QColor('#354b73'))
                with patch('price_lens.capture.time.monotonic',return_value=100):PixelReader.scan(reader)
                if changed_ink:reader.submit.assert_called_once()
                else:
                    reader.submit.assert_not_called()
                    self.assertEqual(reader.submitted_sequence,reader.image_sequence)

    def test_scroll_observation_uses_full_shop_geometry_under_a_description(self):
        reader,area=self.scanning_reader();reader.live_source=True
        reader.shop_browsing=SimpleNamespace(observe_frame=Mock(return_value=False))
        reader.shop_tooltip_bounds=None;reader.shop_exclusions=lambda:[]
        PixelReader.observe_shop_frame(reader)
        self.assertEqual(reader.shop_browsing.observe_frame.call_args.args[1],area)

    def pending_reader(self):
        request=SubmittedRequest('prices',QImage(),None,1,0,100,shop_epoch=0)
        reader=SimpleNamespace(paused=False,experience_enabled=False,pickup_worker=None,pending=True,
            pending_since=100.0,process=Mock(),status=SimpleNamespace(emit=Mock()),shop_fingerprint=b'known',
            image_sequence=1,rescan_requested=False,active_request=request)
        reader.scan=MethodType(PixelReader.scan,reader)
        reader.request_rescan=MethodType(PixelReader.request_rescan,reader)
        return reader

    def test_retiring_shop_during_native_ocr_preserves_the_active_timeout(self):
        from price_lens.shop_dialog import ShopPriceEntry
        reader=self.pending_reader()
        entry=ShopPriceEntry(QRect(400,200,232,139))
        window=SimpleNamespace(reader=reader,observations=PriceObservations(),shop_price_entry=entry)
        with patch('price_lens.capture.QTimer.singleShot') as queued,patch('price_lens.capture.time.monotonic',return_value=101):
            LensWindow.retire_shop_source(window)
            reader.scan()
        self.assertEqual(reader.pending_since,100)
        self.assertTrue(reader.pending);self.assertTrue(reader.rescan_requested)
        self.assertEqual(reader.image_sequence,2)
        reader.process.kill.assert_not_called();reader.status.emit.assert_not_called()
        queued.assert_called_once_with(0,reader.scan)
        self.assertFalse(entry.blocking)

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

    def test_owned_annotation_geometry_is_submitted_in_source_coordinates_and_frozen(self):
        reader,_=self.scanning_reader();rect=QRect(250,170,230,36)
        reader.annotation_regions=lambda:[rect]
        with patch('price_lens.capture.time.monotonic',return_value=100):PixelReader.scan(reader)
        payload=reader.submit.call_args.args[0]
        self.assertEqual(payload['annotations'],[dict(x=250,y=170,width=230,height=36)])
        reader.generation=3;reader.tracking_epoch=0;reader.shop_browsing=SimpleNamespace(epoch=7)
        PixelReader.submit(reader,payload,mode='prices',now=100)
        payload['annotations'][0]['x']=0
        self.assertEqual(reader.active_request.annotations,((250,170,230,36),))

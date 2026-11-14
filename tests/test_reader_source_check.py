"""Native-control discovery yields to Qt without weakening reply authority."""
import json
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor,QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from price_lens.capture import PixelReader
from price_lens.reader_request import SubmittedRequest


class ReaderSourceCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.reader=PixelReader(Path(__file__).resolve().parents[1]);self.reader.timer.stop()
        self.addCleanup(self.reader.close)
        self.image=QImage(800,600,QImage.Format.Format_RGBA8888);self.image.fill(QColor('#223344'))
        r=self.reader;r.image=self.image
        self.request=SubmittedRequest('prices',self.image,(200,250),0,r.generation,time.monotonic(),shop_epoch=r.shop_browsing.epoch)
        r.active_request=r.submitted_request=self.request
        self.readings=[];r.reading.connect(self.readings.append)
        self.message=dict(atMs=int(self.request.started_at*1000),shop=dict(
            area=dict(x=100,y=150,width=199,height=260),rows=[]),tooltip=None)

    def wait_for(self,condition):
        until=time.monotonic()+3
        while not condition() and time.monotonic()<until:QTest.qWait(2)
        self.assertTrue(condition())

    def submit(self,**fields):
        self.reader.buffer+=(json.dumps({**self.message,**fields})+'\n').encode();self.reader.on_output()

    def test_slow_discovery_keeps_the_gui_and_original_deadline_live(self):
        started=threading.Event();release=threading.Event();heartbeats=[];gui=threading.get_ident();threads=[]
        def discover(*args,**kwargs):
            threads.append(threading.get_ident());started.set();release.wait(2);return None
        self.addCleanup(release.set)
        with patch('price_lens.capture.find_npc_shop',side_effect=discover):
            self.submit();self.assertTrue(started.wait(1))
            self.assertTrue(self.reader.pending);self.assertIs(self.reader.active_request,self.request)
            self.assertEqual(self.reader.active_request.deadline_at,self.request.deadline_at)
            QTimer.singleShot(0,lambda:heartbeats.append(True));self.wait_for(lambda:bool(heartbeats))
            self.assertEqual(self.readings,[]);self.assertNotEqual(threads,[gui])
            release.set();self.wait_for(lambda:len(self.readings)==1)
        self.assertIsNone(self.reader.active_request)

    def test_final_phase_waits_behind_its_partial_without_a_new_request(self):
        release=threading.Event();started=threading.Event();self.addCleanup(release.set)
        def discover(*args,**kwargs):started.set();release.wait(2);return None
        with patch('price_lens.capture.find_npc_shop',side_effect=discover):
            self.submit(shopPartial=True);self.assertTrue(started.wait(1))
            self.submit();self.assertEqual(self.readings,[])
            self.assertIs(self.reader.active_request,self.request)
            release.set();self.wait_for(lambda:len(self.readings)==2)
        self.assertIsNone(self.reader.active_request)
        self.assertTrue(self.readings[0]['shopPartial']);self.assertFalse(self.readings[1].get('shopPartial',False))
        self.assertTrue(all(result['_submitted_request'] is self.request for result in self.readings))

    def test_pause_during_discovery_cannot_publish_a_late_reply(self):
        release=threading.Event();started=threading.Event();self.addCleanup(release.set)
        def discover(*args,**kwargs):started.set();release.wait(2);return None
        with patch('price_lens.capture.find_npc_shop',side_effect=discover):
            self.submit();self.assertTrue(started.wait(1));self.reader.pause(keep_stream=True)
            release.set();self.wait_for(lambda:not self.reader.source_check.busy and self.reader.active_request is None)
        self.assertEqual(self.readings,[])

    def test_discovery_failure_never_becomes_a_negative_npc_result(self):
        with patch('price_lens.capture.find_npc_shop',side_effect=RuntimeError('fixture failure')):
            self.submit();self.wait_for(lambda:not self.reader.source_check.busy and self.reader.active_request is None)
        self.assertEqual(self.readings,[])

    def test_close_during_discovery_returns_without_waiting_and_ignores_late_work(self):
        release=threading.Event();started=threading.Event();self.addCleanup(release.set)
        def discover(*args,**kwargs):started.set();release.wait(2);return None
        with patch('price_lens.capture.find_npc_shop',side_effect=discover):
            self.submit();self.assertTrue(started.wait(1));future=self.reader.source_check.work.future;self.reader.close()
            heartbeats=[];QTimer.singleShot(0,lambda:heartbeats.append(True))
            self.wait_for(lambda:bool(heartbeats));self.assertFalse(release.is_set())
            release.set();self.wait_for(future.done)
        self.assertEqual(self.readings,[]);self.reader.close()

    def test_scroll_during_discovery_keeps_the_original_epoch_and_rejects_the_old_shop(self):
        release=threading.Event();started=threading.Event();self.addCleanup(release.set)
        def discover(*args,**kwargs):started.set();release.wait(2);return None
        with patch('price_lens.capture.find_npc_shop',side_effect=discover):
            self.submit();self.assertTrue(started.wait(1));self.reader.shop_browsing.reset()
            release.set();self.wait_for(lambda:self.reader.active_request is None)
        self.assertEqual(self.readings,[]);self.assertTrue(self.reader.rescan_requested)

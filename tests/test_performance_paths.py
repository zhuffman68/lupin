"""Offline retention, bounded background work and query-count regressions."""
from concurrent.futures import CancelledError
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import tempfile
import json
import threading
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QColor
from PySide6.QtCore import QRect

from price_lens.background_job import LatestJob
from price_lens.data import Cache
from price_lens.domain import Catalog
from price_lens.reference_availability import market_proofs
from price_lens.reference_data import ReferenceStore
from price_lens.snapshot import SnapshotStore
from price_lens.snapshot_updater import SnapshotUpdater
from price_lens.chat import ChatTranslation
from price_lens.chat_ocr import pixels,with_frame_pixels
from test_reference import generation
from test_snapshot import document


class PerformancePathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)

    def wait_for(self,predicate):
        deadline=time.monotonic()+3
        while not predicate() and time.monotonic()<deadline:QTest.qWait(5)
        self.assertTrue(predicate())

    def test_stale_catalog_survives_cleanup_but_obsolete_response_does_not(self):
        path=Path(self.folder.name)/'cache.sqlite';cache=Cache(path);old=time.time()-10*86400
        cache.put('catalog','osms',{'items':['last good']},saved=old)
        cache.put('response','obsolete',{},saved=old)
        reopened=Cache(path)
        self.assertEqual(reopened.get('catalog','osms'),{'items':['last good']})
        self.assertIsNone(reopened.get('catalog','osms',86400))
        self.assertIsNone(reopened.get('response','obsolete'))

    def test_prepared_generation_is_not_visible_until_adoption_and_cancel_rolls_back(self):
        cache=Cache(Path(self.folder.name)/'cache.sqlite');store=SnapshotStore(cache)
        now=time.time();store.save(document(now));old=store.meta.copy()
        prepared=store.prepare(document(now+60))
        self.assertEqual(store.meta,old)
        store.adopt(prepared);self.assertEqual(store.meta,prepared.meta)
        calls=0
        def cancelled():
            nonlocal calls
            calls+=1
            if calls==3:raise CancelledError()
        with self.assertRaises(CancelledError):store.prepare(document(now+120),guard=cancelled)
        self.assertEqual(SnapshotStore(cache).meta,prepared.meta)

    def test_market_evidence_uses_one_name_projection_for_all_rows(self):
        store=ReferenceStore(Path(self.folder.name)/'ref.sqlite');store.replace(*generation())
        catalog=Catalog({'items':[{'id':1001,'name':'Leaf Earrings'},{'id':4001,'name':'Green Mushroom Cap'}]})
        now=time.time();rows={item.game_id:dict(name=item.name,quote=dict(game_id=item.game_id,world='Classic World',
             basis='observed shop sales',observed_at=now,sample_count=8)) for item in catalog.items}
        count=0;original=store.connect
        @contextmanager
        def counted():
            nonlocal count
            count+=1
            with original() as db:yield db
        store.connect=counted
        self.assertEqual(len(market_proofs(store,catalog,SimpleNamespace(meta={'checked_at':now},rows=rows))),2)
        self.assertEqual(count,1)

    def test_latest_job_replaces_pending_work_and_never_delivers_cancelled_result(self):
        job=LatestJob('test-latest');self.addCleanup(job.pool.shutdown,wait=True);self.addCleanup(job.close)
        started=threading.Event();release=threading.Event();ran=[];results=[];job.completed.connect(results.append)
        def first(token):started.set();release.wait(2);token.check();return 'obsolete'
        job.submit(first);self.assertTrue(started.wait(1))
        job.submit(lambda token:ran.append('skipped'))
        job.submit(lambda token:ran.append('current') or 'current')
        release.set();self.wait_for(lambda:len(results)==1)
        self.assertEqual(ran,['current']);self.assertEqual(results[0].value,'current')

    def test_snapshot_storage_does_not_block_qt_or_publish_after_disable(self):
        store=SnapshotStore(Cache(Path(self.folder.name)/'cache.sqlite'));updater=SnapshotUpdater(store)
        self.addCleanup(updater.storage.pool.shutdown,wait=True);self.addCleanup(updater.close)
        release=threading.Event();started=threading.Event();heartbeat=[]
        original=store.prepare
        def slow(doc,**kwargs):started.set();release.wait(2);return original(doc,**kwargs)
        updater.enabled=True
        with patch.object(store,'prepare',side_effect=slow):
            updater.accept(document());self.assertTrue(started.wait(1))
            QTimer.singleShot(0,lambda:heartbeat.append(True));self.wait_for(lambda:bool(heartbeat))
            self.assertIsNone(store.meta);updater.set_enabled(False);release.set()
            self.wait_for(lambda:updater.storage.future is None)
            self.assertIsNone(store.meta)

    def test_translation_counts_only_current_accepted_rows_including_late_results(self):
        class Pipe:
            def readAllStandardOutput(self):data,self.output=self.output,b'';return data
        image=QImage(100,80,QImage.Format.Format_RGB888);image.fill(QColor('#eeeeee'))
        row=dict(box=[5,5,50,30],speaker='Fixture',original='안녕하세요',text='Hello',note='Local')
        for changed,expected in ((False,1),(True,0)):
            chat=ChatTranslation(Path(self.folder.name));pipe=Pipe();chat.process=pipe;chat.enabled=chat.ready=True
            chat.frame=QImage(image);chat.region=image.rect();chat.current_frame=QImage(image)
            if changed:chat.current_frame.fill(QColor('#111111'))
            chat.current_frame_at=time.monotonic();chat.started=time.monotonic()-3;chat.identity=chat.batch_identity=1
            pipe.output=(json.dumps(dict(id=1,row=row))+'\n'+json.dumps(dict(id=1,done={'count':20}))+'\n').encode()
            try:
                chat.receive();self.assertEqual(chat.hits,expected);self.assertEqual(len(chat.cards),expected)
                if changed:self.assertIn('changed',chat.notice)
            finally:chat.process=None;chat.close()

    def test_enabling_translation_is_lazy_and_releases_without_disabling_feature(self):
        chat=ChatTranslation(Path(self.folder.name));chat.enable(True)
        self.assertTrue(chat.enabled);self.assertIsNone(chat.process)
        chat.release_idle();self.assertTrue(chat.enabled);self.assertFalse(chat.ready);chat.close()

    def test_rgb_analysis_is_shared_only_inside_the_current_frame_scope(self):
        image=QImage(40,30,QImage.Format.Format_RGB888);image.fill(QColor('#4488aa'))
        @with_frame_pixels
        def check(frame):
            first=pixels(frame);self.assertIs(first,pixels(frame))
            edited=QImage(frame);edited.fill(QColor('#222222'));self.assertIsNot(first,pixels(edited))
            return first
        first=check(image);self.assertIsNot(first,pixels(image))

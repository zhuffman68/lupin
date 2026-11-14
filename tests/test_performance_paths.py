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
from price_lens.reader_process import ReaderProcess
from price_lens.process_lifecycle import drain_retired
from price_lens.update_cache import usage,clear
from price_lens.service import PriceService
from price_lens.data import load_catalog
from test_reference import generation
from test_snapshot import document


class PerformancePathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)

    def wait_for(self,predicate,timeout=3):
        deadline=time.monotonic()+timeout
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
        def slow(doc,*args,**kwargs):started.set();release.wait(2);return original(doc,*args,**kwargs)
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

    def test_reader_starts_lazily_recovers_and_stops_retrying_when_paused(self):
        import sys
        from PySide6.QtCore import QProcess
        worker=ReaderProcess(sys.executable);self.addCleanup(drain_retired);self.addCleanup(worker.close)
        counter=Path(self.folder.name)/'attempts'
        program="import pathlib,sys;p=pathlib.Path(sys.argv[1]);n=int(p.read_text())+1 if p.exists() else 1;p.write_text(str(n));sys.exit(1) if n<3 else None;print('ready',flush=True);sys.stdin.read()"
        worker.process.setArguments(['-B','-c',program,str(counter)])
        self.assertEqual(worker.process.state(),QProcess.ProcessState.NotRunning)
        losses=[];worker.lost.connect(losses.append);worker.ensure()
        # Observe all three sequential subprocess launches, including the real
        # retry delays. This is a recovery-contract check, not a startup benchmark.
        self.wait_for(lambda:counter.exists() and counter.read_text()=='3' and worker.process.state()==QProcess.ProcessState.Running,timeout=15)
        self.assertEqual(len(losses),2);worker.accepted();self.assertEqual(worker.attempts,0)
        worker.restart('Fixture timeout');worker.pause();QTest.qWait(100)
        self.assertFalse(worker.retry.isActive());self.assertEqual(counter.read_text(),'3')

    def test_update_cache_counts_links_once_and_never_deletes_unowned_files_or_symlink_targets(self):
        import os
        folder=Path(self.folder.name);package=folder/'lupin-1.0.5-1-x86_64.pkg.tar.zst';package.write_bytes(b'x'*256)
        os.link(package,folder/('base-'+'a'*64))
        keep=folder/'notes.txt';keep.write_text('keep')
        outside=folder/'outside';outside.mkdir();target=outside/'keep';target.write_text('keep')
        try:(folder/'Lupin-fixture.exe').symlink_to(target);linked=True
        except OSError:linked=False  # Windows may disallow symlinks without Developer Mode.
        self.assertEqual(usage(folder),256);clear(folder)
        self.assertTrue(keep.exists());self.assertEqual(target.read_text(),'keep')
        if linked:self.assertTrue((folder/'Lupin-fixture.exe').is_symlink())

    def test_cached_catalog_and_snapshot_are_not_blocked_by_catalog_network_refresh(self):
        service=PriceService(Path(self.folder.name)/'prices.sqlite')
        release=threading.Event();self.addCleanup(service.wait_closed);self.addCleanup(service.close);self.addCleanup(release.set)
        doc={'items':[dict(id=4010000,name='Bronze Ore')],'scrolls':[]}
        service.cache.put('catalog','osms',doc,saved=time.time()-90000)
        ready=[];service.catalog_ready.connect(ready.append)
        def slow(_):release.wait(2);return Catalog(doc)
        with patch('price_lens.service.load_catalog',side_effect=slow),patch('price_lens.snapshot_fetcher.SnapshotFetcher.start'):
            service.start();self.wait_for(lambda:bool(ready))
            self.assertTrue(service.catalog_pending);self.assertEqual(ready[0].items[0].game_id,4010000)
            service.set_snapshot_enabled(True);service.snapshot_updater.accept(document())
            self.wait_for(lambda:not service.snapshot_updater.busy)
            self.assertTrue(service.catalog_pending);self.assertEqual(service.snapshot.meta['rows'],1)
            release.set();self.wait_for(lambda:not service.catalog_pending)
            self.assertEqual(len(ready),1)

    def test_invalid_new_catalog_cannot_replace_last_good_identifiers(self):
        cache=Cache(Path(self.folder.name)/'prices.sqlite');old={'items':[dict(id=4010000,name='Bronze Ore')],'scrolls':[]}
        cache.put('catalog','osms',old,saved=time.time()-90000)
        with patch('price_lens.data.get_json',return_value={'items':[dict(id=True,name='Wrong')],'scrolls':[]}):
            result=load_catalog(cache)
        self.assertEqual([item.game_id for item in result.items],[4010000]);self.assertEqual(cache.get('catalog','osms'),old)

    def test_installed_update_prunes_only_older_version_proven_bases(self):
        from price_lens.updates import ReleaseClient
        client=ReleaseClient(Path(self.folder.name),{});folder=client.cache/'packages';folder.mkdir()
        first=folder/'lupin-1.0.4-1-x86_64.pkg.tar.zst';first.write_bytes(b'old')
        second=folder/'lupin-1.0.5-1-x86_64.pkg.tar.zst'
        client.keep_base(first,{'sha256':'a'*64},'1.0.4')
        second.write_bytes(b'current');client.keep_base(second,{'sha256':'b'*64},'1.0.5')
        unknown=folder/('base-'+'c'*64);unknown.write_bytes(b'legacy unknown')
        notes=folder/'notes.txt';notes.write_text('keep')
        client.prune_cache('1.0.5')
        self.assertFalse((folder/('base-'+'a'*64)).exists());self.assertTrue((folder/('base-'+'b'*64)).exists())
        self.assertTrue(unknown.exists());self.assertTrue(notes.exists());self.assertTrue(second.exists())

    def test_unsupported_hard_links_do_not_accumulate_named_installers(self):
        from price_lens.updates import ReleaseClient
        client=ReleaseClient(Path(self.folder.name),{});folder=client.cache/'packages';folder.mkdir()
        old=folder/'Lupin-Windows-x64-Setup-old.exe';old.write_bytes(b'old')
        current=folder/'Lupin-Windows-x64-Setup.exe';current.write_bytes(b'current')
        notes=folder/'notes.txt';notes.write_text('keep')
        with patch('price_lens.updates.os.link',side_effect=OSError('Unsupported filesystem')):
            client.keep_base(current,{'sha256':'a'*64},'1.0.5')
        self.assertFalse(old.exists());self.assertEqual(current.read_bytes(),b'current')
        self.assertTrue(notes.exists());self.assertFalse(list(folder.glob('base-*')))

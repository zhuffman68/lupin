"""Sighting identity, bounded asynchronous caching and visible-only card demand."""
from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PySide6.QtCore import QObject, QEvent, QCoreApplication, Signal
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget
from PySide6.QtTest import QTest

from price_lens.data import Cache
from price_lens.domain import Catalog, Item
from price_lens.listing_service import ListingFetcher, ListingService
from price_lens.listing_widgets import WhereSeenPanel
from price_lens.market_listings import LISTING_TTL, parse_listings, provider_id, valid_provider_id
from price_lens.motion import AnimatedTabs
from price_lens.platform_paths import market_binary
from price_lens.search import PriceSearch


ITEM = Item(1082000, 'Work Gloves', equipment=True)


def iso(at):
    return datetime.fromtimestamp(at, timezone.utc).isoformat()


def document(item=ITEM, now=None, **row):
    now = time.time() if now is None else now
    identity = provider_id(item)
    return {'version':2, 'kind':'item', 'market':'Classic World', 'id':identity,
            'generated_at':iso(now),
            'catalog':{'id':identity, 'catalogId':identity, 'name':item.name,
                       'unitBasis':'set' if item.per_set else 'item'},
            'listings':[dict(seller='Seller', location='Free Market <7>', channel=3,
                             channelRoom=7, price=15000, qty=1, stock=None,
                             lastSeen=iso(now-60), up=True, **row)]}


class ListingParserTests(unittest.TestCase):
    def test_sightings_preserve_asking_stack_location_and_distinct_ages(self):
        value = document(now=100000)
        value['listings'][0].update(qty=3, price=90000, stock=6)
        parsed = parse_listings(value, ITEM, 100100)
        self.assertEqual((parsed.checked_at, parsed.published_at), (100100,100000))
        row = parsed.rows[0]
        self.assertEqual((row.price,row.quantity,row.stock,row.place,row.last_seen),
                         (90000,3,6,'CH 3 · FM 7',99940))
        value['listings'][0].update(location='Perion Street Corner', channelRoom=None, channel=33)
        self.assertEqual(parse_listings(value,ITEM,100100).rows[0].place,'CH 33 · Perion Street Corner')

    def test_world_name_id_alias_unit_and_publication_must_all_match(self):
        changes = [dict(market='Other'),dict(kind='list'),dict(version=1),dict(id='basil:01082001'),
                   dict(generated_at='wrong'),dict(generated_at=iso(time.time()+301))]
        for change in changes:
            value = document();value.update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):parse_listings(value,ITEM)
        for key,value in [('catalogId','cash:01082000'),('id','basil:01082001'),
                          ('name','Brown Work Gloves'),('unitBasis','set')]:
            data=document();data['catalog'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):parse_listings(data,ITEM)

    def test_invalid_sold_out_and_incomplete_rows_are_not_offers(self):
        for change in [dict(up=False),dict(stock=0),dict(price=-1),dict(price=1.5),
                       dict(qty=True),dict(lastSeen='wrong'),dict(seller=''),dict(seller='x\ny')]:
            value=document();value['listings'][0].update(change)
            with self.subTest(change=change):self.assertEqual(parse_listings(value,ITEM).rows,())

    def test_empty_misses_and_nx_set_units_are_valid_without_any_price_quote(self):
        item=replace(ITEM,cash=True,per_set=True)
        value=document(item);value['listings']=[]
        parsed=parse_listings(value,item)
        self.assertEqual(parsed.identity,'cash:01082000');self.assertEqual(parsed.rows,())
        self.assertFalse(hasattr(parsed,'quote'))

    def test_rows_are_deduplicated_newest_first_and_capped(self):
        value=document(now=100000)
        base=value['listings'][0]
        value['listings']=[dict(base,seller=f'Seller{i}',lastSeen=iso(99900+i)) for i in range(110)]
        value['listings']+=value['listings'][:5]
        parsed=parse_listings(value,ITEM,100100)
        self.assertEqual(len(parsed.rows),100);self.assertTrue(parsed.more)
        self.assertEqual(parsed.rows[0].seller,'Seller109')

    def test_identity_cannot_inject_a_helper_script_or_request_path(self):
        for identity in ['basil:01082000\n','basil:01082000/../x',"cash:00000001';alert(1)//",'basil:1',None]:
            self.assertFalse(valid_provider_id(identity))
        self.assertTrue(valid_provider_id('cash:05011111'))
        with self.assertRaises(ValueError):provider_id(replace(ITEM,game_id=True))


class FakeFetcher(QObject):
    ready=Signal(object)
    failed=Signal(str)
    def __init__(self):super().__init__();self.identity='';self.requests=[];self.closed=False
    def start(self):self.requests.append(self.identity)
    def close(self):self.closed=True


class ListingTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.cache=Cache(Path(self.directory.name)/'cache.sqlite')
        self.fetcher=FakeFetcher();self.now=time.time();self.busy=False
        self.service=ListingService(self.cache,fetcher=self.fetcher,clock=lambda:self.now,market_busy=lambda:self.busy)
        self.owner=QObject()

    def tearDown(self):
        self.service.close();self.service.wait_closed();self.service.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.app.processEvents();self.directory.cleanup()

    def until(self,predicate,timeout=3):
        end=time.monotonic()+timeout
        while not predicate() and time.monotonic()<end:self.app.processEvents();time.sleep(.001)
        self.assertTrue(predicate())

    def load(self,item=ITEM):
        self.service.set_interest(self.owner,item)
        self.until(lambda:bool(self.fetcher.requests))

    def accept(self,data=None,item=ITEM):
        self.fetcher.ready.emit(document(item,self.now) if data is None else data)
        self.until(lambda:not self.service.operation and not self.service.fetching)


class ListingServiceTests(ListingTestCase):

    def test_demand_and_repeat_interest_never_poll_api_and_expiry_refreshes_once(self):
        self.assertFalse(self.fetcher.requests)
        self.load();self.accept()
        for _ in range(100):self.service.set_interest(self.owner,ITEM)
        self.assertEqual(self.fetcher.requests,['basil:01082000'])
        self.now+=LISTING_TTL-1;self.service._pump();self.assertEqual(len(self.fetcher.requests),1)
        self.now+=2;self.service._pump();self.assertEqual(len(self.fetcher.requests),2)
        self.service._pump();self.assertEqual(len(self.fetcher.requests),2)

    def test_empty_sightings_are_cached_and_survive_service_restart(self):
        self.load();empty=document(ITEM,self.now);empty['listings']=[];self.accept(empty)
        self.assertEqual(self.service.state(ITEM).snapshot.rows,())
        self.service.close();self.service.wait_closed()
        self.fetcher=FakeFetcher()
        self.service=ListingService(self.cache,fetcher=self.fetcher,clock=lambda:self.now)
        self.service.set_interest(self.owner,ITEM)
        self.until(lambda:self.service.state(ITEM) is not None)
        self.assertFalse(self.fetcher.requests);self.assertEqual(self.service.state(ITEM).snapshot.rows,())

    def test_failure_retains_last_good_and_has_no_immediate_retry(self):
        self.load();self.accept();previous=self.service.state(ITEM).snapshot
        self.now+=LISTING_TTL+1;self.service._pump();self.fetcher.failed.emit('Private unbounded error')
        self.until(lambda:not self.service.operation)
        self.assertEqual(self.service.state(ITEM).snapshot,previous)
        self.assertNotIn('Private',self.service.state(ITEM).error)
        for _ in range(20):self.service.set_interest(self.owner,ITEM)
        self.assertEqual(len(self.fetcher.requests),2)

    def test_memory_cache_does_not_lend_sightings_to_another_name_or_unit(self):
        self.load();self.accept()
        self.assertIsNotNone(self.service.state(ITEM).snapshot)
        self.assertIsNone(self.service.state(replace(ITEM,name='Brown Work Gloves')))
        self.assertIsNone(self.service.state(replace(ITEM,per_set=True)))
        self.assertNotIn('sales',self.cache.get('market-listings',provider_id(ITEM))['document'])

    def test_wrong_item_reply_is_rejected_and_last_good_survives(self):
        self.load();self.accept();previous=self.service.state(ITEM).snapshot
        self.now+=LISTING_TTL+1;self.service._pump()
        bad=document(ITEM,self.now);bad['catalog']['catalogId']='basil:01082001'
        self.fetcher.ready.emit(bad);self.until(lambda:not self.service.operation)
        self.assertEqual(self.service.state(ITEM).snapshot,previous)
        self.assertTrue(self.service.state(ITEM).error)

    def test_hiding_during_full_market_refresh_removes_pending_demand(self):
        self.busy=True;self.service.set_interest(self.owner,ITEM)
        self.until(lambda:self.service.state(ITEM) is not None)
        self.assertFalse(self.fetcher.requests)
        self.service.set_interest(self.owner,None);self.busy=False;self.service._pump()
        self.assertFalse(self.fetcher.requests);self.assertFalse(self.service.timer.isActive())

    def test_newest_selection_replaces_pending_network_demand(self):
        self.load();other=replace(ITEM,game_id=1082001,name='Other Gloves')
        third=replace(ITEM,game_id=1082002,name='Third Gloves')
        self.service.set_interest(self.owner,other);self.service.set_interest(self.owner,third)
        self.fetcher.ready.emit(document(ITEM,self.now))
        self.until(lambda:len(self.fetcher.requests)==2)
        self.assertEqual(self.fetcher.requests,['basil:01082000','basil:01082002'])

    def test_closed_service_ignores_late_result(self):
        self.load();self.service.close();self.fetcher.ready.emit(document(ITEM,self.now))
        self.app.processEvents();self.assertIsNone(self.service.state(ITEM).snapshot)


class ListingWidgetTests(ListingTestCase):
    def test_cached_sightings_do_not_build_hidden_rows_while_other_cards_animate(self):
        from price_lens.listing_widgets import ListingRow
        self.tabs.setCurrentWidget(self.panel);self.until(lambda:bool(self.fetcher.requests));self.accept()
        self.tabs.setCurrentIndex(0);self.app.processEvents()
        with patch('price_lens.listing_widgets.ListingRow',wraps=ListingRow) as rows:
            candidate=WhereSeenPanel(ITEM,self.service,selected=lambda:self.tabs.currentWidget() is candidate)
            self.tabs.addTab(candidate,'Other item')
            for _ in range(5):self.service.changed.emit(ITEM.game_id);candidate.refresh()
            rows.assert_not_called();self.assertIsNone(candidate.widget())
            self.assertFalse(candidate.timer.isActive())
            self.tabs.setCurrentWidget(candidate);self.app.processEvents()
            self.assertEqual(len(candidate.rows),1);rows.assert_called_once()

    def setUp(self):
        super().setUp()
        self.app.setProperty('reduceMotion',True)
        self.host=QWidget();self.host.resize(250,300);layout=QVBoxLayout(self.host)
        self.tabs=AnimatedTabs();layout.addWidget(self.tabs)
        self.tabs.addTab(QWidget(),'Overview')
        self.panel=WhereSeenPanel(ITEM,self.service,selected=lambda:self.tabs.currentWidget() is self.panel)
        self.tabs.addTab(self.panel,'Where seen');self.tabs.currentChanged.connect(lambda *_:self.panel.sync())
        self.host.show();self.app.processEvents()

    def tearDown(self):
        self.host.close();self.host.deleteLater();self.app.processEvents();super().tearDown()

    def test_inactive_subtab_never_fetches_and_rows_remain_stable_on_age_ticks(self):
        self.assertFalse(self.fetcher.requests)
        self.tabs.setCurrentWidget(self.panel);self.until(lambda:bool(self.fetcher.requests));self.accept()
        self.assertEqual(len(self.panel.rows),1);row=self.panel.rows[0]
        for _ in range(5):self.panel.refresh()
        self.assertIs(self.panel.rows[0],row)
        self.assertIn('CH 3 · FM 7',row.listing.place)
        self.assertGreater(self.panel.listing_view.width(),100)
        self.tabs.setCurrentIndex(0);self.app.processEvents()
        self.assertFalse(self.panel.timer.isActive());self.assertFalse(self.service.interests)

    def test_loaded_results_reveal_once_and_unchanged_refresh_does_not_restart_motion(self):
        self.tabs.setCurrentWidget(self.panel);self.until(lambda:bool(self.fetcher.requests))
        self.app.setProperty('reduceMotion',False);self.accept()
        view=self.panel.listing_view
        self.assertTrue(view.revealing);self.assertEqual(view.animation.duration(),220)
        view.animation.pause();view.animation.setCurrentTime(110)
        held=view.alpha;row=view.rows[0];height=view.height()
        for _ in range(5):self.panel.refresh()
        self.assertEqual(view.alpha,held);self.assertEqual(view.animation.currentTime(),110)
        self.assertIs(view.rows[0],row);self.assertEqual(view.height(),height)
        self.assertEqual(len(self.fetcher.requests),1)
        self.tabs.setCurrentIndex(0);self.tabs.finish_slide();self.app.processEvents()
        self.assertEqual(view.animation.state(),view.animation.State.Stopped)

    def test_minimized_window_releases_demand_and_preserves_rows(self):
        self.tabs.setCurrentWidget(self.panel);self.until(lambda:bool(self.fetcher.requests));self.accept()
        self.host.showMinimized();self.app.processEvents();self.panel.sync()
        self.assertFalse(self.panel.timer.isActive());self.assertFalse(self.service.interests)
        self.host.showNormal();self.app.processEvents();self.panel.sync()
        self.assertTrue(self.service.interests);self.assertEqual(len(self.fetcher.requests),1)

    def test_live_slide_reaches_sightings_while_selection_checks_run(self):
        import gc
        self.app.setProperty('reduceMotion',False)
        self.tabs.setCurrentWidget(self.panel);self.until(lambda:bool(self.fetcher.requests));self.accept()
        for _ in range(15):
            self.panel.sync();gc.collect();QTest.qWait(25)
        self.assertFalse(self.tabs.sliding)
        self.assertFalse(self.tabs.widget(0).isVisible())
        self.assertEqual(self.panel.geometry(),self.tabs.stack.contentsRect())
        self.assertTrue(self.tabs.stack.layout().isEnabled())
        self.assertEqual(self.panel.rows[0].listing.seller,'Seller')

    def test_exact_search_without_database_has_tabs_and_no_hidden_listing_request(self):
        prices=PriceSearch()
        try:
            prices.market=SimpleNamespace(listings=self.service)
            prices.set_catalog(Catalog({'items':[{'id':ITEM.game_id,'name':ITEM.name,'category':'Equipment'},
                                                {'id':1082001,'name':'Brown Work Gloves','category':'Equipment'}]}))
            prices.resize(460,680);prices.show()
            prices.query.setText('Work');prices.timer.stop();prices.find_items();prices.results.setCurrentRow(0)
            self.app.processEvents();card=prices.price_view
            self.assertEqual([card.tabs.tabText(i) for i in range(card.tabs.count())],['Overview','Sources','Where seen'])
            self.assertLessEqual(card.tabs.tabBar().sizeHint().width(),card.tabs.width())
            self.assertFalse(self.fetcher.requests)
            card.tabs.setCurrentIndex(2);self.until(lambda:bool(self.fetcher.requests))
            prices.results.setCurrentRow(1);self.app.processEvents()
            self.assertIsNot(prices.price_view,card)
            self.assertEqual(prices.price_view.where_seen.item,prices.selected)
        finally:
            prices.close();prices.deleteLater();self.app.processEvents()


class NativeListingTests(unittest.TestCase):
    def test_native_local_fixture_uses_the_real_async_parser_and_omits_sale_history(self):
        binary=market_binary(Path(__file__).resolve().parents[1])
        if not binary.is_file() or not os.environ.get('DISPLAY'):
            self.skipTest('Native helper check runs in isolated Xvfb')
        with tempfile.TemporaryDirectory() as profile:
            result=subprocess.run([str(binary),'--profile',profile,'--self-test','--listing-item',provider_id(ITEM)],
                                  capture_output=True,timeout=25)
        self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))
        value=json.loads(result.stdout)
        self.assertEqual(parse_listings(value,ITEM).rows[0].place,'CH 3 · FM 7')
        self.assertNotIn('sales',value);self.assertNotIn(b'private',result.stdout)

    def test_fetcher_keeps_its_item_mode_explicit_and_validates_arguments(self):
        app=QApplication.instance() or QApplication([])
        fetcher=ListingFetcher(Path(tempfile.gettempdir())/'unused-listing-profile')
        try:
            fetcher.identity='basil:01082000'
            self.assertEqual(fetcher.command()[-2:],['--listing-item','basil:01082000'])
            fetcher.identity='basil:01082000/../x'
            with self.assertRaises(ValueError):fetcher.command()
        finally:fetcher.close();fetcher.deleteLater();app.processEvents()

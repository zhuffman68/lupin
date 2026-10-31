"""Whole-market freshness, conservative identity, last-good storage and scheduling."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from price_lens.data import Cache
from price_lens.domain import Catalog, Item, Quote, compare
from price_lens.service import PriceService
from price_lens.snapshot import SnapshotStore
from price_lens.snapshot_updater import SnapshotUpdater
from price_lens.market_lookup import market_lookup,market_lookup_reason


def iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def document(now=None):
    now = time.time() if now is None else now
    return {"version": 2, "kind": "list", "market": "Classic World", "preview": False,
            "generated_at": iso(now-60), "items": [
                {"id": "basil:04010000", "name": "Bronze Ore", "unitBasis": "item", "price": 100,
                 "priceSales": 9, "sold": 1000, "priceBasis": "24h", "lastSold": iso(now-120),
                 "lowData": False, "scrolledOnly": False}]}


class SnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.cache = Cache(Path(self.directory.name)/"cache.sqlite")
        self.store = SnapshotStore(self.cache)
        self.item = Item(4010000, "Bronze Ore")
        self.now = round(time.time(), 6)

    def tearDown(self):
        self.directory.cleanup()

    def test_full_snapshot_survives_restart_with_three_separate_ages(self):
        meta = self.store.save(document(self.now), self.now)
        reopened = SnapshotStore(self.cache)
        quote = reopened.quote(self.item)
        self.assertEqual(meta["priced"], 1)
        self.assertEqual((quote.fetched_at, quote.published_at, quote.observed_at),
                         (self.now, self.now-60, self.now-120))
        self.assertEqual(quote.sample_count, 9)  # not lifetime sold=1000
        self.assertEqual(compare(self.item, 1, 10, quote, self.now).tone, "green")

    def test_invalid_failed_or_older_refresh_preserves_last_good_copy_and_ages(self):
        doc = document(self.now)
        self.store.save(doc, self.now)
        original = self.store.quote(self.item)
        changes = [{"market": "COT2"}, {"preview": True}, {"version": 9}, {"kind": "item"},
                   {"generated_at": iso(self.now+301)}, {"generated_at": iso(self.now-600)}, {"items": []}]
        for changeset in changes:
            with self.subTest(changeset=changeset), self.assertRaises(ValueError):
                self.store.save(dict(doc, **changeset), self.now)
            self.assertEqual(SnapshotStore(self.cache).quote(self.item), original)
        with patch.object(self.cache, "connect", side_effect=OSError("disk unavailable")):
            with self.assertRaises(OSError):
                self.store.save(document(self.now+60), self.now+60)
        self.assertEqual(self.store.quote(self.item), original)

    def test_recent_download_does_not_resurrect_old_snapshot_or_market_report(self):
        doc = document(self.now)
        doc["generated_at"] = iso(self.now-3601)
        self.store.save(doc, self.now)
        quote = self.store.quote(self.item)
        self.assertFalse(quote.fresh(self.now, 3600))
        doc["generated_at"] = iso(self.now-60)
        doc["items"][0]["lastSold"] = iso(self.now-86401)
        self.store.save(doc, self.now)
        self.assertFalse(self.store.quote(self.item).fresh(self.now))

    def test_reference_lifetime_honors_selected_interval_and_publication_age(self):
        self.store.save(document(self.now), self.now)
        quote = self.store.quote(self.item)
        self.assertTrue(quote.cache_valid(self.now+299, 300))
        self.assertFalse(quote.cache_valid(self.now+301,300))
        self.assertFalse(quote.cache_valid(self.now+3541, 3600))
        self.assertFalse(replace(quote, fetched_at=self.now+1).cache_valid(self.now))

    def test_item_name_id_and_per_set_units_must_match(self):
        self.store.save(document(self.now), self.now)
        for item in (replace(self.item, name="Other Ore"), replace(self.item, game_id=4010001),
                     replace(self.item, per_set=True)):
            self.assertIsNone(self.store.quote(item))

    def test_blue_moon_top_never_inherits_the_same_name_earring_price(self):
        top=Item(1041078,'Blue Moon',equipment=True,gender='female',sub_category='Top')
        earring=Item(1032011,'Blue Moon',equipment=True,sub_category='Earring')
        catalog=Catalog.from_items([top,earring])
        doc=document(self.now)
        source=doc['items'][0]
        doc['items']=[dict(source,id='basil:01032011',name='Blue Moon',price=28888),
                      dict(source,id='basil:01041078',name='Blue Moon (F)',price=None)]
        self.store.save(doc,self.now)
        self.assertIsNone(catalog.resolve('Blue Moon'))
        self.assertEqual(self.store.lookup(top).reason,'no-sales')
        self.assertIsNone(self.store.quote(top))
        self.assertEqual(self.store.quote(earring).price,28888)
        doc['items']=doc['items'][:1]
        self.store.save(doc,self.now)
        self.assertIsNone(catalog.resolve('Blue Moon'))
        self.assertEqual(self.store.lookup(top).reason,'missing')

    def test_source_typography_is_safe_but_combined_variant_names_stay_rejected(self):
        doc=document(self.now);source=doc['items'][0]
        doc['items']=[dict(source,id='cash:01047097',name='Black “Hit Me” Shirt',price=22111),
                      dict(source,id='cash:01057090',name='Buddy Overall Jeans (Blue or Red)',price=19999.5)]
        self.store.save(doc,self.now)
        shirt=Item(1047097,'Black "Hit Me" Shirt',equipment=True,cash=True)
        blue=Item(1057090,'Buddy Overall Jeans (Blue)',equipment=True,cash=True)
        self.assertEqual(self.store.lookup(shirt).reason,'priced')
        self.assertEqual(self.store.quote(shirt).price,22111)
        # The same row has both the native missing-space spelling and the
        # provider's curly quotes. Neither may block the other layer's repair.
        catalog=Catalog.from_items([shirt,blue])
        native=catalog.resolve('Black "Hit Me"Shirt','chaos')
        self.assertEqual(native,shirt)
        self.assertEqual(self.store.quote(native).price,22111)
        self.assertEqual(self.store.lookup(blue).reason,'variant-mismatch')
        self.assertIsNone(self.store.quote(blue))

    def test_clipped_ring_with_native_colour_tier_reaches_its_exact_quote(self):
        catalog=Catalog({'items':[{'id':1112223,'name':'Ink-and-Wash Painting Name Tag Ring',
                                  'category':'Equipment','sub_category':'Ring'},
                                 {'id':1112227,'name':'Ink-and-Wash Thought Bubble Ring'}]})
        doc=document(self.now)
        doc['items'][0].update(id='cash:01112223',name='Ink-and-Wash Painting Name Tag Ring',price=1900000)
        self.store.save(doc,self.now)
        item=catalog.resolve('Ink-and-Wash Painting N...','chaos')
        self.assertEqual(item.game_id,1112223)
        self.assertEqual(self.store.quote(item).price,1900000)

    def test_lookup_reasons_distinguish_missing_sales_name_and_units(self):
        self.store.save(document(self.now),self.now)
        self.assertEqual(self.store.lookup(None).reason,'unidentified')
        self.assertEqual(self.store.lookup(replace(self.item,game_id=8)).reason,'missing')
        self.assertEqual(self.store.lookup(replace(self.item,name='Other Ore')).reason,'variant-mismatch')
        self.assertEqual(self.store.lookup(replace(self.item,per_set=True)).reason,'unit-mismatch')
        doc=document(self.now);doc['items'][0]['price']=None
        self.store.save(doc,self.now)
        self.assertEqual(self.store.lookup(self.item).reason,'no-sales')
        service=PriceService(self.cache.path)
        try:
            with patch('price_lens.data.get_json',side_effect=AssertionError('No item request')):
                self.assertEqual(market_lookup_reason(service,self.item),'no-sales')
                self.assertIn('No observed sales',service.reference(self.item).basis)
                self.assertEqual(market_lookup_reason(service,replace(self.item,name='Other Ore')),'variant-mismatch')
                self.assertIn('variant',service.reference(replace(self.item,name='Other Ore')).basis)
        finally:service.close();service.pool.shutdown(wait=True)

    def test_combined_reference_adapter_reads_each_negative_snapshot_result_once(self):
        doc=document(self.now);doc['items'][0]['price']=None
        self.store.save(doc,self.now)
        service=PriceService(self.cache.path)
        try:
            for item,reason in ((self.item,'no-sales'),
                                (replace(self.item,name='Other Ore'),'variant-mismatch'),
                                (replace(self.item,per_set=True),'unit-mismatch'),
                                (replace(self.item,game_id=8),'missing')):
                with self.subTest(reason=reason),patch.object(service.snapshot,'lookup',wraps=service.snapshot.lookup) as lookup:
                    result=market_lookup(service,item)
                    lookup.assert_called_once_with(item)
                    self.assertEqual(result.reason,reason)
                    self.assertEqual(result.quote.game_id,item.game_id)
                    self.assertIsNone(result.quote.price)
        finally:service.close();service.pool.shutdown(wait=True)

    def test_cash_items_use_meso_prices_and_missing_prices_remain_unpriced(self):
        doc = document(self.now)
        doc["items"] = [dict(doc["items"][0], id="cash:01087020", name="Blue Watch", cash={"nx": 500}),
                        dict(doc["items"][0], id="cash:01087021", name="Other Watch", price=None)]
        meta = self.store.save(doc, self.now)
        self.assertEqual((meta["rows"], meta["priced"]), (2, 1))
        self.assertEqual(self.store.quote(Item(1087020,"Blue Watch",cash=True)).price, 100)
        self.assertIsNone(self.store.quote(Item(1087021,"Other Watch",cash=True)))

    def test_thin_scrolled_unknown_basis_or_missing_window_count_never_get_deal_colors(self):
        for change in ({"priceSales": 1}, {"scrolledOnly": True}, {"priceBasis": "unknown"},
                       {"priceSales": None}, {"lowData": True}):
            doc = document(self.now)
            doc["items"][0].update(change)
            self.store.save(doc, self.now)
            self.assertEqual(compare(self.item, 1, 10, self.store.quote(self.item), self.now).tone, "muted")

    def test_duplicate_or_malformed_source_ids_reject_complete_generation(self):
        for change in ({"id": "other:04010000"}, {"catalogId": "basil:invalid"}):
            doc = document(self.now); doc["items"][0].update(change)
            with self.assertRaises(ValueError):self.store.save(doc, self.now)
        doc = document(self.now);doc["items"].append(deepcopy(doc["items"][0]))
        with self.assertRaises(ValueError):self.store.save(doc, self.now)

    def test_source_aliases_remain_unpriced_without_blocking_exact_items(self):
        doc = document(self.now)
        doc["items"].append(dict(doc["items"][0], id="basil:02014698",
                                 catalogId="basil:02009666", name="Unverified alias", price=999))
        meta = self.store.save(doc, self.now)
        self.assertEqual((meta["rows"], meta["priced"], meta["excluded_aliases"]), (1, 1, 1))
        self.assertEqual(self.store.quote(self.item).price, 100)
        for identity in (2014698, 2009666):
            self.assertIsNone(self.store.quote(Item(identity,"Unverified alias")))
        original = self.store.meta.copy()
        doc["items"] = doc["items"][1:]
        with self.assertRaises(ValueError):self.store.save(doc,self.now)
        self.assertEqual(self.store.meta,original)

    def test_cached_store_page_never_calls_item_api_even_after_fallback_interval(self):
        self.store.save(document(self.now-901), self.now-901)
        service = PriceService(self.cache.path)
        try:
            with patch("price_lens.data.get_json", side_effect=AssertionError("No item API calls")) as fetch:
                for _ in range(20):service.observe([self.item])
                self.assertEqual(fetch.call_count, 0)
                self.assertEqual(service.delivered[self.item.game_id].source, "MesoWatch")
        finally:service.close()

    def test_fresh_snapshot_loads_immediately_but_still_refreshes_on_launch_and_selected_interval(self):
        self.store.save(document(self.now), self.now)
        updater = SnapshotUpdater(self.store)
        try:
            with patch.object(updater.fetcher, "start") as start:
                updater.set_enabled(True)
                QCoreApplication.processEvents()
                self.assertEqual(start.call_count, 1)
                updater.refresh();updater.set_enabled(True)
                self.assertEqual(start.call_count, 1)
                updater.accept(document(self.now))
                self.assertGreater(updater.timer.interval(),895000)
                self.assertLessEqual(updater.timer.interval(),900000)
                updater.set_interval(300)
                self.assertGreater(updater.timer.interval(),295000)
                self.assertLessEqual(updater.timer.interval(),300000)
                self.assertFalse(updater.busy)
                updater.timer.timeout.emit()
                self.assertEqual(start.call_count, 2)
                updater.set_enabled(False)
                self.assertFalse(updater.timer.isActive())
        finally:updater.close()

    def test_already_old_publication_does_not_cause_a_refresh_loop(self):
        updater = SnapshotUpdater(self.store)
        try:
            updater.enabled = True
            doc = document(self.now);doc["generated_at"] = iso(self.now-3601)
            updater.accept(doc)
            self.assertGreater(updater.timer.interval(), 59000)
            self.assertLessEqual(updater.timer.interval(), 60000)
            self.assertFalse(self.store.quote(self.item).fresh(self.now))
        finally:updater.close()

    def test_failed_background_refresh_keeps_data_with_bounded_retry_and_can_disable(self):
        self.store.save(document(self.now), self.now)
        original = self.store.meta.copy()
        updater = SnapshotUpdater(self.store)
        try:
            updater.enabled = True
            for expected in (300000, 900000, 3600000, 3600000):
                updater.failed("offline")
                self.assertEqual(updater.timer.interval(), expected)
            self.assertEqual(self.store.meta, original)
            updater.set_enabled(False)
            updater.accept(document(self.now+60))
            self.assertEqual(self.store.meta, original)
        finally:updater.close()

    def test_one_startup_retry_precedes_normal_backoff_and_never_discards_prices(self):
        self.store.save(document(self.now),self.now);original=self.store.meta.copy()
        updater=SnapshotUpdater(self.store)
        try:
            updater.enabled=True;updater.startup_pending=True;updater.fetcher.failure_kind='timeout'
            for expected in (15000,300000,900000,3600000):
                updater.failed('Connection took too long')
                self.assertEqual(updater.timer.interval(),expected)
                self.assertEqual(self.store.meta,original)
        finally:updater.close()

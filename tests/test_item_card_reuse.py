"""Stable item widgets still replace canonical data and release old demand."""
import time
import unittest
from PySide6.QtCore import QObject,Signal,Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QWidget
from price_lens.domain import Catalog,Item,Quote
from price_lens.item_overview import ItemOverview,item_overview
from price_lens.motion import MotionLabel
from price_lens.reference_details import EntryDetails
from price_lens.watchlist_ui import WatchButton
import test_ui_context as fixture
from test_reference import documents,generation,allow_fixture


class ItemCardReuseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.ContextUiTests.setUpClass.__func__(cls)

    def setUp(self):
        fixture.ContextUiTests.setUp(self)
        self.app.setProperty('reduceMotion',True);self.addCleanup(lambda:self.app.setProperty('reduceMotion',False))
        w=self.window;w.timer.stop();w.show();self.app.processEvents()
        docs=documents();docs['items.json']+=list((
            dict(id=101,name='First Hat',category='Equipment',stats=dict(incPAD=3,reqLevel=10)),
            dict(id=102,name='Second Hat',category='Equipment',stats=dict(incMHP=50,reqDEX=20)),
            dict(id=103,name='Test Potion',category='Use',spec=dict(hp=100,mp=50)),
        ))
        w.reference.store.replace(*generation(docs));allow_fixture(w.reference.store)
        w.on_catalog(Catalog({'items':[dict(id=row['id'],name=row['name'],category=row['category']) for row in docs['items.json'] if row['id'] in (101,102,103)]}))
        now=time.time();w.quotes={i:Quote(i,i*100,now,now,20,'Fixture','','24h') for i in (101,102,103)}
        w.service.cached_values=dict(w.quotes)

    def tearDown(self):fixture.ContextUiTests.tearDown(self)

    def observe(self,identity):
        w=self.window;w.rows=[];w.last_screen=time.time()
        w.tooltip_result=dict(name=w.catalog.by_id[identity].name,area=dict(x=100,y=100,width=140,height=16),_pointer=[200,250])
        w.render(update_overlay=False);self.app.processEvents()
        return next(card for card in w.card_views.values() if isinstance(card,EntryDetails))

    def test_observed_item_reuses_shell_but_replaces_prices_stats_and_watch_identity(self):
        first=self.observe(101);summary=first.summary_card;overview=first.overview_content
        second=self.observe(102)
        self.assertIs(second,first);self.assertIs(second.summary_card,summary);self.assertIs(second.overview_content,overview)
        self.assertEqual(second.entry.id,102);self.assertEqual(second.summary_card.content_item.game_id,102)
        self.assertEqual(second.watch_button.item.game_id,102)
        self.assertIn('10,200',second.fields['market'].text());self.assertNotIn('10,100',second.fields['market'].text())
        shown=[label.text() for label in overview.findChildren(MotionLabel) if label.isVisible()]
        self.assertIn('HP',shown);self.assertNotIn('Weapon attack',shown)
        self.assertEqual(second.tabs.currentIndex(),0)

    def test_old_sighting_lease_is_released_and_old_item_updates_cannot_change_the_new_one(self):
        card=self.observe(101)
        class Listings(QObject):
            changed=Signal(int)
            def __init__(self):super().__init__();self.calls=[]
            def set_interest(self,scope,item):self.calls.append(item.game_id if item else None)
            def state(self,item):return None
            def loading(self,item):return False
        service=Listings();view=card.where_seen;view.service=service;view.observing=True
        self.observe(102)
        self.assertIs(card.where_seen,view);self.assertEqual(service.calls,[None])
        self.assertEqual(view.item.game_id,102);self.assertFalse(view.observing);self.assertEqual(view.rows,[])
        service.changed.emit(101);self.assertEqual(view.item.game_id,102)

    def test_recycled_card_rejects_a_different_canonical_identity(self):
        card=self.observe(101);record=self.window.reference.store.entry('items',102)
        data=dict(card.data);data['item']=self.window.catalog.by_id[101]
        self.assertFalse(card.rebind_item(*record,**data));self.assertEqual(card.entry.id,101)

    def test_cash_schema_changes_keep_the_summary_and_replace_only_inner_pages(self):
        card=self.observe(101);summary=card.summary_card
        for identity in (5001,102,5001,103,101):
            entry,row=self.window.reference.store.entry('items',identity)
            item=Item(identity,entry.name,row.get('category')=='Equipment',cash=bool(row.get('cash')))
            data=dict(card.data,item=item,row={'name':entry.name},quote=None,now=time.time(),ttl=self.window.ttl)
            self.assertTrue(card.rebind_item(entry,row,automatic=True,**data))
            self.app.processEvents()
            self.assertIs(card.summary_card,summary)
            self.assertEqual(card.entry.id,identity)
            self.assertEqual(card.watch_button.item.game_id,identity)
            self.assertEqual(card.where_seen.item.game_id,identity)
            self.assertEqual(len(card.lists),1)
            expected=['Sources','Where seen'] if row.get('cash') else ['Overview','Sources','Where seen']
            self.assertEqual([card.tabs.tabText(i) for i in range(card.tabs.count())],expected)

    def test_rebinding_keeps_the_card_morph_and_frozen_departing_pixels(self):
        card=self.observe(101);self.app.setProperty('reduceMotion',False)
        self.observe(102);area=self.window.card_area
        self.assertIs(next(card for card in self.window.card_views.values() if isinstance(card,EntryDetails)),card)
        self.assertIsNotNone(area.outgoing);self.assertIsNotNone(area.outgoing.morph)
        self.assertEqual(area.animation.duration(),180)
        old=area.outgoing.morph.old.foreground.toImage()
        area.animation.pause();area.animation.setCurrentTime(65)
        self.assertEqual(area.outgoing.morph.old.foreground.toImage(),old)
        self.assertNotEqual(area.outgoing.morph.new.foreground.toImage(),old)

    def test_one_dormant_card_releases_demand_and_is_reused_after_history_retirement(self):
        w=self.window;card=self.observe(101)
        w.tooltip_result=None;w.render(update_overlay=False)
        w.card_sightings.discard(True);w.render(update_overlay=False)
        self.assertIs(w.spare_detail_card,card);self.assertTrue(card.isHidden())
        self.assertFalse(card.where_seen.allowed);self.assertNotIn(card,w.card_views.values())
        self.assertIs(self.observe(102),card);self.assertIsNone(w.spare_detail_card)
        self.assertTrue(card.where_seen.allowed)

    def test_compact_shop_rows_reuse_four_hidden_shells_without_retaining_asking_proofs(self):
        from price_lens.price_widgets import PriceCard
        w=self.window
        def shop(identities):
            w.tooltip_result=None;w.shop_open=bool(identities);w.last_screen=time.time()
            w.rows=[dict(name=w.catalog.by_id[i].name,price=dict(quantity=1,mesos=i*10),
                        area=dict(x=100,y=200+index*40,width=180,height=40)) for index,i in enumerate(identities)]
            if not identities:w.card_sightings.discard(False)
            w.render(update_overlay=False);self.app.processEvents()
        shop((101,102,103,101));original={id(card) for card in w.card_views.values() if isinstance(card,PriceCard)}
        self.assertEqual(len(original),4)
        shop(())
        self.assertEqual(len(w.spare_shop_cards),4)
        self.assertTrue(all(card.isHidden() and card.content_row=={} for card in w.spare_shop_cards))
        shop((103,101,102,103))
        current=[card for card in w.card_views.values() if isinstance(card,PriceCard)]
        self.assertEqual({id(card) for card in current},original);self.assertEqual(w.spare_shop_cards,[])
        self.assertEqual([card.content_item.game_id for card in current],[103,101,102,103])

    def test_overview_cells_remain_bounded_and_do_not_create_top_level_windows(self):
        owner=QWidget();owner.setProperty('suppressMotion',True)
        self.addCleanup(owner.deleteLater)
        models=[item_overview('Item',row) for row in (
            dict(stats=dict(incPAD=3,reqLevel=10)),dict(spec=dict(hp=100,mp=50)),
            dict(scroll=dict(success_rate=60,stats=dict(incDEX=3),slot='Bottomwear')),
        )]
        view=ItemOverview(models[0],owner)
        for model in models:view.set_model(model)
        count=len(view.findChildren(QObject))
        for _ in range(30):
            for model in models:view.set_model(model)
        self.assertEqual(len(view.findChildren(QObject)),count)
        self.assertNotIn(view,QApplication.topLevelWidgets())
        self.assertTrue(all(not section.isWindow() for section in view.sections.values()))

    def test_watch_press_cannot_apply_to_a_different_item_after_rebinding(self):
        button=WatchButton();self.addCleanup(button.deleteLater);button.bind(self.window.watchlist)
        button.set_item(self.window.catalog.by_id[101]);button.show();self.app.processEvents()
        QTest.mousePress(button,Qt.MouseButton.LeftButton)
        button.set_item(self.window.catalog.by_id[102]);QTest.mouseRelease(button,Qt.MouseButton.LeftButton)
        self.assertEqual(self.window.watchlist.ids,set())
        QTest.mouseClick(button,Qt.MouseButton.LeftButton);self.assertIn(102,self.window.watchlist.ids)

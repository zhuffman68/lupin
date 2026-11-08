"""Exercise real UI context rules with fake pixel/input data and no OS capture."""
import os
from dataclasses import replace
from pathlib import Path
import time
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QRect, Qt, QTimer, Signal,QPoint
from PySide6.QtGui import QColor, QImage, QKeySequence, QMouseEvent,QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QKeySequenceEdit, QLabel, QPushButton

from price_lens.domain import Catalog, Quote
from price_lens.ui import LensWindow
from price_lens.capture import PixelReader as ActualPixelReader


class FakeOverlay(QObject):
    pointer = Signal(int, int)
    writer_event = Signal(dict)
    writer_lost = Signal()
    writer_available = True

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.rows = []

    def update(self, geometry, rows, hover_enabled=False):
        self.rows = rows

    def update_writer(self,state):self.writer_state=state

    def close(self):
        pass


class FakeReader(QObject):
    reading = Signal(dict)
    status = Signal(str)
    image_ready = Signal(QImage)
    area_changed = Signal()
    experience = Signal(dict)
    fingerprint = staticmethod(ActualPixelReader.fingerprint)

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.image = QImage(800, 800, QImage.Format.Format_RGBA8888)
        self.image.fill(QColor('#171c25'))
        self.crop = None
        self.pointer = (340, 240)
        self.shop_context = QRect(300, 200, 240, 300)
        self.latest_latency_ms = 30
        self.image_sequence = 0
        self.last_frame = time.monotonic()
        self.starts = 0
        self.pauses = []
        self.auto_active = True
        self.game_area = QRect(0, 0, 800, 800)

    def set_auto_area(self, enabled):
        self.auto_active = enabled

    def request_rescan(self,*,preserve_shop_cache=False):
        if not preserve_shop_cache:self.shop_fingerprint=None
        self.image_sequence+=1

    def start(self, *args):
        self.starts += 1

    def pause(self, keep_stream=False):
        self.pauses.append(keep_stream)

    def close(self, keep_stream=False):
        pass


class FakeService(QObject):
    catalog_ready = Signal(object)
    quote_ready = Signal(int, object)
    error = Signal(int, str)
    state_changed = Signal()

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.requests = []
        self.catalog_starts = 0
        self.visible = []
        self.states = {}

    def start(self):
        self.catalog_starts += 1

    def request(self, item, ttl):
        self.requests.append(item.game_id)

    def observe(self, items):
        self.visible = [item.game_id for item in items]
        self.requests.extend(self.visible)

    def clear_visible(self):
        self.visible = []

    def set_manual(self, item):
        self.manual_item = item

    def set_snapshot_enabled(self, enabled):
        self.refresh_snapshot = enabled

    def set_refresh_interval(self,seconds):self.interval=seconds

    def cached(self,item):return getattr(self,'cached_values',{}).get(item.game_id) if item else None

    def lookup_reason(self,item):
        quote=self.cached(item)
        return 'missing' if quote is None else 'priced' if quote.price is not None else 'no-sales'

    def deliver_quote(self,identity,quote):
        if not hasattr(self,'cached_values'):self.cached_values={}
        self.cached_values[identity]=quote
        self.quote_ready.emit(identity,quote)

    def state_for(self):
        return next(iter(self.states.values()),'')

    def close(self):
        pass


class FakeSettings:
    def __init__(self, *args):
        self.values = {}

    def value(self, key, default, type=None):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value


class FakeHotkeys(QObject):
    activated = Signal()
    activation_token = Signal(str)
    changed = Signal(str)
    status = Signal(str)
    portal = False

    def start(self, text):
        self.changed.emit(text)
        return True

    def close(self):
        pass


class FakeThumbnails(QObject):
    ready=Signal(int)
    def __init__(self,*args):super().__init__();self.items=[]
    def image(self,item_id):return QImage()
    def observe(self,items):self.items=list(items)
    def close(self):pass


class ContextUiTests(unittest.TestCase):
    def test_a_full_page_of_cached_prices_updates_the_control_panel_once(self):
        w=self.window;w.mode='live';now=time.time()
        w.on_catalog(Catalog({'items':[dict(id=i,name=f'Example Item {i}') for i in range(1,7)]}))
        w.rows=[dict(name=f'Example Item {i}',area=dict(x=100,y=100+i*40,width=162,height=35),
            price=dict(quantity=1,mesos=100*i)) for i in range(1,7)]
        def deliver(items):
            for item in items:
                w.service.quote_ready.emit(item.game_id,Quote(item.game_id,item.game_id*100,now,now,20,
                    'MesoWatch','https://meso.watch/','24h'))
        with patch.object(w.service,'observe',side_effect=deliver),patch.object(w,'render') as render,\
                patch.object(w.database_panel,'update_market') as database:
            self.assertTrue(w.request_prices())
            self.assertEqual(set(w.quotes),set(range(1,7)))
            render.assert_called_once();database.assert_called_once()

    def test_single_inventory_card_keeps_its_native_frame_and_title_uncovered(self):
        from types import SimpleNamespace
        from price_lens.annotation_geometry import label_rectangle
        w=self.window;w.mode='live';w.last_screen=time.time();w.rows=[]
        screen=w.screens[w.screen_index].geometry()
        w.reader.image=QImage(screen.width(),screen.height(),QImage.Format.Format_RGBA8888)
        panel=QRect(400,250,236,300);point=QPoint(500,225)
        w.reader.tooltip_title_proof=SimpleNamespace(panel=panel.getRect())
        w.tooltip_result=dict(name='Example Hat',area=dict(x=409,y=262,width=100,height=12),_pointer=[500,225])
        w.draw_labels(time.time(),False)
        row=next(r for r in w.overlay.rows if r.get('kind')=='item')
        self.assertIn(list(panel.getRect()),row['avoid_regions'])
        row={**row,'_width':230,'_cursor_offset':(-91,-3)}
        placed=label_rectangle(row,point+screen.topLeft(),screen.translated(-screen.topLeft()),screen.topLeft())
        self.assertIsNotNone(placed);self.assertFalse(placed.intersects(panel))
        # The OCR bridge may keep a verified popup briefly without a new title
        # proof. A tick must not move our card back over its native frame.
        w.reader.tooltip_title_proof=None;w.tooltip_reference.panel=panel
        with patch('price_lens.ui.still_present',return_value=True):w.draw_labels(time.time(),False)
        row=next(r for r in w.overlay.rows if r.get('kind')=='item')
        self.assertIn(list(panel.getRect()),row['avoid_regions'])
        with patch('price_lens.ui.still_present',return_value=False):w.draw_labels(time.time(),False)
        row=next(r for r in w.overlay.rows if r.get('kind')=='item')
        self.assertNotIn(list(panel.getRect()),row['avoid_regions'])

    def test_verified_full_shop_context_takes_precedence_over_a_truncated_native_crop(self):
        w=self.window;area=dict(x=300,y=200,width=240,height=300)
        w.shop_rows.area=area;w.shop_rows._page_proven=True;w.shop_open=True
        w.reader.shop_context=QRect(300,200,240,35)
        self.assertEqual(w.effective_shop_context(),QRect(300,200,240,300))
        w.shop_rows._page_proven=False
        self.assertEqual(w.effective_shop_context(),QRect(300,200,240,300))
        w.shop_open=False
        self.assertEqual(w.effective_shop_context(),w.reader.shop_context)

    def test_database_is_the_fourth_tab_and_browsing_needs_no_capture_or_price_request(self):
        from test_reference import generation,allow_fixture
        w=self.window;w.reference.store.replace(*generation())
        allow_fixture(w.reference.store)
        w.on_catalog(Catalog({'items':[{'id':1001,'name':'Leaf Earrings','category':'Equipment'}]}))
        w.database_panel.reloaded();w.tabs.setCurrentIndex(w.database_tab_index)
        self.assertEqual(w.database_tab_index,3);self.assertEqual(w.tabs.tabText(3),'Database')
        w.database_panel.query.setText('leaf');w.database_panel.open_first()
        self.assertEqual(w.database_panel.selected.id,1001);self.assertEqual(w.reader.starts,0)
        self.assertEqual(w.service.requests,[])
        self.assertIsNotNone(w.database_panel.detail.summary_card)
        w.tabs.setCurrentIndex(w.search_tab_index);w.search_panel.query.setText('leaf');w.search_panel.choose_first()
        self.assertEqual(w.search_panel.selected.game_id,1001)
        self.assertEqual(w.search_panel.price_view.row,w.database_panel.detail.row)
        self.assertEqual(w.reader.starts,0);self.assertEqual(w.service.requests,[])

    def test_main_and_subnavigation_tabs_remain_centered_at_compact_widths(self):
        from test_reference import generation,allow_fixture
        w=self.window;w.reference.store.replace(*generation());allow_fixture(w.reference.store);w.show()
        for width in (460,509):
            w.resize(width,829);self.app.processEvents()
            bar=w.tabs.tabBar();self.assertLessEqual(abs(bar.geometry().center().x()-w.tabs.rect().center().x()),2)
            w.tabs.setCurrentIndex(w.database_tab_index);QTest.qWait(300);self.app.processEvents()
            p=w.database_panel;self.assertLessEqual(abs(p.kind_bar.geometry().center().x()-p.rect().center().x()),2)
            p.open(('monsters',13));self.app.processEvents()
            self.assertLessEqual(abs(p.detail.tabs.tabBar().geometry().center().x()-p.detail.tabs.rect().center().x()),2)
            w.tabs.setCurrentIndex(w.translation_tab_index);QTest.qWait(300);self.app.processEvents()
            tabs=w.translation_panel.modes;self.assertLessEqual(abs(tabs.tabBar().geometry().center().x()-tabs.rect().center().x()),2)

    def test_database_update_check_lives_in_settings_and_does_not_force_a_redownload(self):
        w=self.window
        self.assertTrue(w.settings_dialog.isAncestorOf(w.database_update_button))
        self.assertFalse(w.database_panel.isAncestorOf(w.database_update_button))
        with patch.object(w.reference,'start') as start:
            w.database_update_button.click();start.assert_called_once_with()

    def test_source_navigation_from_prices_returns_to_the_same_selected_card(self):
        w=self.window;w.show();w.search_panel.query.setText('Example');w.search_panel.choose_first()
        selected=w.search_panel.selected;card=w.search_panel.price_view;card.tabs.setCurrentIndex(1)
        w.open_reference_entry(('quests',10002));self.assertEqual(w.tabs.currentIndex(),w.database_tab_index)
        w.database_panel.go_back();self.app.processEvents()
        self.assertEqual(w.tabs.currentIndex(),w.search_tab_index);self.assertIs(w.search_panel.selected,selected)
        self.assertIs(w.search_panel.price_view,card);self.assertEqual(card.tabs.currentIndex(),1)

    def test_selected_cards_share_stats_prices_sources_and_retain_controls_on_quote_update(self):
        from test_reference import documents,generation,allow_fixture
        from price_lens.reference_details import EntryDetails
        from price_lens.price_widgets import PriceCard
        w=self.window;w.show();docs=documents();w.reference.store.replace(*generation(docs));allow_fixture(w.reference.store)
        raw=Catalog({'items':[dict(id=1001,name='Leaf Earrings',category='Equipment'),dict(id=999,name='Never released')]})
        now=time.time();w.service.cached_values={1001:Quote(1001,5000,now,now,20,'MesoWatch','https://meso.watch/items/1001','24h')}
        w.on_catalog(raw);w.search_panel.query.setText('leaf');w.search_panel.choose_first();self.app.processEvents()
        card=w.search_panel.price_view;self.assertIsInstance(card,EntryDetails);self.assertIsInstance(card.summary_card,PriceCard)
        self.assertIn('Requirements Level 25',' '.join(label.text() for label in card.findChildren(QLabel)))
        self.assertEqual([card.tabs.tabText(i) for i in range(card.tabs.count())],['Overview','Sources'])
        self.assertNotIn(999,[i.game_id for i in w.search_panel.catalog.items])
        self.assertEqual(set(i.game_id for i in w.search_panel.catalog.items),set(w.database_panel.catalog))
        header=card.item_name;watch=card.watch_button
        quote=Quote(1001,6000,now,now,25,'MesoWatch','https://meso.watch/items/1001','24h')
        w.service.deliver_quote(1001,quote);self.assertIs(w.search_panel.price_view,card);self.assertIs(card.item_name,header);self.assertIs(card.watch_button,watch)
        self.assertIn('6,000',card.fields['market'].text());self.assertTrue(card.fields['age'].isHidden())
        self.assertIn('Latest observed sale',card.fields['recent'].text())
        w.database_panel.open(('items',1001));self.assertEqual(card.row,w.database_panel.detail.row)
        self.assertEqual(w.reader.starts,0);self.assertEqual(w.service.requests,[])

    def test_real_panel_keeps_the_slide_running_after_page_layout_updates(self):
        w=self.window;w.resize(460,960);w.show();self.app.processEvents()
        self.app.setProperty('reduceMotion',False)
        for index in (w.exp_tab_index,w.translation_tab_index,0):
            w.tabs.setCurrentIndex(index)
            self.assertTrue(w.tabs.sliding)
            QTest.qWait(80)
            self.assertTrue(w.tabs.sliding)
            self.assertGreater(w.tabs.animation.currentTime(),0)
            QTest.qWait(260)
            for _ in range(10):
                if not w.tabs.sliding:break
                QTest.qWait(25)
            self.assertFalse(w.tabs.sliding)

    def test_display_resolution_fits_at_460_pixel_width(self):
        w=self.window;w.resize(460,960)
        index=w.monitor.currentIndex()
        w.monitor.setItemText(index,'Display 2 · Centre · 1920 × 1080')
        w.update_capture_controls();w.show();self.app.processEvents()
        self.assertEqual(w.width(),460)
        required=w.monitor.fontMetrics().horizontalAdvance(w.monitor.currentText())+46
        self.assertGreaterEqual(w.monitor.width(),required)

    def test_removed_on_top_preference_cannot_trap_a_new_panel(self):
        settings=FakeSettings();settings.values['keep-on-top']=True
        with patch('price_lens.ui.QSettings',return_value=settings):
            fresh=LensWindow(Path.cwd(),Path('unused-cache'))
        try:
            self.assertFalse(fresh.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
            self.assertFalse(settings.values['keep-on-top'])
            self.assertFalse(hasattr(fresh,'pin_check'))
        finally:fresh.close();fresh.deleteLater()

    def test_translation_timings_fit_inline_at_minimum_width(self):
        w=self.window;w.resize(460,960);w.show();w.tabs.setCurrentIndex(w.translation_tab_index)
        QTest.qWait(350);self.app.processEvents()
        panel=w.translation_panel
        for label,spin,value in zip(panel.timing_labels,(panel.scan,panel.linger),(10,5)):
            spin.setValue(value);self.app.processEvents()
            self.assertLess(abs(label.mapTo(panel,label.rect().center()).y()-spin.mapTo(panel,spin.rect().center()).y()),3)
            editor=spin.lineEdit()
            self.assertLess(editor.fontMetrics().horizontalAdvance(editor.text())+8,editor.width())

    def test_display_selector_and_tab_position_remain_stable_on_every_page(self):
        self.window.mode="idle"
        self.window.show();self.app.processEvents()
        height=self.window.height();positions=[]
        for index in (0,1,2,0,2,1):
            self.window.tabs.setCurrentIndex(index);self.app.processEvents()
            bar=self.window.tabs.tabBar()
            positions.append(bar.mapTo(self.window,bar.rect().topLeft()).y())
            self.assertTrue(self.window.monitor.isVisible())
            self.assertTrue(self.window.setup_frame.isVisible())
            self.assertEqual(self.window.height(),height)
        self.assertEqual(len(set(positions)),1)
        self.assertEqual(self.window.reader.starts,0)
        self.assertFalse(any(b.text() in ("Setup help","Preview with examples") for b in self.window.findChildren(QPushButton)))

    def test_rate_display_and_reduce_motion_settings_are_persistent(self):
        self.assertEqual(self.window.exp_panel.display_mode,"percent")
        self.window.exp_display_combo.setCurrentIndex(self.window.exp_display_combo.findData("both"))
        self.assertEqual(self.window.settings.values["exp-display"],"both")
        self.assertEqual(self.window.exp_panel.display_mode,"both")
        self.window.motion_check.setChecked(True)
        self.assertTrue(self.window.settings.values["reduce-motion"])
        self.assertTrue(self.window.overlay.reduce_motion)

    def test_quote_and_age_updates_keep_the_same_price_card(self):
        self.window.on_reading(self.reading(shop_hover=True))
        before=next(iter(self.window.card_views.values()))
        now=time.time()
        for value in (1000,1200):
            self.window.service.deliver_quote(1,Quote(1,value,now,now,20,"Test","","24h"))
            self.assertIs(next(iter(self.window.card_views.values())),before)
        self.assertEqual(before.fields["market"].text(),"1,200 mesos")
        with patch("price_lens.ui.time.time",return_value=now+6):self.window.render()
        self.assertIs(next(iter(self.window.card_views.values())),before)

    def test_shop_thumbnail_uses_exact_item_and_stays_left_of_name(self):
        self.window.on_reading(self.reading(shop_hover=True))
        card=next(iter(self.window.card_views.values()))
        self.assertEqual(card.property('gameItemId'),1)
        self.assertFalse(card.thumbnail.isHidden())
        self.window.resize(460,960);self.window.show();self.app.processEvents()
        self.assertLess(card.thumbnail.x(),card.fields['name'].mapTo(card,card.fields['name'].rect().topLeft()).x())
        self.assertIn(1,[item.game_id for item in self.window.thumbnails.items])

    def test_shop_and_inventory_cards_can_watch_the_exact_item_without_lookup(self):
        w=self.window;w.on_reading(self.reading(shop_hover=True))
        card=next(iter(w.card_views.values()));before=list(w.service.requests)
        self.assertFalse(card.watch_button.isHidden());card.watch_button.click()
        self.assertIn(1,w.watchlist.ids);self.assertTrue(card.watch_button.isChecked())
        self.assertEqual(w.service.requests,before)
        card.watch_button.click();self.assertNotIn(1,w.watchlist.ids)

    def test_inventory_appearing_before_shop_cards_does_not_recreate_the_shop_cards(self):
        w=self.window;w.on_reading(self.reading(shop_hover=True))
        old=next(iter(w.card_views.values()))
        w.tooltip_result={'name':'Example Hat','area':dict(x=100,y=100,width=120,height=16)}
        w.render()
        self.assertIn(old,w.card_views.values())

    def test_missing_hover_card_gets_two_second_gui_grace_without_retaining_its_overlay(self):
        w=self.window;w.show();self.app.processEvents()
        with patch('price_lens.recent_items.time.monotonic',return_value=99):
            w.on_reading(self.reading(shop_hover=False));card=next(iter(w.card_views.values()))
        self.assertTrue(w.overlay.rows)
        w.tooltip_result=None
        for clock in (100,101.999):
            with patch('price_lens.recent_items.time.monotonic',return_value=clock):w.render()
            self.assertIn(card,w.card_views.values());self.assertEqual(w.overlay.rows,[])
            self.assertEqual(w.recent_items.rows.count(),0)
        with patch('price_lens.recent_items.time.monotonic',return_value=102):w.render()
        self.assertNotIn(card,w.card_views.values());self.assertIn(1,w.recent_items.rows_by_id)
        self.assertEqual(w.recent_items.height(),0)
        self.assertEqual(w.cards_stack.spacing(),0)
        start=w.card_area.height()
        for ms in (0,45,90,135,180):
            w.card_area.animation.setCurrentTime(ms);w.recent_items.geometry_animation.setCurrentTime(ms);self.app.processEvents()
            self.assertLessEqual(w.card_area.height()+w.recent_items.height(),max(start,w.recent_items.full_height))

    def test_new_hover_reuses_the_active_card_before_history_grace_expires(self):
        w=self.window;w.on_catalog(Catalog({'items':[dict(id=1,name='Example Hat'),dict(id=2,name='Example Cape')]}))
        w.show();self.app.processEvents()
        with patch('price_lens.recent_items.time.monotonic',return_value=99):
            w.on_reading(self.reading(shop_hover=False));card=next(iter(w.card_views.values()))
        w.tooltip_result=None
        with patch('price_lens.recent_items.time.monotonic',return_value=100):w.render()
        w.tooltip_result={'name':'Example Cape','area':dict(x=100,y=100,width=180,height=20)}
        with patch('price_lens.recent_items.time.monotonic',return_value=100.8):w.render()
        self.assertEqual(len(w.card_views),1);self.assertIs(next(iter(w.card_views.values())),card)
        self.assertEqual(card.property('gameItemId'),2);self.assertIn(1,w.recent_items.rows_by_id)
        self.assertIsNone(w.price_content.outgoing)
        outgoing=w.card_area.outgoing;w.card_area.animation.setCurrentTime(70)
        now=time.time();w.service.deliver_quote(2,Quote(2,1200,now,now,20,'Test','','24h'))
        self.assertIs(w.card_area.outgoing,outgoing);self.assertEqual(w.card_area.animation.currentTime(),70)

    def check_natural_card_retirement(self,*,shop=False,history=False,reduced=False):
        w=self.window;self.app.setProperty('reduceMotion',reduced)
        w.resize(520,840);w.show();self.app.processEvents()
        if history:
            w.on_catalog(Catalog({'items':[dict(id=1,name='Example Hat'),dict(id=2,name='Example Cape')]}))
            w.recent_items.observe([dict(name='Example Cape',price=dict(quantity=1,mesos=900))],w.catalog,time.time())
            w.recent_items.observe([],w.catalog,time.time());w.recent_items.refresh(w.service,w.ttl,time.time())
        w.on_reading(self.reading(shop_hover=shop));QTest.qWait(230)
        self.assertGreater(w.card_area.height(),40)
        original_area=QRect(w.reader.game_area);initial=w.card_area.height();samples=[];retired=[]
        w.card_sightings.changed.connect(lambda:retired.append(time.monotonic()))
        timer=QTimer(w);timer.setInterval(10)
        timer.timeout.connect(lambda:samples.append((w.card_area.height(),w.recent_items.mapTo(w,QPoint()).y())))
        w.rows=[];w.tooltip_result=None;started=time.monotonic();w.render();timer.start()
        deadline=started+3
        while time.monotonic()<deadline:
            QTest.qWait(10)
            if retired and not w.card_views and w.card_area.animation.state()!=w.card_area.animation.State.Running:break
        timer.stop();self.app.processEvents()
        self.assertTrue(retired);self.assertGreaterEqual(retired[0]-started,1.999)
        self.assertFalse(w.card_views);self.assertEqual(w.card_area.height(),0);self.assertEqual(w.card_area.full_height,0)
        self.assertTrue(w.card_list.isHidden());self.assertTrue(w.summary.isHidden())
        self.assertEqual(w.recent_items.mapTo(w,QPoint()).y(),w.card_area.mapTo(w,QPoint()).y())
        self.assertEqual(w.reader.game_area,original_area);self.assertEqual(w.reader.starts,0)
        self.assertTrue(all(height<=initial for height,_ in samples),samples)
        if not reduced:self.assertTrue(any(0<height<initial for height,_ in samples),samples)

    def test_hover_retirement_collapses_the_canvas_through_the_real_event_loop(self):
        self.check_natural_card_retirement()

    def test_shop_retirement_moves_existing_history_up_without_a_locator_change(self):
        self.check_natural_card_retirement(shop=True,history=True)

    def test_natural_retirement_with_reduced_motion_leaves_no_empty_canvas(self):
        self.check_natural_card_retirement(reduced=True)

    def test_scrollbar_changes_do_not_resize_or_finish_the_price_transition(self):
        w=self.window;w.resize(460,840);w.show();self.app.processEvents()
        w.rows=[dict(name='Example Hat',price=dict(quantity=1,mesos=100),
                     area=dict(x=340,y=100+60*index,width=180,height=40)) for index in range(6)]
        w.render();w.card_area.animation.setCurrentTime(180);self.app.processEvents()
        self.assertGreater(w.scroll.verticalScrollBar().maximum(),0)
        width=w.card_area.width()
        w.rows=[];w.tooltip_result=dict(name='Example Hat',area=dict(x=100,y=100,width=180,height=20))
        w.render();w.card_area.animation.pause();w.card_area.animation.setCurrentTime(140)
        for _ in range(5):self.app.processEvents()
        self.assertEqual(w.scroll.verticalScrollBar().maximum(),0)
        with self.subTest(property='content width'):
            self.assertEqual(w.card_area.width(),width)
        with self.subTest(property='outgoing transition frame'):
            self.assertIsNotNone(w.card_area.outgoing)
        with self.subTest(property='transition clock'):
            self.assertEqual(w.card_area.animation.currentTime(),140)

    def test_shop_annotation_identity_survives_an_omitted_neighbor(self):
        w=self.window;w.on_catalog(Catalog({'items':[dict(id=1,name='Example Hat'),dict(id=2,name='Example Cape')]}))
        geometry=w.screens[w.screen_index].geometry();w.reader.image=QImage(geometry.width(),geometry.height(),QImage.Format.Format_RGBA8888)
        w.rows=[dict(name=name,price=dict(quantity=1,mesos=100),area=dict(x=100,y=100+60*index,width=180,height=40),
                     shop_page=1,shop_slot=(40,20+60*index,180,40)) for index,name in enumerate(('Example Hat','Example Cape'))]
        w.draw_labels(time.time(),False);key=w.overlay.rows[-1]['key']
        w.rows=w.rows[1:];w.draw_labels(time.time(),False)
        self.assertEqual(w.overlay.rows[-1]['key'],key);self.assertEqual(w.overlay.rows[-1]['shop_slot'],[40,80,180,40])

    def test_search_transitions_preserve_shop_cards_and_animate_their_return(self):
        self.window.on_reading(self.reading(shop_hover=True))
        self.window.resize(460,960);self.window.show();self.app.processEvents()
        before=dict(self.window.card_views)
        self.window.search_panel.query.setText('Example')
        self.assertTrue(self.window.scroll.isHidden())
        self.window.search_panel.timer.stop();self.window.search_panel.find_items()
        self.assertIn('1 matches',self.window.search_panel.hint.text())
        self.window.search_panel.query.clear()
        self.assertFalse(self.window.scroll.isHidden())
        self.assertEqual(self.window.card_views,before)
        self.assertIsNotNone(self.window.price_content.outgoing)
        deadline=time.monotonic()+1
        while self.window.price_content.outgoing is not None and time.monotonic()<deadline:QTest.qWait(10)
        self.assertIsNone(self.window.price_content.outgoing)

    def test_price_search_works_without_starting_capture(self):
        self.window.mode = "idle"
        self.window.tabs.setCurrentIndex(self.window.search_tab_index)
        panel = self.window.search_panel
        panel.query.setText("Example Hat")
        panel.timer.stop()
        panel.find_items()
        panel.results.setCurrentRow(0)
        self.assertEqual(self.window.service.manual_item.game_id,1)
        self.assertEqual(self.window.reader.starts,0)
        self.window.tabs.setCurrentIndex(self.window.exp_tab_index)
        self.assertIsNone(self.window.service.manual_item)

    def test_watch_toggle_needs_no_price_request_and_marks_a_pending_reference(self):
        from price_lens.domain import Item
        before=list(self.window.service.requests)
        self.window.watchlist.toggle(Item(1,'Example Hat'))
        self.assertEqual(self.window.service.requests,before)
        self.window.on_reading(self.reading(shop_hover=True))
        row=self.window.overlay.rows[0]
        self.assertTrue(row['watched'])
        event=row['watch_event']
        self.window.service.deliver_quote(1,Quote(1,1000,time.time(),time.time(),20,'Test','','24h'))
        self.assertEqual(self.window.overlay.rows[0]['watch_event'],event)
        self.window.watchlist.remove(1)
        self.assertFalse(self.window.overlay.rows[0]['watched'])

    def test_watched_list_opens_without_details_and_collapse_restores_shop(self):
        from price_lens.domain import Item
        w=self.window;w.on_reading(self.reading(shop_hover=True));w.show();self.app.processEvents()
        quote=Quote(1,1000,time.time(),time.time(),20,'MesoWatch','','24h')
        w.service.cached_values={1:quote};w.watchlist.toggle(Item(1,'Example Hat'))
        section=w.search_panel.watched_items;QTest.qWait(230);self.app.processEvents()
        self.assertIsNone(w.search_panel.selected)
        self.assertTrue(w.search_panel.detail_scroll.isHidden())
        self.assertEqual(section.rows.item(0).data(Qt.ItemDataRole.UserRole+1)[0],1000)
        point=section.rows.visualItemRect(section.rows.item(0)).center()
        QTest.mouseClick(section.rows.viewport(),Qt.MouseButton.LeftButton,pos=point)
        self.assertEqual(w.search_panel.selected.game_id,1)
        self.assertTrue(w.scroll.isHidden())
        QTest.mouseClick(section.rows.viewport(),Qt.MouseButton.LeftButton,pos=point)
        self.assertIsNone(w.search_panel.selected)
        self.assertTrue(w.scroll.isHidden())
        QTest.mouseClick(section.rows.viewport(),Qt.MouseButton.LeftButton,pos=point)
        section.set_expanded(False)
        self.assertIsNone(w.search_panel.selected)
        self.assertFalse(w.scroll.isHidden())
        self.assertIsNone(w.service.manual_item)

    def test_watched_section_clips_stable_contents_and_limits_to_three_rows(self):
        from price_lens.domain import Item
        w=self.window;w.show();self.app.processEvents()
        for n in range(5):w.watchlist.toggle(Item(1000000+n,f'Example {n}'))
        section=w.search_panel.watched_items;self.app.processEvents()
        # Delivered animation ticks can lag wall time under load. Establish
        # the actual endpoint before using it as the strict geometry baseline.
        section.body.animation.setCurrentTime(section.body.animation.duration());self.app.processEvents()
        self.assertEqual(section.rows.height(),130)
        self.assertGreater(section.rows.verticalScrollBar().maximum(),0)
        full=section.body.height();contents=section.body.content.height()
        self.assertEqual(full,section.body.full_height)
        section.set_expanded(False);section.body.animation.setCurrentTime(100)
        self.assertGreater(section.body.height(),0);self.assertLess(section.body.height(),full)
        self.assertEqual(section.body.content.height(),contents)
        middle=section.body.height();section.set_expanded(True)
        self.assertEqual(section.body.height(),middle)
        section.body.animation.setCurrentTime(section.body.animation.duration())
        self.assertEqual(section.body.height(),full)
        for expanded in (False,True):
            section.set_expanded(expanded);positions=[]
            for ms in range(0,section.body.animation.duration()+1,20):
                section.body.animation.setCurrentTime(ms);self.app.processEvents()
                positions.append(section.body.content.mapTo(w,QPoint()).y())
            self.assertEqual(len(set(positions)),1,positions)

    def test_watched_item_and_ready_panel_share_an_origin_without_a_collapsed_gap(self):
        from price_lens.domain import Item
        w=self.window;w.resize(509,829);w.render();w.show();self.app.processEvents()
        w.watchlist.toggle(Item(1,'Example Hat'))
        section=w.search_panel.watched_items;QTest.qWait(section.body.animation.duration()+60)
        ready=next(iter(w.card_views.values()))
        ready_top=ready.mapTo(w,QPoint()).y()
        w.search_panel.select_watched(1);self.app.processEvents()
        self.assertEqual(w.search_panel.price_view.mapTo(w,QPoint()).y(),ready_top)
        QTest.qWait(50)
        w.search_panel.select_watched(None);self.app.processEvents()
        self.assertEqual(ready.mapTo(w,QPoint()).y(),ready_top)
        QTest.qWait(180)
        section.set_expanded(False)
        for ms in range(0,section.body.animation.duration()+1,20):
            section.body.animation.setCurrentTime(ms);self.app.processEvents()
            gap=ready.mapTo(w,QPoint()).y()-section.mapTo(w,QPoint()).y()-section.height()
            self.assertEqual(gap,w.prices_layout.spacing())
        self.assertTrue(w.search_panel.detail_scroll.isHidden())
        self.assertFalse(w.scroll.isHidden())
        self.app.setProperty('reduceMotion',True)
        try:
            section.set_expanded(True);w.search_panel.select_watched(1)
            self.assertIsNone(w.price_content.outgoing)
            w.search_panel.select_watched(None)
            self.assertIsNone(w.price_content.outgoing)
        finally:self.app.setProperty('reduceMotion',False)

    def test_market_generation_refreshes_selected_watched_and_paused_shop_cards(self):
        from price_lens.service import PriceService
        from test_snapshot import document
        w=self.window;service=PriceService(Path(self.exp_directory.name)/'refresh.sqlite')
        previous=w.service;w.service=service
        service.quote_ready.connect(w.on_quote);service.state_changed.connect(w.on_price_state)
        now=time.time()
        def update(price,seconds):
            doc=document(now+seconds);doc['items'][0].update(id='basil:00000001',name='Example Hat',price=price)
            service.snapshot.save(doc,now+seconds);service._snapshot_updated()
        try:
            update(100,0);w.on_reading(self.reading(shop_hover=True));w.show();self.app.processEvents()
            item=w.catalog.items[0];w.watchlist.toggle(item)
            w.search_panel.select_watched(item.game_id)
            with patch('price_lens.data.get_json',side_effect=AssertionError('No item/network requests')):
                update(250,1)
                self.assertEqual(w.search_panel.quote.price,250)
                self.assertEqual(w.quote_for(item).price,250)
                reference=w.search_panel.watched_items.rows.item(0).data(Qt.ItemDataRole.UserRole+1)
                self.assertEqual(reference[0],250)
                w.search_panel.watched_items.set_expanded(False)
                w.mode='paused';w.request_prices()
                self.assertEqual(service._screen_demand,[])
                update(400,2)
                self.assertEqual(w.quote_for(item).price,400)
                card=next(iter(w.card_views.values()))
                self.assertTrue(any('400' in label.text() for label in card.findChildren(QLabel)))
                service.snapshot.save(document(now+3),now+3);service._snapshot_updated()
                self.assertIsNone(w.quote_for(item).price)
                self.assertEqual(w.quote_for(item).basis,'Item is absent from the market snapshot')
        finally:
            service.close();service.pool.shutdown(wait=True);w.service=previous

    def test_overlay_sale_age_is_independent_of_cache_age_and_keeps_expiry_warning(self):
        w=self.window;now=time.time()
        quote=Quote(1,1000,now-30,now-720,20,'MesoWatch','','24h')
        with patch('price_lens.ui.time.time',return_value=now):
            w.on_reading(self.reading(shop_hover=True));w.service.deliver_quote(1,quote)
            self.assertIn('Last sale 12m ago',w.overlay.rows[0]['text'])
            self.assertNotIn('30s',w.overlay.rows[0]['text'])
            w.rows=[];w.tooltip_result={'name':'Example Hat','area':dict(x=100,y=100,width=120,height=18),'_pointer':[340,240]}
            w.render();self.assertIn('Last sale 12m ago',w.overlay.rows[-1]['text'])
            w.service.deliver_quote(1,replace(quote,fetched_at=now-w.ttl-1))
            self.assertIn('refresh needed',w.overlay.rows[-1]['text'])
            w.service.deliver_quote(1,replace(quote,observed_at=None))
            self.assertIn('Last sale unknown',w.overlay.rows[-1]['text'])

    def test_windows_starting_state_does_not_request_a_system_chooser(self):
        self.window.mode='idle'
        with patch('price_lens.ui.uses_system_picker',return_value=False):
            self.window.start_capture()
            self.assertEqual(self.window.status_badge.text(),'Starting screen reading')
            self.assertEqual(self.window.capture_info.text(),f'Connecting to {self.window.selected_display()}.')
            self.assertNotIn('behind another window',self.window.capture_info.text())

    def test_wayland_starting_state_still_requests_the_system_picker(self):
        self.window.mode='idle'
        with patch('price_lens.ui.uses_system_picker',return_value=True):
            self.window.start_capture()
            self.assertEqual(self.window.status_badge.text(),'Waiting for screen sharing')
            self.assertIn('system sharing dialog',self.window.capture_info.text())

    def test_no_displays_disables_start_without_a_selectable_placeholder(self):
        with patch('price_lens.ui.QApplication.screens',return_value=[]):
            self.window.refresh_monitors()
        self.assertEqual(self.window.monitor.count(),0)
        self.assertIsNone(self.window.screen_index)
        self.assertFalse(self.window.share.isEnabled())
        self.assertEqual(self.window.status_badge.text(),'No display available')

    def test_catalog_certificate_error_keeps_the_diagnostic_and_explains_the_failure(self):
        message='Item catalog unavailable: [SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate'
        self.window.on_error(0,message)
        self.assertEqual(self.window.last_diagnostic,message)
        self.assertIn('secure item connection',self.window.search_panel.hint.text())

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.exp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.exp_directory.cleanup)
        self.patchers = [patch("price_lens.ui." + name, replacement) for name, replacement in
                         [("Overlay", FakeOverlay), ("PixelReader", FakeReader),
                          ("PriceService", FakeService), ("QSettings", FakeSettings), ("HotkeyManager", FakeHotkeys),
                          ("data_directory", lambda: Path(self.exp_directory.name)),("ThumbnailCache",FakeThumbnails)]]
        for patcher in self.patchers:
            patcher.start()
        self.tray_show = patch("price_lens.tray.QSystemTrayIcon.show")
        self.tray_show.start()
        self.reference_start_patch=patch('price_lens.ui.ReferenceService.start');self.reference_start_patch.start()
        self.addCleanup(self.reference_start_patch.stop)
        # Installed roots qualify for real automatic update checks. These UI
        # fixtures must stay offline; UpdateService has separate fake-feed tests.
        self.updater_start_patch=patch('price_lens.ui.UpdateService.start');self.updater_start_patch.start()
        self.addCleanup(self.updater_start_patch.stop)
        media_patch=patch('price_lens.reference_ui.ReferenceMedia.observe');media_patch.start();self.addCleanup(media_patch.stop)
        self.window = LensWindow(Path.cwd(), Path("unused-cache"))
        from test_reference import documents,generation,allow_fixture
        docs=documents();docs['items.json'].append({'id':1,'name':'Example Hat','category':'Equipment'})
        self.window.reference.store.replace(*generation(docs));allow_fixture(self.window.reference.store)
        self.window.monitor.setCurrentIndex(0)
        self.window.on_catalog(Catalog({"items": [{"id": 1, "name": "Example Hat"}], "scrolls": []}))
        self.window.mode = "live"
        self.window.last_screen = time.time()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.tray_show.stop()

    def reading(self, shop_hover, store=None):
        store = shop_hover if store is None else store
        if not store:
            self.window.reader.shop_context=None
            self.window.shop_rows.reset()  # Closing removes the header/scrollbar pixels in a real frame.
        return {"atMs": 123, "shop": {"area": {"x": 300, "y": 200, "width": 240, "height": 300},
                "rows": [{"name": "Example Hat", "price": {"quantity": 1, "mesos": 100},
                          "area": {"x": 340, "y": 220, "width": 180, "height": 40}}]} if store else None,
                "hover": {"pointer": {"x": 340, "y": 240}} if shop_hover else None,
                "tooltip": {"found": {"name": "Example Hat", "area": {"x": 100, "y": 100, "width": 180, "height": 20}}}}

    def test_hover_is_on_by_default_and_the_import_button_is_gone(self):
        self.assertTrue(self.window.hover_check.isChecked())
        self.assertTrue(self.window.reader.tooltip_enabled)
        self.assertFalse(any("Import MesoWatch" in button.text() for button in self.window.findChildren(QPushButton)))

    def primary_inventory_reading(self):
        w=self.window;w.reader.image.fill(QColor('#24384b'))
        reading=self.reading(False)
        reading['tooltipAssociation']={'state':'inventory-primary','token':'inventory:tab:slot',
            'source':dict(x=300,y=200,width=240,height=300),
            'slot':dict(x=324,y=224,width=36,height=36),
            'panel':dict(x=95,y=95,width=220,height=330),
            'guards':[dict(x=300,y=200,width=240,height=16),dict(x=95,y=95,width=220,height=2)]}
        return reading

    def test_inventory_antialias_blending_survives_capture_and_ui_title_checks(self):
        from PySide6.QtGui import QPainter
        w=self.window;screen=w.screens[w.screen_index].geometry()
        w.reader.image=QImage(screen.width(),screen.height(),QImage.Format.Format_RGBA8888)
        reading=self.primary_inventory_reading();reading['pointerAtRead']=[340,240]
        before=w.reader.image.copy();p=QPainter(before)
        p.fillRect(110,107,30,5,QColor('white'));p.fillRect(110,112,30,1,QColor('#adb2cb'));p.end()
        latest=before.copy();p=QPainter(latest);p.fillRect(110,112,30,1,QColor('#bbc0d4'));p.end()
        w.reader.submitted_image=before;w.reader.image=latest
        w.on_reading(reading)
        self.assertIsNotNone(w.tooltip_context)
        self.assertEqual(w.item_for(w.tooltip_result).game_id,1)
        self.assertEqual(len([r for r in w.overlay.rows if r.get('kind')=='item']),1)
        context=w.tooltip_context
        next_frame=latest.copy();p=QPainter(next_frame);p.fillRect(110,112,30,1,QColor('#c5c9d9'));p.end()
        w.reader.image=next_frame;w.on_image(next_frame)
        self.assertIs(w.tooltip_context,context)
        self.assertIsNotNone(w.tooltip_result)
        # A real changed opaque letter still retires the reference immediately.
        next_frame.setPixelColor(111,108,QColor('red'));w.reader.image=next_frame;w.on_image(next_frame)
        self.assertIsNone(w.tooltip_context);self.assertIsNone(w.tooltip_result)

    def test_primary_inventory_proof_expires_when_pointer_changes_cells(self):
        w=self.window;w.on_reading(self.primary_inventory_reading())
        self.assertEqual(w.tooltip_context.token,'inventory:tab:slot')
        self.assertEqual(w.tooltip_result['_association_token'],'inventory:tab:slot')
        w.on_pointer(350,245);self.assertIsNotNone(w.tooltip_result)
        w.on_pointer(376,245)
        self.assertIsNone(w.tooltip_result);self.assertIsNone(w.tooltip_context)
        self.assertEqual(w.overlay.rows,[])

    def test_native_rejection_cannot_resurrect_a_bridged_comparison(self):
        w=self.window;w.on_reading(self.primary_inventory_reading())
        result=self.reading(False);result['tooltipAssociation']={'state':'rejected'}
        result['tooltip']['found']=None;w.on_reading(result)
        self.assertIsNone(w.tooltip_result);self.assertIsNone(w.tooltip_context)
        self.assertEqual(w.overlay.rows,[])
        self.assertIsNone(w.tooltip_reference.observe(None,w.reader.image,w.reader.pointer))

    def test_old_shop_epoch_cannot_discard_an_independently_current_inventory_proof(self):
        w=self.window;reading=self.primary_inventory_reading()
        reading.update(shopViewportEpoch=w.shop_browsing.epoch-1,_shop_stale=True)
        reading['shop']={'area':dict(x=600,y=500,width=100,height=100),'rows':[]}
        with patch.object(w.observations,'observe_shop',side_effect=AssertionError('Old shop data reached the current page')):
            w.on_reading(reading)
        self.assertEqual(w.tooltip_result['name'],'Example Hat')
        self.assertIsNotNone(w.tooltip_context)
        self.assertEqual(w.rows,[])

    def test_early_inventory_reply_does_not_retire_or_reread_shop_observations(self):
        w=self.window;reading=self.primary_inventory_reading()
        saved=[dict(name='Example Hat',price=dict(quantity=1,mesos=100),
            area=dict(x=340,y=220,width=180,height=40))]
        w.rows=saved;w.shop_open=True
        reading.update(_shop_deferred=True)
        with patch.object(w.observations,'observe_shop',side_effect=AssertionError('Deferred shop must be untouched')):
            w.on_reading(reading)
        self.assertIs(w.rows,saved);self.assertTrue(w.shop_open)
        self.assertEqual(w.tooltip_result['name'],'Example Hat')

    def test_an_old_shop_popup_cannot_be_relabelled_as_inventory_after_scrolling(self):
        w=self.window;reading=self.reading(True)
        reading['shopViewportEpoch']=w.shop_browsing.epoch-1
        w.reader.shop_context=None;w.shop_rows.reset()
        w.on_reading(reading)
        self.assertIsNone(w.tooltip_result)

    def test_retrying_shop_rows_cannot_discard_an_independently_current_inventory_proof(self):
        from price_lens.price_observations import ShopRead
        w=self.window;reading=self.primary_inventory_reading()
        with patch.object(w.observations,'observe_shop',return_value=ShopRead(None,retry=True)):
            w.on_reading(reading)
        self.assertEqual(w.tooltip_result['name'],'Example Hat')
        self.assertIsNotNone(w.tooltip_context)

    def test_lost_shop_clears_cached_routing_before_inventory_reacquisition(self):
        w=self.window;self.prepare_shop_description()
        old=QRect(w.effective_shop_context());w.reader.shop_context=old;w.reader.shop_rect=old
        w.reader.image.fill(QColor('white'));w.on_image(w.reader.image)
        self.assertFalse(w.shop_open)
        self.assertIsNone(w.reader.shop_context);self.assertIsNone(w.reader.shop_rect)
        self.assertIsNone(w.effective_shop_context())

    def test_late_inventory_result_requires_the_same_latest_header_pixels(self):
        w=self.window;reading=self.primary_inventory_reading()
        w.reader.submitted_image=w.reader.image.copy()
        w.reader.image.setPixelColor(310,205,QColor('red'));w.on_reading(reading)
        self.assertIsNone(w.tooltip_result);self.assertIsNone(w.tooltip_context)
        self.assertEqual(w.overlay.rows,[])

    def native_single_tooltip(self,pointer=(340,240)):
        from PySide6.QtGui import QPainter
        w=self.window;reading=self.reading(False)
        w.reader.image.fill(QColor('#eeeeee'))
        painter=QPainter(w.reader.image)
        painter.fillRect(QRect(95,95,220,330),QColor('#464b78'))
        for x in (112,124,139,151,166,183):painter.fillRect(x,105,5,9,QColor('white'))
        painter.end();w.reader.pointer=pointer
        reading['pointerAtRead']=list(pointer)
        return reading

    def test_translucent_inventory_title_background_does_not_delay_a_current_item(self):
        from PySide6.QtGui import QPainter
        w=self.window;reading=self.native_single_tooltip()
        w.reader.submitted_image=w.reader.image.copy()
        painter=QPainter(w.reader.image);painter.fillRect(270,102,8,16,QColor('#354b73'));painter.end()
        w.on_reading(reading)
        self.assertEqual(w.tooltip_result['name'],'Example Hat')

    def test_new_title_ink_cannot_hide_in_a_translucent_background_change(self):
        from PySide6.QtGui import QPainter
        w=self.window;reading=self.native_single_tooltip()
        w.reader.submitted_image=w.reader.image.copy()
        painter=QPainter(w.reader.image);painter.fillRect(270,102,8,16,QColor('white'));painter.end()
        w.on_reading(reading)
        self.assertIsNone(w.tooltip_result)

    def test_a_far_old_popup_is_not_attached_to_a_new_equipment_pointer(self):
        w=self.window;reading=self.native_single_tooltip((600,500))
        # The old 640px title search would accept this stale popup even though
        # its native panel has no proximity to the new source item.
        w.on_reading(reading)
        self.assertIsNone(w.tooltip_result)

    def test_new_frame_checks_only_the_bound_source_and_name_guards(self):
        w=self.window;w.on_reading(self.primary_inventory_reading())
        w.reader.image.setPixelColor(740,700,QColor('red'));w.on_image(w.reader.image)
        self.assertIsNotNone(w.tooltip_result)
        w.reader.image.setPixelColor(310,205,QColor('red'));w.on_image(w.reader.image)
        self.assertIsNone(w.tooltip_result);self.assertIsNone(w.tooltip_context)
        self.assertEqual(w.overlay.rows,[])

    def test_translation_store_context_is_current_clipped_and_in_full_frame_coordinates(self):
        w=self.window;geometry=w.screens[w.screen_index].geometry()
        dpr=w.screens[w.screen_index].devicePixelRatio()
        w.reader.image=QImage(round(geometry.width()*dpr),round(geometry.height()*dpr),QImage.Format.Format_RGBA8888)
        w.reader.image.fill(QColor('navy'));w.reader.last_frame=time.monotonic()
        w.reader.auto_active=False;w.reader.crop=QRect(100,50,500,500)
        w.reader.manual_game_footer=QRect(100,510,500,40)
        w.reader.shop_context=QRect(30,40,200,160);w.shop_open=True
        w.chat.watching=True
        with patch.object(w.chat,'request') as request:
            w.submit_chat_frame()
            self.assertEqual(request.call_args.kwargs['hud'],w.reader.manual_game_footer)
            self.assertEqual(request.call_args.kwargs['contexts'],[
                {'role':'store','box':[130,90,200,160],'verified':True}])
            w.shop_open=False;w.submit_chat_frame()
            self.assertEqual(request.call_args.kwargs['contexts'],[])
            w.shop_open=True;w.reader.shop_context=QRect(450,450,200,160);w.submit_chat_frame()
            self.assertEqual(request.call_args.kwargs['contexts'],[
                {'role':'store','box':[550,500,50,50],'verified':True}])

    def test_chat_and_pickups_exclude_only_current_visible_control_panel_paint(self):
        w=self.window;w.resize(506,914);w.show();self.app.processEvents()
        screen=w.screens[w.screen_index].geometry()
        image=QImage(screen.width(),screen.height(),QImage.Format.Format_RGB888);image.fill(QColor('navy'))
        w.reader.image=image;w.reader.auto_active=False;w.reader.crop=image.rect()
        w.chat.watching=True
        with patch.object(w,'mapToGlobal',return_value=QPoint(0,0)),\
             patch('price_lens.owned_capture.time.monotonic',return_value=1):
            self.assertEqual(w.owned_capture_exclusions(),[])
        x,y=screen.width()-w.width()-20,40
        painter=QPainter(image);painter.drawImage(x,y,w.grab().toImage());painter.end()
        expected=QRect(x,y,w.width(),w.height()).intersected(image.rect())
        with patch.object(w,'mapToGlobal',return_value=QPoint(0,0)),\
             patch('price_lens.owned_capture.time.monotonic',return_value=2.1),\
             patch.object(w.chat,'request') as request:
            w.reader.image=image;w.reader.last_frame=2.1
            w.submit_chat_frame()
            self.assertIn(list(expected.getRect()),request.call_args.args[2])
            self.assertNotIn([0,0,w.width(),w.height()],request.call_args.args[2])
            self.assertIn(expected,w.pickup_capture_exclusions())

    def test_automatic_game_area_is_enabled_by_default(self):
        self.assertTrue(self.window.auto_area_check.isChecked())
        self.assertTrue(self.window.reader.auto_enabled)

    def test_update_handoff_closes_windows_helpers_but_keeps_compatible_linux_sharing(self):
        from price_lens import __version__
        w=self.window;w.updates.offer={'manifest':{'capture_compatible_from':[__version__]}}
        for name,keep in (('windows-installer-x64',False),('linux-arch-x64',True)):
            w.updates.target=replace(w.updates.target,name=name)
            with patch.object(w.updates,'commit',return_value=True) as commit,patch.object(w,'close') as close:
                w.install_update_restart();commit.assert_called_once_with(True);close.assert_called_once()
                self.assertEqual(w.keep_capture,keep)
        w.keep_capture=False

    def test_market_updates_on_launch_with_the_selected_global_interval(self):
        self.assertTrue(self.window.service.refresh_snapshot)
        self.assertEqual(self.window.service.interval,self.window.ttl)
        self.window.ttl_combo.setCurrentIndex(0)
        self.assertEqual(self.window.service.interval,300)
        self.assertFalse(hasattr(self.window,'bulk_check'))

    def test_lost_game_area_hides_labels_and_stops_price_requests(self):
        self.window.on_reading(self.reading(shop_hover=True))
        count=len(self.window.service.requests)
        self.window.reader.game_area=None
        self.window.reader.area_changed.emit()
        self.assertEqual(self.window.rows,[])
        self.assertEqual(self.window.overlay.rows,[])
        self.assertEqual(self.window.status_badge.text(),"Looking for Classic World")
        self.window.on_reading(self.reading(shop_hover=True))
        self.window.tick()
        self.assertEqual(len(self.window.service.requests),count)
        self.assertEqual(self.window.overlay.rows,[])

    def test_auto_area_toggle_is_saved_without_restarting_capture(self):
        self.window.auto_area_check.setChecked(False)
        self.assertFalse(self.window.settings.values["auto-game-area"])
        self.assertFalse(self.window.reader.auto_active)
        self.assertEqual(self.window.reader.starts,0)

    def test_store_hover_never_draws_a_duplicate_inventory_label(self):
        self.window.on_reading(self.reading(shop_hover=True))
        self.assertIsNone(self.window.tooltip_result)
        self.assertEqual(len(self.window.overlay.rows), 1)

    def test_description_disappearance_restores_market_labels_without_waiting_for_ocr(self):
        self.window.on_reading(self.reading(shop_hover=True))
        self.window.rows=[{**r,'covered':True,'reference_only':True,'price':None} for r in self.window.rows]
        self.window.shop_tooltip_rect=QRect(300,200,220,200)
        self.window.reader.image.fill(QColor('#171c25'))
        count=len(self.window.service.requests)
        self.window.on_image(self.window.reader.image)
        self.assertNotIn('obscured',self.window.overlay.rows[0])
        self.assertNotIn('occlusion',self.window.overlay.rows[0])
        self.assertEqual(len(self.window.service.requests),count)

    def test_inventory_hover_outside_store_list_can_show_its_price(self):
        self.window.reader.pointer = (100, 100)
        self.window.on_reading(self.reading(shop_hover=False))
        self.assertEqual(self.window.tooltip_result["name"], "Example Hat")
        self.assertEqual(len(self.window.overlay.rows), 1)

    def test_linked_item_far_from_pointer_requires_a_visible_description_panel(self):
        from PySide6.QtGui import QPainter
        w=self.window;w.reader.pointer=(10,790)
        reading=self.reading(shop_hover=False)
        found=reading['tooltip']['found'];found['area']=dict(x=690,y=100,width=100,height=18);found['pinned']=True
        self.window.on_reading(reading);self.assertIsNone(w.tooltip_result)
        painter=QPainter(w.reader.image);painter.fillRect(675,80,125,260,QColor('#464b78'));painter.end()
        w.on_reading(reading)
        self.assertIsNotNone(w.tooltip_result)
        self.assertNotIn('follow_pointer',w.overlay.rows[-1])
        self.assertEqual(w.overlay.rows[-1]['name'],'Example Hat')

    def test_absent_tooltip_enums_do_not_interrupt_shop_close_or_next_inventory_read(self):
        reading = self.reading(shop_hover=True)
        reading['tooltip'] = 'not_found'
        reading['hover']['tooltip'] = 'not_found'
        self.window.on_reading(reading)
        self.assertTrue(self.window.shop_open)
        closed = self.reading(shop_hover=False)
        closed['tooltip'] = 'not_found'
        self.window.on_reading(closed)
        self.assertFalse(self.window.shop_open)
        self.window.reader.pointer = (100, 100)
        self.window.on_reading(self.reading(shop_hover=False))
        self.assertEqual(self.window.tooltip_result['name'], 'Example Hat')

    def test_disabling_setting_stops_tooltip_processing_and_clears_label(self):
        self.window.reader.pointer = (100, 100)
        self.window.on_reading(self.reading(shop_hover=False))
        self.window.set_hover(False)
        self.assertIsNone(self.window.tooltip_result)
        self.assertFalse(self.window.reader.tooltip_enabled)
        self.assertFalse(self.window.settings.values["tooltip-prices"])

    def test_empty_or_unknown_tooltip_candidates_never_draw_floating_prices(self):
        self.window.reader.pointer = (100, 100)
        for name in (None, "", "Random scenery OCR"):
            with self.subTest(name=name):
                reading = self.reading(shop_hover=False)
                reading["tooltip"]["found"]["name"] = name
                self.window.on_reading(reading)
                self.assertIsNone(self.window.tooltip_result)
                self.assertEqual(len(self.window.overlay.rows), 0)

    def test_tooltip_without_pointer_or_far_from_it_is_ignored(self):
        self.window.reader.pointer = None
        self.window.on_reading(self.reading(shop_hover=False))
        self.assertIsNone(self.window.tooltip_result)
        self.window.reader.pointer = (1500, 1500)
        self.window.on_reading(self.reading(shop_hover=False))
        self.assertIsNone(self.window.tooltip_result)

    def test_tall_tooltip_name_above_pointer_is_valid(self):
        self.window.reader.pointer = (100, 600)
        self.window.on_reading(self.reading(shop_hover=False))
        self.assertEqual(self.window.tooltip_result["name"], "Example Hat")
        self.assertEqual(len(self.window.overlay.rows), 1)

    def test_named_bandana_and_greater_scroll_use_the_actual_item_name(self):
        self.window.on_catalog(Catalog({"items": [{"id": 1002013, "name": "Blue Bandana", "category": "Equipment"}],
                                       "scrolls": [{"id": 2040002, "name": "Hat Accuracy Scroll: Greater", "tier": "Greater"}]}))
        self.window.reader.pointer = (100, 650)
        for name, expected in [("Blue Bandana", "Blue Bandana"),
                               ("Hat Accuracy Scroll:Greater", "Hat Accuracy Scroll: Greater")]:
            with self.subTest(name=name):
                reading = self.reading(shop_hover=False)
                reading["tooltip"]["found"]["name"] = name
                self.window.on_reading(reading)
                self.assertEqual(self.window.overlay.rows[-1]["name"], expected)

    def test_native_shop_stats_popup_keeps_shop_prices_visible(self):
        reading = self.reading(shop_hover=True)
        reading["hover"]["tooltip"] = {"found": reading["tooltip"]["found"]}
        self.window.on_reading(reading)
        self.assertTrue(self.window.shop_open)
        self.assertEqual(len(self.window.overlay.rows), 1)
        self.assertEqual(self.window.overlay.rows[0]["kind"],"shop")
        self.window.on_reading(self.reading(shop_hover=True))
        self.assertTrue(self.window.shop_open)
        self.assertEqual(len(self.window.overlay.rows), 1)

    def test_price_entry_keeps_shop_labels_and_only_exports_current_form_geometry(self):
        from price_lens.reader_request import SubmittedRequest
        w=self.window;reading=self.reading(shop_hover=True);w.on_reading(reading)
        cards=dict(w.card_views);saved=list(w.rows)
        with patch('price_lens.shop_dialog.price_entry_dialog',return_value=QRect(450,260,232,139)):
            w.reader.image=w.reader.image.copy()
            w.on_image(w.reader.image)
            self.assertTrue(w.shop_price_entry.blocking)
            labels=[row for row in w.overlay.rows if row['kind']=='shop']
            self.assertTrue(labels);self.assertTrue(all(row['shop_entry']==[450,260,232,139] for row in labels))
            self.assertEqual(w.rows,saved);self.assertEqual(w.recent_items.rows.count(),0)
            self.assertTrue(all(w.card_views[key] is card for key,card in cards.items()))
            with patch.object(w.observations,'observe_shop',side_effect=AssertionError('The form is not a shop page')):
                w.on_reading(reading)
            self.assertEqual(w.rows,saved)
        with patch('price_lens.shop_dialog.price_entry_dialog',return_value=None):
            w.reader.image=w.reader.image.copy()
            w.on_image(w.reader.image);closed_at=w.shop_price_entry.closed_at
            self.assertIsNotNone(closed_at)
            for started,blocking in ((closed_at-1,True),(closed_at+.01,False)):
                request=SubmittedRequest('prices',w.reader.image,w.reader.pointer,1,0,started,
                    shop_epoch=w.shop_browsing.epoch)
                w.on_reading({**reading,'_submitted_request':request})
                self.assertEqual(w.shop_price_entry.blocking,blocking)
                labels=[row for row in w.overlay.rows if row['kind']=='shop']
                self.assertTrue(labels);self.assertTrue(all(row['shop_entry'] is None for row in labels))
                if blocking:self.assertEqual(w.rows,saved)
                self.assertEqual([(row['name'],row.get('price')) for row in w.rows],
                                 [(row['name'],row.get('price')) for row in saved])

    def test_price_entry_cannot_keep_labels_when_the_shop_container_disappears(self):
        w=self.window;w.on_reading(self.reading(shop_hover=True))
        with patch('price_lens.shop_dialog.price_entry_dialog',return_value=QRect(450,260,232,139)):
            w.reader.image=w.reader.image.copy();w.on_image(w.reader.image)
            self.assertTrue(w.shop_price_entry.blocking);self.assertTrue(w.rows)
        missing=w.reader.image.copy();missing.fill(QColor('#374963'));w.reader.image=missing
        with patch('price_lens.shop_dialog.price_entry_dialog',return_value=None):w.on_image(missing)
        self.assertFalse(w.shop_open);self.assertFalse(w.shop_price_entry.blocking)
        self.assertFalse(any(row['kind']=='shop' for row in w.overlay.rows))

    def test_a_form_first_seen_in_a_reader_reply_cannot_mutate_shop_observations(self):
        w=self.window;reading=self.reading(shop_hover=True);w.on_reading(reading)
        saved=list(w.rows)
        with patch('price_lens.shop_dialog.price_entry_dialog',return_value=QRect(450,260,232,139)),patch.object(
                w.observations,'observe_shop',side_effect=AssertionError('The form is not a shop read')):
            w.reader.image=w.reader.image.copy();w.on_reading(reading)
        self.assertTrue(w.shop_price_entry.blocking);self.assertEqual(w.rows,saved)

    def test_add_item_fade_geometry_uses_capture_scale_and_crop_and_needs_an_open_shop(self):
        from types import SimpleNamespace
        w=self.window;w.on_reading(self.reading(shop_hover=True))
        screen=w.screens[w.screen_index].geometry()
        w.reader.image=QImage(screen.width()*2,screen.height()*2,QImage.Format.Format_RGBA8888)
        w.reader.crop=QRect(100,200,900,900)
        w.shop_price_entry.rectangle=QRect(450,260,232,139)
        screens=list(w.screens)
        screens[w.screen_index]=SimpleNamespace(geometry=lambda:screen,devicePixelRatio=lambda:2)
        with patch.object(w,'screens',screens):w.draw_labels(time.time(),False)
        labels=[row for row in w.overlay.rows if row['kind']=='shop']
        self.assertTrue(labels);self.assertTrue(all(row['shop_entry']==[275,230,116,70] for row in labels))
        w.shop_open=False
        with patch.object(w,'screens',screens):w.draw_labels(time.time(),False)
        self.assertTrue(all(row.get('shop_entry') is None for row in w.overlay.rows))

    def test_paired_inventory_card_avoids_both_complete_description_panels(self):
        w=self.window;w.reader.pointer=(340,190);w.reader.image.fill(QColor('#24384b'))
        reading={'atMs':123,'shop':None,'hover':None,
            'tooltip':{'found':{'name':'Example Hat','area':dict(x=58,y=231,width=180,height=12)}},
            'tooltipAssociation':dict(state='inventory-primary',version=2,token='source:slot',
                sourceKind='inventory',layout='primary-left',source=dict(x=300,y=150,width=230,height=300),
                slot=dict(x=324,y=174,width=36,height=36),panel=dict(x=50,y=220,width=240,height=330),
                comparison=dict(x=292,y=220,width=240,height=300),pointer=dict(x=340,y=190),
                cursor=dict(x=334,y=184,width=32,height=36),guards=[dict(x=300,y=150,width=230,height=20)])}
        w.on_reading(reading)
        item=next(row for row in w.overlay.rows if row['kind']=='item')
        protected=[QRect(*rect) for rect in item['avoid_regions']]
        self.assertIn(QRect(50,220,240,330),protected)
        self.assertIn(QRect(292,220,240,300),protected)
        self.assertIn(QRect(300,150,230,300),protected)

    def prepare_shop_description(self,*,covered=True):
        from PySide6.QtGui import QPainter
        w=self.window;w.on_catalog(Catalog({'items':[dict(id=1,name='Example Hat'),dict(id=2,name='Example Cape')]}))
        w.reader.image.fill(QColor('#223344'));w.show();self.app.processEvents()
        def reading():
            value=self.reading(shop_hover=True)
            value['shop']['rows'].append(dict(name='Example Cape',price=dict(quantity=1,mesos=200),area=dict(x=340,y=280,width=180,height=40)))
            return value
        plain=reading();w.on_reading(plain);QTest.qWait(200);original=w.reader.image.copy();cards=dict(w.card_views)
        title=dict(x=500 if covered else 570,y=210,width=180,height=20)
        painter=QPainter(w.reader.image);painter.fillRect(480 if covered else 550,190,260 if covered else 240,260,QColor('#464b78'))
        painter.setPen(QColor('white'));painter.drawText(QRect(*(title[key] for key in ('x','y','width','height'))),Qt.AlignmentFlag.AlignVCenter,'Example Hat');painter.end()
        hovered=reading();hovered['hover']['tooltip']={'found':dict(name='Example Hat',area=title)}
        if covered:
            for row in hovered['shop']['rows']:row.update(name=None,price=None,covered=True)
        self.initial_shop_transition=w.card_area.outgoing
        w.on_reading(hovered)
        return original,cards,hovered

    def test_shop_hover_keeps_the_same_cards_and_only_shop_overlays(self):
        w=self.window;original,cards,_=self.prepare_shop_description()
        self.assertIsNotNone(w.shop_description);self.assertIsNone(w.tooltip_result)
        self.assertEqual([card.property('gameItemId') for card in w.card_views.values() if not card.isHidden()],[1,2])
        self.assertEqual(w.service.visible,[1,2]);self.assertEqual(w.recent_items.rows.count(),0)
        self.assertEqual(len(w.overlay.rows),2);self.assertTrue(all(row['kind']=='shop' for row in w.overlay.rows))
        self.assertTrue(all(w.card_views[key] is card and not card.isHidden() for key,card in cards.items()))
        self.assertIs(w.card_area.outgoing,self.initial_shop_transition)
        w.reader.image=original;w.on_image(original)
        self.assertIsNone(w.shop_description);self.assertEqual(w.recent_items.rows.count(),0)
        self.assertTrue(all(w.card_views[key] is card and not card.isHidden() for key,card in cards.items()))
        self.assertEqual(len(w.overlay.rows),2);self.assertIs(w.card_area.outgoing,self.initial_shop_transition)

    def test_brief_native_shop_ocr_miss_cannot_turn_its_description_into_an_inventory_card(self):
        w=self.window;_,cards,reading=self.prepare_shop_description()
        w.reader.shop_context=None
        reading['tooltip']=reading['hover']['tooltip']
        reading['hover']=None;reading['shop']=None
        w.on_reading(reading)
        self.assertTrue(w.shop_open);self.assertIsNone(w.tooltip_result)
        self.assertEqual(len(w.overlay.rows),2)
        self.assertTrue(all(row['kind']=='shop' for row in w.overlay.rows))
        self.assertTrue(all(w.card_views[key] is card and not card.isHidden() for key,card in cards.items()))

    def test_an_unchanged_proven_description_reuses_geometry_without_searching_the_frame_again(self):
        w=self.window;_,cards,reading=self.prepare_shop_description()
        bounds=QRect(w.shop_tooltip_rect)
        with patch('price_lens.ui.description_bounds',side_effect=AssertionError('Unchanged geometry was searched again')):
            w.on_reading(reading)
        self.assertEqual(w.shop_tooltip_rect,bounds)
        self.assertEqual(len(w.overlay.rows),2)
        self.assertTrue(all(w.card_views[key] is card for key,card in cards.items()))

    def test_known_shop_rows_skip_name_recovery_but_an_unknown_scrolled_row_requests_it(self):
        w=self.window;self.prepare_shop_description(covered=False)
        self.assertFalse(w.needs_shop_name_read((340,240)))
        self.assertFalse(w.needs_shop_name_read((700,550)))
        w.shop_browsing._advance();w.on_shop_viewport_changed()
        self.assertTrue(w.needs_shop_name_read((340,240)))

    def test_recovery_includes_unknown_neighbours_when_the_hovered_row_is_known(self):
        w=self.window;self.prepare_shop_description(covered=False)
        self.assertIsNotNone(w.item_for(w.rows[0]))
        w.rows[1]={'area':dict(w.rows[1]['area']),'name':None,'price':None,'covered':True}
        self.assertTrue(w.needs_shop_name_read((340,240)))
        self.assertTrue(w.needs_shop_name_read((700,550)))

    def test_known_name_without_an_asking_line_can_request_component_recovery(self):
        w=self.window;self.prepare_shop_description(covered=False)
        row=w.rows[1];price=dict(quantity=1,mesos=200)
        row.update(nameOnly=True,price=None)
        self.assertTrue(w.needs_shop_name_read((340,240)))
        row['price']=price
        self.assertFalse(w.needs_shop_name_read((340,240)))

    def test_a_known_subset_cannot_disable_recovery_for_slots_omitted_beneath_a_pane(self):
        w=self.window;self.prepare_shop_description()
        w.rows=[w.rows[0]]
        self.assertIsNotNone(w.item_for(w.rows[0]))
        self.assertFalse(w.shop_browsing.pending)
        self.assertTrue(w.needs_shop_name_read((340,240)))
        self.assertTrue(w.needs_shop_name_read((700,550)))
        w.shop_tooltip_rect=None;w.observations.occlusion_trail.clear()
        self.assertFalse(w.needs_shop_name_read((340,240)))

    def test_unread_shop_page_keeps_shop_description_out_of_inventory_pricing(self):
        w=self.window;_,_,reading=self.prepare_shop_description()
        area=QRect(w.effective_shop_context())
        w.observations.viewport_changed();w.reader.shop_context=None
        w.observations.shop_tooltip_from_shop=False
        self.assertFalse(w.shop_rows._page_proven);self.assertEqual(w.rows,[])
        reading['tooltip']=reading['hover']['tooltip'];reading['hover']=None;reading['shop']=None
        w.on_reading(reading)
        self.assertTrue(w.shop_open);self.assertEqual(w.effective_shop_context(),area)
        self.assertIsNone(w.tooltip_result)
        self.assertFalse(any(row.get('kind')=='item' for row in w.overlay.rows))

    def test_loaded_shop_labels_and_cards_survive_an_unlocated_description_with_unchanged_neighbours(self):
        from PySide6.QtGui import QPainter
        w=self.window;w.on_catalog(Catalog({'items':[dict(id=1,name='Example Hat'),dict(id=2,name='Example Cape')]}))
        w.reader.image.fill(QColor('#223344'));value=self.reading(shop_hover=True)
        value['shop']['rows'].append(dict(name='Example Cape',price=dict(quantity=1,mesos=200),
            area=dict(x=340,y=280,width=180,height=40)))
        painter=QPainter(w.reader.image)
        painter.fillRect(300,200,240,300,QColor('#cad5df'))
        for y in (220,280):
            painter.fillRect(345,y+5,80,6,QColor('black'))
            painter.fillRect(345,y+24,50,6,QColor('black'))
        painter.end();w.on_reading(value);QTest.qWait(220)
        keys=[row['key'] for row in w.overlay.rows];cards=dict(w.card_views)
        self.assertEqual(len(keys),2)
        image=w.reader.image.copy();painter=QPainter(image)
        painter.fillRect(335,278,200,110,QColor('#464b78'));painter.end()
        w.reader.pointer=(600,400);w.reader.image=image
        for _ in range(6):w.on_image(image)
        self.assertEqual([row['key'] for row in w.overlay.rows],keys)
        self.assertTrue(all(row['kind']=='shop' for row in w.overlay.rows))
        self.assertEqual(len(w.rows),2);self.assertIsNone(w.rows[1]['price'])
        self.assertTrue(w.rows[1]['reference_only'])
        self.assertTrue(all(w.card_views[key] is card and not card.isHidden() for key,card in cards.items()))
        self.assertEqual(w.recent_items.rows.count(),0)

    def test_lingering_shop_description_does_not_become_a_card_when_pointer_leaves_the_list(self):
        w=self.window;_,cards,reading=self.prepare_shop_description(covered=False)
        self.assertTrue(w.observations.shop_tooltip_from_shop)
        w.reader.pointer=(650,300)
        reading['pointerAtRead']=[650,300];reading['tooltip']=reading['hover']['tooltip'];reading['hover']=None
        w.on_reading(reading)
        self.assertIsNone(w.tooltip_result)
        self.assertTrue(all(row['kind']=='shop' for row in w.overlay.rows))
        self.assertTrue(all(w.card_views[key] is card and not card.isHidden() for key,card in cards.items()))

    def test_a_late_unpinned_title_cannot_return_after_its_native_pixels_disappear(self):
        w=self.window;original,_,reading=self.prepare_shop_description(covered=False)
        w.reader.submitted_image=w.reader.image.copy();w.reader.image=original
        w.reader.pointer=(650,300);w.on_image(original)
        reading['pointerAtRead']=[650,300];reading['tooltip']=reading['hover']['tooltip'];reading['hover']=None
        w.on_reading(reading)
        self.assertIsNone(w.tooltip_result)
        self.assertTrue(all(row['kind']=='shop' for row in w.overlay.rows))

    def test_visible_clipped_listing_can_use_its_full_native_description_without_an_extra_card(self):
        from PySide6.QtGui import QPainter
        w=self.window
        w.on_catalog(Catalog({'items':[dict(id=1,name='Example Hat of Attack'),dict(id=3,name='Example Hat of Defense')]}))
        w.reader.image.fill(QColor('#223344'))
        reading=self.reading(shop_hover=True)
        reading['shop']['rows'][0]['name']='Example Hat...'
        w.on_reading(reading)
        self.assertNotIn('_item_id',w.rows[0])
        original=w.reader.image.copy()
        painter=QPainter(w.reader.image);painter.fillRect(480,190,260,260,QColor('#464b78'))
        painter.setPen(QColor('white'));painter.drawText(500,224,'Example Hat of Defense');painter.end()
        reading['hover']['tooltip']={'found':dict(name='Example Hat of Defense',area=dict(x=500,y=210,width=190,height=20))}
        w.on_reading(reading)
        self.assertEqual(w.rows[0]['_item_id'],3)
        self.assertEqual(w.item_for(w.rows[0]).name,'Example Hat of Defense')
        self.assertEqual(len(w.overlay.rows),1);self.assertEqual(w.overlay.rows[0]['kind'],'shop')
        self.assertEqual(w.service.visible,[3])
        key=w.overlay.rows[0]['key'];page=w.shop_rows.page_revision
        w.reader.image=original.copy();reading['hover']['tooltip']={}
        w.on_reading(reading)
        self.assertEqual(w.rows[0]['_item_id'],3)
        self.assertEqual(w.overlay.rows[0]['key'],key);self.assertEqual(w.shop_rows.page_revision,page)
        painter=QPainter(w.reader.image);painter.fillRect(480,190,260,260,QColor('#464b78'))
        painter.setPen(QColor('white'));painter.drawText(500,224,'Example Hat of Attack');painter.end()
        reading['hover']['tooltip']={'found':dict(name='Example Hat of Attack',area=dict(x=500,y=210,width=190,height=20))}
        w.on_reading(reading)
        self.assertEqual(w.rows[0]['_item_id'],1)
        self.assertEqual(w.service.visible,[1]);self.assertEqual(len(w.overlay.rows),1)


    def test_shop_quote_refresh_updates_existing_cards_without_a_hover_transition(self):
        w=self.window;self.prepare_shop_description(covered=False)
        card=next(card for card in w.card_views.values() if card.property('gameItemId')==1)
        self.assertIn('100',card.fields['store'].text())
        outgoing=w.card_area.outgoing;structure=w.screen_card_structure
        now=time.time();w.service.deliver_quote(1,Quote(1,2400,now,now,20,'Test','','24h'))
        self.assertIs(next(card for card in w.card_views.values() if card.property('gameItemId')==1),card)
        self.assertIs(w.card_area.outgoing,outgoing);self.assertEqual(w.screen_card_structure,structure)
        self.assertEqual(card.fields['market'].text(),'2,400 mesos')


    def test_covered_shop_item_receives_a_new_snapshot_price_without_an_initial_quote(self):
        w=self.window;self.prepare_shop_description();w.quotes.clear()
        card=next(card for card in w.card_views.values() if card.property('gameItemId')==1)
        outgoing=w.card_area.outgoing;motion_time=w.card_area.animation.currentTime()
        moving=w.card_area.animation.state()==w.card_area.animation.State.Running
        requests=list(w.service.requests)
        snapshot=type('Snapshot',(),{'meta':{'checked_at':1},'rows':{}})()
        w.service.snapshot=snapshot;lookups=[]
        def reference(item):lookups.append(item.game_id);return w.service.cached(item)
        w.service.reference=reference
        now=time.time();w.service.cached_values={1:Quote(1,1400,now,now,20,'Test','','24h')}
        w.on_price_state()
        self.assertIn(1,lookups);self.assertEqual(card.fields['market'].text(),'1,400 mesos')
        self.assertIs(w.card_area.outgoing,outgoing)
        # A first quote can change height; an existing transition must keep its progress.
        if moving:self.assertEqual(w.card_area.animation.currentTime(),motion_time)
        snapshot.meta['checked_at']=2;w.service.cached_values[1]=Quote(1,2500,now,now,20,'Test','','24h')
        w.on_price_state()
        self.assertIs(next(card for card in w.card_views.values() if card.property('gameItemId')==1),card)
        self.assertEqual(card.fields['market'].text(),'2,500 mesos');self.assertEqual(w.service.requests,requests)
        self.assertEqual(w.recent_items.rows.count(),0)


    def test_hovering_different_shop_rows_keeps_the_list_and_does_not_make_history(self):
        from PySide6.QtGui import QPainter
        w=self.window;original,cards,reading=self.prepare_shop_description()
        w.reader.pointer=(340,300);reading['pointerAtRead']=[340,300]
        reading['hover']['pointer']={'x':340,'y':300};reading['hover']['tooltip']['found']['name']='Example Cape'
        painter=QPainter(w.reader.image);painter.fillRect(500,210,180,20,QColor('#464b78'));painter.setPen(QColor('white'))
        painter.drawText(QRect(500,210,180,20),Qt.AlignmentFlag.AlignVCenter,'Example Cape');painter.end()
        w.on_reading(reading)
        self.assertEqual(w.shop_description['name'],'Example Cape')
        self.assertTrue(all(w.card_views[key] is card and not card.isHidden() for key,card in cards.items()))
        self.assertTrue(all(row['kind']=='shop' for row in w.overlay.rows))
        w.reader.image=original;w.on_image(original)
        self.assertIsNone(w.shop_description);self.assertEqual(w.recent_items.rows.count(),0)


    def test_shop_focus_requires_a_native_panel_unique_identity_and_current_title_pixels(self):
        w=self.window;original,_,reading=self.prepare_shop_description()
        w.reader.submitted_image=w.reader.image.copy()
        w.reader.image=original;w.on_reading(reading)
        self.assertIsNone(w.shop_description)
        w.reader.image=w.reader.submitted_image.copy()
        del w.reader.submitted_image
        w.on_catalog(Catalog({'items':[dict(id=1,name='Example Hat'),dict(id=3,name='Example Hat')]}))
        w.on_reading(reading);self.assertIsNotNone(w.shop_tooltip_rect);self.assertIsNone(w.shop_description)

    def test_fading_our_shop_label_cannot_change_the_native_description_identity(self):
        from PySide6.QtGui import QPainter
        w=self.window;self.prepare_shop_description()
        w.overlay.layout_boxes=[(500,210,40,20)]
        painter=QPainter(w.reader.image);painter.fillRect(500,210,40,20,QColor('#171c25'));painter.end()
        w.on_image(w.reader.image)
        self.assertIsNotNone(w.shop_description);self.assertEqual(w.shop_description['name'],'Example Hat')

    def test_masked_shop_title_uses_only_the_same_verified_native_source(self):
        w=self.window;self.prepare_shop_description()
        proof=w.shop_description_proof
        self.assertTrue(w.shop_description_matches(w.reader.image,w.reader.pointer))
        # A price label crossing most of the native title must not establish
        # an identity from its own pixels, even if native OCR supplied a name.
        w.overlay.layout_boxes=[(500,210,150,20)]
        self.assertTrue(w.shop_description_matches(w.reader.image,w.reader.pointer))
        w.on_image(w.reader.image)
        self.assertIsNotNone(w.shop_description)
        w.rows[0]['name']='Example Cape'
        self.assertFalse(w.shop_description_matches(w.reader.image,w.reader.pointer))
        w.overlay.layout_boxes=[]
        self.assertTrue(w.observations.description_title_matches(w.reader.image,proof,[]))

    def test_inventory_hover_outside_shop_has_its_own_overlay_while_shop_labels_stay(self):
        w=self.window;self.prepare_shop_description();w.reader.pointer=(100,100)
        w.on_reading(self.reading(shop_hover=False,store=True))
        self.assertIsNone(w.shop_description);self.assertIsNotNone(w.tooltip_result)
        self.assertEqual(w.tooltip_result['name'],'Example Hat')
        self.assertTrue(any(row['kind']=='item' for row in w.overlay.rows))

    def test_shop_hover_can_first_identify_a_masked_title_from_its_verified_slot(self):
        w=self.window;_,_,reading=self.prepare_shop_description();w.clear_shop_description();w.shop_tooltip_rect=None
        w.overlay.layout_boxes=[(500,210,150,20)]
        reading['hover']['tooltip']['found']['name']=None
        w.on_reading(reading)
        self.assertIsNotNone(w.shop_description);self.assertEqual(w.shop_description['name'],'Example Hat')
        self.assertIsNone(w.rows[0]['price'])
        self.assertEqual(w.service.visible,[1,2]);self.assertEqual(w.recent_items.rows.count(),0)

    def test_shop_hover_preserves_search_watch_precedence_and_reduced_motion(self):
        w=self.window;self.app.setProperty('reduceMotion',True);original,_,_=self.prepare_shop_description()
        self.assertIsNone(w.card_area.outgoing)
        w.search_panel.query.setText('Example');self.assertTrue(w.scroll.isHidden())
        w.search_panel.query.clear();w.watchlist.toggle(w.catalog.resolve('Example Hat'))
        w.search_panel.select_watched(1);self.assertTrue(w.scroll.isHidden())
        self.assertEqual(w.search_panel.selected.game_id,1)
        w.reader.image=original;w.on_image(original)
        self.assertTrue(w.scroll.isHidden());self.assertEqual(w.search_panel.selected.game_id,1)
        self.assertIsNone(w.card_area.outgoing)

    def test_covered_shop_rows_do_not_draw_unreadable_price_badges(self):
        reading = self.reading(shop_hover=True)
        reading["shop"]["rows"][0].update(name=None, price=None, covered=True)
        self.window.on_reading(reading)
        self.assertEqual(self.window.overlay.rows, [])

    def test_small_cursor_moves_keep_the_identified_price_and_card(self):
        self.window.reader.pointer = (100, 100)
        self.window.on_reading(self.reading(shop_hover=False))
        card = self.window.cards_layout.itemAt(0).widget()
        key = self.window.card_key
        self.window.on_pointer(108, 105)
        self.assertIsNotNone(self.window.tooltip_result)
        self.window.render()
        self.assertIs(self.window.cards_layout.itemAt(0).widget(), card)
        self.assertEqual(self.window.card_key, key)
        hover = self.window.overlay.rows[-1]
        self.assertEqual(hover["follow_pointer"], [100, 100])

    def test_reading_for_a_pointer_that_has_moved_away_is_rejected(self):
        self.window.reader.pointer = (700, 700)
        reading = self.reading(shop_hover=False)
        reading["pointerAtRead"] = [100, 100]
        self.window.on_reading(reading)
        self.assertIsNone(self.window.tooltip_result)

    def test_error_for_a_previous_store_is_not_left_on_the_status_line(self):
        self.window.status_label.setText("Price lookup: old item: HTTP Error 400")
        self.window.errors[999] = "HTTP Error 400"
        self.window.on_reading(self.reading(shop_hover=True))
        self.assertNotIn("400", self.window.status_label.text())

    def test_one_button_covers_monitor_selection_start_pause_and_resume(self):
        fresh = LensWindow(Path.cwd(), Path("unused-cache"))
        try:
            self.assertIsNotNone(fresh.screen_index)
            self.assertTrue(fresh.share.isEnabled())
            self.assertEqual(fresh.monitor.count(), len(fresh.screens))
            self.assertFalse(fresh.crop_button.isEnabled())
            self.assertEqual(fresh.reader.starts, 0)
            fresh.monitor.setCurrentIndex(0)
            self.assertTrue(fresh.share.isEnabled())
            self.assertEqual(fresh.share.text(), "Start reading")
            fresh.share.click()
            self.assertEqual(fresh.reader.starts, 1)
            self.assertFalse(fresh.share.isEnabled())
            self.assertEqual(fresh.share.text(), "Starting reading…")
            fresh.reader.image = QImage(800, 800, QImage.Format.Format_RGBA8888)
            fresh.on_image(fresh.reader.image)
            self.assertTrue(fresh.share.isEnabled())
            self.assertEqual(fresh.share.text(), "Pause reading")
            fresh.share.click()
            self.assertEqual(fresh.mode, "paused")
            self.assertEqual(fresh.share.text(), "Resume reading")
            self.assertEqual(fresh.reader.pauses, [True])
            self.assertEqual(fresh.overlay.rows, [])
            fresh.share.click()
            self.assertEqual(fresh.reader.starts, 2)
        finally:
            fresh.close()
            fresh.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_price_hotkey_is_independent_of_screen_reading_and_exp(self):
        self.window.hotkeys.activated.emit()
        self.assertEqual(self.window.mode,'live')
        self.assertFalse(self.window.prices_enabled)
        self.assertFalse(self.window.reader.prices_enabled)
        self.window.hotkeys.activated.emit()
        self.assertTrue(self.window.prices_enabled)
        self.window.share.click()
        self.assertEqual(self.window.mode,'paused')


    def test_pause_ignores_pending_readings_and_does_not_refresh_prices(self):
        self.window.on_reading(self.reading(shop_hover=True))
        count = len(self.window.service.requests)
        self.window.pause()
        self.window.on_reading(self.reading(shop_hover=False))
        self.window.tick()
        self.assertIsNone(self.window.tooltip_result)
        self.assertEqual(len(self.window.service.requests), count)
        self.assertFalse(self.window.overlay.rows)

    def test_key_combination_is_configurable_and_saved(self):
        def edit():
            dialog = self.window.findChild(QDialog, "hotkeyDialog")
            editor = dialog.findChild(QKeySequenceEdit, "shortcut-prices")
            editor.setKeySequence(QKeySequence("Ctrl+Shift+F10"))
            dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Apply).click()
        QTimer.singleShot(0, edit)
        self.window.configure_shortcuts()
        self.assertEqual(self.window.settings.values["hotkey-sequence"], "Ctrl+Shift+F10")
        self.assertTrue(self.window.settings.values["hotkey-enabled"])

    def test_first_run_display_selection_waits_for_explicit_start(self):
        fresh = LensWindow(Path.cwd(), Path("unused-cache"), auto_capture=True)
        try:
            fresh.monitor.setCurrentIndex(0)
            self.app.processEvents()
            self.assertEqual(fresh.reader.starts, 0)
            self.assertEqual(fresh.mode, "idle")
            self.assertEqual(fresh.status_badge.text(), "Ready to start")
            self.assertIn("Click Start reading", fresh.capture_info.text())
            self.assertFalse(fresh.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        finally:
            fresh.close()
            fresh.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_sharing_setup_can_be_canceled_and_late_readings_are_ignored(self):
        self.window.mode = "idle"
        self.window.start_capture()
        from price_lens.capture_platform import uses_system_picker
        self.assertEqual(self.window.status_badge.text(), "Waiting for screen sharing" if uses_system_picker() else "Starting screen reading")
        self.assertFalse(self.window.cancel_setup.isHidden())
        self.window.cancel_setup.click()
        self.window.on_reading(self.reading(shop_hover=True))
        self.assertEqual(self.window.mode, "idle")
        self.assertEqual(self.window.rows, [])
        self.assertEqual(self.window.reader.pauses[-1], False)
        self.assertIn("canceled", self.window.capture_info.text())

    def test_lost_sharing_waits_for_explicit_reconnect(self):
        self.window.show_status("OS capture: user stopped sharing")
        self.assertEqual(self.window.reader.starts, 0)
        self.assertEqual(self.window.status_badge.text(), "Screen reading needs attention")
        self.assertFalse(self.window.recovery_button.isHidden())
        self.window.recovery_button.click()
        self.assertEqual(self.window.reader.starts, 1)

    def test_changing_display_stops_the_old_source_without_opening_another_picker(self):
        from types import SimpleNamespace
        self.window.screens.append(SimpleNamespace(name=lambda:'Other',geometry=lambda:QRect(800,0,800,800),devicePixelRatio=lambda:1))
        self.window.monitor.addItem('Other display',1)
        self.window.monitor.setCurrentIndex(1)
        self.assertEqual(self.window.mode, "idle")
        self.assertEqual(self.window.reader.starts, 0)
        self.assertEqual(self.window.reader.pauses, [False])

    def test_catalog_retry_is_bounded_while_a_request_is_in_progress(self):
        self.window.catalog = None
        self.window.on_error(0, "HTTP Error 503")
        self.assertTrue(self.window.catalog_error)
        for _ in range(500):
            self.window.retry_catalog()
        self.assertEqual(self.window.service.catalog_starts, 2)
        self.assertTrue(self.window.catalog_loading)


    def test_recognised_item_without_reports_is_not_called_unreadable(self):
        self.window.on_reading(self.reading(shop_hover=True))
        now = time.time()
        self.window.service.deliver_quote(1, Quote(1, None, now, None, 0, "Test", "", "24h"))
        content = "\n".join(widget.text() for widget in self.window.cards.findChildren(QLabel))
        self.assertNotIn("Item unidentified", content)
        self.assertIn("No observed sales", content)
        self.assertNotIn("unreadable", content.lower())

    def test_empty_hover_reference_is_not_left_checking_forever(self):
        self.window.reader.pointer = (100, 100)
        self.window.on_reading(self.reading(shop_hover=False))
        self.window.service.deliver_quote(1, Quote(1, None, time.time(), None, 0, "Test", "", "24h"))
        self.assertEqual(len(self.window.overlay.rows), 1)
        self.assertEqual(self.window.overlay.rows[-1]["text"], "FM • no observed sales")

    def test_saved_screenshot_is_labeled_even_without_a_display_selected(self):
        self.window.monitor.setCurrentIndex(-1)
        self.window.mode = "screenshot"
        self.window.render()
        self.assertEqual(self.window.status_badge.text(), "Saved screenshot")
        self.assertFalse(self.window.share.isEnabled())
        self.assertIn("saved image", self.window.capture_info.text())
        self.assertEqual(self.window.overlay.rows, [])


    def test_price_cards_have_no_details_toggle_and_show_observed_sale_time(self):
        self.window.on_reading(self.reading(shop_hover=True))
        now=time.time()
        self.window.service.deliver_quote(1,Quote(1,1000,now,now-120,20,'MesoWatch','','24h',basis='observed shop sales'))
        card=next(iter(self.window.card_views.values()))
        self.assertFalse(hasattr(card,'toggle'))
        self.assertIn('Most recent observed sale',card.fields['recent'].text())

    def test_expiration_removes_comparison_inside_the_same_age_bucket(self):
        with patch("price_lens.ui.time.time", return_value=1001):
            self.window.last_screen = 1001
            self.window.on_reading(self.reading(shop_hover=True))
            self.window.service.deliver_quote(1, Quote(1, 1000, 101.2, 1000, 20, "Test", "", "24h"))
            previous = self.window.card_key
            self.assertTrue(any("below reference" in widget.text() for widget in self.window.cards.findChildren(QLabel)))
        with patch("price_lens.ui.time.time", return_value=1001.3):
            self.window.render()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            self.assertNotEqual(previous, self.window.card_key)
            content = "\n".join(widget.text() for widget in self.window.cards.findChildren(QLabel))
            self.assertIn("Older reference", content)
            self.assertNotIn("below reference", content)
            self.assertTrue(any("refresh needed" in row["text"] for row in self.window.overlay.rows))

    def test_inventory_hover_outside_open_shop_keeps_both_references_visible(self):
        self.window.on_catalog(Catalog({"items": [{"id": 1, "name": "Example Hat"},
                                                  {"id": 2, "name": "Other Hat"}], "scrolls": []}))
        self.window.reader.pointer = (100, 100)
        reading = self.reading(shop_hover=False,store=True)
        reading["tooltip"]["found"]["name"] = "Other Hat"
        self.window.on_reading(reading)
        self.assertEqual(self.window.tooltip_result['name'], 'Other Hat')
        self.assertEqual(set(self.window.service.visible), {1,2})
        self.assertEqual(len(self.window.overlay.rows), 2)
        self.window.on_pointer(340, 240)
        self.assertIsNone(self.window.tooltip_result)
        self.assertEqual(self.window.service.visible, [1])

    def test_refresh_progress_updates_cards_and_both_overlay_contexts(self):
        for shop in (True,False):
            with self.subTest(shop=shop):
                self.window.reader.pointer = (340,240) if shop else (100,100)
                self.window.on_reading(self.reading(shop_hover=shop))
                now=time.time()
                self.window.service.deliver_quote(1,Quote(1,1000,now-1080,now,20,"Test","","24h"))
                self.window.service.states[1]="refreshing"
                self.window.service.state_changed.emit();self.app.processEvents()
                content="\n".join(widget.text() for widget in self.window.cards.findChildren(QLabel))
                self.assertIn("Refreshing market reference",content)
                self.assertEqual(len(self.window.overlay.rows),1)
                row=self.window.overlay.rows[0]
                self.assertIn("Latest report 0s ago",row["text"])
                self.assertNotIn("18m old",row["text"])
                self.assertIn("refreshing",row["text"])
                self.assertNotEqual(row["color"],"#86ceac")
        self.window.pause()
        self.assertEqual(self.window.service.visible,[])

    def test_recent_lookup_with_old_reports_explains_the_market_data_age(self):
        self.window.on_reading(self.reading(shop_hover=True))
        now = time.time()
        self.window.service.deliver_quote(1, Quote(1, 1000, now, now - 90000, 20, "Test", "", "24h"))
        self.assertIn("old market reports", self.window.overlay.rows[0]["text"])
        self.assertNotIn("EXPIRED", self.window.overlay.rows[0]["text"])

    def test_hidden_labels_can_be_restored_without_reconnecting(self):
        self.window.on_reading(self.reading(shop_hover=True))
        self.window.labels_check.setChecked(False)
        self.window.on_pointer(100, 100)
        self.assertFalse(self.window.reader.tooltip_enabled)
        self.assertIsNone(self.window.reader.pointer)
        self.assertEqual(self.window.overlay.rows, [])
        self.assertEqual(self.window.recovery_button.text(), "Show price labels")
        self.window.recovery_button.click()
        self.assertTrue(self.window.labels_enabled)
        self.assertTrue(self.window.reader.tooltip_enabled)
        self.assertEqual(self.window.reader.starts, 0)

    def test_mismatched_references_never_reach_overlay_or_success_message(self):
        self.window.on_reading(self.reading(shop_hover=True))
        now = time.time()
        valid = Quote(1, 987654, now, now, 20, "Test", "", "24h")
        for change in ({"world": "Other World"}, {"game_id": 2}, {"condition": "scrolled"}, {"per_set": True}):
            with self.subTest(change=change):
                self.window.service.deliver_quote(1, replace(valid, **change))
                self.assertFalse(self.window.first_price_seen)
                self.assertNotIn("987,654", "\n".join(row["text"] for row in self.window.overlay.rows))
                self.assertIn("0 market references ready", self.window.summary.text())

    def test_single_display_dropdown_and_three_feature_tabs(self):
        self.assertFalse(hasattr(self.window,'display_map'))
        self.window.monitor.setCurrentIndex(0)
        self.assertIsNotNone(self.window.screen_index)
        self.assertEqual([self.window.tabs.tabText(i) for i in range(3)],['Prices','EXP/Meso Tracking','Translation'])
        self.assertEqual(self.window.search_panel.parentWidget(),self.window.prices_page)
        self.assertFalse(self.window.exp_enabled)
        for i in range(3):
            self.window.tabs.setCurrentIndex(i);self.app.processEvents()
            self.assertFalse(self.window.shortcuts_button.isHidden())

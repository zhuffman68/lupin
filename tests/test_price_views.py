"""Navigate full-size Prices views without losing the selected item or position."""
from unittest.mock import patch
import time
import unittest

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from price_lens.domain import Catalog,Quote
import test_ui_context as fixture


class PriceViewsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.ContextUiTests.setUpClass.__func__(cls)

    def setUp(self):
        fixture.ContextUiTests.setUp(self)
        self.app.setProperty('reduceMotion',True)
        w=self.window;w.timer.stop();w.resize(520,840);w.show()
        for service in (w.reference.extra,w.reference.sources,w.reference.geometry):
            replacement=patch.object(service,'select');replacement.start();self.addCleanup(replacement.stop)
        w.on_reading(fixture.ContextUiTests.reading(self,True))
        row=w.rows[0]
        w.rows=[{**row,'area':{**row['area'],'y':220+40*i}} for i in range(6)]
        w.render();self.app.processEvents()

    def tearDown(self):
        fixture.ContextUiTests.tearDown(self);self.app.setProperty('reduceMotion',False)

    def select(self):
        self.window.search_panel.select_observed(self.window.catalog.by_id[1],self.window.rows[0])
        self.app.processEvents();return self.window.search_panel.price_view

    def click_switch(self):
        QTest.mouseClick(self.window.onscreen_button,Qt.MouseButton.LeftButton);self.app.processEvents()

    def reopen(self):
        p=self.window.search_panel;p.select_observed(p.selected,p.selected_row or {'name':p.selected.name})
        self.app.processEvents()

    def test_switch_uses_the_available_height_at_both_supported_widths(self):
        w=self.window;self.select()
        for width in (460,520):
            w.resize(width,840);self.app.processEvents()
            self.assertTrue(w.scroll.isHidden());self.assertTrue(w.onscreen_button.isVisible())
            self.click_switch()
            self.assertTrue(w.search_panel.detail_scroll.isHidden());self.assertFalse(w.scroll.isHidden())
            expected=w.price_content.height()
            self.assertGreater(w.scroll.viewport().height(),250)
            self.assertGreaterEqual(w.scroll.height(),expected-2)
            self.assertGreater(w.scroll.verticalScrollBar().maximum(),0)
            self.assertTrue(w.onscreen_button.isHidden())
            self.reopen()

    def test_selection_subtab_and_both_scroll_positions_survive_the_round_trip(self):
        w=self.window;w.scroll.verticalScrollBar().setValue(140);card=self.select()
        card.tabs.setCurrentIndex(1)
        w.search_panel.detail.setMinimumHeight(1200);self.app.processEvents()
        w.search_panel.detail_scroll.verticalScrollBar().setValue(120)
        self.assertEqual(w.search_panel.detail_scroll.verticalScrollBar().value(),120)
        self.click_switch()
        self.assertEqual(w.scroll.verticalScrollBar().value(),140)
        w.scroll.verticalScrollBar().setValue(210)
        self.reopen()
        self.assertIs(w.search_panel.price_view,card);self.assertEqual(card.tabs.currentIndex(),1)
        self.assertEqual(w.search_panel.detail_scroll.verticalScrollBar().value(),120)
        self.click_switch();self.assertEqual(w.scroll.verticalScrollBar().value(),210)

    def test_prices_update_while_the_selected_card_is_retained_out_of_view(self):
        w=self.window;card=self.select();self.click_switch()
        quote=Quote(1,123456,time.time(),time.time(),10,'Test','','24h')
        w.service.deliver_quote(1,quote);self.app.processEvents()
        self.assertEqual(w.price_content.pane,'screen');self.assertIs(w.search_panel.price_view,card)
        self.reopen();self.assertIn('123,456',card.fields['market'].text())

    def test_clicking_a_listing_returns_to_details_even_for_the_same_item(self):
        w=self.window;card=self.select();self.click_switch()
        w.search_panel.select_observed(w.catalog.by_id[1],w.rows[0]);self.app.processEvents()
        self.assertEqual(w.price_content.pane,'detail');self.assertIs(w.search_panel.price_view,card)

    def test_a_different_item_opens_at_the_top_instead_of_inheriting_the_old_position(self):
        w=self.window;self.select();w.search_panel.detail.setMinimumHeight(1200);self.app.processEvents()
        w.search_panel.detail_scroll.verticalScrollBar().setValue(160);self.click_switch()
        w.on_catalog(Catalog({'items':[{'id':1,'name':'Example Hat'},{'id':2,'name':'Example Cape'}]}))
        w.search_panel.select_observed(w.catalog.by_id[2],{'name':'Example Cape'});self.app.processEvents()
        self.assertEqual(w.price_content.pane,'detail')
        self.assertEqual(w.search_panel.detail_scroll.verticalScrollBar().value(),0)

    def test_closed_shop_and_main_tab_changes_do_not_restore_a_return_button(self):
        w=self.window;card=self.select();self.click_switch()
        w.rows=[];w.shop_open=False;w.render();self.app.processEvents()
        self.assertTrue(w.onscreen_button.isHidden())
        w.tabs.setCurrentIndex(w.exp_tab_index);w.tabs.setCurrentIndex(0);self.app.processEvents()
        self.assertEqual(w.price_content.pane,'screen')
        w.search_panel.choose_first();self.app.processEvents();self.assertIs(w.search_panel.price_view,card)
        self.assertEqual(w.price_content.pane,'detail')

    def test_clicking_the_same_search_result_reopens_it_without_a_return_button(self):
        w=self.window;card=self.select();p=w.search_panel;self.click_switch()
        p.find_items();self.app.processEvents()
        item=p.results.item(0);QTest.mouseClick(p.results.viewport(),Qt.MouseButton.LeftButton,pos=p.results.visualItemRect(item).center())
        self.app.processEvents()
        self.assertIs(p.price_view,card);self.assertEqual(w.price_content.pane,'detail')

    def test_search_without_a_selection_keeps_navigation_at_the_top(self):
        w=self.window;p=w.search_panel;p.query.setText('No matching item');p.timer.stop();p.find_items()
        self.app.processEvents()
        self.assertIsNone(w.price_content.pane);self.assertTrue(w.onscreen_button.isVisible())
        self.assertEqual(w.onscreen_button.y(),0)

    def test_a_new_search_selection_requests_its_image_before_the_view_is_shown(self):
        w=self.window;w.rows=[];w.tooltip_result=None;w.render()
        p=w.search_panel;p.query.setText('Example Hat');p.choose_first();self.app.processEvents()
        self.assertIn(1,[item.game_id for item in w.thumbnails.items])

    def test_editing_a_query_returns_from_the_list_to_search_results(self):
        w=self.window;p=w.search_panel
        p.query.setText('Exam');p.timer.stop();p.find_items();self.app.processEvents();self.click_switch()
        self.assertEqual(w.price_content.pane,'screen');self.assertIsNone(p.selected)
        p.query.setText('Example H');p.timer.stop();p.find_items();self.app.processEvents()
        self.assertIsNone(w.price_content.pane);self.assertFalse(w.onscreen_button.isChecked())

    def test_departing_prices_page_releases_external_image_demand_while_still_sliding(self):
        w=self.window;self.select();self.app.setProperty('reduceMotion',False)
        w.tabs.setCurrentIndex(w.exp_tab_index);w.tabs.animation.pause()
        self.assertTrue(w.prices_page.isVisible())
        self.assertEqual(w.price_reference_demand(),[])

    def test_departing_prices_snapshot_contains_the_open_card(self):
        w=self.window;self.select();self.app.processEvents()
        before=w.prices_page.grab().toImage();self.app.setProperty('reduceMotion',False)
        w.tabs.setCurrentIndex(w.exp_tab_index);w.tabs.animation.pause()
        self.assertEqual(w.tabs.surface.pictures[0].toImage(),before)

    def test_view_replacement_retains_the_full_animation_and_handles_rapid_return(self):
        w=self.window;self.select();self.app.setProperty('reduceMotion',False)
        self.click_switch();frame=w.price_content.outgoing
        self.assertIsNotNone(frame);self.assertEqual(w.price_content.animation.duration(),130)
        w.price_content.animation.pause();w.price_content.animation.setCurrentTime(60)
        self.reopen()
        self.assertEqual(w.price_content.pane,'detail');self.assertIsNotNone(w.price_content.outgoing)
        w.price_content.finish();self.assertTrue(w.scroll.isHidden())


if __name__=='__main__':unittest.main()

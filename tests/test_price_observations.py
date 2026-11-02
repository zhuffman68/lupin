"""Widget-free observation acceptance and retirement from generated native pixels."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication,QRect
from PySide6.QtGui import QColor,QImage,QPainter

from price_lens.domain import Catalog
from price_lens.price_observations import PriceObservations
from price_lens.shop_browsing import ShopBrowsing
from price_lens.shop_source import cursor_rectangle,native_occlusion,proof_state


class PriceObservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.state=PriceObservations(catalog=Catalog({'items':[dict(id=1,name='Example Hat')]}))
        self.state.browsing=ShopBrowsing(identity=self.state.shop_identity)
        self.image=QImage(800,600,QImage.Format.Format_RGBA8888);self.image.fill(QColor('#cad5df'))
        painter=QPainter(self.image)
        painter.fillRect(104,154,24,27,QColor('#992211'))
        painter.fillRect(145,155,80,6,QColor('black'))
        painter.fillRect(145,174,50,6,QColor('black'));painter.end()
        self.area=QRect(100,150,199,260);self.point=(180,160)
        self.shop=dict(area=dict(zip(('x','y','width','height'),self.area.getRect())),rows=[
            dict(name='Example Hat',price=dict(quantity=1,mesos=100),area=dict(x=137,y=150,width=162,height=35))])

    def observe(self,image=None,latest=None,**kwargs):
        image=self.image if image is None else image
        return self.state.observe_shop(deepcopy(self.shop),image,image if latest is None else latest,
            pointer=self.point,read_point=self.point,**kwargs)

    def test_only_fresh_matching_source_becomes_an_accepted_offer(self):
        read=self.observe()
        self.assertTrue(read.changed);self.assertFalse(read.retry)
        self.assertEqual(self.state.rows[0]['_item_id'],1)
        changed=self.image.copy();changed.setPixelColor(220,176,QColor('white'))
        read=self.observe(latest=changed)
        self.assertTrue(read.retry)
        self.assertIsNone(self.state.rows[0]['price'])
        self.assertTrue(self.state.rows[0]['reference_only'])
        self.assertEqual(self.state.shop_rows.presentation_for(self.state.rows[0])['mesos'],100)
        self.assertTrue(self.state.shop_open)

    def test_a_late_rejected_read_cannot_blank_an_independently_verified_page(self):
        self.observe();page=self.state.shop_rows.page_revision
        old_frame=self.image.copy();old_frame.setPixelColor(220,176,QColor('white'))
        read=self.observe(image=old_frame,latest=self.image)
        self.assertTrue(read.retry);self.assertFalse(read.changed)
        self.assertEqual(self.state.rows[0]['_item_id'],1)
        self.assertEqual(self.state.rows[0]['price']['mesos'],100)
        self.assertEqual(self.state.shop_rows.page_revision,page)

    def test_ocr_rounding_cannot_accumulate_duplicate_page_proofs_or_fake_scrolling(self):
        self.observe();original=deepcopy(self.shop)
        for delta in (-1,1,0,2,-2):
            self.shop=deepcopy(original)
            self.shop['area']['y']+=delta;self.shop['area']['height']-=delta
            row=self.shop['rows'][0]['area'];row['y']+=delta;row['height']-=delta
            read=self.observe()
            self.assertFalse(read.viewport_changed)
            self.assertEqual(len(self.state.browsing.rows),1)
            self.assertEqual(self.state.browsing.area,self.area)
            self.assertFalse(self.state.browsing.observe_frame(self.image,self.area))
            self.assertEqual(self.state.rows[0]['area'],original['rows'][0]['area'])

    def test_source_retirement_and_proven_viewport_change_keep_separate_authority(self):
        self.observe();page=self.state.shop_rows.page_revision;epoch=self.state.browsing.epoch
        changed=self.image.copy();changed.setPixelColor(220,176,QColor('white'))
        frame=self.state.validate_frame(changed,pointer=self.point,shop_context=self.area)
        self.assertTrue(frame.retired);self.assertIsNone(self.state.rows[0]['price'])
        self.assertEqual(self.state.browsing.epoch,epoch);self.assertFalse(self.state.browsing.pending)
        self.assertFalse(frame.container_lost)
        self.assertTrue(self.state.shop_open)
        self.assertTrue(self.state.shop_rows.rows,'Last-seen presentation is separate from a current offer')
        self.state.viewport_changed()
        self.assertGreater(self.state.shop_rows.page_revision,page)
        self.assertEqual(self.state.shop_rows.rows,{})

    def test_an_ocr_miss_after_a_visible_row_change_cannot_resurrect_old_items(self):
        self.observe();changed=self.image.copy();painter=QPainter(changed)
        painter.fillRect(145,155,80,6,QColor('#cad5df'))
        painter.fillRect(240,155,40,6,QColor('black'));painter.end()
        self.assertTrue(self.state.validate_frame(changed,pointer=self.point).retired)
        self.state.observe_shop(None,changed,changed,pointer=self.point,read_point=self.point)
        self.assertEqual(self.state.rows,[])
        self.assertEqual(self.state.shop_rows.rows,{})
        self.assertEqual(self.state.shop_rows.area,self.shop['area'])
        self.assertTrue(self.state.shop_open,'The independently verified frame remains a scan hint only')
        self.assertFalse(self.state.validate_frame(changed,pointer=self.point).retired)

    def test_one_rejected_row_does_not_clear_other_independently_verified_listings(self):
        other=deepcopy(self.shop['rows'][0]);other['area']['y']=230;other['price']['mesos']=200
        self.shop['rows'].append(other);self.observe()
        changed=self.image.copy();changed.setPixelColor(220,236,QColor('white'))
        frame=self.state.validate_frame(changed,pointer=self.point)
        self.assertTrue(frame.retired);self.assertTrue(self.state.shop_open)
        self.assertEqual(len(self.state.rows),1)
        self.assertEqual(self.state.rows[0]['price']['mesos'],100)
        self.state.observe_shop(None,changed,changed,pointer=self.point,read_point=self.point)
        self.assertEqual(len(self.state.rows),1)
        self.assertEqual(self.state.rows[0]['price']['mesos'],100)

    def test_late_read_rejecting_one_current_row_preserves_other_rows_and_shop_mode(self):
        other=deepcopy(self.shop['rows'][0]);other['area']['y']=230;other['price']['mesos']=200
        self.shop['rows'].append(other);self.observe()
        submitted=self.image.copy();submitted.setPixelColor(220,176,QColor('white'))
        latest=self.image.copy();latest.setPixelColor(220,236,QColor('white'))
        read=self.observe(image=submitted,latest=latest)
        self.assertTrue(read.retry);self.assertTrue(read.changed)
        self.assertTrue(self.state.shop_open)
        self.assertEqual([row['price']['mesos'] for row in self.state.rows],[100])

    def test_rejected_rows_do_not_clear_native_shop_description_routing(self):
        self.observe();self.state.shop_tooltip_from_shop=True
        changed=self.image.copy();changed.setPixelColor(220,176,QColor('white'))
        frame=self.state.validate_frame(changed,pointer=self.point)
        self.assertTrue(frame.retired);self.assertFalse(frame.container_lost)
        self.assertTrue(self.state.shop_open);self.assertTrue(self.state.shop_tooltip_from_shop)
        self.assertEqual(self.state.shop_rows.area,self.shop['area'])
        self.assertIsNone(self.state.rows[0]['price'])
        self.assertTrue(self.state.rows[0]['reference_only'])

    def native_pair(self):
        other=deepcopy(self.shop['rows'][0]);other['area']['y']=230;other['price']['mesos']=200
        self.shop['rows'].append(other)
        painter=QPainter(self.image)
        painter.fillRect(104,234,24,27,QColor('#992211'))
        painter.fillRect(145,235,80,6,QColor('black'))
        painter.fillRect(145,254,50,6,QColor('black'));painter.end()
        self.observe()

    def test_unchanged_neighbours_hold_blocked_loaded_rows_without_a_complete_panel_rectangle(self):
        self.native_pair();image=self.image.copy();painter=QPainter(image)
        painter.fillRect(133,228,170,110,QColor('#464b78'));painter.end()
        # Geometry has not found this entire native description yet. The first
        # unchanged title anchors the loaded page; the hidden second is unknown.
        frame=self.state.validate_frame(image,pointer=(400,400))
        self.assertFalse(frame.container_lost);self.assertEqual(len(self.state.rows),2)
        held=self.state.rows[1]
        self.assertIsNone(held['price']);self.assertTrue(held['reference_only'])
        self.assertEqual(self.state.shop_rows.presentation_for(held)['mesos'],200)
        for _ in range(12):
            frame=self.state.validate_frame(image,pointer=(400,400))
            self.assertFalse(frame.retired);self.assertFalse(frame.changed)
        self.state.observe_shop(None,image,image,pointer=(400,400),read_point=(400,400))
        self.assertEqual(len(self.state.rows),2)
        self.assertEqual(self.state.shop_rows.presentation_for(self.state.rows[1])['mesos'],200)

    def test_changed_exposed_name_cannot_borrow_the_old_item_from_unchanged_neighbours(self):
        self.native_pair();image=self.image.copy();painter=QPainter(image)
        painter.fillRect(137,230,162,17,QColor('#cad5df'))
        painter.fillRect(240,235,40,6,QColor('black'));painter.end()
        self.state.validate_frame(image,pointer=(180,240))
        self.assertEqual(len(self.state.rows),1)
        self.assertEqual(self.state.rows[0]['price']['mesos'],100)

    def test_a_viewport_change_clears_even_references_held_under_an_unknown_panel(self):
        self.native_pair();image=self.image.copy();painter=QPainter(image)
        painter.fillRect(133,228,170,110,QColor('#464b78'));painter.end()
        self.state.validate_frame(image,pointer=(400,400))
        self.assertEqual(len(self.state.rows),2)
        self.state.browsing._advance();self.state.viewport_changed()
        self.state.observe_shop(None,image,image,pointer=(400,400),read_point=(400,400))
        self.assertEqual(len(self.state.rows),0);self.assertEqual(self.state.shop_rows.rows,{})

    def name_only_shop(self):
        shop=deepcopy(self.shop)
        shop['rows'][0].update(nameOnly=True,price=None,
            nameArea=dict(x=137,y=150,width=162,height=17))
        return shop

    def test_a_fresh_readable_name_can_finish_a_scrolled_page_without_an_asking_price(self):
        self.observe();self.state.browsing._advance();self.state.viewport_changed()
        shop=self.name_only_shop();shop['area']['height']=21
        read=self.state.observe_shop(shop,self.image,self.image,pointer=self.point,read_point=self.point)
        self.assertFalse(read.retry);self.assertFalse(self.state.browsing.pending)
        self.assertEqual(self.state.rows[0]['_item_id'],1)
        self.assertIsNone(self.state.rows[0]['price'])
        self.assertIsNone(self.state.shop_rows.presentation_for(self.state.rows[0]))
        self.assertEqual(self.state.rows[0]['_identity_source'].rect,(137,150,162,17))
        self.assertEqual(self.state.browsing.area,self.area)

    def test_name_only_identity_is_independent_of_later_asking_line_changes(self):
        self.observe();self.state.browsing._advance();self.state.viewport_changed()
        self.state.observe_shop(self.name_only_shop(),self.image,self.image,pointer=self.point,read_point=self.point)
        changed=self.image.copy();painter=QPainter(changed)
        painter.fillRect(137,170,162,15,QColor('#bbaa22'));painter.end()
        frame=self.state.validate_frame(changed,pointer=self.point)
        self.assertFalse(frame.retired);self.assertEqual(self.state.rows[0]['_item_id'],1)
        self.assertIsNone(self.state.rows[0]['price'])

    def test_name_only_market_reference_survives_later_native_misses_without_inventing_an_amount(self):
        self.observe();self.state.browsing._advance();self.state.viewport_changed()
        self.state.observe_shop(self.name_only_shop(),self.image,self.image,pointer=self.point,read_point=self.point)
        page=self.state.shop_rows.page_revision
        self.state.observe_shop(None,self.image,self.image,pointer=self.point,read_point=self.point)
        self.assertEqual(len(self.state.rows),1);self.assertEqual(self.state.rows[0]['_item_id'],1)
        self.assertIsNone(self.state.rows[0]['price'])
        self.assertIsNone(self.state.shop_rows.presentation_for(self.state.rows[0]))
        self.observe()
        self.assertEqual(self.state.rows[0]['price']['mesos'],100)
        self.assertEqual(self.state.shop_rows.page_revision,page)

    def test_name_only_read_requires_an_independently_verified_shop(self):
        shop=self.name_only_shop()
        read=self.state.observe_shop(shop,self.image,self.image,pointer=self.point,read_point=self.point)
        self.assertFalse(read.retry)
        self.assertFalse(any(row.get('_item_id') for row in self.state.rows))
        self.assertFalse(any(row.get('name') for row in self.state.rows))

    def test_name_only_read_never_resolves_an_ambiguous_name_using_a_covered_icon(self):
        self.state.catalog=Catalog({'items':[dict(id=1,name='Example Hat'),dict(id=2,name='Example Hat')]})
        self.observe()
        self.state.observe_shop(self.name_only_shop(),self.image,self.image,pointer=self.point,read_point=self.point)
        self.assertIsNone(self.state.item_for(self.state.rows[0]))
        self.assertEqual(self.state.rows[0]['_identity_reason'],'ambiguous')

    def test_missing_table_guards_retire_the_container_even_without_rows(self):
        self.observe();self.state.viewport_changed()
        changed=self.image.copy();changed.fill(QColor('#172333'))
        frame=self.state.validate_frame(changed,pointer=self.point)
        self.assertTrue(frame.container_lost);self.assertFalse(self.state.shop_open)

    def test_known_description_occlusion_preserves_reference_but_never_current_offer(self):
        self.observe();panel=QRect(200,158,100,160)
        latest=self.image.copy();painter=QPainter(latest);painter.fillRect(panel,QColor('#464b78'));painter.end()
        self.state.shop_tooltip_rect=panel
        read=self.observe(latest=latest,panel=panel,source_exclude=[panel])
        self.assertFalse(read.retry);self.assertTrue(self.state.rows)
        self.assertIsNone(self.state.rows[0]['price']);self.assertTrue(self.state.rows[0]['reference_only'])
        self.assertEqual(self.state.rows[0]['name'],'Example Hat')

    def test_our_annotation_changes_are_never_native_source_contradictions(self):
        self.observe();annotation=QRect(210,151,70,25)
        latest=self.image.copy();painter=QPainter(latest);painter.fillRect(annotation,QColor('#171c25'));painter.end()
        frame=self.state.validate_frame(latest,pointer=self.point,shop_context=self.area,
            exclude=[annotation],source_exclusions=lambda panel:[annotation])
        self.assertFalse(frame.retired);self.assertEqual(self.state.rows[0]['price']['mesos'],100)

    def test_cursor_crossing_shop_guards_keeps_the_verified_page_and_rows(self):
        self.observe();page=self.state.shop_rows.page_revision
        for point in ((305,180),(95,180),(180,146),(150,160)):
            image=self.image.copy();painter=QPainter(image)
            painter.fillRect(cursor_rectangle(point),QColor('white'));painter.end()
            frame=self.state.validate_frame(image,pointer=point,shop_context=self.area)
            self.assertFalse(frame.retired)
            self.assertEqual(self.state.rows[0]['_item_id'],1)
            self.assertEqual(self.state.shop_rows.page_revision,page)

    def test_late_captured_cursor_pixels_are_masked_briefly_without_hiding_a_real_change(self):
        self.state.observe_shop(deepcopy(self.shop),self.image,self.image)
        with patch('price_lens.price_observations.time.monotonic',return_value=1):
            self.state.validate_frame(self.image,pointer=self.point)
        image=self.image.copy();painter=QPainter(image)
        painter.fillRect(cursor_rectangle(self.point),QColor('white'));painter.end()
        with patch('price_lens.price_observations.time.monotonic',return_value=1.1):
            self.assertFalse(self.state.validate_frame(image,pointer=(180,240)).retired)
        with patch('price_lens.price_observations.time.monotonic',return_value=1.9):
            self.assertTrue(self.state.validate_frame(image,pointer=(180,240)).retired)

    def test_several_quick_moves_cannot_drop_a_cursor_still_present_in_a_delayed_frame(self):
        self.state.observe_shop(deepcopy(self.shop),self.image,self.image)
        with patch('price_lens.price_observations.time.monotonic',return_value=1):
            self.state.validate_frame(self.image,pointer=self.point)
        for index in range(6):
            self.state.cursor_exclusions((400+index*20,450),now=1.05+index*.05)
        image=self.image.copy();painter=QPainter(image)
        painter.fillRect(cursor_rectangle(self.point),QColor('white'));painter.end()
        with patch('price_lens.price_observations.time.monotonic',return_value=1.6):
            self.assertFalse(self.state.validate_frame(image,pointer=(500,450)).retired)
        with patch('price_lens.price_observations.time.monotonic',return_value=1.9):
            self.assertTrue(self.state.validate_frame(image,pointer=(500,450)).retired)

    def test_duplicate_cursor_masks_do_not_exhaust_the_source_proof_bound(self):
        with patch('price_lens.price_observations.time.monotonic',return_value=1):
            for index in range(9):self.state.cursor_exclusions((400+index*20,450))
            point=self.state.cursor_point
            annotations=[QRect(400+index,10,1,1) for index in range(48)]
            caller_exclude=annotations+list(self.state.cursor_exclusions(point))
            read=self.state.observe_shop(deepcopy(self.shop),self.image,self.image,
                pointer=point,read_point=point,source_exclude=caller_exclude)
        self.assertFalse(read.retry)
        self.assertIsNotNone(self.state.rows[0].get('_identity_source'))
        self.assertEqual(self.state.rows[0]['price']['mesos'],100)

    def test_a_native_ocr_miss_restores_the_exact_unchanged_visible_row(self):
        self.observe();page=self.state.shop_rows.page_revision
        read=self.state.observe_shop({**self.shop,'rows':[]},self.image,self.image,
            pointer=self.point,read_point=self.point)
        self.assertFalse(read.retry);self.assertEqual(len(self.state.rows),1)
        row=self.state.rows[0]
        self.assertEqual(row['name'],'Example Hat');self.assertEqual(row['price']['mesos'],100)
        self.assertEqual(self.state.shop_rows.presentation_for(row)['mesos'],100)
        self.assertEqual(self.state.shop_rows.page_revision,page)
        changed=self.image.copy();changed.setPixelColor(220,176,QColor('white'))
        self.assertTrue(self.state.validate_frame(changed,pointer=self.point).retired)

    def test_a_tooltip_truncated_ocr_crop_cannot_replace_the_verified_table(self):
        self.observe();page=self.state.shop_rows.page_revision
        panel=QRect(240,158,150,160);image=self.image.copy()
        painter=QPainter(image);painter.fillRect(panel,QColor('#464b78'));painter.end()
        shop=dict(area=dict(x=100,y=150,width=140,height=40),rows=[
            dict(name='Example Hat',price=None,area=dict(x=137,y=150,width=103,height=31))])
        read=self.state.observe_shop(shop,image,image,pointer=self.point,read_point=self.point,
            panel=panel,source_exclude=[panel])
        self.assertFalse(read.retry);self.assertEqual(self.state.shop_rows.area,self.shop['area'])
        self.assertEqual(self.state.shop_rows.page_revision,page)
        self.assertEqual(self.state.rows[0]['area'],self.shop['rows'][0]['area'])
        self.assertEqual(self.state.shop_rows.presentation_for(self.state.rows[0])['mesos'],100)

    def test_a_fully_hidden_known_source_keeps_only_its_last_seen_presentation(self):
        old_mask=QRect(150,140,160,60)
        self.state.observe_shop(deepcopy(self.shop),self.image,self.image,source_exclude=[old_mask])
        proof=self.state.rows[0]['_identity_source']
        self.assertIsNotNone(proof)
        panel=QRect(98,150,55,120)
        image=self.image.copy();painter=QPainter(image)
        painter.fillRect(panel,QColor('#464b78'));painter.end()
        self.assertEqual(proof_state(proof,image,exclude=[native_occlusion(panel)]),'unknown')
        self.state.shop_tooltip_rect=panel
        read=self.state.observe_shop({**self.shop,'rows':[]},image,image,panel=panel)
        self.assertFalse(read.retry);self.assertEqual(len(self.state.rows),1)
        row=self.state.rows[0]
        self.assertEqual(row['_item_id'],1);self.assertIsNone(row['price'])
        self.assertEqual(self.state.shop_rows.presentation_for(row)['mesos'],100)
        self.state.viewport_changed()
        self.state.observe_shop({**self.shop,'rows':[]},image,image,panel=panel)
        self.assertEqual(self.state.rows,[],'A new viewport cannot borrow the previous page')

    def test_a_complete_native_row_touching_a_panel_is_still_an_accepted_offer(self):
        self.observe();panel=QRect(295,158,100,160)
        image=self.image.copy();painter=QPainter(image)
        painter.fillRect(panel,QColor('#464b78'));painter.end()
        read=self.state.observe_shop(deepcopy(self.shop),image,image,panel=panel)
        self.assertFalse(read.retry)
        self.assertEqual(self.state.rows[0]['name'],'Example Hat')
        self.assertEqual(self.state.rows[0]['price']['mesos'],100)
        self.assertFalse(self.state.rows[0].get('presentation_held'))

    def component_page(self,*,fresh=False):
        point=(500,450)
        self.state.observe_shop(deepcopy(self.shop),self.image,self.image,pointer=point,read_point=point)
        if fresh:
            self.state.browsing._advance();self.state.viewport_changed()
        # Both complete text runs end before this native pane: title x224,
        # asking line x194. Its full rectangle still crosses the row's band.
        panel=QRect(240,158,150,160);image=self.image.copy()
        painter=QPainter(image);painter.fillRect(panel,QColor('#464b78'));painter.end()
        return point,panel,image

    def test_clipping_only_a_blank_tail_preserves_a_fresh_complete_offer(self):
        point,panel,image=self.component_page();shop=deepcopy(self.shop)
        shop['rows'][0]['area']['width']=103
        read=self.state.observe_shop(shop,image,image,pointer=point,read_point=point,panel=panel)
        self.assertFalse(read.retry)
        row=self.state.rows[0]
        self.assertEqual(row['_item_id'],1);self.assertEqual(row['price']['mesos'],100)
        self.assertEqual(row['area'],self.shop['rows'][0]['area'])
        self.assertFalse(row.get('reference_only'));self.assertFalse(row.get('presentation_held'))

    def test_a_clipped_readable_new_title_cannot_disappear_before_viewport_comparison(self):
        point,panel,image=self.component_page()
        self.state.catalog=Catalog({'items':[dict(id=1,name='Example Hat'),dict(id=2,name='Other Hat')]})
        painter=QPainter(image);painter.fillRect(137,150,99,17,QColor('#cad5df'))
        painter.fillRect(145,155,25,6,QColor('black'));painter.fillRect(180,155,35,6,QColor('black'));painter.end()
        shop=deepcopy(self.shop);shop['rows'][0].update(name='Other Hat',price=dict(quantity=1,mesos=200))
        shop['rows'][0]['area']['width']=103
        read=self.state.observe_shop(shop,image,image,pointer=point,read_point=point,panel=panel)
        self.assertTrue(read.viewport_changed);self.assertFalse(read.retry)
        row=self.state.rows[0]
        self.assertEqual(row['_item_id'],2);self.assertEqual(row['price']['mesos'],200)

    def test_clipped_name_only_read_keeps_its_own_complete_native_title(self):
        point,panel,image=self.component_page();shop=self.name_only_shop()
        shop['rows'][0].update(nameArea=dict(x=137,y=150,width=99,height=17))
        shop['rows'][0]['area']['width']=103
        self.state.observe_shop(shop,image,image,pointer=point,read_point=point,panel=panel)
        row=self.state.rows[0]
        self.assertEqual(row['_item_id'],1);self.assertTrue(row.get('nameOnly'))
        self.assertIsNone(row['price']);self.assertFalse(row.get('reference_only'))

    def test_fresh_complete_components_survive_deltas_only_in_a_masked_blank_tail(self):
        for name_only in (False,True):
            with self.subTest(name_only=name_only):
                self.setUp();point,panel,image=self.component_page(fresh=True)
                shop=deepcopy(self.shop);latest=image.copy()
                if name_only:
                    shop['rows'][0].update(nameOnly=True,price=None,
                        nameArea=dict(x=137,y=150,width=103,height=17))
                    latest.setPixelColor(238,156,QColor('#b8b4c7'))
                else:latest.setPixelColor(260,176,QColor('#484d7a'))
                read=self.state.observe_shop(shop,image,latest,pointer=point,read_point=point,
                    panel=panel,source_exclude=[panel])
                self.assertFalse(read.retry);self.assertFalse(self.state.browsing.pending)
                row=self.state.rows[0]
                self.assertEqual(row['_item_id'],1);self.assertFalse(row.get('reference_only'))
                if name_only:self.assertIsNone(row['price'])
                else:self.assertEqual(row['price']['mesos'],100)

    def test_each_readable_row_gets_its_own_fresh_components_without_pointer_priority(self):
        other=deepcopy(self.shop['rows'][0]);other['area']['y']=230;other['price']['mesos']=200
        self.shop['rows'].append(other)
        painter=QPainter(self.image)
        painter.fillRect(104,234,24,27,QColor('#992211'))
        painter.fillRect(145,235,80,6,QColor('black'))
        painter.fillRect(145,254,50,6,QColor('black'));painter.end()
        point,panel,image=self.component_page(fresh=True);latest=image.copy()
        latest.setPixelColor(260,176,QColor('#484d7a'));latest.setPixelColor(260,256,QColor('#484d7a'))
        self.state.observe_shop(deepcopy(self.shop),image,latest,pointer=point,read_point=point,
            panel=panel,source_exclude=[panel])
        self.assertEqual([row['price']['mesos'] for row in self.state.rows],[100,200])
        self.assertTrue(all(row.get('_item_id')==1 and not row.get('reference_only') for row in self.state.rows))

    def test_native_separator_above_a_component_is_not_foreign_text(self):
        point,panel,image=self.component_page(fresh=True)
        painter=QPainter(image)
        painter.fillRect(137,150,162,1,QColor('#f5f6f7'))
        painter.fillRect(141,168,155,1,QColor('white'));painter.end()
        latest=image.copy();latest.setPixelColor(260,176,QColor('#484d7a'))
        self.state.observe_shop(deepcopy(self.shop),image,latest,pointer=point,read_point=point,
            panel=panel,source_exclude=[panel])
        row=self.state.rows[0]
        self.assertEqual(row['_item_id'],1);self.assertEqual(row['price']['mesos'],100)
        self.assertFalse(row.get('reference_only'))

    def test_isolated_white_pixels_above_ink_are_not_a_native_separator(self):
        _,_,image=self.component_page(fresh=True)
        image.setPixelColor(170,150,QColor('white'))
        self.assertIsNone(self.state.component_proof(self.shop['rows'][0],'name',image,image))

    def test_separator_support_cannot_hide_changed_name_or_asking_ink(self):
        for kind,y in (('name',150),('price',168)):
            with self.subTest(kind=kind):
                self.setUp();_,_,image=self.component_page(fresh=True)
                painter=QPainter(image);painter.fillRect(137,y,162,1,QColor('white'));painter.end()
                latest=image.copy();latest.setPixelColor(170,y+6,QColor('#cad5df'))
                self.assertIsNone(self.state.component_proof(self.shop['rows'][0],kind,image,latest))

    def test_only_a_complete_native_ellipsis_uses_the_smaller_name_ending(self):
        _,_,image=self.component_page(fresh=True)
        painter=QPainter(image);painter.fillRect(201,150,99,17,QColor('#cad5df'))
        for x in (205,209,213):painter.fillRect(x,158,2,2,QColor('black'))
        painter.fillRect(220,150,150,17,QColor('#464b78'));painter.end()
        for suffix,expected in (('...',True),('…',True),('..',False),('.',False),('',False)):
            with self.subTest(suffix=suffix):
                row={**self.shop['rows'][0],'name':'Example'+suffix}
                self.assertEqual(self.state.component_proof(row,'name',image,image) is not None,expected)
        row={**self.shop['rows'][0],'name':'Example...'}
        clipped=image.copy();painter=QPainter(clipped)
        painter.fillRect(213,150,150,17,QColor('#464b78'));painter.end()
        self.assertIsNone(self.state.component_proof(row,'name',clipped,clipped))
        changed=image.copy();changed.setPixelColor(213,158,QColor('#cad5df'))
        self.assertIsNone(self.state.component_proof(row,'name',image,changed))
        for missing in ((213,),(209,213)):
            with self.subTest(missing=missing):
                incomplete=image.copy();painter=QPainter(incomplete)
                for x in missing:painter.fillRect(x,158,2,2,QColor('#cad5df'))
                painter.end()
                self.assertIsNone(self.state.component_proof(row,'name',incomplete,incomplete))
        nonbaseline=image.copy();painter=QPainter(nonbaseline)
        painter.fillRect(213,158,2,2,QColor('#cad5df'));painter.fillRect(213,153,2,2,QColor('black'));painter.end()
        self.assertIsNone(self.state.component_proof(row,'name',nonbaseline,nonbaseline))
        asking=image.copy();painter=QPainter(asking)
        painter.fillRect(200,168,150,17,QColor('#464b78'));painter.end()
        self.assertIsNone(self.state.component_proof(row,'price',asking,asking))

    def test_an_exposed_title_with_blocked_asking_ink_supplies_no_current_amount(self):
        point,_,_=self.component_page(fresh=True);panel=QRect(180,170,170,160)
        latest=self.image.copy();painter=QPainter(latest);painter.fillRect(panel,QColor('#464b78'));painter.end()
        self.state.observe_shop(deepcopy(self.shop),self.image,latest,pointer=point,read_point=point,
            panel=panel,source_exclude=[panel])
        row=self.state.rows[0]
        self.assertEqual(row['_item_id'],1);self.assertTrue(row.get('nameOnly'))
        self.assertIsNone(row['price']);self.assertIsNone(self.state.shop_rows.presentation_for(row))

    def semantic_asking(self):
        image=self.image.copy();painter=QPainter(image)
        painter.fillRect(137,168,162,17,QColor('#cad5df'))
        # Generated native glyph spans isolate current-pixel/controller proof;
        # the native integration tests separately exercise actual text OCR.
        for start,width in ((0,3),(9,3),(14,4),(20,3),(27,4),(33,1),(37,4),(44,4),(51,5)):
            painter.fillRect(142+start,173,width,6,QColor('black'))
        painter.fillRect(204,173,5,6,QColor('black'))
        painter.fillRect(210,173,5,6,QColor('black'));painter.end()
        row=deepcopy(self.shop['rows'][0])
        row.update(price=dict(quantity=1,mesos=9999),priceText='1 for 9,999',
            priceArea=dict(x=137,y=168,width=65,height=17),
            priceValueArea=dict(x=137,y=168,width=65,height=17))
        return row,image

    def test_semantic_asking_keeps_complete_numbers_when_only_currency_tail_is_masked(self):
        row,image=self.semantic_asking()
        proof=self.state.component_proof(row,'price',image,image,
            pointer=(221,160),exclude=(QRect(211,168,20,17),))
        self.assertIsNotNone(proof)
        self.assertEqual(proof.rect,(137,168,65,17))
        # The same overlap is rejected when it covers any numeric-core ink.
        self.assertIsNone(self.state.component_proof(row,'price',image,image,pointer=(180,160)))
        self.assertIsNone(self.state.component_proof(row,'price',image,image,exclude=(QRect(193,173,2,2),)))

    def test_semantic_asking_requires_matching_strict_numeric_text(self):
        row,image=self.semantic_asking()
        for text in ('1 for 9,999 m','1 for 9,99','1 for 9999','0 for 9,999',
                     '2 for 9,999','1 for 8,999','1 for 9,999 mesos'):
            with self.subTest(text=text):
                self.assertIsNone(self.state.component_proof({**row,'priceText':text},'price',image,image))
        for price in (dict(quantity=True,mesos=9999),dict(quantity=1,mesos=9999.0),dict(quantity=1,mesos=999)):
            with self.subTest(price=price):
                self.assertIsNone(self.state.component_proof({**row,'price':price},'price',image,image))

    def test_joined_final_digit_cells_keep_the_same_complete_numeric_boundary(self):
        row,image=self.semantic_asking()
        painter=QPainter(image);painter.fillRect(190,173,3,6,QColor('black'));painter.end()
        self.assertIsNotNone(self.state.component_proof(row,'price',image,image))
        # A low comma stroke where the next group would start is a numeric
        # continuation, even when the ordinary baseline remains blank.
        continuation=image.copy();continuation.setPixelColor(200,181,QColor('black'))
        self.assertIsNone(self.state.component_proof(row,'price',continuation,continuation))

    def test_semantic_asking_cannot_hide_changed_digits_or_numeric_boundary(self):
        row,image=self.semantic_asking()
        for x in (151,196):
            with self.subTest(changed=x):
                latest=image.copy();latest.setPixelColor(x,174,QColor('#cad5df'))
                self.assertIsNone(self.state.component_proof(row,'price',image,latest,
                    exclude=(QRect(x,173,2,3),)))
        hidden=image.copy();painter=QPainter(hidden);painter.fillRect(198,168,4,17,QColor('#464b78'));painter.end()
        self.assertIsNone(self.state.component_proof(row,'price',hidden,hidden,
            exclude=(QRect(198,168,4,17),)))
        # Covering or changing the currency word supplies no numeric authority
        # and cannot invalidate the independently complete number.
        suffix=image.copy();painter=QPainter(suffix);painter.fillRect(203,168,20,17,QColor('#464b78'));painter.end()
        self.assertIsNotNone(self.state.component_proof(row,'price',image,suffix,
            exclude=(QRect(203,168,20,17),)))
        self.assertIsNotNone(self.state.component_proof(row,'price',suffix,suffix))

    def test_semantic_asking_rejects_partial_or_misplaced_numeric_geometry(self):
        row,image=self.semantic_asking()
        for key,value in (('x',138),('y',169),('height',16),('width',55),('width',79)):
            with self.subTest(key=key,value=value):
                malformed=deepcopy(row);malformed['priceValueArea'][key]=value
                self.assertIsNone(self.state.component_proof(malformed,'price',image,image))
        malformed=deepcopy(row);malformed['priceValueArea']=None
        self.assertIsNone(self.state.component_proof(malformed,'price',image,image))

    def test_semantic_numeric_proof_runs_even_when_a_broader_row_mask_matches(self):
        row,image=self.semantic_asking();self.image=image
        self.shop['rows']=[row];self.observe()
        latest=image.copy();latest.setPixelColor(196,174,QColor('#cad5df'))
        self.observe(latest=latest,source_exclude=(QRect(194,168,5,17),))
        self.assertFalse(any(row.get('price') for row in self.state.rows))

    def test_a_mask_cannot_hide_a_changed_asking_digit_while_reusing_a_fresh_amount(self):
        point,_,_=self.component_page(fresh=True);panel=QRect(180,170,170,160)
        latest=self.image.copy();latest.setPixelColor(190,176,QColor('#cad5df'))
        self.state.observe_shop(deepcopy(self.shop),self.image,latest,pointer=point,read_point=point,
            panel=panel,source_exclude=[panel])
        row=self.state.rows[0]
        self.assertEqual(row['_item_id'],1);self.assertIsNone(row['price'])
        self.assertTrue(row.get('nameOnly'))

    def test_a_masked_title_suffix_cannot_supply_a_fresh_item_or_offer(self):
        point,_,_=self.component_page(fresh=True);panel=QRect(200,154,150,160)
        latest=self.image.copy();painter=QPainter(latest);painter.fillRect(panel,QColor('#464b78'));painter.end()
        self.state.observe_shop(deepcopy(self.shop),self.image,latest,pointer=point,read_point=point,
            panel=panel,source_exclude=[panel])
        self.assertFalse(any(row.get('name') or row.get('_item_id') or row.get('price') for row in self.state.rows))

    def test_a_clipped_native_name_prefix_is_never_promoted_to_a_complete_title(self):
        point,panel,image=self.component_page();shop=deepcopy(self.shop)
        shop['rows'][0]['area']['width']=60
        read=self.state.observe_shop(shop,image,image,pointer=point,read_point=point,panel=panel)
        # The original page may retain its independently established reference;
        # the newly supplied prefix itself must not become an accepted offer.
        self.assertIsNone(read.shop['rows'][0].get('name'))
        self.assertIsNone(self.state.rows[0]['price']);self.assertTrue(self.state.rows[0].get('reference_only'))

    def test_masked_native_blank_guard_is_allowed_but_cursor_ink_is_not(self):
        for point,accepted in (((238,156),True),((180,160),False)):
            with self.subTest(point=point):
                self.setUp();_,panel,image=self.component_page(fresh=True)
                latest=image.copy();latest.setPixelColor(260,176,QColor('#484d7a'))
                self.state.observe_shop(deepcopy(self.shop),image,latest,pointer=point,read_point=point,
                    panel=panel,source_exclude=[panel])
                self.assertEqual(any(row.get('_item_id') for row in self.state.rows),accepted)
                if accepted:self.assertEqual(self.state.rows[0]['price']['mesos'],100)

    def test_component_recovery_does_not_reuse_an_old_ambiguous_popup_identity(self):
        point,panel,image=self.component_page()
        self.state.catalog=Catalog({'items':[dict(id=1,name='Example Hat'),dict(id=2,name='Example Hat')]})
        saved=self.state.shop_rows.rows[self.state.shop_rows.slot(self.shop['rows'][0])][0]
        saved.update(_identity_evidence='shop-description',_identity_epoch=self.state.browsing.epoch)
        shop=deepcopy(self.shop);shop['rows'][0]['area']['width']=103
        self.state.observe_shop(shop,image,image,pointer=point,read_point=point,panel=panel)
        self.assertIsNone(self.state.item_for(self.state.rows[0]))
        self.assertNotEqual(self.state.rows[0].get('_identity_evidence'),'shop-description')

    def test_component_metadata_cannot_move_name_or_amount_proof_to_another_slot(self):
        for field in ('nameArea','priceArea'):
            with self.subTest(field=field):
                self.setUp();point,panel,image=self.component_page(fresh=True)
                shop=deepcopy(self.shop);shop['rows'][0][field]=dict(x=137,y=230,width=99,height=17)
                latest=image.copy();latest.setPixelColor(260,176,QColor('#484d7a'))
                self.state.observe_shop(shop,image,latest,pointer=point,read_point=point,
                    panel=panel,source_exclude=[panel])
                if field=='nameArea':self.assertFalse(any(row.get('_item_id') for row in self.state.rows))
                else:
                    self.assertEqual(self.state.rows[0]['_item_id'],1)
                    self.assertIsNone(self.state.rows[0]['price'])

    def test_native_panel_trail_is_bounded_and_cleared_by_a_viewport_change(self):
        old=QRect(200,158,100,160);new=QRect(200,240,100,160)
        with patch('price_lens.price_observations.time.monotonic',return_value=1):
            self.state.shop_tooltip_rect=old
        with patch('price_lens.price_observations.time.monotonic',return_value=1.1):
            self.state.shop_tooltip_rect=new
            hidden=self.state.native_exclusions(new)
            self.assertIn(native_occlusion(old),hidden)
            self.assertIn(native_occlusion(new),hidden)
        with patch('price_lens.price_observations.time.monotonic',return_value=1.5):
            self.assertEqual(self.state.native_exclusions(new),(native_occlusion(new),))
            self.state.shop_tooltip_rect=old
            self.assertTrue(self.state.native_exclusions())
            self.state.viewport_changed()
            self.assertEqual(self.state.native_exclusions(),())

    def test_a_covered_unknown_row_never_captures_a_tooltip_as_its_source(self):
        self.shop['rows'][0].update(covered=True,name=None,price=None)
        self.observe()
        self.assertNotIn('_identity_source',self.state.rows[0])
        changed=self.image.copy();changed.setPixelColor(220,176,QColor('white'))
        frame=self.state.validate_frame(changed,pointer=self.point)
        self.assertFalse(frame.retired)

    def test_previous_native_panel_mask_cannot_erase_the_current_panel_geometry(self):
        self.observe();old=QRect(205,170,236,220);current=QRect(200,170,236,220)
        image=self.image.copy();painter=QPainter(image)
        painter.fillRect(current,QColor(70,65,105));painter.end()
        with patch('price_lens.price_observations.time.monotonic',return_value=1):
            self.state.shop_tooltip_rect=old
            self.state.shop_tooltip_rect=current
            frame=self.state.validate_frame(image,pointer=self.point)
        self.assertFalse(frame.retired)
        self.assertEqual(self.state.shop_tooltip_rect,current)

    def test_newer_pointer_coordinates_cannot_mask_the_captured_native_header(self):
        self.observe();image=self.image.copy();painter=QPainter(image)
        painter.fillRect(200,170,236,220,QColor(70,65,105))
        for x in (200,433):
            painter.fillRect(x,170,3,220,QColor(60,60,90))
            painter.fillRect(x+1,170,1,220,QColor(30,26,40))
        for y in (170,387):
            painter.fillRect(200,y,236,3,QColor(60,60,90))
            painter.fillRect(200,y+1,236,1,QColor(30,26,40))
        painter.fillRect(211,185,5,5,QColor(85,204,255));painter.end()
        frame=self.state.validate_frame(image,pointer=(200,180),shop_context=self.area)
        self.assertFalse(frame.retired)
        self.assertIsNotNone(self.state.shop_tooltip_rect)
        self.assertEqual(self.state.rows[0]['_item_id'],1)

    def test_ocr_rounding_and_missing_row_recovery_do_not_duplicate_a_slot(self):
        self.observe();shop=deepcopy(self.shop);shop['rows'][0]['area']['y']+=1
        read=self.state.observe_shop(shop,self.image,self.image,pointer=self.point,read_point=self.point)
        self.assertFalse(read.retry);self.assertEqual(len(self.state.rows),1)
        self.assertEqual(self.state.rows[0]['area'],self.shop['rows'][0]['area'])

    def test_personalized_description_keeps_the_known_shop_rows_visible(self):
        self.observe();image=self.image.copy();painter=QPainter(image)
        painter.fillRect(200,170,236,240,QColor(70,65,105))
        for x in (200,433):
            painter.fillRect(x,170,3,240,QColor(60,60,90))
            painter.fillRect(x+1,170,1,240,QColor(30,26,40))
        for y in (170,205):
            painter.fillRect(200,y,236,3,QColor(60,60,90))
            painter.fillRect(200,y+1,236,1,QColor(30,26,40))
        painter.fillRect(211,222,5,5,QColor(85,204,255));painter.end()
        frame=self.state.validate_frame(image,pointer=self.point,shop_context=self.area)
        self.assertFalse(frame.retired);self.assertTrue(frame.panel_changed)
        self.assertEqual(self.state.rows[0]['_item_id'],1)
        self.assertLessEqual(self.state.shop_tooltip_rect.top(),172)

    def test_an_overlapping_moved_description_refreshes_geometry_before_retirement(self):
        from price_lens.tooltip_geometry import still_present
        other=deepcopy(self.shop['rows'][0]);other['area']['y']=395
        self.shop['rows'].append(other)
        self.observe();old=QRect(200,170,236,220);panel=QRect(200,190,236,220)
        self.state.shop_tooltip_rect=old
        image=self.image.copy();painter=QPainter(image)
        painter.fillRect(panel,QColor(70,65,105))
        for x in (panel.left(),panel.right()-2):
            painter.fillRect(x,panel.top(),3,panel.height(),QColor(60,60,90))
            painter.fillRect(x+1,panel.top(),1,panel.height(),QColor(30,26,40))
        painter.fillRect(panel.left(),panel.top(),panel.width(),3,QColor(60,60,90))
        painter.fillRect(panel.left(),panel.top()+1,panel.width(),1,QColor(30,26,40))
        painter.fillRect(211,205,5,5,QColor(85,204,255));painter.end()
        self.assertTrue(still_present(image,old),'The old rectangle alone cannot detect this move')
        frame=self.state.validate_frame(image,pointer=self.point,shop_context=self.area,
            source_exclusions=lambda bounds:[bounds] if bounds is not None else [])
        self.assertFalse(frame.retired);self.assertTrue(frame.panel_changed)
        self.assertLessEqual(abs(self.state.shop_tooltip_rect.top()-panel.top()),4)

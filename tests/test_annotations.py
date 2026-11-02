"""Only our own offscreen window and mocked OS pointer; no input is sent."""
import json
import os
import unittest
from unittest.mock import patch

from PySide6.QtCore import QPoint, QCoreApplication, QEvent,QRect
from PySide6.QtWidgets import QApplication
from price_lens.annotations import AnnotationWindow


class AnnotationMotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = AnnotationWindow(start_listener=False)
        self.command = {"geometry": [0, 0, 800, 800], "hover_enabled": True, "rows": [
            {"x": 120, "y": 90, "name": "Example Hat", "key": 1, "text": "FM 1,000 mesos",
             "follow_pointer": [100, 100], "pointer_region": [0, 0, 800, 800]}]}
        with patch("price_lens.annotations.QCursor.pos", return_value=QPoint(100, 100)):
            self.window.read_command(json.dumps(self.command))

    def tearDown(self):
        self.window.pointer_timer.stop()
        self.window.watchdog.stop()
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def test_card_follows_pointer_without_a_new_reading_or_drawing_command(self):
        row = self.window.rows[0]
        before = self.window.label_rect(row, QPoint(100, 100))
        last_command = self.window.last_command
        with patch("price_lens.annotations.QCursor.pos", return_value=QPoint(108, 105)), patch("builtins.print"):
            self.window.report_pointer()
        after = self.window.label_rect(row, QPoint(108, 105))
        self.assertEqual((after.x() - before.x(), after.y() - before.y()), (8, 5))
        self.assertEqual(self.window.last_command, last_command)
        self.assertEqual(self.window.pointer_timer.interval(), 16)

    def test_description_flip_replaces_the_pointer_offset_and_omission_clears_the_anchor(self):
        row=dict(x=410,y=310,key='item',kind='item',name='Hat',text='FM 1,000',
            follow_pointer=[450,300],pointer_region=[0,0,800,800],bounds=[0,0,800,800],
            description_box=[400,350,236,260],avoid_regions=[[400,350,236,260]])
        self.window.read_command(json.dumps({**self.command,'rows':[row]}));active=self.window.rows[0]
        self.assertEqual(active['_cursor_offset'],(-40,10))
        flipped={**row,'x':60,'follow_pointer':[460,300],'description_box':[50,350,236,260],
            'avoid_regions':[[50,350,236,260]],'comparison_box':[289,350,236,200]}
        self.window.read_command(json.dumps({**self.command,'rows':[flipped]}))
        self.assertIs(self.window.rows[0],active);self.assertEqual(active['_cursor_offset'],(-400,10))
        plain={key:value for key,value in row.items() if key not in ('description_box','comparison_box')}
        self.window.read_command(json.dumps({**self.command,'rows':[plain]}))
        self.assertIsNone(active['description_box']);self.assertIsNone(active['comparison_box'])

    def test_inventory_card_avoids_source_cells_and_the_native_title(self):
        row=dict(x=1000,y=238,key='inventory',kind='item',name='Hat',text='FM 1,000',
                 follow_pointer=[1100,300],pointer_region=[0,28,1366,766],bounds=[0,28,1366,766],
                 avoid_regions=[[1030,220,207,300],[900,233,180,20]])
        with patch('price_lens.annotations.QCursor.pos',return_value=QPoint(1100,300)):
            self.window.read_command(json.dumps({**self.command,'geometry':[0,0,1366,794],'rows':[row]}))
        active=self.window.rows[0];box=self.window.label_rect(active,QPoint(1100,300))
        self.assertIsNotNone(box);self.assertTrue(QRect(*row['bounds']).contains(box))
        self.assertTrue(all(not box.intersects(QRect(*rect).adjusted(-3,-3,3,3)) for rect in row['avoid_regions']))
        self.assertLess(abs(box.x()-row['x'])+abs(box.y()-(row['y']-5)),250)

    def test_avoiding_proof_keeps_pointer_following_on_unblocked_axes_without_new_commands(self):
        row={**self.command['rows'][0],'kind':'item','bounds':[0,0,800,800],
             'avoid_regions':[[110,80,300,100]]}
        self.window.read_command(json.dumps({**self.command,'rows':[row]}));active=self.window.rows[0]
        before=self.window.label_rect(active,QPoint(100,100));stamp=self.window.last_command
        after=self.window.label_rect(active,QPoint(108,105))
        self.assertEqual(after.x()-before.x(),8);self.assertEqual(after.y(),before.y())
        self.assertFalse(after.intersects(QRect(*row['avoid_regions'][0])))
        self.assertEqual(self.window.last_command,stamp)
        for point in (QPoint(99,100),QPoint(101,100),QPoint(100,99),QPoint(100,101)):
            self.assertEqual(self.window.label_rect(active,point).y(),before.y())

    def test_safe_pointer_following_has_the_original_offset_when_proof_is_far_away(self):
        row={**self.command['rows'][0],'kind':'item','bounds':[0,0,800,800],
             'avoid_regions':[[500,500,50,50]]}
        self.window.read_command(json.dumps({**self.command,'rows':[row]}));active=self.window.rows[0]
        before=self.window.label_rect(active,QPoint(100,100));after=self.window.label_rect(active,QPoint(108,105))
        self.assertEqual((after.x()-before.x(),after.y()-before.y()),(8,5))

    def test_small_game_bounds_find_a_safe_edge_or_suppress_an_unplaceable_card(self):
        row=dict(x=200,y=80,key='item',kind='item',name='Hat',text='FM 1,000',bounds=[20,20,300,180],
                 avoid_regions=[[20,20,220,80],[150,100,150,25]])
        self.window.read_command(json.dumps({**self.command,'rows':[row]}));active=self.window.rows[0]
        box=self.window.label_rect(active,QPoint())
        self.assertIsNotNone(box);self.assertTrue(QRect(*row['bounds']).contains(box))
        self.assertTrue(all(not box.intersects(QRect(*rect)) for rect in row['avoid_regions']))
        blocked={**row,'bounds':[20,20,140,80],'avoid_regions':[[20,20,140,80]]}
        self.window.read_command(json.dumps({**self.command,'rows':[blocked]}))
        self.assertIsNone(self.window.label_rect(self.window.rows[0],QPoint()))
        short={**row,'bounds':[20,20,300,30],'avoid_regions':[[20,20,10,10]]}
        self.window.read_command(json.dumps({**self.command,'rows':[short]}))
        self.assertIsNone(self.window.label_rect(self.window.rows[0],QPoint()))

    def test_omitted_avoid_regions_clear_old_evidence_on_a_reused_item(self):
        row=dict(x=120,y=90,key='item',kind='item',name='Hat',text='FM 1,000',bounds=[0,0,800,800])
        self.window.read_command(json.dumps({**self.command,'rows':[{**row,'avoid_regions':[[110,80,300,100]]}]}))
        active=self.window.rows[0];avoiding=self.window.label_rect(active,QPoint())
        self.window.read_command(json.dumps({**self.command,'rows':[row]}))
        self.assertIs(self.window.rows[0],active);self.assertEqual(active['avoid_regions'],[])
        self.assertEqual(self.window.label_rect(active,QPoint()),QRect(120,85,active['_width'],36))
        self.assertNotEqual(self.window.label_rect(active,QPoint()),avoiding)

    def test_watched_label_pulses_twice_then_stays_marked_without_restarting(self):
        row={**self.command['rows'][0],'watched':True,'watch_event':10,'color':'#86ceac'}
        self.window.read_command(json.dumps({**self.command,'rows':[row]}))
        active=self.window.rows[0];animation=active['_watch_pulse']
        for when, expected in ((400,1),(800,0),(1200,1)):
            animation.setCurrentTime(when)
            self.assertAlmostEqual(active['_watch_level'],expected,places=5)
        self.window.read_command(json.dumps({**self.command,'rows':[{**row,'text':'FM 1,200 mesos'}]}))
        self.assertIs(self.window.rows[0]['_watch_pulse'],animation)
        animation.setCurrentTime(1600)
        self.assertIsNone(active['_watch_pulse'])
        self.assertTrue(active['watched'])
        self.assertEqual(active['color'],'#86ceac')
        self.window.read_command(json.dumps({**self.command,'rows':[row]}))
        self.assertIsNone(self.window.rows[0]['_watch_pulse'])

    def test_short_missing_label_does_not_replay_the_same_watch_event(self):
        row={**self.command['rows'][0],'watched':True,'watch_event':20}
        self.window.read_command(json.dumps({**self.command,'rows':[row]}))
        self.window.read_command(json.dumps({**self.command,'rows':[],'hover_enabled':False}))
        self.window.read_command(json.dumps({**self.command,'rows':[row]}))
        self.assertIsNone(self.window.rows[0].get('_watch_pulse'))
        self.window.read_command(json.dumps({**self.command,'rows':[{**row,'watch_event':21}]}))
        self.assertIsNotNone(self.window.rows[0].get('_watch_pulse'))

    def test_reduce_motion_keeps_the_watch_marker_without_a_deferred_pulse(self):
        row={**self.command['rows'][0],'watched':True,'watch_event':30}
        self.window.read_command(json.dumps({**self.command,'rows':[row],'reduce_motion':True}))
        self.assertTrue(self.window.rows[0]['watched'])
        self.assertIsNone(self.window.rows[0].get('_watch_pulse'))
        self.window.read_command(json.dumps({**self.command,'rows':[row],'reduce_motion':False}))
        self.assertIsNone(self.window.rows[0].get('_watch_pulse'))

    def test_watched_shop_label_stays_opaque_under_native_tooltips(self):
        row={'x':120,'y':90,'name':'Example Hat','key':'shop:0:1','text':'FM 1,000 mesos',
             'kind':'shop','color':'#86ceac','watched':True,'watch_event':40,'occlusion':[110,80,300,100]}
        self.window.read_command(json.dumps({**self.command,'rows':[row]}))
        active=self.window.rows[0]
        self.assertEqual(active['_target_alpha'],1.0)
        pulse=active['_watch_pulse']
        self.window.read_command(json.dumps({**self.command,'rows':[row]}))
        self.assertIs(self.window.rows[0]['_watch_pulse'],pulse)
        self.assertEqual(self.window.rows[0]['_target_alpha'],1.0)

    def test_shop_labels_stay_opaque_with_and_without_a_native_description(self):
        row={'x':120,'y':90,'name':'Hat','key':'shop:1:1','kind':'shop','text':'FM 1,000','viewport_epoch':1}
        state={**self.command,'shop_viewport_epoch':1,'rows':[row],'reduce_motion':True}
        self.window.read_command(json.dumps(state));active=self.window.rows[0]
        before=self.window.label_rect(active,QPoint(0,0))
        for box in ([110,80,300,100],None,[0,0,800,800],None):
            self.window.read_command(json.dumps({**state,'rows':[{**row,'occlusion':box}]}))
            self.assertIs(self.window.rows[0],active);self.assertEqual(active['_alpha'],1)
            self.assertEqual(self.window.label_rect(active,QPoint(500,500)),before)


    def test_shop_description_clones_are_rejected_without_suppressing_inventory(self):
        shop={'x':120,'y':90,'name':'Hat','key':'shop:1:1','kind':'shop','text':'FM 1,000','viewport_epoch':1}
        clone={**shop,'key':'description:shop:1:1','kind':'item','source_shop_key':shop['key']}
        inventory={**self.command['rows'][0],'key':'inventory','kind':'item'}
        self.window.read_command(json.dumps({**self.command,'shop_viewport_epoch':1,'rows':[shop,clone,inventory]}))
        self.assertEqual([row['key'] for row in self.window.rows],[shop['key'],'inventory'])
        self.assertFalse(any(row.get('source_shop_key') for row in self.window.retiring))

    def test_add_item_form_fades_only_actual_shop_label_intersections_and_clears(self):
        shop=dict(x=120,y=90,name='Hat',key='shop:1:1',kind='shop',text='FM 1,000',viewport_epoch=1)
        other={**shop,'key':'shop:1:2','y':250}
        item={**shop,'key':'inventory','kind':'item'}
        state={**self.command,'shop_viewport_epoch':1,'reduce_motion':True}
        self.window.read_command(json.dumps({**state,'rows':[shop,other,item]}))
        active,uncovered,inventory=self.window.rows
        box=self.window.label_rect(active,QPoint())
        form=[box.right()-1,box.top(),50,box.height()]
        rows=[{**row,'shop_entry':form} for row in (shop,other,item)]
        self.window.read_command(json.dumps({**state,'rows':rows}))
        self.assertIs(self.window.rows[0],active)
        self.assertEqual(active['_alpha'],.35)
        self.assertEqual(uncovered['_alpha'],1)
        self.assertEqual(inventory['_alpha'],1)
        # Move the form away while retaining the same native row identity.
        self.window.read_command(json.dumps({**state,'rows':[{**shop,'shop_entry':[700,700,50,50]},other,item]}))
        self.assertEqual(active['_alpha'],1)
        self.window.read_command(json.dumps({**state,'rows':rows}))
        self.window.read_command(json.dumps({**state,'rows':[shop,other,item]}))
        self.assertIsNone(active['shop_entry']);self.assertEqual(active['_alpha'],1)

    def test_add_item_form_fade_is_continuous_interruptible_and_not_restarted(self):
        from PySide6.QtTest import QTest
        shop=dict(x=120,y=90,name='Hat',key='shop:1:1',kind='shop',text='FM 1,000',viewport_epoch=1)
        state={**self.command,'shop_viewport_epoch':1}
        self.window.read_command(json.dumps({**state,'rows':[shop]}));QTest.qWait(150)
        active=self.window.rows[0];box=self.window.label_rect(active,QPoint())
        covered={**shop,'shop_entry':list(box.getRect())}
        self.window.read_command(json.dumps({**state,'rows':[covered]}))
        fade=active['_fade'];self.assertEqual(fade.endValue(),.35)
        QTest.qWait(45);middle=active['_alpha'];self.assertGreater(middle,.35);self.assertLess(middle,1)
        self.window.read_command(json.dumps({**state,'rows':[covered]}))
        self.assertIs(active['_fade'],fade)
        self.window.read_command(json.dumps({**state,'rows':[shop]}))
        self.assertEqual(active['_fade'].startValue(),middle);self.assertEqual(active['_fade'].endValue(),1)
        QTest.qWait(150);self.assertEqual(active['_alpha'],1)
        self.assertFalse(self.window.retiring)

    def test_invalid_add_item_geometry_cannot_dim_a_shop_label(self):
        shop=dict(x=120,y=90,name='Hat',key='shop:1:1',kind='shop',text='FM 1,000')
        for form in (None,[],[100,80,-1,50],[100,80,200,0],[100,80,'200',50]):
            self.window.read_command(json.dumps({**self.command,'reduce_motion':True,'rows':[{**shop,'shop_entry':form}]}))
            self.assertEqual(self.window.rows[0]['_alpha'],1)

    def test_rejected_shop_source_disappears_without_a_stale_fade_at_the_same_epoch(self):
        shop={'x':120,'y':90,'name':'Hat','key':'shop:1:1','kind':'shop','text':'FM 1,000','viewport_epoch':1}
        inventory={'x':120,'y':190,'name':'Other Hat','key':'inventory','kind':'item','text':'FM 2,000'}
        state={**self.command,'shop_viewport_epoch':1,'hover_enabled':True}
        self.window.read_command(json.dumps({**state,'rows':[shop,inventory]}))
        self.window.read_command(json.dumps({**state,'rows':[]}))
        self.assertFalse(any(row.get('kind')=='shop' for row in self.window.retiring))
        self.assertTrue(any(row.get('kind')=='item' for row in self.window.retiring))


    def test_unknown_new_viewport_retires_old_shop_and_clone_without_new_rows(self):
        shop={'x':120,'y':90,'name':'Hat','key':'shop:1:1','kind':'shop','text':'FM 1,000',
              'viewport_epoch':1,'occlusion':[250,80,300,240]}
        clone={**shop,'key':'description:shop:1:1','kind':'item','source_shop_key':shop['key'],
               'description_box':[250,80,300,240],'bounds':[0,0,800,800],'occlusion':None}
        state={**self.command,'shop_viewport_epoch':1,'rows':[shop,clone]}
        self.window.read_command(json.dumps(state));old=list(self.window.rows)
        self.window.read_command(json.dumps({**state,'shop_viewport_epoch':2,'shop_viewport_pending':True,'rows':[]}))
        self.assertEqual(self.window.rows,[]);self.assertEqual(self.window.retiring,[])
        self.assertTrue(all(row.get('_fade') is None for row in old))

    def test_old_epoch_annotations_are_rejected_and_inventory_hover_is_independent(self):
        shop={'x':120,'y':90,'name':'Hat','key':'shop:1:1','kind':'shop','text':'FM 1,000','viewport_epoch':1}
        inventory={**self.command['rows'][0],'kind':'item'}
        self.window.read_command(json.dumps({**self.command,'shop_viewport_epoch':2,'shop_browsing_priority':True,
                                             'rows':[shop,inventory]}))
        self.assertEqual(len(self.window.rows),1);self.assertEqual(self.window.rows[0]['key'],inventory['key'])

    def test_cursor_jump_or_leaving_game_hides_the_old_reference(self):
        row = self.window.rows[0]
        self.assertIsNone(self.window.label_rect(row, QPoint(250, 250)))
        row["pointer_region"] = [95, 95, 10, 10]
        self.assertIsNone(self.window.label_rect(row, QPoint(110, 100)))

    def test_stationary_pointer_does_not_repaint(self):
        with patch("price_lens.annotations.QCursor.pos", return_value=QPoint(100, 100)), patch("builtins.print"):
            self.window.report_pointer()
            with patch.object(self.window, "update") as repaint:
                self.window.report_pointer()
            repaint.assert_not_called()

    def test_linked_description_replaces_cursor_tracking_and_stays_inside_game_bounds(self):
        old=self.window.rows[0]
        fixed={k:v for k,v in self.command['rows'][0].items() if k not in ('follow_pointer','pointer_region')}
        fixed.update(kind='item',x=490,y=490,bounds=[20,20,480,480])
        self.window.read_command(json.dumps({**self.command,'rows':[fixed],'reduce_motion':True}))
        row=self.window.rows[0]
        self.assertIs(row,old);self.assertNotIn('follow_pointer',row)
        box=self.window.label_rect(row,QPoint(900,900))
        self.assertLess(box.right(),500);self.assertLess(box.bottom(),500)

    def test_shop_label_positions_stay_fixed(self):
        row = {"x": 120, "y": 90, "_width": 230}
        self.assertEqual(self.window.label_rect(row, QPoint(100, 100)),
                         self.window.label_rect(row, QPoint(140, 130)))




    def test_inventory_card_has_a_short_fade_in_and_out(self):
        row = self.window.rows[0]
        row["_fade"].setCurrentTime(110)
        self.assertAlmostEqual(row["_alpha"], 1.0)
        with patch("price_lens.annotations.QCursor.pos", return_value=QPoint(100, 100)):
            self.window.read_command(json.dumps({**self.command, "rows": []}))
        self.assertIn(row, self.window.retiring)
        fade = row["_fade"]
        fade.setCurrentTime(45)
        self.assertGreater(row["_alpha"], 0.0)
        self.assertLess(row["_alpha"], 1.0)
        fade.setCurrentTime(90)
        self.assertNotIn(row, self.window.retiring)

    def test_shop_prices_fade_and_move_between_captured_positions(self):
        shop = {"x": 120, "y": 90, "name": "Example Hat", "key": "shop:0:1",
                "text": "FM 1,000 mesos", "animate_move": True}
        self.window.read_command(json.dumps({**self.command, "rows": [shop]}))
        row = self.window.rows[0]
        row["_fade"].setCurrentTime(110)
        self.assertAlmostEqual(row["_alpha"], 1.0)
        before = self.window.label_rect(row, QPoint(0, 0))
        shop = {**shop, "x": 160, "y": 130}
        self.window.read_command(json.dumps({**self.command, "rows": [shop]}))
        move = row["_move"]
        move.setCurrentTime(45)
        middle = self.window.label_rect(row, QPoint(0, 0))
        self.assertGreater(middle.x(), before.x())
        self.assertLess(middle.x(), 160)
        move.setCurrentTime(95)
        self.assertEqual(self.window.label_rect(row, QPoint(0, 0)).x(), 160)
        self.window.read_command(json.dumps({**self.command, "rows": []}))
        self.assertIn(row, self.window.retiring)
        row["_fade"].setCurrentTime(90)
        self.assertNotIn(row, self.window.retiring)

    def test_disabling_labels_clears_immediately_instead_of_leaving_a_fade(self):
        self.window.read_command(json.dumps({**self.command, "rows": [], "hover_enabled": False}))
        self.assertEqual(self.window.retiring, [])
        self.assertTrue(self.window.isHidden())

    def test_repeated_tooltip_changes_keep_the_same_pixels_color_and_label(self):
        self.window.read_command(json.dumps({**self.command,'rows':[],'hover_enabled':False}))
        row={'x':120,'y':90,'name':'Hat','key':'shop:0','kind':'shop','text':'FM 1,000',
             'color':'#86ceac','deal_delta':'-25%'}
        state={**self.command,'rows':[row]}
        self.window.read_command(json.dumps(state));active=self.window.rows[0]
        active['_fade'].setCurrentTime(110);before=self.window.grab().toImage()
        for box in ([200,80,300,100],None)*6:
            self.window.read_command(json.dumps({**state,'rows':[{**row,'occlusion':box}]}))
            self.assertIs(self.window.rows[0],active)
            self.assertEqual(active['_alpha'],1.0);self.assertEqual(active['_target_alpha'],1.0)
            self.assertEqual(active['color'],'#86ceac');self.assertEqual(active['deal_delta'],'-25%')
            self.assertEqual(self.window.grab().toImage(),before)

    def test_new_shop_page_or_new_item_in_the_slot_does_not_trail_old_references(self):
        self.window.read_command(json.dumps({**self.command,'rows':[],'hover_enabled':False}))
        row={'x':120,'y':90,'name':'Hat','key':'shop:2:100:slot','kind':'shop',
             'shop_page':2,'shop_slot':[60,20,180,40],'text':'FM 1,000'}
        for changed in ({**row,'shop_page':3,'key':'shop:3:100:slot'},
                        {**row,'key':'shop:2:200:slot','name':'Shoes'}):
            self.window.read_command(json.dumps({**self.command,'rows':[row]}))
            old=self.window.rows[0];old['_fade'].setCurrentTime(110)
            self.window.read_command(json.dumps({**self.command,'rows':[changed]}))
            self.assertNotIn(old,self.window.retiring)
            self.assertIsNone(old.get('_fade'))

    def test_reduce_motion_keeps_shop_labels_opaque_without_an_animation(self):
        self.window.read_command(json.dumps({**self.command,'reduce_motion':True,'rows':[
            {'x':120,'y':90,'name':'Hat','key':'shop:0','kind':'shop','text':'FM 1,000','occlusion':[200,80,300,100]}]}))
        self.assertAlmostEqual(self.window.rows[0]['_alpha'],1.0)
        self.assertIsNone(self.window.rows[0].get('_fade'))




    def test_age_updates_do_not_pulse_a_stable_market_price(self):
        row={'x':120,'y':90,'name':'Hat','key':'shop:0','kind':'shop','text':'FM 1,000 · 1s',
             'content_id':[1,1000]}
        state={**self.command,'rows':[row]};self.window.read_command(json.dumps(state))
        self.window.rows[0]['_fade'].setCurrentTime(110)
        self.window.read_command(json.dumps({**state,'rows':[{**row,'text':'FM 1,000 · 2s'}]}))
        self.assertIsNone(self.window.rows[0].get('_text_fade'))
        self.assertAlmostEqual(self.window.rows[0].get('_text_alpha',1),1)

    def test_scan_status_uses_game_bottom_right_and_stacks_above_tracker(self):
        from price_lens.overlay_layout import corner_offset
        bounds=[100,150,600,500]
        tracker={'kind':'tracking','anchor':'bottom_left','bounds':bounds,'tracking_height':56}
        offset=corner_offset(bounds,[tracker]);self.assertEqual(offset,62)
        status={'kind':'translation_status','key':'chat:status','name':'Korean translation','text':'Scanning… 4s',
                'x':0,'y':0,'anchor':'bottom_right','bounds':bounds,'bottom_offset':offset}
        self.window.read_command(json.dumps({**self.command,'reduce_motion':True,'rows':[status]}))
        rect=self.window.label_rect(self.window.rows[0],QPoint())
        self.assertEqual(rect.right(),695)
        self.assertEqual(rect.bottom(),645-offset)

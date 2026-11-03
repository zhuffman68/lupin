"""Late shop OCR cannot cross a captured viewport boundary."""
import json
from pathlib import Path
import time
import unittest
from dataclasses import replace
from unittest.mock import PropertyMock,patch
from PySide6.QtGui import QColor,QImage

from PySide6.QtWidgets import QApplication

from price_lens.capture import PixelReader
from price_lens.reader_request import SubmittedRequest
from price_lens.platform_paths import reader_binary


ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(reader_binary(ROOT).is_file(),'existing reader binary required; never build in this suite')
class ShopViewportCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.reader=PixelReader(ROOT);self.reader.timer.stop()
        self.addCleanup(self.reader.close)
        self.reader.active_request=self.reader.submitted_request=SubmittedRequest('prices',self.reader.image,None,
            self.reader.image_sequence,self.reader.generation,time.monotonic(),shop_epoch=self.reader.shop_browsing.epoch)
        self.readings=[];self.reader.reading.connect(self.readings.append)

    def deliver(self,**fields):
        self.reader.buffer=json.dumps({'atMs':int(time.monotonic()*1000),'shop':None,'tooltip':None,**fields}).encode()+b'\n'
        self.reader.on_output()

    def test_late_shop_result_is_discarded_after_viewport_changes(self):
        previous=self.reader.image_sequence
        self.reader.shop_browsing.reset()
        self.deliver()
        self.assertEqual(self.readings,[])
        self.assertGreater(self.reader.image_sequence,previous)
        self.assertIsNone(self.reader.shop_fingerprint)

    def test_current_result_carries_its_viewport_epoch(self):
        self.deliver()
        self.assertEqual(len(self.readings),1)
        self.assertEqual(self.readings[0]['shopViewportEpoch'],self.reader.shop_browsing.epoch)

    def test_partial_reply_keeps_the_same_immutable_request_and_deadline_until_final(self):
        request=self.reader.active_request
        self.deliver(shopPartial=True)
        self.assertIs(self.reader.active_request,request)
        self.assertEqual(self.reader.active_request.deadline_at,request.deadline_at)
        self.assertEqual(len(self.readings),1)
        self.deliver()
        self.assertIsNone(self.reader.active_request)
        self.assertEqual(len(self.readings),2)

    def test_scroll_between_partial_and_final_rejects_the_old_final(self):
        self.deliver(shopPartial=True)
        self.assertEqual(len(self.readings),1)
        self.reader.shop_browsing.reset()
        self.deliver()
        self.assertIsNone(self.reader.active_request)
        self.assertEqual(len(self.readings),1)

    def test_partial_roi_reply_publishes_fresh_rows_while_requesting_full_frame(self):
        image=QImage(800,600,QImage.Format.Format_RGBA8888);image.fill(QColor('#cad5df'))
        self.reader.image=image
        self.reader.active_request=replace(self.reader.active_request,frame=image,using_roi=True)
        shop=dict(area=dict(x=100,y=150,width=199,height=235),rows=[
            dict(area=dict(x=137,y=150,width=162,height=35),name='Work Gloves',price=dict(quantity=1,mesos=100)),
            dict(area=dict(x=137,y=190,width=162,height=35),name='Incomplete row',price=None)])
        self.deliver(shop=shop)
        self.assertEqual(len(self.readings),1)
        self.assertEqual(self.readings[0]['shop']['rows'][0]['price']['mesos'],100)
        self.assertTrue(self.reader.rescan_requested)
        self.assertFalse(self.reader.roi_clean)

    def test_npc_lists_and_their_hover_are_filtered_before_player_context_is_established(self):
        from test_npc_shop import NpcShopTests
        image=NpcShopTests().example();self.reader.image=image
        self.reader.active_request=replace(self.reader.active_request,frame=image,pointer=(160,250))
        self.deliver(shop=dict(area=dict(x=100,y=230,width=199,height=230),rows=[
            dict(name='Orange Potion',price=None)]),tooltip=dict(found=dict(name='Orange Potion')),
            hover=dict(tooltip=dict(found=dict(name='Orange Potion'))))
        self.assertEqual(len(self.readings),1)
        self.assertIsNone(self.readings[0]['shop'])
        self.assertIsNone((self.readings[0]['tooltip'] or {}).get('found'))
        self.assertIsNone(self.reader.shop_context)
        self.assertIsNotNone(self.reader.npc_shop)

    def test_npc_exclusion_preserves_an_outside_inventory_tooltip(self):
        from test_npc_shop import NpcShopTests
        image=NpcShopTests().example();self.reader.image=image
        self.reader.active_request=replace(self.reader.active_request,frame=image,pointer=(650,250))
        found=dict(name='Work Gloves',area=dict(x=580,y=180,width=130,height=17))
        self.deliver(shop=dict(area=dict(x=100,y=230,width=199,height=230),rows=[
            dict(name='Orange Potion',price=None)]),tooltip=dict(found=found))
        self.assertEqual(self.readings[0]['tooltip']['found'],found)
        self.assertIsNone(self.readings[0]['shop'])

    def test_a_false_inventory_claim_inside_npc_lists_still_fails_pixel_validation(self):
        from test_npc_shop import NpcShopTests
        image=NpcShopTests().example();self.reader.image=image
        self.reader.active_request=replace(self.reader.active_request,frame=image,pointer=(360,250))
        self.deliver(shop=dict(area=dict(x=100,y=230,width=199,height=230),rows=[
            dict(name='Orange Potion',price=None)]),tooltip=dict(found=dict(name='Orange Potion')),
            tooltipAssociation=dict(state='inventory-primary'))
        self.assertIsNone((self.readings[0]['tooltip'] or {}).get('found'))
        self.assertEqual(self.readings[0]['tooltipAssociation']['state'],'rejected')

    def test_shop_change_does_not_discard_independent_exp_reply(self):
        self.reader.experience_enabled=True
        self.reader.active_request=replace(self.reader.active_request,mode='experience',shop_epoch=None,
            tracking_epoch=self.reader.tracking_epoch)
        self.reader.shop_browsing.reset()
        results=[];self.reader.experience.connect(results.append)
        with patch.object(PixelReader,'tracking_ready',new_callable=PropertyMock,return_value=True):
            self.deliver(experience={'level':32,'percent':64.0})
        self.assertEqual(len(results),1)
        self.assertEqual(results[0]['experience']['level'],32)
        self.assertEqual(self.readings,[])

    def test_npc_state_changes_once_and_uncertainty_never_promotes_rows(self):
        from test_npc_shop import NpcShopTests
        from price_lens.npc_shop import find_npc_shop
        from PySide6.QtCore import QRect
        image=NpcShopTests().example();npc=find_npc_shop(image)
        changes=[];self.reader.npc_shop_changed.connect(changes.append)
        self.reader.update_npc_shop(image,candidate=npc)
        self.reader.update_npc_shop(image,exclude=(QRect(250,114,66,14),))
        self.assertEqual(self.reader.npc_shop_state,'unknown')
        self.assertIsNotNone(self.reader.npc_shop)
        self.reader.update_npc_shop(image)
        self.assertEqual(self.reader.npc_shop_state,'present');self.assertEqual(len(changes),1)
        self.reader.pointer=(260,128);self.reader.update_npc_shop(image)
        self.assertEqual(self.reader.npc_shop_state,'unknown')
        self.assertIsNotNone(self.reader.npc_shop)
        self.reader.pointer=None
        closed=image.copy();closed.fill(QColor('#223344'));self.reader.update_npc_shop(closed)
        self.assertIsNone(self.reader.npc_shop);self.assertEqual(changes,[npc.rectangle,None])

    def test_late_npc_reply_after_closure_cannot_publish_its_old_rows(self):
        from test_npc_shop import NpcShopTests
        image=NpcShopTests().example()
        self.reader.active_request=replace(self.reader.active_request,frame=image,pointer=(160,250))
        self.reader.image=image.copy();self.reader.image.fill(QColor('#223344'))
        self.deliver(shop=dict(area=dict(x=100,y=230,width=199,height=230),rows=[dict(name='Orange Potion',price=None)]))
        self.assertIsNone(self.readings[0]['shop']);self.assertIsNone(self.reader.npc_shop)

    def test_current_inventory_header_proof_is_preserved_even_inside_npc_bounds(self):
        from test_npc_shop import NpcShopTests
        image,value,found,pointer,_=NpcShopTests().overlapping_inventory()
        self.reader.image=image;self.reader.pointer=pointer
        self.reader.active_request=replace(self.reader.active_request,frame=image,pointer=pointer)
        self.deliver(shop=dict(area=dict(x=550,y=230,width=199,height=230),rows=[dict(name='Orange Potion',price=None)]),
            tooltipAssociation=value,tooltip=dict(found=found))
        self.assertIsNone(self.readings[0]['shop'])
        self.assertEqual(self.readings[0]['tooltip']['found'],found)
        self.assertIsNotNone(self.readings[0]['_tooltip_context'].header)

    def test_inventory_only_reply_validates_its_proof_without_a_full_npc_search(self):
        from test_npc_shop import NpcShopTests
        image,value,found,pointer,_=NpcShopTests().overlapping_inventory()
        self.reader.image=image;self.reader.pointer=pointer
        self.reader.active_request=replace(self.reader.active_request,frame=image,pointer=pointer)
        with patch('price_lens.capture.find_npc_shop',side_effect=AssertionError('Inventory alone must not scan all NPC controls')):
            self.deliver(tooltipAssociation=value,tooltip=dict(found=found))
        self.assertEqual(self.readings[0]['tooltip']['found'],found)
        self.assertIsNotNone(self.readings[0]['_tooltip_context'].header)


if __name__=='__main__':unittest.main()

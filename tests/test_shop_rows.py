from copy import deepcopy
import unittest
from PySide6.QtCore import QRect
from PySide6.QtGui import QColor,QImage,QPainter
from price_lens.shop_rows import ShopRows


class ShopRowsTests(unittest.TestCase):
    def test_sold_out_row_bevel_does_not_invalidate_the_fixed_shop_frame(self):
        image=QImage(500,500,QImage.Format.Format_RGBA8888);image.fill(QColor('#cad5df'))
        area=dict(x=100,y=150,width=199,height=235)
        painter=QPainter(image)
        painter.fillRect(97,146,2,243,QColor('#f5f6f7'))
        painter.fillRect(100,144,199,4,QColor('#929ba4'));painter.end()
        memory=ShopRows();memory.set_guards(area,image)
        changed=image.copy();painter=QPainter(changed)
        # Native sold-out blending reaches the inner bevel, beside the row,
        # while the independent solid frame remains identical.
        painter.fillRect(99,350,1,35,QColor('#fcfdfd'));painter.end()
        self.assertTrue(memory.guards_match(changed))
        changed.setPixelColor(97,355,QColor('#223344'))
        self.assertFalse(memory.guards_match(changed),'A changed actual frame must still be rejected')

    def setUp(self):
        self.image=QImage(800,800,QImage.Format.Format_RGBA8888);self.image.fill(QColor("#223344"))
        self.row={"name":"Work Gloves","price":{"quantity":1,"mesos":100},"area":{"x":160,"y":170,"width":180,"height":40}}
        self.shop={"area":{"x":100,"y":150,"width":260,"height":300},"rows":[self.row]}
        self.memory=ShopRows();self.memory.observe(self.shop,self.image,0)

    def covered(self):
        result=deepcopy(self.shop)
        result["rows"][0].update(name=None,price=None,covered=True)
        return result

    def test_occluded_row_keeps_reference_without_an_assumed_listing(self):
        result=self.memory.observe(self.covered(),self.image,1)[0]
        self.assertEqual(result["name"],"Work Gloves")
        self.assertIsNone(result["price"])
        self.assertTrue(result["retained"])

    def test_held_presentation_lasts_for_the_verified_page_without_promoting_an_offer(self):
        for now in (1,31,600,3600):
            row=self.memory.observe(self.covered(),self.image,now)[0]
            self.assertIsNone(row['price']);self.assertTrue(row['reference_only'])
            self.assertTrue(row['presentation_held'])
            self.assertEqual(self.memory.presentation_for(row,now),{'quantity':1,'mesos':100})
        self.memory.retire_context()
        self.assertIsNone(self.memory.presentation_for(row,3601))


    def test_changed_page_invalidates_a_previously_returned_presentation(self):
        held=self.memory.observe(self.covered(),self.image,1)[0]
        changed=deepcopy(self.shop);changed['rows'][0]['price']['mesos']=200
        self.memory.observe(changed,self.image,2)
        self.assertIsNone(self.memory.presentation_for(held,2))
        current=self.memory.observe(self.covered(),self.image,3)[0]
        self.assertEqual(self.memory.presentation_for(current,3)['mesos'],200)

    def test_confirmed_asking_price_stays_available_for_fresh_market_comparisons(self):
        held=self.memory.observe(self.covered(),self.image,2)[0]
        self.assertEqual(self.memory.presentation_for(held,2)['mesos'],100)
        self.assertEqual(self.memory.presentation_for(held,600)['mesos'],100)
        self.assertIsNone(held['price'])
        self.memory.invalidate_viewport()
        self.assertIsNone(self.memory.presentation_for(held,601))

    def test_name_only_read_keeps_last_seen_amount_separate_from_current_offer(self):
        name_only=deepcopy(self.shop)
        name_only['rows'][0].update(nameOnly=True,price=None,_identity_source=object())
        for now in (1,2,3):
            row=self.memory.observe(name_only,self.image,now)[0]
            self.assertIsNone(row['price']);self.assertTrue(row['presentation_held'])
            self.assertEqual(self.memory.presentation_for(row,now),{'quantity':1,'mesos':100})
            # Even identical pixels from the name-only capture must not promote
            # the old asking amount to a current, newly verified offer.
            restored=self.memory.restore_visible(self.image,[row],now)[0]
            self.assertIsNone(restored['price'])
        self.memory.invalidate_viewport()
        fresh=self.memory.observe(name_only,self.image,4)[0]
        self.assertIsNone(self.memory.presentation_for(fresh,4))

    def test_name_only_amount_retention_requires_the_same_exact_item_identity(self):
        memory,shop=self.contextual()
        name_only=deepcopy(shop)
        name_only['rows'][0].update(nameOnly=True,price=None,_identity_source=object())
        row=memory.observe(name_only,self.image,2)[0]
        self.assertEqual(memory.presentation_for(row,2)['mesos'],100)
        for identity in (None,99):
            other=deepcopy(name_only)
            other['rows'][0].pop('_item_id',None)
            if identity is not None:other['rows'][0]['_item_id']=identity
            current=memory.observe(other,self.image,3)[0]
            self.assertIsNone(memory.presentation_for(current,3))

    def test_native_row_cannot_supply_its_own_last_seen_presentation(self):
        self.memory.invalidate_viewport()
        name_only=deepcopy(self.shop)
        name_only['rows'][0].update(nameOnly=True,price=None,_identity_source=object(),
            _last_seen_price={'quantity':1,'mesos':999999})
        row=self.memory.observe(name_only,self.image,1)[0]
        self.assertIsNone(self.memory.presentation_for(row,1))

    def test_scrolling_keeps_only_container_geometry_for_a_covered_new_page(self):
        held=self.memory.observe(self.covered(),self.image,1)[0]
        self.memory.invalidate_viewport()
        self.assertEqual(self.memory.rows,{})
        self.assertEqual(self.memory.row_pixels,{})
        self.assertTrue(self.memory.guards_match(self.image))
        partial=self.covered();partial['area']['height']=70
        row=self.memory.observe(partial,self.image,2)[0]
        self.assertEqual(self.memory.area,self.shop['area'])
        self.assertIsNone(row['name']);self.assertIsNone(row['price'])
        self.assertIsNone(self.memory.presentation_for(row,2))
        self.assertIsNone(self.memory.presentation_for(held,2))


    def test_unsafe_guard_invalidates_held_presentation_even_without_another_read(self):
        held=self.memory.observe(self.covered(),self.image,1)[0]
        self.image.setPixelColor(97,160,QColor('white'))
        self.memory.observe(self.covered(),self.image,2)
        self.assertIsNone(self.memory.presentation_for(held,2))

    def test_animated_scenery_outside_the_inner_bevel_does_not_retire_the_shop(self):
        held=self.memory.observe(self.covered(),self.image,1)[0]
        for color in ('black','white','#223344','red'):
            self.image.setPixelColor(95,220,QColor(color))
            self.assertTrue(self.memory.guards_match(self.image))
            self.assertEqual(self.memory.presentation_for(held,2),{'quantity':1,'mesos':100})
        # A real change within the fixed native border still rejects it.
        self.image.setPixelColor(97,220,QColor('white'))
        self.assertFalse(self.memory.guards_match(self.image))

    def test_slot_and_page_identity_survive_ocr_order_changes_and_shop_drag(self):
        shop=deepcopy(self.shop);other=deepcopy(self.row)
        other['name']='Other Hat';other['area']['y']+=50;shop['rows'].append(other)
        original=self.memory.observe(shop,self.image,1)
        keys={r['name']:(r['shop_page'],r['shop_slot']) for r in original}
        moved=deepcopy(shop);moved['area']['x']+=30;moved['area']['y']+=20
        for row in moved['rows']:row['area']['x']+=30;row['area']['y']+=20
        moved['rows'].reverse()
        latest=self.memory.observe(moved,self.image,2)
        self.assertEqual(keys,{r['name']:(r['shop_page'],r['shop_slot']) for r in latest})

    def test_reset_ends_the_page_identity_even_for_the_same_item(self):
        row=self.memory.observe(self.shop,self.image,1)[0]
        self.memory.reset()
        self.assertIsNone(self.memory.presentation_for(row,2))
        new=self.memory.observe(self.shop,self.image,2)[0]
        self.assertNotEqual(row['shop_page'],new['shop_page'])

    def test_slot_recovery_cache_is_bounded_even_with_unstable_geometry(self):
        for index in range(self.memory.ROW_LIMIT+8):
            noisy=deepcopy(self.shop)
            noisy['rows'][0]['area']['y']=170+index*5
            self.memory.observe(noisy,self.image,index+1)
        self.assertLessEqual(len(self.memory.rows),self.memory.ROW_LIMIT)
        self.assertTrue(set(self.memory.row_pixels)<=set(self.memory.rows))

    def test_watch_page_revision_changes_for_another_listing_but_not_occlusion_or_drag(self):
        initial=self.memory.page_revision
        self.memory.observe(self.covered(),self.image,1)
        self.assertEqual(self.memory.page_revision,initial)
        moved=deepcopy(self.shop)
        moved['area']['x']+=30;moved['rows'][0]['area']['x']+=30
        self.memory.observe(moved,self.image,2)
        self.assertEqual(self.memory.page_revision,initial)
        changed=deepcopy(moved);changed['rows'][0]['name']='Another item'
        self.memory.observe(changed,self.image,3)
        self.assertGreater(self.memory.page_revision,initial)

    def test_long_occlusion_keeps_reference_identity_without_a_deal_rating(self):
        result=self.memory.observe(self.covered(),self.image,4)[0]
        self.assertEqual(result["name"],"Work Gloves")
        self.assertIsNone(result["price"])
        self.assertTrue(result["listing_old"])

    def test_unreadable_selected_name_keeps_reference_with_no_assumed_listing(self):
        selected=deepcopy(self.shop);selected['rows'][0].update(name=None,price=None,covered=False)
        row=self.memory.observe(selected,self.image,1)[0]
        self.assertEqual(row['name'],'Work Gloves');self.assertFalse(row['covered'])
        self.assertIsNone(row['price']);self.assertTrue(row['reference_only'])

    def test_listing_returns_without_ocr_only_when_the_exact_visible_pixels_return(self):
        rows=self.memory.observe(self.covered(),self.image,1)
        changed=self.image.copy();changed.setPixelColor(180,180,QColor('white'))
        self.assertIsNone(self.memory.restore_visible(changed,rows)[0]['price'])
        restored=self.memory.restore_visible(self.image,rows)[0]
        self.assertEqual(restored['price']['mesos'],100)
        self.assertFalse(restored.get('covered'))

    def test_changed_fixed_table_rim_invalidates_covered_rows(self):
        self.image.setPixelColor(97,160,QColor("white"))
        result=self.memory.observe(self.covered(),self.image,1)[0]
        self.assertIsNone(result["name"])

    def test_store_movement_and_close_clear_old_coordinates(self):
        moved=self.covered();moved["area"]["x"]+=20
        self.assertIsNone(self.memory.observe(moved,self.image,1)[0]["name"])
        self.image.fill(QColor("black"))
        self.assertEqual(self.memory.observe(None,self.image,2),[])
        self.assertFalse(self.memory.active)

    def test_verified_shop_pixels_suppress_inventory_even_when_list_is_occluded(self):
        rows=self.memory.observe(None,self.image,1)
        self.assertTrue(self.memory.active)
        self.assertEqual(rows[0]["name"],"Work Gloves")
        self.image.fill(QColor("black"))
        self.assertEqual(self.memory.observe(None,self.image,2),[])
        self.assertFalse(self.memory.active)

    def test_changed_visible_listing_invalidates_hidden_page_rows(self):
        other=deepcopy(self.row);other["area"]["y"]+=50;other["name"]="Other Hat"
        self.shop["rows"].append(other);self.memory.observe(self.shop,self.image,1)
        changed=self.covered();changed["rows"][1]["name"]="New page"
        self.assertIsNone(self.memory.observe(changed,self.image,2)[0]["name"])

    def test_small_row_geometry_noise_keeps_the_same_anchor(self):
        for delta in (1,-1,2,-2):
            noisy=deepcopy(self.shop)
            noisy['area']['y']+=delta
            noisy['rows'][0]['area']['y']+=delta
            result=self.memory.observe(noisy,self.image,1)[0]
            self.assertEqual(result['area'],self.row['area'])

    def test_guard_occlusion_does_not_destroy_recovery_data(self):
        original=self.image.copy()
        self.image.setPixelColor(97,160,QColor('white'))
        self.assertIsNone(self.memory.observe(self.covered(),self.image,1)[0]['name'])
        result=self.memory.observe(self.covered(),original,2)[0]
        self.assertEqual(result['name'],'Work Gloves')
        self.assertIsNone(result['price'])
        visible=self.memory.observe(self.shop,original,3)[0]
        self.assertEqual(visible['price']['mesos'],100)

    def test_native_tooltip_can_keep_a_hidden_reference_but_never_an_assumed_deal(self):
        tip=QRect(90,150,220,300)
        self.image.setPixelColor(97,160,QColor('white'))
        row=self.memory.observe(self.covered(),self.image,10,tooltip=tip)[0]
        self.assertTrue(row['reference_only']);self.assertTrue(row['covered'])
        self.assertEqual(row['name'],'Work Gloves');self.assertIsNone(row['price'])
        self.assertEqual(row['area'],self.row['area'])

    def test_readable_rows_do_not_capture_a_tooltip_as_part_of_the_shop_frame(self):
        pane=QRect(90,180,50,200)
        covered=self.image.copy();painter=QPainter(covered)
        painter.fillRect(pane,QColor('#464b78'));painter.end()
        self.memory.observe(self.shop,covered,1,tooltip=pane)
        row=self.memory.observe(self.covered(),self.image,2)[0]
        self.assertEqual(row['name'],'Work Gloves')
        self.assertEqual(self.memory.presentation_for(row,2)['mesos'],100)

    def test_guard_changed_outside_tooltip_cannot_reuse_a_hidden_reference(self):
        self.image.setPixelColor(110,146,QColor('white'))
        row=self.memory.observe(self.covered(),self.image,10,tooltip=QRect(200,150,220,300))[0]
        self.assertFalse(row.get('reference_only'));self.assertIsNone(row['name'])

    def test_partial_guard_overlap_does_not_excuse_changes_outside_tooltip(self):
        # The tooltip covers the lower left rim, not its changed upper pixels.
        self.image.setPixelColor(97,160,QColor('white'))
        row=self.memory.observe(self.covered(),self.image,1,tooltip=QRect(90,250,220,200))[0]
        self.assertIsNone(row['name']);self.assertFalse(row['presentation_held'])

    def test_fully_hidden_guards_do_not_prove_a_page(self):
        self.image.fill(QColor('black'))
        row=self.memory.observe(self.covered(),self.image,1,tooltip=QRect(0,0,800,800))[0]
        self.assertIsNone(row['name']);self.assertFalse(row['presentation_held'])

    def test_animated_owner_portrait_is_not_a_page_guard(self):
        self.image.setPixelColor(110,120,QColor('white'))
        self.assertEqual(self.memory.observe(self.covered(),self.image,1)[0]['name'],'Work Gloves')

    def test_own_overlay_pixels_do_not_invalidate_a_page_but_changed_fixed_rims_do(self):
        mask=QRect(360,170,230,36)
        original=self.image.copy();painter=QPainter(self.image);painter.fillRect(mask,QColor('white'));painter.end()
        self.assertEqual(self.memory.observe(self.covered(),self.image,1,exclude=[mask])[0]['name'],'Work Gloves')
        self.memory.observe(self.shop,self.image,2,exclude=[mask])
        self.assertEqual(self.memory.observe(self.covered(),original,3)[0]['name'],'Work Gloves')
        original.setPixelColor(97,160,QColor('white'))
        self.assertIsNone(self.memory.observe(self.covered(),original,4)[0]['name'])

    def test_scrollbar_highlights_are_not_container_guards(self):
        self.image.setPixelColor(363,160,QColor('white'))
        self.assertEqual(self.memory.observe(self.covered(),self.image,1)[0]['name'],'Work Gloves')

    def contextual(self):
        memory=ShopRows(identity=lambda row:row.get('_item_id'))
        shop=deepcopy(self.shop)
        shop['rows'][0].update(name='Blue Moon',_item_id=1041121,
            _identity_evidence='icon',_identity_guard=('native icon',),_identity_epoch=1)
        other=deepcopy(self.row);other['area']['y']+=50;other.update(name='Other Hat',_item_id=1000001)
        shop['rows'].append(other)
        memory.observe(shop,self.image,0)
        return memory,shop

    def test_identity_proof_downgrade_keeps_page_without_lending_old_id_or_quote(self):
        memory,shop=self.contextual();page=memory.page_revision
        visible=memory.observe(shop,self.image,1)[0]
        memory.presentation_for(visible,1)
        weak=deepcopy(shop);weak['rows'][0].pop('_item_id')
        result=memory.observe(weak,self.image,2)
        self.assertEqual(memory.page_revision,page);self.assertEqual(len(memory.rows),2)
        self.assertNotIn('_item_id',result[0]);self.assertNotIn('_item_id',memory.rows[memory.slot(result[0])][0])
        self.assertEqual(result[0]['price'],visible['price'])
        self.assertIsNone(memory.presentation_for(result[0],2))
        covered=deepcopy(weak)
        covered['rows'][0].update(name=None,price=None,covered=True)
        retained=memory.observe(covered,self.image,3)[0]
        self.assertNotIn('_item_id',retained)
        self.assertIsNone(memory.presentation_for(retained,3))

    def test_current_weak_identity_stays_weak_during_retention_and_exact_pixel_restore(self):
        memory,shop=self.contextual();page=memory.page_revision
        visible=memory.observe(shop,self.image,1)[0]
        memory.presentation_for(visible,1)
        weak=deepcopy(shop);weak['rows'][0].pop('_item_id')
        weak['rows'][0].update(price=None,covered=True,_identity_reason='Icon covered')
        retained=memory.observe(weak,self.image,2)[0]
        self.assertEqual(memory.page_revision,page);self.assertNotIn('_item_id',retained)
        self.assertNotIn('_identity_evidence',retained)
        self.assertEqual(retained['_identity_reason'],'Icon covered')
        self.assertIsNone(memory.presentation_for(retained,2))
        restored=memory.restore_visible(self.image,[retained],3)[0]
        self.assertNotIn('_item_id',restored)
        self.assertEqual(restored['price'],visible['price'])
        self.assertIsNone(memory.presentation_for(restored,3))

    def test_weak_to_newly_proven_identity_and_shop_drag_do_not_claim_another_page(self):
        memory,shop=self.contextual();page=memory.page_revision
        weak=deepcopy(shop);weak['rows'][0].pop('_item_id')
        weak['area']['x']+=30;weak['area']['y']+=20
        for row in weak['rows']:row['area']['x']+=30;row['area']['y']+=20
        result=memory.observe(weak,self.image,1)
        self.assertEqual(memory.page_revision,page);self.assertNotIn('_item_id',result[0])
        proven=deepcopy(weak);proven['rows'][0]['_item_id']=1041121
        result=memory.observe(proven,self.image,2)
        self.assertEqual(memory.page_revision,page);self.assertEqual(result[0]['_item_id'],1041121)

    def test_two_positive_different_ids_invalidate_even_with_the_same_name_and_asking_price(self):
        memory,shop=self.contextual();page=memory.page_revision
        changed=deepcopy(shop);changed['rows'][0]['_item_id']=1032011
        changed['rows'][1].update(name=None,price=None,covered=True)
        result=memory.observe(changed,self.image,1)
        self.assertGreater(memory.page_revision,page)
        self.assertEqual(result[0]['_item_id'],1032011)
        self.assertIsNone(result[1]['name'])

    def test_a_changed_weak_label_tier_or_asking_price_still_invalidates_the_page(self):
        for change in ({'name':'Different Moon'},{'tier':'chaos'},{'price':{'quantity':1,'mesos':999}}):
            with self.subTest(change=change):
                memory,shop=self.contextual();page=memory.page_revision
                changed=deepcopy(shop);changed['rows'][0].pop('_item_id');changed['rows'][0].update(change)
                memory.observe(changed,self.image,1)
                self.assertGreater(memory.page_revision,page)

    def test_small_ocr_punctuation_changes_do_not_invalidate_other_covered_rows(self):
        shop=deepcopy(self.shop);other=deepcopy(self.row);other['area']['y']+=50;shop['rows'].append(other)
        shop['rows'][0]['name']='Overall Armor LUK Scroll:...';shop['rows'][0]['tier']='greater'
        self.memory.observe(shop,self.image,1)
        changed=deepcopy(shop);changed['rows'][0]['name']='Overall Armor LUK Soroll....'
        changed['rows'][1].update(name=None,price=None,covered=True)
        self.assertEqual(self.memory.observe(changed,self.image,2)[1]['name'],'Work Gloves')

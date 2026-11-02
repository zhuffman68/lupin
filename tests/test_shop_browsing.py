"""Native-pixel browse events; fixtures never capture or send game input."""
from copy import deepcopy
import unittest

from PySide6.QtCore import QCoreApplication, QRect
from PySide6.QtGui import QColor, QImage, QPainter

from price_lens.shop_browsing import ShopBrowsing
from price_lens.shop_rows import ShopRows


class ShopBrowsingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.area=QRect(100,100,199,260)
        self.state=ShopBrowsing(identity=lambda row:row.get('item_id'))

    def frame(self,thumb=60,*,area=None,glyph=0):
        area=area or self.area
        image=QImage(800,600,QImage.Format.Format_RGBA8888);image.fill(QColor('#223344'))
        painter=QPainter(image)
        painter.fillRect(QRect(area.x(),area.y()-6,area.width(),4),QColor('#ddeeff'))
        painter.fillRect(QRect(area.right()+3,area.top()+14,14,area.height()-28),QColor('#e6e6e6'))
        painter.fillRect(QRect(area.right()+3,area.top()+thumb,14,24),QColor('#5577aa'))
        for index in range(3):
            x,y=area.x()+37,area.y()+index*41
            painter.fillRect(QRect(x,y,162,35),QColor('#cad5df'))
            for column in range(8):
                painter.fillRect(QRect(x+3+column*13+glyph,y+5,6,8),QColor('black'))
        painter.end()
        return image

    def rows(self,*,area=None,identity=1):
        area=area or self.area
        return [dict(item_id=identity+index,name='Fixture '+str(identity+index),
                     price=dict(quantity=1,mesos=100+index),
                     area=dict(x=area.x()+37,y=area.y()+index*41,width=162,height=35)) for index in range(3)]

    def seed(self):
        image=self.frame();self.state.observe_rows(self.rows(),image,area=self.area)
        return image

    def test_native_thumb_change_advances_once_until_fresh_rows_arrive(self):
        self.seed();changed=self.frame(80)
        self.assertTrue(self.state.observe_frame(changed,self.area))
        self.assertEqual(self.state.epoch,1);self.assertTrue(self.state.pending)

        for when in (100.1,100.8,101.4):
            self.assertFalse(self.state.observe_frame(changed,self.area))
            self.state.observe_rows(self.rows(identity=20),changed,area=self.area)
        self.assertEqual(self.state.epoch,1)
        self.assertFalse(self.state.pending)

    def test_cursor_crossing_thumb_and_frame_cannot_create_a_scroll(self):
        original=self.seed()
        for point in ((305,160),(305,180),(180,95)):
            image=original.copy();painter=QPainter(image)
            painter.fillRect(point[0]-4,point[1]-4,24,28,QColor('white'));painter.end()
            self.assertFalse(self.state.observe_frame(image,self.area,pointer=point))
            self.assertEqual(self.state.epoch,0)
        self.assertFalse(self.state.observe_frame(original,self.area,pointer=(50,50)))
        self.assertTrue(self.state.observe_frame(self.frame(90),self.area,pointer=(180,150)))

    def test_cursor_partially_covering_a_new_row_does_not_block_fresh_page_acceptance(self):
        self.seed();changed=self.frame(90,glyph=5)
        self.state.observe_frame(changed,self.area,pointer=(145,105))
        self.assertTrue(self.state.pending)
        self.state.observe_rows(self.rows(identity=20),changed,area=self.area,pointer=(145,105),latest=changed)
        self.assertFalse(self.state.pending)

    def test_backscroll_and_another_real_scroll_advance_separate_epochs(self):
        original=self.seed();self.state.observe_frame(self.frame(80),self.area)
        self.assertTrue(self.state.observe_frame(original,self.area))
        self.assertEqual(self.state.epoch,2)

    def test_description_over_rows_does_not_hide_exposed_thumb_change(self):
        self.seed();image=self.frame(80);tooltip=QRect(120,110,175,220)
        painter=QPainter(image);painter.fillRect(tooltip,QColor('#464b78'));painter.end()
        self.assertTrue(self.state.observe_frame(image,self.area,tooltip=tooltip))

    def test_hidden_thumb_is_unknown_and_revealed_native_movement_is_an_event(self):
        self.seed();image=self.frame(80);tooltip=QRect(280,130,70,200)
        painter=QPainter(image);painter.fillRect(tooltip,QColor('#464b78'));painter.end()
        self.assertIsNone(self.state.scrollbar_thumb(image,self.area,tooltip=tooltip))
        self.assertFalse(self.state.observe_frame(image,self.area,tooltip=tooltip))
        self.assertEqual(self.state.epoch,0)
        self.assertTrue(self.state.observe_frame(self.frame(80),self.area))

    def test_two_exposed_changed_names_invalidate_before_ocr_with_a_hidden_thumb(self):
        self.seed();image=self.frame(80,glyph=5);mask=QRect(300,110,30,240)
        painter=QPainter(image);painter.fillRect(mask,QColor('#464b78'));painter.end()
        self.assertTrue(self.state.observe_frame(image,self.area,exclude=[mask]))
        self.assertEqual(self.state.epoch,1);self.assertTrue(self.state.pending)
        self.assertIsNone(self.state.thumb)
        self.assertFalse(self.state.observe_frame(image,self.area,exclude=[mask]))
        self.state.observe_rows(self.rows(identity=20),image,area=self.area,exclude=[mask],latest=image)
        self.assertFalse(self.state.pending)
        self.assertFalse(self.state.observe_frame(self.frame(80,glyph=5),self.area))
        self.assertEqual(self.state.epoch,1,'Revealing the thumb must not invalidate the same page twice')

    def test_one_changed_name_does_not_invalidate_other_rows_before_ocr(self):
        image=self.seed();new=self.frame(glyph=5)
        rect=QRect(137,100,162,35);painter=QPainter(image);painter.drawImage(rect,new.copy(rect));painter.end()
        self.assertFalse(self.state.observe_frame(image,self.area))
        self.assertEqual(self.state.epoch,0)

    def test_covered_names_cannot_establish_a_frame_first_page_change(self):
        self.seed();image=self.frame(glyph=5);panel=QRect(133,98,168,125)
        painter=QPainter(image);painter.fillRect(panel,QColor('#464b78'));painter.end()
        # Even before geometry has found this pane, purple body pixels are
        # not admitted as a native blue/orange item-name band.
        self.assertFalse(self.state.observe_frame(image,self.area))
        self.assertFalse(self.state.observe_frame(image,self.area,tooltip=panel))
        self.assertEqual(self.state.epoch,0)

    def test_orange_selection_recolours_two_names_without_a_page_change(self):
        image=self.frame()
        def selected(image,index):
            x,y=137,100+index*41;painter=QPainter(image)
            painter.fillRect(x,y,162,35,QColor(251,167,46))
            for column in range(8):painter.fillRect(x+3+column*13,y+5,6,8,QColor('black'))
            painter.end()
        selected(image,0);self.state.observe_rows(self.rows(),image,area=self.area)
        after=self.frame();selected(after,1)
        self.assertFalse(self.state.observe_frame(after,self.area))
        self.assertEqual(self.state.epoch,0)

    def test_changed_asking_prices_alone_are_not_a_frame_first_page_change(self):
        image=self.seed();painter=QPainter(image)
        for index in range(3):painter.fillRect(150,123+index*41,80,5,QColor('black'))
        painter.end()
        self.assertFalse(self.state.observe_frame(image,self.area))

    def test_unchanged_exposed_rows_veto_name_only_scrolling_when_other_names_change(self):
        image=self.seed();different=self.frame(glyph=5)
        painter=QPainter(image)
        for y in (141,182):
            rect=QRect(137,y,162,35);painter.drawImage(rect,different.copy(rect))
        painter.end();mask=QRect(300,110,30,240)
        self.assertFalse(self.state.observe_frame(image,self.area,exclude=[mask]))
        self.assertEqual(self.state.epoch,0)

    def test_an_unchanged_native_scrollbar_vetoes_name_only_page_changes(self):
        self.seed();image=self.frame(glyph=5)
        self.assertFalse(self.state.observe_frame(image,self.area))
        self.assertEqual(self.state.epoch,0)

    def test_visible_scrollbar_movement_wins_even_when_one_row_name_is_unchanged(self):
        original=self.seed();image=self.frame(80,glyph=5)
        rect=QRect(137,100,162,35);painter=QPainter(image);painter.drawImage(rect,original.copy(rect));painter.end()
        self.assertTrue(self.state.observe_frame(image,self.area))
        self.assertEqual(self.state.epoch,1)

    def test_blank_native_bands_cannot_prove_an_unchanged_item_name(self):
        image=self.frame();painter=QPainter(image)
        painter.fillRect(137,100,162,35,QColor('#cad5df'));painter.end()
        self.state.observe_rows(self.rows(),image,area=self.area)
        states=self.state.name_states(image,self.area)
        self.assertEqual(states[(137,100,162,35)],'unproven')

    def test_a_masked_read_cannot_erase_the_previous_same_item_name_template(self):
        original=self.seed();old=self.state.rows[(37,0,162,35)]
        self.state.observe_rows(self.rows(),original,area=self.area,exclude=[QRect(137,100,162,17)])
        self.assertIs(self.state.rows[(37,0,162,35)],old)

    def test_frame_first_name_proofs_respect_previous_and_current_masks(self):
        mask=QRect(137,100,162,100);image=self.frame()
        self.state.observe_rows(self.rows(),image,area=self.area,exclude=[mask])
        self.assertFalse(self.state.observe_frame(self.frame(glyph=5),self.area,exclude=[mask]))
        self.assertEqual(self.state.epoch,0)

    def test_a_description_tint_cannot_turn_thumb_edge_rounding_into_a_scroll(self):
        original=self.seed();image=original.copy();painter=QPainter(image)
        painter.fillRect(self.area.right()+3,self.area.top()+60,14,24,QColor('#e6e6e6'))
        painter.fillRect(self.area.right()+3,self.area.top()+62,14,22,QColor(34,51,107));painter.end()
        self.assertIsNone(self.state.scrollbar_thumb(image,self.area))
        self.assertFalse(self.state.observe_frame(image,self.area))
        self.assertEqual(self.state.epoch,0)
        self.assertFalse(self.state.observe_frame(original,self.area))
        self.assertTrue(self.state.observe_frame(self.frame(80),self.area))

    def test_our_fading_annotation_is_never_a_native_thumb(self):
        image=self.seed();mask=QRect(300,140,30,100)
        for color in ('#5577aa','#171c25','#e6e6e6'):
            sample=image.copy();painter=QPainter(sample);painter.fillRect(mask,QColor(color));painter.end()
            self.assertFalse(self.state.observe_frame(sample,self.area,exclude=[mask]))
        self.assertEqual(self.state.epoch,0)
        self.assertFalse(self.state.observe_frame(image,self.area))

    def test_noise_or_unknown_rail_does_not_rearm_priority(self):
        original=self.seed();image=original.copy();image.setPixelColor(305,230,QColor('#5577aa'))
        self.assertFalse(self.state.observe_frame(image,self.area))
        image.fill(QColor('#464b78'))
        self.assertFalse(self.state.observe_frame(image,self.area))
        self.assertFalse(self.state.observe_frame(image,self.area))
        self.assertEqual(self.state.epoch,0)

    def test_drag_preserves_local_thumb_and_row_identity(self):
        self.seed();area=self.area.translated(40,30);image=self.frame(area=area)
        self.assertFalse(self.state.observe_rows(self.rows(area=area),image,area=area))
        self.assertFalse(self.state.observe_frame(image,area))
        self.assertEqual(self.state.epoch,0)
        self.assertTrue(self.state.observe_frame(self.frame(80,area=area),area))
        self.assertEqual(self.state.epoch,1)

    def test_ocr_correction_order_or_quote_change_is_not_a_browse_event(self):
        image=self.seed();rows=self.rows(identity=20)
        self.assertFalse(self.state.observe_rows(rows,image,area=self.area))
        for row in rows:row['price']['mesos']+=10
        self.assertFalse(self.state.observe_rows(list(reversed(rows)),image,area=self.area))
        self.assertEqual(self.state.epoch,0)

    def test_rounded_row_rectangles_keep_one_template_per_slot_without_a_false_scroll(self):
        image=self.seed()
        for delta in (-1,1,2,-2,0):
            rows=self.rows()
            for row in rows:
                row['area']['y']+=delta;row['area']['width']-=delta
            self.assertFalse(self.state.observe_rows(rows,image,area=self.area))
            self.assertEqual(len(self.state.rows),3)
            self.assertFalse(self.state.observe_frame(image,self.area))
        self.assertEqual(self.state.epoch,0)

    def test_a_real_new_page_with_rounded_rows_advances_once_and_cannot_leave_duplicate_templates(self):
        self.seed();image=self.frame(glyph=5);rows=self.rows(identity=20)
        for row in rows:row['area']['y']-=1;row['area']['height']-=1
        self.assertTrue(self.state.observe_rows(rows,image,area=self.area))
        self.assertEqual(len(self.state.rows),3);self.assertEqual(self.state.epoch,1)
        self.assertFalse(self.state.observe_frame(image,self.area))
        self.assertEqual(self.state.epoch,1)

    def test_new_exact_row_id_and_changed_native_name_ink_prove_a_page(self):
        self.seed();image=self.frame(glyph=5)
        self.assertTrue(self.state.observe_rows(self.rows(identity=20),image,area=self.area))
        self.assertEqual(self.state.epoch,1)
        self.assertFalse(self.state.pending)
        self.assertFalse(self.state.observe_rows(self.rows(identity=20),image,area=self.area))


    def test_revealing_a_thumb_after_row_proof_does_not_count_the_same_scroll_twice(self):
        self.seed();image=self.frame(80,glyph=5);mask=QRect(300,110,30,240)
        self.assertTrue(self.state.observe_rows(self.rows(identity=20),image,area=self.area,exclude=[mask]))
        self.assertIsNone(self.state.thumb)
        self.assertFalse(self.state.observe_frame(image,self.area))
        self.assertEqual(self.state.epoch,1)

    def test_covered_or_changed_during_ocr_rows_cannot_establish_the_new_viewport(self):
        original=self.seed();changed=self.frame(80,glyph=5)
        self.state.observe_frame(changed,self.area)
        self.assertFalse(self.state.observe_rows(self.rows(),original,area=self.area,latest=changed))
        self.assertTrue(self.state.pending)
        rows=self.rows(identity=20)
        for row in rows:row.update(covered=True)
        self.state.observe_rows(rows,changed,area=self.area)
        self.assertTrue(self.state.pending)




    def test_reset_rejects_old_submission_epoch_without_starting_priority(self):
        self.seed();epoch=self.state.epoch;self.state.reset()
        self.assertNotEqual(self.state.epoch,epoch)
        self.assertFalse(self.state.pending)
        self.assertIsNone(self.state.area)

    def test_viewport_invalidation_drops_old_amounts_and_covered_identities(self):
        image=self.frame();memory=ShopRows();shop=dict(area=dict(zip(('x','y','width','height'),self.area.getRect())),rows=self.rows())
        visible=memory.observe(shop,image)[0];old_page=memory.page_revision
        memory.presentation_for(visible)
        memory.invalidate_viewport()
        self.assertGreater(memory.page_revision,old_page);self.assertTrue(memory.active)
        self.assertIsNone(memory.presentation_for(visible))
        covered=deepcopy(shop)
        for row in covered['rows']:row.update(name=None,price=None,covered=True)
        rows=memory.observe(covered,image)
        self.assertTrue(all(row.get('name') is None and row.get('price') is None for row in rows))


if __name__=='__main__':unittest.main()

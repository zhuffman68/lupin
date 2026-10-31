"""Native-pixel browse events; fixtures never capture or send game input."""
from copy import deepcopy
import unittest
from unittest.mock import patch

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

    def tearDown(self):
        self.state.timer.stop()

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
        image=self.frame();self.state.observe_rows(self.rows(),image,area=self.area,now=99)
        return image

    def test_native_thumb_change_advances_once_and_expires_at_1500_ms(self):
        self.seed();changed=self.frame(80)
        self.assertTrue(self.state.observe_frame(changed,self.area,now=100))
        self.assertEqual(self.state.epoch,1);self.assertTrue(self.state.pending)
        self.assertTrue(self.state.active(101.499));self.assertFalse(self.state.active(101.5))
        for when in (100.1,100.8,101.4):
            self.assertFalse(self.state.observe_frame(changed,self.area,now=when))
            self.state.observe_rows(self.rows(identity=20),changed,area=self.area,now=when)
        self.assertEqual(self.state.priority_until,101.5);self.assertEqual(self.state.epoch,1)
        self.assertFalse(self.state.pending)

    def test_backscroll_and_another_real_scroll_restart_the_deadline(self):
        original=self.seed();self.state.observe_frame(self.frame(80),self.area,now=100)
        self.assertTrue(self.state.observe_frame(original,self.area,now=100.5))
        self.assertEqual(self.state.epoch,2);self.assertEqual(self.state.priority_until,102)

    def test_description_over_rows_does_not_hide_exposed_thumb_change(self):
        self.seed();image=self.frame(80);tooltip=QRect(120,110,175,220)
        painter=QPainter(image);painter.fillRect(tooltip,QColor('#464b78'));painter.end()
        self.assertTrue(self.state.observe_frame(image,self.area,tooltip=tooltip,now=100))

    def test_hidden_thumb_is_unknown_and_revealed_native_movement_is_an_event(self):
        self.seed();image=self.frame(80);tooltip=QRect(280,130,70,200)
        painter=QPainter(image);painter.fillRect(tooltip,QColor('#464b78'));painter.end()
        self.assertIsNone(self.state.scrollbar_thumb(image,self.area,tooltip=tooltip))
        self.assertFalse(self.state.observe_frame(image,self.area,tooltip=tooltip,now=100))
        self.assertEqual(self.state.epoch,0)
        self.assertTrue(self.state.observe_frame(self.frame(80),self.area,now=100.2))

    def test_our_fading_annotation_is_never_a_native_thumb(self):
        image=self.seed();mask=QRect(300,140,30,100)
        for color in ('#5577aa','#171c25','#e6e6e6'):
            sample=image.copy();painter=QPainter(sample);painter.fillRect(mask,QColor(color));painter.end()
            self.assertFalse(self.state.observe_frame(sample,self.area,exclude=[mask],now=100))
        self.assertEqual(self.state.epoch,0);self.assertFalse(self.state.active())
        self.assertFalse(self.state.observe_frame(image,self.area,now=101))

    def test_noise_or_unknown_rail_does_not_rearm_priority(self):
        original=self.seed();image=original.copy();image.setPixelColor(305,230,QColor('#5577aa'))
        self.assertFalse(self.state.observe_frame(image,self.area,now=100))
        image.fill(QColor('#464b78'))
        self.assertFalse(self.state.observe_frame(image,self.area,now=100.5))
        self.assertFalse(self.state.observe_frame(image,self.area,now=101))
        self.assertEqual(self.state.epoch,0)

    def test_drag_preserves_local_thumb_and_row_identity(self):
        self.seed();area=self.area.translated(40,30);image=self.frame(area=area)
        self.assertFalse(self.state.observe_rows(self.rows(area=area),image,area=area,now=100))
        self.assertFalse(self.state.observe_frame(image,area,now=100.2))
        self.assertEqual(self.state.epoch,0)
        self.assertTrue(self.state.observe_frame(self.frame(80,area=area),area,now=100.4))
        self.assertEqual(self.state.epoch,1);self.assertEqual(self.state.priority_until,101.9)

    def test_ocr_correction_order_or_quote_change_is_not_a_browse_event(self):
        image=self.seed();rows=self.rows(identity=20)
        self.assertFalse(self.state.observe_rows(rows,image,area=self.area,now=100))
        for row in rows:row['price']['mesos']+=10
        self.assertFalse(self.state.observe_rows(list(reversed(rows)),image,area=self.area,now=101))
        self.assertEqual(self.state.epoch,0);self.assertFalse(self.state.active())

    def test_new_exact_row_id_and_changed_native_name_ink_prove_a_page(self):
        self.seed();image=self.frame(glyph=5)
        self.assertTrue(self.state.observe_rows(self.rows(identity=20),image,area=self.area,now=100))
        self.assertEqual(self.state.epoch,1);self.assertTrue(self.state.active(101))
        self.assertFalse(self.state.pending)
        self.assertFalse(self.state.observe_rows(self.rows(identity=20),image,area=self.area,now=101))
        self.assertEqual(self.state.priority_until,101.5)

    def test_revealing_a_thumb_after_row_proof_does_not_count_the_same_scroll_twice(self):
        self.seed();image=self.frame(80,glyph=5);mask=QRect(300,110,30,240)
        self.assertTrue(self.state.observe_rows(self.rows(identity=20),image,area=self.area,exclude=[mask],now=100))
        self.assertIsNone(self.state.thumb)
        self.assertFalse(self.state.observe_frame(image,self.area,now=101))
        self.assertEqual(self.state.epoch,1);self.assertEqual(self.state.priority_until,101.5)

    def test_covered_or_changed_during_ocr_rows_cannot_establish_the_new_viewport(self):
        original=self.seed();changed=self.frame(80,glyph=5)
        self.state.observe_frame(changed,self.area,now=100)
        self.assertFalse(self.state.observe_rows(self.rows(),original,area=self.area,latest=changed,now=100.1))
        self.assertTrue(self.state.pending)
        rows=self.rows(identity=20)
        for row in rows:row.update(covered=True)
        self.state.observe_rows(rows,changed,area=self.area,now=100.2)
        self.assertTrue(self.state.pending)

    def test_expiry_wakes_once_without_a_new_frame_or_read(self):
        self.seed();self.state.observe_frame(self.frame(80),self.area,now=100)
        wakes=[];self.state.changed.connect(lambda:wakes.append(True))
        with patch('price_lens.shop_browsing.time.monotonic',return_value=101.5):
            self.state._expire();self.state._expire()
        self.assertEqual(wakes,[True]);self.assertFalse(self.state.active())

    def test_reset_rejects_old_submission_epoch_without_starting_priority(self):
        self.seed();epoch=self.state.epoch;self.state.reset()
        self.assertNotEqual(self.state.epoch,epoch)
        self.assertFalse(self.state.active());self.assertFalse(self.state.pending)
        self.assertIsNone(self.state.area)

    def test_viewport_invalidation_drops_old_amounts_and_covered_identities(self):
        image=self.frame();memory=ShopRows();shop=dict(area=dict(zip(('x','y','width','height'),self.area.getRect())),rows=self.rows())
        visible=memory.observe(shop,image,now=99)[0];old_page=memory.page_revision
        memory.presentation_for(visible,now=99,quote_key='generation1')
        memory.invalidate_viewport()
        self.assertGreater(memory.page_revision,old_page);self.assertTrue(memory.active)
        self.assertIsNone(memory.presentation_for(visible,now=100,quote_key='generation1'))
        covered=deepcopy(shop)
        for row in covered['rows']:row.update(name=None,price=None,covered=True)
        rows=memory.observe(covered,image,now=100)
        self.assertTrue(all(row.get('name') is None and row.get('price') is None for row in rows))


if __name__=='__main__':unittest.main()

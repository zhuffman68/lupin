"""Native description bounds from public OCR samples, including clipped panels."""
from pathlib import Path
import unittest
from PySide6.QtCore import QRect,Qt
from PySide6.QtGui import QImage,QColor
from price_lens.tooltip_geometry import description_bounds,still_present,TooltipReference

ROOT=Path(__file__).resolve().parents[1]


class TooltipGeometryTests(unittest.TestCase):
    def test_light_shop_pane_is_not_a_description_even_with_our_dark_labels(self):
        from PySide6.QtGui import QPainter
        image=QImage(800,600,QImage.Format.Format_RGBA8888);image.fill(QColor('#ad969e'))
        pane=QRect(200,100,296,364)
        painter=QPainter(image);painter.fillRect(pane,QColor('#e6dcbd'))
        for x in (200,493):
            painter.fillRect(x,100,3,364,QColor(30,26,40))
            painter.fillRect(x+1,100,1,364,QColor(170,150,160))
        painter.fillRect(200,100,296,3,QColor(30,26,40))
        painter.fillRect(200,101,296,1,QColor(170,150,160));painter.end()
        area=dict(x=212,y=111,width=160,height=18)
        self.assertIsNone(description_bounds(image,area))
        self.assertFalse(still_present(image,pane))
        masks=[QRect(206,y,283,60) for y in (135,200,265,330)]
        painter=QPainter(image)
        for mask in masks:painter.fillRect(mask,QColor('#161c26'))
        painter.end()
        self.assertIsNone(description_bounds(image,area,masks))
        self.assertFalse(still_present(image,pane,masks))

    def test_name_inside_our_annotation_cannot_anchor_a_new_description(self):
        from PySide6.QtGui import QPainter
        image=QImage(800,600,QImage.Format.Format_RGBA8888);image.fill(QColor('#eeeeee'))
        painter=QPainter(image);painter.fillRect(QRect(200,200,300,180),QColor('#464b78'))
        painter.end();area=dict(x=212,y=211,width=160,height=12)
        self.assertIsNotNone(description_bounds(image,area))
        self.assertIsNone(description_bounds(image,area,[QRect(208,208,220,36)]))

    def test_own_price_cards_do_not_clip_the_native_panel_bounds(self):
        from PySide6.QtGui import QPainter
        image=QImage(800,600,QImage.Format.Format_RGBA8888);image.fill(QColor('#eeeeee'))
        painter=QPainter(image);painter.fillRect(QRect(200,200,300,180),QColor('#464b78'))
        masks=[QRect(350,y,240,36) for y in (195,235,275,315)]
        for mask in masks:painter.fillRect(mask,QColor('#161c26'))
        painter.end();area=dict(x=212,y=211,width=160,height=12)
        bounds=description_bounds(image,area,masks)
        self.assertIsNotNone(bounds);self.assertGreaterEqual(bounds.right(),499)
        self.assertGreaterEqual(bounds.bottom(),379)
    def test_brief_miss_retains_only_the_same_visible_item_and_stationary_pointer(self):
        image=QImage(str(ROOT/'vendor/minerva/samples/player-shop/equips-under-the-pointer-and-its-tooltip.png'))
        found={'name':'Fixture item','area':dict(x=214,y=150,width=164,height=18),'_pointer':[60,20]}
        for reason in ('gone','name_changed','pointer_moved','expired'):
            with self.subTest(reason=reason):
                tracker=TooltipReference();self.assertIs(tracker.observe(found,image,(60,20),now=1),found)
                self.assertIsNotNone(tracker.panel)
                self.assertIs(tracker.observe(None,image,(60,20),now=1.2),found)
                changed=image.copy();point=(60,20);now=1.25
                if reason=='gone':changed.fill(QColor('#171c25'))
                if reason=='name_changed':
                    from PySide6.QtGui import QPainter
                    painter=QPainter(changed);painter.fillRect(QRect(214,150,164,18),QColor('#555577'));painter.end()
                if reason=='pointer_moved':point=(120,20)
                if reason=='expired':now=1.5
                self.assertIsNone(tracker.observe(None,changed,point,now=now))

    def test_clipped_real_description_is_larger_than_its_recognized_name_line(self):
        image=QImage(str(ROOT/'vendor/minerva/samples/player-shop/equips-under-the-pointer-and-its-tooltip.png'))
        self.assertFalse(image.isNull())
        box=description_bounds(image,dict(x=214,y=150,width=164,height=18))
        self.assertIsNotNone(box)
        self.assertLessEqual(abs(box.x()-202),6)
        self.assertLessEqual(abs(box.y()-130),6)
        self.assertEqual(box.right(),image.width()-1)
        self.assertEqual(box.bottom(),image.height()-1)
        self.assertTrue(still_present(image,box))
        image.fill(QColor('#171c25'));self.assertFalse(still_present(image,box))

    def test_no_panel_is_inferred_from_an_unanchored_or_plain_image(self):
        image=QImage(800,800,QImage.Format.Format_RGBA8888);image.fill(QColor('#171c25'))
        self.assertIsNone(description_bounds(image,None))
        self.assertIsNone(description_bounds(image,dict(x=200,y=200,width=140,height=18)))

    def test_warm_translucent_panels_remain_distinct_from_adjacent_comparison(self):
        from PySide6.QtGui import QPainter
        image=QImage(800,600,QImage.Format.Format_RGBA8888);image.fill(QColor('#ad969e'))
        painter=QPainter(image)
        for left in (200,441):
            painter.fillRect(QRect(left,350,236,240),QColor(78,65,62))
            for x in (left,left+233):
                painter.fillRect(x,350,3,240,QColor(30,26,40))
                painter.fillRect(x+1,350,1,240,QColor(170,150,160))
        painter.end()
        box=description_bounds(image,dict(x=210,y=363,width=120,height=18))
        self.assertIsNotNone(box);self.assertEqual(box.x(),200);self.assertEqual(box.right(),435)
        self.assertLessEqual(abs(box.top()-350),2);self.assertLessEqual(abs(box.bottom()-590),2)
        self.assertTrue(still_present(image,box))
        image.fill(QColor('#ad969e'));self.assertFalse(still_present(image,box))

    def test_centered_header_uses_top_rim_when_chat_hides_part_of_a_side(self):
        from PySide6.QtGui import QPainter
        image=QImage(640,800,QImage.Format.Format_RGBA8888);image.fill(QColor('#ad969e'))
        painter=QPainter(image);painter.fillRect(QRect(200,480,236,310),QColor(78,65,62))
        for x in (200,433):
            painter.fillRect(x,480,3,310,QColor(30,26,40));painter.fillRect(x+1,480,1,310,QColor(170,150,160))
        painter.fillRect(434,480,1,60,QColor(39,31,68))
        painter.fillRect(200,480,236,3,QColor(30,26,40));painter.fillRect(200,481,236,1,QColor(170,150,160));painter.end()
        box=description_bounds(image,dict(x=208,y=492,width=219,height=28))
        self.assertIsNotNone(box);self.assertTrue(box.contains(QRect(208,492,219,28)))
        self.assertTrue(still_present(image,box));self.assertGreater(box.height(),300)

    def comparison_pair(self):
        from PySide6.QtGui import QPainter
        image=QImage(800,600,QImage.Format.Format_RGBA8888);image.fill(QColor('#eeeeee'))
        painter=QPainter(image)
        for left,height in ((200,210),(441,240)):
            painter.fillRect(left,350,236,height,QColor(70,65,105))
            # A real frame can have a darker middle stroke. Requiring only a
            # bright stripe loses the frame and joins the two purple bodies.
            for x in (left,left+233):
                painter.fillRect(x,350,3,height,QColor(60,60,90))
                painter.fillRect(x+1,350,1,height,QColor(30,26,40))
            painter.fillRect(left,350,236,3,QColor(60,60,90))
            painter.fillRect(left,351,236,1,QColor(30,26,40))
        painter.end();return image

    def test_comparison_panels_do_not_merge_when_the_rim_middle_is_darker(self):
        image=self.comparison_pair()
        primary=description_bounds(image,dict(x=210,y=363,width=120,height=12))
        comparison=description_bounds(image,dict(x=451,y=363,width=120,height=12))
        self.assertIsNotNone(primary);self.assertIsNotNone(comparison)
        self.assertLess(primary.right(),comparison.left())
        self.assertLess(primary.width(),260);self.assertLess(comparison.width(),260)
        self.assertLess(primary.height(),comparison.height())

    def test_colour_fallback_stops_at_a_proven_comparison_divider(self):
        from PySide6.QtGui import QPainter
        image=self.comparison_pair();painter=QPainter(image)
        painter.fillRect(200,350,4,210,QColor(70,65,105));painter.end()
        bounds=description_bounds(image,dict(x=210,y=363,width=120,height=12))
        self.assertIsNotNone(bounds);self.assertLess(bounds.right(),441)

    def test_scaled_pairs_keep_unequal_panels_separate_in_small_windows(self):
        original=self.comparison_pair()
        for scale in (.8,1.,1.25,1.5,2.):
            with self.subTest(scale=scale):
                image=original.scaled(round(original.width()*scale),round(original.height()*scale),
                                      Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.SmoothTransformation)
                area=dict(x=round(210*scale),y=round(363*scale),width=round(120*scale),height=round(12*scale))
                bounds=description_bounds(image,area)
                self.assertIsNotNone(bounds)
                self.assertLess(bounds.width(),270*scale)
                self.assertLess(bounds.right(),441*scale)
                self.assertTrue(still_present(image,bounds))

"""Native description bounds from public OCR samples, including clipped panels."""
from pathlib import Path
import unittest
from PySide6.QtCore import QRect,Qt
from PySide6.QtGui import QImage,QColor
from price_lens.tooltip_geometry import description_bounds,still_present,TooltipReference,shop_description_bounds

ROOT=Path(__file__).resolve().parents[1]


class TooltipGeometryTests(unittest.TestCase):
    def test_shared_cap_grid_agrees_with_individual_widths_and_exclusions(self):
        from price_lens.tooltip_geometry import _rim_pixels
        image=self.comparison_pair()
        rim=_rim_pixels(image,[QRect(230,348,30,8),QRect(400,350,10,15)])
        rights=[275,300,350,400,433,455,674]
        ys=range(345,360)
        scores=rim.cap_scores(200,rights,ys)
        for right in rights:
            expected=rim.axis_scores(range(205,right-4,6),ys,True)
            self.assertEqual(scores[right],expected)

    def test_batched_native_frame_scores_preserve_masked_and_edge_stroke_results(self):
        from price_lens.tooltip_geometry import _rim_pixels
        from PySide6.QtGui import QPainter
        image=QImage(83,69,QImage.Format.Format_RGBA8888);image.fill(QColor('#55507a'))
        painter=QPainter(image)
        for width in (1,2,3):
            x=10+width*12
            painter.fillRect(x,5,width,50,QColor('#302a45'))
            painter.fillRect(x+width,5,width,50,QColor('#70718a'))
            painter.fillRect(x+2*width,5,width,50,QColor('#302a45'))
        painter.fillRect(2,60,75,1,QColor('#302a45'))
        painter.fillRect(2,61,75,1,QColor('#70718a'))
        painter.fillRect(2,62,75,1,QColor('#302a45'));painter.end()
        rim=_rim_pixels(image,[QRect(20,20,10,12),QRect(50,55,10,8)])
        xs=range(0,83,2);ys=range(0,69,2)
        for horizontal in (False,True):
            scores=rim.axis_scores(xs,ys,horizontal)
            for fixed,value in scores.items():
                samples=[rim(x,fixed,True) for x in xs] if horizontal else [rim(fixed,y) for y in ys]
                samples=[sample for sample in samples if sample is not None]
                expected=sum(samples)/len(samples) if len(samples)>=4 else 0
                self.assertAlmostEqual(value,expected)

    def test_sparse_bright_glyphs_do_not_toggle_a_dark_native_body(self):
        from PySide6.QtGui import QPainter
        from price_lens.tooltip_geometry import _description_body
        image=QImage(400,400,QImage.Format.Format_RGBA8888);image.fill(QColor('#eeeeee'))
        panel=QRect(100,100,100,100);inner=panel.adjusted(6,6,-6,-6)
        painter=QPainter(image);painter.fillRect(panel,QColor('#464b78'))
        for fy in (.1,.3,.5,.7,.9):
            for fx in (.1,.3,.5,.7,.9):
                x=inner.x()+round((inner.width()-1)*fx);y=inner.y()+round((inner.height()-1)*fy)
                painter.fillRect(x-1,y-1,3,3,QColor('white'))
        painter.end()
        for offset in (-1,0,1):
            self.assertTrue(_description_body(image,panel.translated(0,offset)))

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

    def test_supplied_frame_requires_two_current_cap_strokes_at_each_corner(self):
        from PySide6.QtGui import QPainter
        from price_lens.tooltip_geometry import verified_frame
        image=self.comparison_pair();box=QRect(200,350,236,210)
        self.assertTrue(verified_frame(image,box))
        painter=QPainter(image)
        for x in (205,428):painter.fillRect(x,351,1,1,QColor(60,60,90))
        painter.end();self.assertTrue(verified_frame(image,box))
        painter=QPainter(image)
        for x in (204,206):painter.fillRect(x,351,1,1,QColor(60,60,90))
        painter.end();self.assertFalse(verified_frame(image,box))

    def test_shop_occlusion_can_be_found_before_ocr_without_reading_a_name(self):
        from PySide6.QtGui import QPainter
        image=self.comparison_pair();painter=QPainter(image)
        painter.fillRect(211,365,5,5,QColor(85,204,255));painter.end()
        box=shop_description_bounds(image,(180,390))
        self.assertIsNotNone(box)
        self.assertEqual(box.x(),200);self.assertLess(box.right(),441)
        self.assertTrue(still_present(image,box))
        self.assertIsNone(shop_description_bounds(image,(180,390),exclude=[QRect(208,362,20,18)]))

    def test_shop_occlusion_probe_requires_native_frame_and_rejects_bright_panes(self):
        from PySide6.QtGui import QPainter
        for color in ('#cad5df','#464b78'):
            image=QImage(800,600,QImage.Format.Format_RGBA8888);image.fill(QColor(color))
            painter=QPainter(image);painter.fillRect(211,365,5,5,QColor(85,204,255));painter.end()
            self.assertIsNone(shop_description_bounds(image,(180,390)))

    def test_cyan_scenery_does_not_prevent_the_bounded_native_header_probe(self):
        from PySide6.QtGui import QPainter
        image=self.comparison_pair();painter=QPainter(image)
        painter.fillRect(0,0,160,160,QColor(85,204,255))
        painter.fillRect(211,365,5,5,QColor(85,204,255));painter.end()
        box=shop_description_bounds(image,(180,340))
        self.assertIsNotNone(box);self.assertEqual(box.x(),200)
        self.assertLess(box.right(),441)

    def test_many_small_cyan_scenery_components_cannot_crowd_out_the_native_title(self):
        from PySide6.QtGui import QPainter
        image=self.comparison_pair();painter=QPainter(image)
        for x in range(115,195,6):
            for y in range(315,420,6):
                painter.fillRect(x,y,3,3,QColor(85,204,255))
        painter.fillRect(211,365,5,5,QColor(85,204,255));painter.end()
        box=shop_description_bounds(image,(150,390))
        self.assertIsNotNone(box);self.assertEqual(box.x(),200)
        self.assertLess(box.right(),441)

    def test_opaque_labels_can_hide_the_far_edge_without_becoming_frame_evidence(self):
        from PySide6.QtGui import QPainter
        image=self.comparison_pair();painter=QPainter(image)
        painter.fillRect(211,365,5,5,QColor(85,204,255))
        masks=[QRect(360,y,300,38) for y in (338,378,418,458,498,538)]
        for mask in masks:painter.fillRect(mask,QColor('#161c26'))
        painter.end()
        box=shop_description_bounds(image,(180,340),exclude=masks)
        self.assertIsNotNone(box);self.assertEqual(box.x(),200)
        self.assertLessEqual(box.right(),362,'A masked edge cannot join an adjacent comparison pane')
        self.assertTrue(still_present(image,box,masks))

    def test_bottom_cap_proves_a_partial_pane_when_the_cursor_hides_its_top_corner(self):
        from PySide6.QtGui import QPainter
        image=self.comparison_pair();painter=QPainter(image)
        painter.fillRect(200,557,236,3,QColor(60,60,90))
        painter.fillRect(200,558,236,1,QColor(30,26,40))
        painter.fillRect(211,365,5,5,QColor(85,204,255))
        masks=[QRect(240,y,300,38) for y in (338,378,418,458,498,538)]
        masks.append(QRect(196,326,32,36))
        for mask in masks:painter.fillRect(mask,QColor('#161c26'))
        painter.end()
        box=shop_description_bounds(image,(200,330),exclude=masks)
        self.assertIsNotNone(box);self.assertEqual(box.x(),200)
        self.assertLess(box.right(),245);self.assertLessEqual(box.top(),350)

    def test_a_narrow_native_strip_can_prove_occlusion_beside_opaque_shop_labels(self):
        from PySide6.QtGui import QPainter
        image=self.comparison_pair();painter=QPainter(image)
        painter.fillRect(200,557,236,3,QColor(60,60,90))
        painter.fillRect(200,558,236,1,QColor(30,26,40))
        painter.fillRect(211,365,5,5,QColor(85,204,255))
        masks=[QRect(228,y,300,38) for y in (338,378,418,458,498,538)]
        for mask in masks:painter.fillRect(mask,QColor('#161c26'))
        painter.end()
        box=shop_description_bounds(image,(180,340),exclude=masks)
        self.assertIsNotNone(box);self.assertEqual(box.x(),200)
        self.assertLessEqual(box.right(),230)
        self.assertLessEqual(box.top(),350)
        self.assertTrue(still_present(image,box,masks))

    def test_partial_native_pane_stops_before_an_unrelated_shop_edge_below_it(self):
        from PySide6.QtGui import QPainter
        image=self.comparison_pair();painter=QPainter(image)
        painter.fillRect(200,557,236,3,QColor(60,60,90))
        painter.fillRect(200,558,236,1,QColor(30,26,40))
        painter.fillRect(211,365,5,5,QColor(85,204,255))
        painter.fillRect(359,560,3,38,QColor(60,60,90))
        painter.fillRect(360,560,1,38,QColor(30,26,40))
        masks=[QRect(360,y,300,38) for y in (338,378,418,458,498,538)]
        for mask in masks:painter.fillRect(mask,QColor('#161c26'))
        painter.end()
        box=shop_description_bounds(image,(180,340),exclude=masks)
        self.assertIsNotNone(box);self.assertLessEqual(box.bottom(),563)

    def test_personalized_header_does_not_move_the_frame_down_to_an_inner_rule(self):
        from PySide6.QtGui import QPainter
        image=self.comparison_pair();painter=QPainter(image)
        painter.fillRect(200,385,236,3,QColor(60,60,90))
        painter.fillRect(200,386,236,1,QColor(30,26,40))
        painter.fillRect(211,397,5,5,QColor(85,204,255));painter.end()
        box=description_bounds(image,dict(x=210,y=395,width=120,height=14))
        self.assertIsNotNone(box);self.assertLessEqual(abs(box.top()-350),3)
        masks=[QRect(360,y,300,38) for y in (338,378,418,458,498,538)]
        painter=QPainter(image)
        for mask in masks:painter.fillRect(mask,QColor('#161c26'))
        painter.end()
        box=shop_description_bounds(image,(180,340),exclude=masks)
        self.assertIsNotNone(box);self.assertLessEqual(abs(box.top()-350),3)

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

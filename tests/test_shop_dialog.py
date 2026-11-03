"""Price-form visibility from pixels, independently of prices/OCR/network."""
import unittest

from PySide6.QtCore import QRect,Qt
from PySide6.QtGui import QColor,QImage,QPainter

from price_lens.shop_dialog import ShopPriceEntry,price_entry_dialog


def form_image(scale=1.0,*,paper=True,fields=True,buttons=True,pink=True):
    image=QImage(round(900*scale),round(650*scale),QImage.Format.Format_RGBA8888)
    image.fill(QColor('#495d81'));p=QPainter(image);p.scale(scale,scale)
    p.fillRect(150,205,199,260,QColor('#d9e2ea'))
    if paper:
        p.fillRect(300,210,232,139,QColor('#d6e4ee'))
        p.fillRect(305,214,220,13,QColor('white'))
    for i in range(3):
        if pink:p.fillRect(306,237+i*20,108,16,QColor(205,77,130))
        if fields:p.fillRect(418,239+i*20,104,12,QColor('white'))
    if buttons:
        for x in (432,482):p.fillRect(x,328,40,12,QColor(235,153,75))
    p.end()
    return image,QRect(round(150*scale),round(205*scale),round(199*scale),round(260*scale))


class ShopDialogTests(unittest.TestCase):
    def moved_native_form(self,x=420,y=250,scale=1,*,cover=True):
        source,shop=form_image()
        form=source.copy(300,210,232,139)
        image=QImage(900,650,QImage.Format.Format_RGBA8888);image.fill(QColor('#495d81'))
        p=QPainter(image);p.fillRect(150,205,199,260,QColor('#d9e2ea'));p.drawImage(x,y,form)
        # Native frame's three alternating rails, independent of all labels.
        for offset,color in ((3,QColor(105,125,140)),(2,QColor(245,249,255)),(1,QColor(105,125,140))):
            p.fillRect(x+232-offset,y,1,139,color)
            p.fillRect(x,y+139-offset,232,1,color)
        for col in range(x+6,x+42,6):p.fillRect(col,y+6,2,5,QColor('black'))
        hidden=[QRect(x-5,y-5,130,98)] if cover else []
        for rect in hidden:p.fillRect(rect,QColor('#171c26'))
        p.end()
        if scale!=1:
            image=image.scaled(round(900*scale),round(650*scale),Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.FastTransformation)
            shop=QRect(*(round(value*scale) for value in shop.getRect()))
            hidden=[QRect(*(round(value*scale) for value in rect.getRect())) for rect in hidden]
        return image,shop,hidden

    def obscured_form(self,*,caption=True,frame=True):
        image,shop=form_image();p=QPainter(image)
        if frame:
            for x in (300,529):
                p.fillRect(x,210,3,139,QColor(100,130,145));p.fillRect(x+1,210,1,139,QColor('white'))
            p.fillRect(300,346,232,3,QColor(100,130,145));p.fillRect(300,347,232,1,QColor('white'))
        if caption:
            for x in range(306,342,6):p.fillRect(x,216,2,5,QColor('black'))
        hidden=[QRect(390,y,180,36) for y in (201,241,281,321)]
        for rect in hidden:p.fillRect(rect,QColor('#171c26'))
        p.end();return image,shop,hidden

    def test_opaque_labels_over_every_input_and_button_need_exposed_caption_and_frame(self):
        image,shop,hidden=self.obscured_form()
        state=ShopPriceEntry();self.assertTrue(state.observe(image,shop,hidden,now=1))
        self.assertIsNotNone(state.rectangle)
        rect=QRect(state.rectangle)
        for now in (2,3,4):
            state.observe(image.copy(),shop,hidden,now=now)
            self.assertEqual(state.rectangle,rect);self.assertIsNone(state.closed_at)
        for missing in ('caption','frame'):
            image,shop,hidden=self.obscured_form(**{missing:False})
            self.assertIsNone(price_entry_dialog(image,shop,hidden),missing)

    def test_our_own_paint_cannot_supply_the_unknown_controls_fallback(self):
        image,shop,hidden=self.obscured_form()
        self.assertIsNone(price_entry_dialog(image,shop,[*hidden,QRect(300,210,90,139)]))
        p=QPainter(image);p.fillRect(300,344,232,5,QColor('#d6e4ee'));p.end()
        self.assertIsNone(price_entry_dialog(image,shop,hidden))

    def test_capture_can_peek_without_consuming_the_ui_visibility_transition(self):
        image,shop=form_image();state=ShopPriceEntry()
        rect=state.peek(image,shop)
        self.assertIsNotNone(rect);self.assertIsNone(state.rectangle);self.assertFalse(state.blocking)
        self.assertTrue(state.observe(image,shop,now=1))
        self.assertEqual(state.rectangle,rect);self.assertTrue(state.blocking)

    def test_native_form_detects_at_supported_scales_without_text_ocr(self):
        for scale in (.75,1.0,1.25,1.5,2.0):
            with self.subTest(scale=scale):
                image,shop=form_image(scale);rect=price_entry_dialog(image,shop)
                self.assertIsNotNone(rect)
                self.assertLessEqual(abs(rect.x()-300*scale),2)
                self.assertLessEqual(abs(rect.y()-210*scale),2)

    def test_form_search_includes_the_complete_dialog_beyond_the_price_labels(self):
        for x,y in ((600,210),(300,100),(300,440)):
            with self.subTest(position=(x,y)):
                image,shop,_=self.moved_native_form(x,y,cover=False)
                rect=price_entry_dialog(image,shop)
                self.assertIsNotNone(rect)
                self.assertLessEqual(abs(rect.x()-x),2);self.assertLessEqual(abs(rect.y()-y),2)

    def test_verified_form_relocates_when_our_labels_hide_the_caption_and_magenta_column(self):
        for scale in (.75,1,1.25,1.5,2):
            with self.subTest(scale=scale):
                first,shop=form_image(scale);state=ShopPriceEntry();state.observe(first,shop,now=1)
                self.assertIsNotNone(state.rectangle)
                image,shop,hidden=self.moved_native_form(scale=scale)
                self.assertIsNone(price_entry_dialog(image,shop,hidden))
                self.assertTrue(state.observe(image,shop,hidden,now=2))
                self.assertIsNotNone(state.rectangle)
                self.assertLessEqual(abs(state.rectangle.x()-420*scale),2)
                self.assertLessEqual(abs(state.rectangle.y()-250*scale),2)
                self.assertIsNone(state.closed_at)
                state.observe(image.copy(),shop,hidden,now=3)
                self.assertIsNotNone(state.rectangle)

    def test_hidden_labels_cannot_bootstrap_a_form_or_keep_it_after_confirmed_closure(self):
        image,shop,hidden=self.moved_native_form();state=ShopPriceEntry()
        state.observe(image,shop,hidden,now=1);self.assertIsNone(state.rectangle)
        first,shop=form_image();state.observe(first,shop,now=2)
        blank=QImage(image);blank.fill(QColor('#495d81'));state.observe(blank,shop,now=3)
        self.assertTrue(state.accept(4,verified=True))
        state.observe(image,shop,hidden,now=5);self.assertIsNone(state.rectangle)

    def test_annotation_rectangles_cannot_erase_a_completely_intact_native_form(self):
        image,shop,_=self.moved_native_form(cover=False)
        hidden=[QRect(415,245,130,98)]
        self.assertIsNone(price_entry_dialog(image,shop,hidden))
        state=ShopPriceEntry();state.observe(image,shop,hidden,now=1)
        self.assertIsNotNone(state.rectangle)
        for now in (2,3,4):
            state.observe(image.copy(),shop,hidden,now=now)
            self.assertIsNotNone(state.rectangle);self.assertIsNone(state.closed_at)
        # Actual foreground paint remains unknown; a rectangle by itself
        # cannot authorize recovery through pixels that are no longer there.
        obscured=image.copy();p=QPainter(obscured)
        for rect in hidden:p.fillRect(rect,QColor('#171c26'))
        p.end();cold=ShopPriceEntry();cold.observe(obscured,shop,hidden,now=5)
        self.assertIsNone(cold.rectangle)

    def test_relocation_needs_current_native_rails_fields_and_exposed_controls(self):
        for missing in ('right','bottom','field','buttons','all'):
            with self.subTest(missing=missing):
                first,shop=form_image();state=ShopPriceEntry();state.observe(first,shop,now=1)
                image,shop,hidden=self.moved_native_form();p=QPainter(image)
                if missing=='right':p.fillRect(648,250,5,139,QColor('#495d81'))
                if missing=='bottom':p.fillRect(420,384,232,5,QColor('#495d81'))
                if missing=='field':p.fillRect(550,298,90,16,QColor('#495d81'))
                if missing=='buttons':p.fillRect(550,365,98,18,QColor('#495d81'))
                if missing=='all':
                    hidden=[QRect(420,250,232,139)];p.fillRect(hidden[0],QColor('#171c26'))
                p.end();state.observe(image,shop,hidden,now=2)
                self.assertIsNone(state.rectangle)

    def test_existing_labels_can_hide_two_fields_without_becoming_evidence(self):
        image,shop=form_image();hidden=QRect(390,210,180,70)
        p=QPainter(image);p.fillRect(hidden,QColor('#171c26'));p.end()
        self.assertIsNotNone(price_entry_dialog(image,shop,[hidden]))
        image,shop=form_image(paper=False,fields=False,buttons=False)
        # A decorative magenta region plus our label cannot invent a form.
        self.assertIsNone(price_entry_dialog(image,shop,[hidden]))

    def test_incomplete_or_unrelated_colours_cannot_suppress_shop_labels(self):
        for missing in ('paper','fields','buttons','pink'):
            with self.subTest(missing=missing):
                image,shop=form_image(**{missing:False})
                self.assertIsNone(price_entry_dialog(image,shop))
        image,shop=form_image()
        self.assertIsNone(price_entry_dialog(image,None))
        self.assertIsNone(price_entry_dialog(image,QRect(0,0,70,70)))
        self.assertIsNone(price_entry_dialog(image,shop,[QRect(300,210,232,139)]))

    def test_closure_needs_a_fresh_verified_shop_read_and_ignores_late_replies(self):
        image,shop=form_image();state=ShopPriceEntry()
        self.assertTrue(state.observe(image,shop,now=10));self.assertTrue(state.blocking)
        blank=QImage(image);blank.fill(QColor('#495d81'))
        self.assertTrue(state.observe(blank,shop,now=11));self.assertTrue(state.blocking)
        self.assertFalse(state.accept(10.9,verified=True))
        self.assertFalse(state.accept(12,verified=False))
        self.assertTrue(state.accept(12,verified=True));self.assertFalse(state.blocking)

    def test_reopening_a_form_revokes_its_pending_restoration(self):
        image,shop=form_image();state=ShopPriceEntry()
        state.observe(image,shop,now=1)
        blank=QImage(image);blank.fill(QColor('black'))
        state.observe(blank,shop,now=2);state.observe(image,shop,now=3)
        self.assertIsNone(state.closed_at);self.assertFalse(state.accept(4,verified=True))
        state.clear();self.assertFalse(state.blocking)

    def test_cursor_fragmenting_labels_does_not_end_a_verified_dialog(self):
        image,shop=form_image();state=ShopPriceEntry();state.observe(image,shop,now=1)
        p=QPainter(image);p.fillRect(344,237,32,36,QColor('white'));p.end()
        state.observe(image,shop,now=2)
        self.assertIsNotNone(state.rectangle);self.assertIsNone(state.closed_at)

    def test_known_form_survives_cursor_over_inputs_and_both_footer_buttons(self):
        from price_lens.shop_source import cursor_rectangle
        for scale in (.75,1,1.25,1.5,2):
            for dx,dy in ((132,119),(182,119),(120,29),(120,49),(120,69),(25,27)):
                with self.subTest(scale=scale,cursor=(dx,dy)):
                    clean,shop,_=self.moved_native_form(cover=False,scale=scale)
                    state=ShopPriceEntry();state.observe(clean,shop,now=1)
                    self.assertIsNotNone(state.rectangle)
                    point=(round((420+dx)*scale),round((250+dy)*scale))
                    image=clean.copy();p=QPainter(image)
                    p.fillRect(cursor_rectangle(point,scale),QColor('white'));p.end()
                    state.observe(image,shop,now=2,pointer=point)
                    self.assertIsNotNone(state.rectangle)
                    self.assertIsNone(state.closed_at)
                    blank=image.copy();blank.fill(QColor('#495d81'))
                    state.observe(blank,shop,now=3,pointer=point)
                    self.assertIsNone(state.rectangle)

    def test_cursor_masks_cannot_bootstrap_an_unverified_form(self):
        image,shop=form_image();point=(482,328)
        p=QPainter(image);p.fillRect(478,321,36,37,QColor('white'));p.end()
        cold=ShopPriceEntry();cold.observe(image,shop,now=1,pointer=point)
        self.assertIsNone(cold.rectangle)

    def test_moving_a_verified_form_updates_its_presentation_rectangle(self):
        from unittest.mock import patch
        image,shop=form_image();state=ShopPriceEntry();state.observe(image,shop,now=1)
        moved=QRect(state.rectangle).translated(12,30)
        with patch('price_lens.shop_dialog._known_form_present',return_value=False),patch(
                'price_lens.shop_dialog.price_entry_dialog',return_value=moved):
            self.assertTrue(state.observe(image.copy(),shop,now=2))
        self.assertEqual(state.rectangle,moved);self.assertIsNone(state.closed_at)


if __name__=='__main__':unittest.main()

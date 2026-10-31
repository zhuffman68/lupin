"""Source proofs use only small local fixtures and never capture a screen."""
from dataclasses import replace
from pathlib import Path
import unittest
import numpy as np

from PySide6.QtCore import QRect
from PySide6.QtGui import QColor,QImage,QPainter

from price_lens.shop_source import MAX_PIXELS,capture_proof,proof_state


class ShopSourceTests(unittest.TestCase):
    def setUp(self):
        self.image=QImage(800,600,QImage.Format.Format_RGBA8888);self.image.fill(QColor('#cad5df'))
        self.rect=QRect(100,100,199,39)
        painter=QPainter(self.image)
        painter.fillRect(QRect(104,104,26,27),QColor('#992211'))
        painter.fillRect(QRect(140,105,100,7),QColor('black'))
        painter.fillRect(QRect(140,123,70,7),QColor('black'));painter.end()
        self.proof=capture_proof(self.image,self.rect)
        self.assertIsNotNone(self.proof)

    def painted(self,rect,color='#775599',image=None):
        result=self.image.copy() if image is None else image.copy()
        painter=QPainter(result);painter.fillRect(rect,QColor(color));painter.end()
        return result

    def test_exact_native_patch_is_same_and_storage_is_only_bounded_rgba(self):
        self.assertEqual(proof_state(self.proof,self.image),'same')
        self.assertEqual(self.proof.rect,self.rect.getRect())
        self.assertEqual(len(self.proof.rgba),199*39*4)
        self.assertIsInstance(self.proof.rgba,bytes)
        self.image.fill(QColor('white'))
        self.assertEqual(proof_state(self.proof,self.image),'changed')

    def test_changed_icon_outside_the_native_name_band_invalidates_the_source(self):
        changed=self.painted(QRect(104,104,26,27),'#2244aa')
        self.assertEqual(proof_state(self.proof,changed),'changed')

    def test_changed_price_or_one_exposed_native_pixel_invalidates_the_source(self):
        changed=self.painted(QRect(150,123,5,7),'#cad5df')
        self.assertEqual(proof_state(self.proof,changed),'changed')
        changed=self.image.copy();changed.setPixelColor(290,125,QColor('white'))
        self.assertEqual(proof_state(self.proof,changed),'changed')

    @staticmethod
    def selected(image,band,tint=(231,153,41)):
        result=image.convertToFormat(QImage.Format.Format_RGBA8888).copy()
        values=np.frombuffer(result.bits(),dtype=np.uint8).reshape(result.height(),result.width(),4)
        rgb=values[band.y():band.y()+band.height(),band.x():band.x()+band.width(),:3]
        old=rgb.astype(np.float32);base=np.array((202,213,223),dtype=np.float32)
        gain=(old*base).sum(axis=2)/float(base@base)
        palette=(gain<=1.08)&(np.max(np.abs(old-gain[:,:,None]*base),axis=2)<=14)
        rule=np.all(old==[222,223,223],axis=2)
        replacement=np.rint(gain[:,:,None]*np.array(tint)).clip(0,255).astype(np.uint8)
        rgb[palette]=replacement[palette];rgb[rule]=[247,192,110]
        return result

    def test_native_selection_preserves_source_glyphs_without_invalidating(self):
        band=QRect(137,102,162,35);selected=self.selected(self.image,band)
        self.assertEqual(proof_state(self.proof,selected),'same')
        reverse=capture_proof(selected,self.rect)
        self.assertEqual(proof_state(reverse,self.image),'same')
        selected.setPixelColor(150,123,QColor('#e79929'))
        self.assertEqual(proof_state(self.proof,selected),'changed')

    def test_selection_under_cursor_mask_is_same_but_real_cursor_changes_are_occluded(self):
        point=(165,115);proof=capture_proof(self.image,self.rect,pointer=point)
        selected=self.selected(self.image,QRect(137,102,162,35))
        self.assertEqual(proof_state(proof,selected,pointer=point),'same')
        cursor=self.painted(QRect(157,107,12,12),'white',selected)
        self.assertEqual(proof_state(proof,cursor,pointer=point),'occluded')

    def test_selected_band_cannot_hide_changed_icon_or_arbitrary_background(self):
        selected=self.selected(self.image,QRect(137,102,162,35))
        selected.setPixelColor(110,110,QColor('blue'))
        self.assertEqual(proof_state(self.proof,selected),'changed')
        foreign=self.painted(QRect(137,102,162,35),'#557799')
        self.assertEqual(proof_state(self.proof,foreign),'changed')

    def test_public_native_antialiased_name_price_and_separator_survive_selection(self):
        root=Path(__file__).resolve().parents[1]
        image=QImage(str(root/'vendor/minerva/samples/player-shop/gems-and-ores.png'))
        self.assertFalse(image.isNull())
        band=QRect(66,10,253,54);rect=QRect(8,7,311,60);scale=253/162
        proof=capture_proof(image,rect,scale=scale)
        for tint in ((251,167,46),(231,153,41),(221,145,38),(235,157,43)):
            with self.subTest(tint=tint):
                selected=self.selected(image,band,tint)
                self.assertEqual(proof_state(proof,selected),'same')
                self.assertEqual(proof_state(capture_proof(selected,rect,scale=scale),image),'same')
    def test_annotation_and_native_tooltip_changes_are_occluded(self):
        for mask in (QRect(145,103,90,10),QRect(235,90,120,110)):
            with self.subTest(mask=mask.getRect()):
                changed=self.painted(mask)
                self.assertEqual(proof_state(self.proof,changed,exclude=[mask]),'occluded')
                old=capture_proof(changed,self.rect,exclude=[mask])
                self.assertEqual(proof_state(old,self.image),'occluded')

    def test_exclusion_union_does_not_excuse_a_change_in_the_remaining_native_pixels(self):
        old_mask=QRect(140,100,25,15);new_mask=QRect(180,100,25,15)
        before=self.painted(old_mask);proof=capture_proof(before,self.rect,exclude=[old_mask])
        latest=self.painted(new_mask);latest.setPixelColor(107,110,QColor('white'))
        self.assertEqual(proof_state(proof,latest,exclude=[new_mask]),'changed')

    def test_old_and_current_cursor_footprints_are_both_masked(self):
        old=(110,110);new=(180,110)
        before=self.painted(QRect(102,102,32,36),'white')
        proof=capture_proof(before,self.rect,pointer=old)
        latest=self.painted(QRect(172,102,32,36),'white')
        self.assertEqual(proof_state(proof,latest,pointer=new),'occluded')
        latest.setPixelColor(280,125,QColor('white'))
        self.assertEqual(proof_state(proof,latest,pointer=new),'changed')

    def test_scaled_cursor_mask_and_two_times_row_keep_exact_native_pixels(self):
        image=QImage(800,600,QImage.Format.Format_RGBA8888);image.fill(QColor('#cad5df'))
        rect=QRect(100,100,398,78);point=(160,120)
        proof=capture_proof(image,rect,pointer=point,scale=2)
        self.assertIsNotNone(proof);self.assertEqual(len(proof.rgba),398*78*4)
        changed=self.painted(QRect(144,104,64,72),'white',image)
        self.assertEqual(proof_state(proof,changed,pointer=point),'occluded')
        changed.setPixelColor(440,125,QColor('black'))
        self.assertEqual(proof_state(proof,changed,pointer=point),'changed')

    def test_full_coverage_and_insufficient_visible_evidence_are_unknown(self):
        for masks in ([self.rect],[QRect(100,100,199,36)],[QRect(100,100,198,39)]):
            self.assertEqual(proof_state(self.proof,self.image,exclude=masks),'unknown')
            self.assertIsNone(capture_proof(self.image,self.rect,exclude=masks))
        tiny=QRect(100,100,5,5)
        self.assertIsNone(capture_proof(self.image,tiny))

    def test_moved_content_changes_and_outside_or_missing_sources_are_unknown(self):
        moved=QImage(self.image.size(),self.image.format());moved.fill(QColor('#cad5df'))
        painter=QPainter(moved);painter.drawImage(20,20,self.image);painter.end()
        self.assertEqual(proof_state(self.proof,moved),'changed')
        self.assertEqual(proof_state(self.proof,QImage(100,100,self.image.format())),'unknown')
        self.assertEqual(proof_state(None,self.image),'unknown')
        self.assertIsNone(capture_proof(self.image,QRect(-1,100,199,39)))

    def test_oversized_or_malformed_proofs_and_exclusions_cannot_establish_identity(self):
        self.assertIsNone(capture_proof(self.image,QRect(0,0,800,600)))
        self.assertLessEqual(len(self.proof.rgba),MAX_PIXELS*4)
        self.assertEqual(proof_state(replace(self.proof,rgba=b'bad'),self.image),'unknown')
        self.assertEqual(proof_state(self.proof,self.image,exclude=[(0,0,-1,10)]),'unknown')
        self.assertIsNone(capture_proof(self.image,self.rect,pointer=('100',100)))
        self.assertIsNone(capture_proof(self.image,self.rect,scale=float('nan')))
        self.assertIsNone(capture_proof(self.image,(0,0,10**30,39)))
        self.assertEqual(proof_state(self.proof,self.image,exclude=[self.rect]*65),'unknown')


if __name__=='__main__':unittest.main()

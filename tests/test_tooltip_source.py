"""Native title ink is stable even when scenery changes behind its blank tail."""
import json
from pathlib import Path
import unittest

from PySide6.QtCore import QRect
from PySide6.QtGui import QColor,QImage,QPainter

from price_lens.tooltip_geometry import description_bounds
from price_lens.tooltip_source import capture_title,MAX_EXCLUSIONS,MAX_TITLE_PIXELS


class TooltipSourceTests(unittest.TestCase):
    def setUp(self):
        self.image=QImage(360,280,QImage.Format.Format_RGBA8888)
        self.image.fill(QColor('#283447'))
        self.panel=QRect(40,40,240,180)
        self.title=QRect(52,54,160,16)
        painter=QPainter(self.image);painter.fillRect(self.panel,QColor('#46416a'));painter.end()
        self.paint_name(self.image)

    def paint_name(self,image,colour='#f6f4f0'):
        painter=QPainter(image)
        for x in (58,69,81,96,110,123,139,151):
            painter.fillRect(x,58,3,8,QColor(colour))
            painter.fillRect(x,58,8,2,QColor(colour))
        painter.end()

    def changed(self,rect,colour):
        image=self.image.copy();painter=QPainter(image);painter.fillRect(rect,QColor(colour));painter.end()
        return image

    def proof(self,**kwargs):
        return capture_title(self.image,self.title,panel=self.panel,**kwargs)

    def test_white_orange_and_green_ink_survive_only_dark_background_changes(self):
        for colour in ('#f6f4f0','#ff9900','#6ffb79'):
            with self.subTest(colour=colour):
                self.setUp();self.paint_name(self.image,colour)
                proof=self.proof();self.assertIsNotNone(proof);self.assertTrue(proof.semantic)
                changed=self.changed(QRect(186,54,26,16),'#354b73')
                self.assertTrue(proof.matches(changed,panel=self.panel))
                # Blank gaps within the name, not just the trailing columns,
                # can also reveal animated scenery through the native panel.
                changed=self.changed(QRect(89,54,4,16),'#354b73')
                self.assertTrue(proof.matches(changed,panel=self.panel))

    def test_prefix_suffix_new_foreign_ink_and_recoloured_letters_are_rejected(self):
        proof=self.proof()
        for rect,colour in ((QRect(58,58,3,8),'#46416a'),
                            (QRect(151,58,8,8),'#46416a'),
                            (QRect(190,58,3,8),'white'),
                            (QRect(58,58,3,8),'#ff9900'),
                            (self.title,'white')):
            with self.subTest(rect=rect,colour=colour):
                self.assertFalse(proof.matches(self.changed(rect,colour),panel=self.panel))

    def test_source_bound_antialias_can_blend_without_changing_opaque_letters(self):
        fringe=QRect(61,60,1,6)
        p=QPainter(self.image);p.fillRect(fringe,QColor('#adb2cb'));p.end()
        proof=self.proof();latest=self.changed(fringe,'#bbc0d4')
        self.assertFalse(proof.matches(latest),'Generic descriptions retain exact bright ink')
        self.assertTrue(proof.matches(latest,antialias=True))
        for rect,colour in ((QRect(58,58,3,8),'#46416a'),
                            (QRect(58,58,3,8),'#f5f4f0'),
                            (QRect(58,58,3,8),'#ff9900'),
                            (QRect(190,58,3,8),'#adb2cb'),
                            (fringe,'#46416a')):
            with self.subTest(rect=rect,colour=colour):
                self.assertFalse(proof.matches(self.changed(rect,colour),antialias=True))

    def test_source_bound_antialias_threshold_crossing_does_not_move_a_letter(self):
        fringe=QRect(61,60,1,6)
        p=QPainter(self.image);p.fillRect(fringe,QColor('#9292b1'));p.end()
        proof=self.proof();latest=self.changed(fringe,'#9898b4')
        self.assertFalse(proof.matches(latest))
        self.assertTrue(proof.matches(latest,antialias=True))
        # Masks cannot hide a changed opaque glyph or supply the independent
        # native panel needed for this source-bound raster comparison.
        gone=self.changed(QRect(58,58,3,8),'#46416a')
        self.assertFalse(proof.matches(gone,antialias=True,exclude=[QRect(56,54,12,16)]))
        self.assertFalse(proof.matches(self.changed(self.panel,'white'),antialias=True))

    def test_changed_source_cannot_be_hidden_by_an_annotation_or_cursor_mask(self):
        proof=self.proof()
        changed=self.changed(QRect(151,58,8,8),'#46416a')
        self.assertFalse(proof.matches(changed,exclude=[QRect(149,54,14,16)]))
        self.assertFalse(proof.matches(changed,pointer=(150,58)))
        self.assertFalse(proof.matches(self.image,exclude=[self.title]))
        self.assertIsNone(self.proof(exclude=[self.title]))

    def test_excluded_blank_tail_does_not_hide_or_remove_any_ink(self):
        blank=QRect(186,54,26,16)
        proof=self.proof(exclude=[blank])
        self.assertTrue(proof.matches(self.changed(blank,'#354b73'),exclude=[blank]))

    def test_missing_changed_or_out_of_frame_panel_cannot_keep_a_title(self):
        proof=self.proof()
        self.assertFalse(proof.matches(self.changed(self.panel,'white')))
        self.assertFalse(proof.matches(self.image,panel=self.panel.translated(1,0)))
        self.assertFalse(proof.matches(self.image.copy(0,0,250,190)))
        self.assertFalse(proof.matches(self.image,exclude=[self.panel]))
        self.assertIsNone(capture_title(self.image,self.title,panel=QRect(250,40,60,180)))

    def test_background_variation_needs_panel_proof_and_blank_titles_stay_exact(self):
        proof=capture_title(self.image,self.title)
        self.assertFalse(proof.semantic)
        changed=self.changed(QRect(186,54,26,16),'#354b73')
        self.assertFalse(proof.matches(changed))
        self.assertFalse(proof.matches(changed,panel=self.panel))
        blank=self.changed(self.title,'#46416a')
        proof=capture_title(blank,self.title,panel=self.panel)
        self.assertFalse(proof.semantic);self.assertTrue(proof.matches(blank))
        blank.setPixelColor(187,55,QColor('#354b73'))
        self.assertFalse(proof.matches(blank))

    def test_title_bounds_and_exclusions_are_bounded(self):
        self.assertIsNone(capture_title(self.image,QRect(-1,54,160,16),panel=self.panel))
        self.assertIsNone(capture_title(self.image,QRect(0,0,256,MAX_TITLE_PIXELS//256+1)))
        self.assertIsNone(self.proof(exclude=[QRect(0,0,1,1)]*(MAX_EXCLUSIONS+1)))
        self.assertIsNone(self.proof(exclude=[None]))
        self.assertIsNone(self.proof(pointer=(True,0)))
        self.assertFalse(self.proof().matches(self.image,exclude=[QRect()]))

    def test_current_private_grey_and_leather_replay_preserves_unchanged_title_ink(self):
        root=Path(__file__).resolve().parents[1]/'evidence/inventory-tooltip-20261031'
        replay=root/'right-edge-native-replay.json'
        if not replay.is_file():self.skipTest('Private capture fixture is not shipped')
        rows=json.loads(replay.read_text())['rows']
        for first,last in ((27,38),(69,73)):
            for index in range(first,last):
                with self.subTest(index=index):
                    row=rows[index];found=row['result']['tooltip']['found']
                    source=QImage(str(root/'right-edge-live'/f'{index:03d}.png'))
                    latest=QImage(str(root/'right-edge-live'/f'{index+1:03d}.png'))
                    if source.isNull() or latest.isNull():self.skipTest('Private frame is unavailable')
                    panel=description_bounds(source,found['area'])
                    self.assertIsNotNone(panel)
                    proof=capture_title(source,found['area'],panel=panel,pointer=row['frame']['pointer'])
                    self.assertIsNotNone(proof);self.assertTrue(proof.semantic)
                    self.assertTrue(proof.matches(latest,panel=panel,pointer=rows[index+1]['frame']['pointer']))


if __name__=='__main__':unittest.main()

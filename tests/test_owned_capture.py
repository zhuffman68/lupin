"""Only visible Lupin paint may exclude a source region from reading."""
from pathlib import Path
import unittest
from unittest.mock import patch

from PySide6.QtCore import QPoint,QRect,Qt
from PySide6.QtGui import QColor,QImage,QPainter
from PySide6.QtWidgets import QApplication,QWidget,QPushButton

from price_lens.branding import Wordmark
from price_lens.owned_capture import OwnedCapture,PaintAnchor,locate_paint
from price_lens.chat_ocr import pixels
from price_lens.chat_history import history_regions
from test_chat_history import panel_scene

ROOT=Path(__file__).resolve().parents[1]


class UnknownPosition(QWidget):
    def mapToGlobal(self,point):return QPoint(point)  # Wayland's unknown origin.


class OwnedCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.widget=UnknownPosition();self.widget.resize(420,900)
        self.widget.setStyleSheet('QWidget {background:#19212d;color:#f4dfb8;} QPushButton {background:#344454;}')
        self.mark=Wordmark(ROOT/'price_lens/resources/wordmark.svg',self.widget);self.mark.move(20,10)
        self.button=QPushButton('Hotkeys…',self.widget);self.button.setGeometry(270,20,120,36)
        self.widget.show();self.app.processEvents();self.locator=OwnedCapture()
        self.screen=QRect(0,0,1920,1080)

    def tearDown(self):self.widget.close();self.widget.deleteLater();self.app.processEvents()

    def scene(self,origin=None,scale=1):
        image=QImage(round(1920*scale),round(1080*scale),QImage.Format.Format_RGB888);image.fill(QColor('#29452c'))
        if origin is not None:
            template=self.widget.grab().toImage()
            if scale!=1:template=template.scaled(round(template.width()*scale),round(template.height()*scale),Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.SmoothTransformation)
            painter=QPainter(image);painter.drawImage(QPoint(*origin),template);painter.end()
        return image

    def rectangle(self,image):return self.locator.rectangle(image,self.widget,(self.mark,self.button),self.screen)

    def test_unknown_origin_cannot_mask_chat_when_our_window_is_elsewhere(self):
        image=self.scene((1400,100));rect=self.rectangle(image)
        self.assertEqual(rect,QRect(1400,100,420,900))
        self.assertFalse(rect.intersects(QRect(284,650,550,74)))

    def test_unrelated_or_capture_omitted_window_does_not_exclude_reported_origin(self):
        with patch('price_lens.owned_capture.time.monotonic',return_value=1):
            self.assertIsNone(self.rectangle(self.scene()))
        with patch('price_lens.owned_capture.time.monotonic',return_value=2.1):
            image=self.scene((1400,100));self.assertIsNotNone(self.rectangle(image))
            self.assertIsNone(self.rectangle(self.scene()))

    def test_real_zero_origin_is_accepted_only_when_its_paint_is_present(self):
        self.assertEqual(self.rectangle(self.scene((0,0))),QRect(0,0,420,900))
        self.assertIsNone(self.rectangle(self.scene()))

    def test_moved_window_never_reuses_a_missing_paint_proof(self):
        with patch('price_lens.owned_capture.time.monotonic',return_value=1):
            self.assertEqual(self.rectangle(self.scene((1400,100))),QRect(1400,100,420,900))
        with patch('price_lens.owned_capture.time.monotonic',return_value=2.1):
            self.assertEqual(self.rectangle(self.scene((800,80))),QRect(800,80,420,900))

    def test_source_scale_and_partial_bottom_are_in_capture_coordinates(self):
        self.assertEqual(self.rectangle(self.scene((1800,120),1.5)),QRect(1800,120,630,1350))
        self.locator=OwnedCapture()
        self.assertEqual(self.rectangle(self.scene((1100,800))),QRect(1100,800,420,280))

    def test_screen_offset_does_not_turn_unknown_global_position_into_a_mask(self):
        self.screen=QRect(1920,0,1920,1080)
        self.assertEqual(self.rectangle(self.scene((1400,100))),QRect(1400,100,420,900))

    def test_missing_secondary_anchor_and_ambiguous_copies_are_not_window_proofs(self):
        anchors=[]
        for child in (self.mark,self.button):
            at=child.mapTo(self.widget,QPoint())
            anchors.append(PaintAnchor.from_image(child.grab().toImage(),QRect(at,child.size())))
        image=self.scene((1400,100));painter=QPainter(image)
        painter.fillRect(self.button.geometry().translated(1400,100),QColor('#29452c'));painter.end()
        self.assertIsNone(locate_paint(pixels(image),anchors))
        image=self.scene((1400,100));painter=QPainter(image);painter.drawImage(100,100,self.widget.grab().toImage());painter.end()
        self.assertIsNone(locate_paint(pixels(image),anchors))

    def test_hidden_window_and_failed_searches_do_not_keep_running_work(self):
        image=self.scene()
        with patch('price_lens.owned_capture.locate_paint',return_value=None) as search,\
             patch('price_lens.owned_capture.time.monotonic',return_value=1):
            for _ in range(5):self.assertIsNone(self.rectangle(image))
            self.assertEqual(search.call_count,1)
        self.widget.hide()
        with patch.object(self.mark,'grab',side_effect=AssertionError('Hidden surface should do no paint work')):
            self.assertIsNone(self.rectangle(image))

    def test_visible_chat_rows_survive_a_wrong_qt_origin(self):
        scene,hud=panel_scene();image=self.scene((1400,100));painter=QPainter(image);painter.drawImage(0,0,scene);painter.end()
        rect=self.rectangle(image);self.assertEqual(rect,QRect(1400,100,420,900))
        rows,_=history_regions(image,hud,exclude=[list(rect.getRect())]);self.assertEqual(len(rows),4)
        rows,_=history_regions(image,hud,exclude=[[0,0,420,900]]);self.assertEqual(rows,[])

"""Compare rendered card transitions with their real endpoint pixels."""
import unittest
from PySide6.QtCore import QRect,QPoint,Qt
from PySide6.QtGui import QPainter,QPixmap,QImage
from PySide6.QtWidgets import QApplication,QWidget,QFrame,QVBoxLayout,QLabel
from price_lens.card_morph import CardMorph,capture_card


class CardMorphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.host=QWidget();self.host.resize(430,500)
        self.host.setStyleSheet('QWidget{background:#171c25;color:#e6eaf3;} QFrame#card{background:#202a38;border:1px solid #3b485a;border-radius:8px;} QLabel{background:transparent;border:0;}')
        self.card=QFrame(self.host);self.card.setObjectName('card');self.card.setGeometry(10,12,400,220)
        layout=QVBoxLayout(self.card);layout.setContentsMargins(12,10,12,10)
        layout.addWidget(QLabel('An item · 123,456'));layout.addStretch()
        self.host.show();self.app.processEvents()

    def tearDown(self):self.host.close();self.host.deleteLater();self.app.processEvents()

    def render(self,morph,progress):
        pixels=QPixmap(self.host.size()*self.host.devicePixelRatioF());pixels.setDevicePixelRatio(self.host.devicePixelRatioF());pixels.fill(Qt.GlobalColor.transparent)
        painter=QPainter(pixels);morph.paint(painter,progress);painter.end();return pixels.toImage()

    def test_endpoints_keep_the_actual_card_pixels_without_stretching_text(self):
        before=self.host.grab();old=capture_card(self.card,self.host,before)
        self.card.resize(400,340);self.app.processEvents()
        after=self.host.grab();new=capture_card(self.card,self.host,after)
        morph=CardMorph(before,after,old,new,self.host)
        self.assertEqual(self.render(morph,0),before.toImage().convertToFormat(QImage.Format.Format_ARGB32_Premultiplied))
        self.assertEqual(self.render(morph,1),after.toImage().convertToFormat(QImage.Format.Format_ARGB32_Premultiplied))
        self.assertEqual(morph.geometry(.5).height(),280)
        self.assertEqual(old.foreground.devicePixelRatioF(),before.devicePixelRatioF())

    def test_a_retarget_begins_from_the_current_visible_frame(self):
        before=self.host.grab();old=capture_card(self.card,self.host,before)
        self.card.resize(400,340);self.app.processEvents();after=self.host.grab();new=capture_card(self.card,self.host,after)
        morph=CardMorph(before,after,old,new,self.host);middle=self.render(morph,.4)
        pixels=QPixmap.fromImage(middle);held=morph.snapshot(pixels,.4)
        retarget=CardMorph(pixels,before,held,old,self.host)
        self.assertEqual(self.render(retarget,0),middle)


if __name__=='__main__':unittest.main()

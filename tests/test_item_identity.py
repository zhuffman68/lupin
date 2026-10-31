"""Exact candidate icon evidence using generated pixels, without screenshots/network."""
from dataclasses import replace
import unittest

from PySide6.QtCore import QRect,Qt
from PySide6.QtGui import QColor,QImage,QPainter

from price_lens.domain import Catalog,Item
from price_lens.item_identity import observed_item,resolve_icon,resolve_shop_item,shop_icon_rect


def icon(seed=0):
    image=QImage(26,27,QImage.Format.Format_RGBA8888)
    image.fill(Qt.GlobalColor.transparent)
    for y in range(2,25):
        for x in range(3,23):
            if x+y>9 and x-y<18:
                image.setPixelColor(x,y,QColor((x*29+seed*91)%256,(y*37+seed*53)%256,((x+y)*19+seed*117)%256))
    return image


class ItemIdentityTests(unittest.TestCase):
    def setUp(self):
        self.top=Item(1041078,'Blue Moon',equipment=True,gender='female',sub_category='Top')
        self.earring=Item(1032011,'Blue Moon',equipment=True,sub_category='Earring')
        self.catalog=Catalog.from_items([self.top,self.earring])
        self.icons={self.top.game_id:icon(),self.earring.game_id:icon(1)}
        self.frame=QImage(240,100,QImage.Format.Format_RGBA8888);self.frame.fill(QColor('#d0dce5'))
        painter=QPainter(self.frame);painter.drawImage(13,20,self.icons[self.top.game_id]);painter.end()
        self.row={'name':'Blue Moon','area':{'x':42,'y':18,'width':162,'height':35}}

    def resolve(self,frame=None,icons=None,row=None):
        return resolve_shop_item(self.catalog,row or self.row,frame if frame is not None else self.frame,
                                 (icons if icons is not None else self.icons).get)

    def test_exclusive_current_pixels_select_top_without_binding_bare_name(self):
        result=self.resolve()
        self.assertEqual(result.item,self.top)
        self.assertEqual(result.evidence,'icon')
        self.assertIsNone(self.catalog.resolve('Blue Moon'))
        self.assertEqual(observed_item(self.catalog,{**self.row,'_item_id':self.top.game_id}),self.top)
        self.assertIsNone(observed_item(self.catalog,{**self.row,'item_id':self.top.game_id}))

    def test_missing_identical_and_near_identical_competitors_abstain(self):
        self.assertIsNone(self.resolve(icons={self.top.game_id:self.icons[self.top.game_id]}).item)
        same=self.icons[self.top.game_id]
        self.assertIsNone(self.resolve(icons={self.top.game_id:same,self.earring.game_id:same}).item)
        near=same.copy();near.setPixelColor(10,10,QColor('#ff00ff'))
        self.assertIsNone(self.resolve(icons={self.top.game_id:same,self.earring.game_id:near}).item)

    def test_fully_or_partly_covered_icons_and_changed_frames_abstain(self):
        self.assertIsNone(self.resolve(row={**self.row,'covered':True}).item)
        self.assertIsNone(self.resolve(row={**self.row,'listing_old':True}).item)
        covered=self.frame.copy();painter=QPainter(covered);painter.fillRect(QRect(13,20,26,27),QColor('#667788'));painter.end()
        self.assertIsNone(self.resolve(covered).item)
        partial=self.frame.copy();painter=QPainter(partial);painter.fillRect(QRect(23,26,8,12),QColor('#667788'));painter.end()
        self.assertIsNone(self.resolve(partial).item)
        other=self.frame.copy();painter=QPainter(other);painter.fillRect(QRect(13,20,26,27),QColor('#d0dce5'))
        painter.drawImage(13,20,self.icons[self.earring.game_id]);painter.end()
        self.assertEqual(self.resolve(other).item,self.earring)

    def test_nearest_scaled_icon_has_exclusive_evidence(self):
        frame=QImage(480,200,QImage.Format.Format_RGBA8888);frame.fill(QColor('#d0dce5'))
        scaled=self.icons[self.top.game_id].scaled(52,54,Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.FastTransformation)
        painter=QPainter(frame);painter.drawImage(26,40,scaled);painter.end()
        row={**self.row,'area':{'x':84,'y':36,'width':324,'height':70}}
        self.assertEqual(self.resolve(frame,row=row).item,self.top)

    def test_unique_names_need_no_images_but_stale_ids_are_rejected(self):
        row={**self.row,'name':'Blue Moon (F)'}
        self.assertEqual(resolve_shop_item(self.catalog,row).item,self.top)
        self.assertIsNone(observed_item(self.catalog,{**row,'_item_id':self.earring.game_id}))
        self.assertIsNone(observed_item(self.catalog,{**row,'_item_id':True}))
        self.assertIsNone(resolve_shop_item(self.catalog,{**row,'name':'Unknown item'}).item)

    def test_bounds_candidate_count_and_degenerate_templates_abstain(self):
        self.assertIsNone(resolve_icon([self.top,self.earring],self.frame,QRect(-1,0,40,40),self.icons.get).item)
        self.assertIsNone(resolve_icon([self.top,self.top],self.frame,shop_icon_rect(self.row),self.icons.get).item)
        many=[replace(self.top,game_id=n) for n in range(9)]
        self.assertIsNone(resolve_icon(many,self.frame,shop_icon_rect(self.row),lambda identity:icon()).item)
        solid=QImage(26,27,QImage.Format.Format_RGBA8888);solid.fill(QColor('#d0dce5'))
        self.assertIsNone(self.resolve(icons={self.top.game_id:solid,self.earring.game_id:solid}).item)


if __name__=='__main__':unittest.main()

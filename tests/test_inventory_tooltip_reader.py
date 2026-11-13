"""Generated public native-frame fixtures exercise the reader's primary role.

No screenshots, game access, markets or live capture are needed. The frame/tab/
slot layout matches the generated Rust association fixtures; titles use the
bundled public UI font rather than private recordings.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor,QFont,QFontDatabase,QImage,QPainter
from PySide6.QtWidgets import QApplication

from price_lens.platform_paths import reader_binary

ROOT=Path(__file__).resolve().parents[1]
BINARY=reader_binary(ROOT)


@unittest.skipUnless(BINARY.is_file(),'Build the screen reader first')
class InventoryTooltipReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        font_id=QFontDatabase.addApplicationFont(str(ROOT/'price_lens/resources/fonts/InterVariable.ttf'))
        cls.font=QFont(QFontDatabase.applicationFontFamilies(font_id)[0]);cls.font.setPixelSize(14)

    def frame(self,*,marker=True,header=True,title=True,comparison=True,primary=True,shop=False,
              tab=0,primary_name='Emerald Staff',single_name='Mithril Pole Arm'):
        image=QImage(1500,900,QImage.Format.Format_RGBA8888);image.fill(QColor(20,35,20))
        painter=QPainter(image);painter.setFont(self.font)
        ix,iy=1293,90
        painter.fillRect(ix,iy,207,285,QColor(245,246,247))
        painter.fillRect(ix+4,iy+2,199,17,QColor('white'))
        for x in range(ix+8,ix+128,6):painter.fillRect(x,iy+7,2,6,QColor('black'))
        for cx,color in [(168,(220,85,68)),(181,(220,85,68)),(194,(51,153,204))]:
            painter.fillRect(ix+cx-4,iy+5,8,10,QColor(*color))
        for index in range(6):
            painter.fillRect(ix+6+33*index,iy+23,29,17,
                QColor(234,101,129) if index==tab else QColor(180,180,180))
        if not header:painter.fillRect(ix+4,iy+21,33,21,QColor(40,40,70))
        for x,height,name,visible,is_primary in [
            (1024,270,primary_name,primary,True),
            (1263,240,single_name,comparison,False)]:
            if not visible:continue
            painter.fillRect(x,180,236,height,QColor(30,30,70))
            painter.fillRect(x+1,180,1,height,QColor(190,190,205))
            painter.fillRect(x+234,180,1,height,QColor(190,190,205))
            painter.fillRect(x,181,236,1,QColor(190,190,205))
            if marker or not is_primary:
                for y in range(5):
                    for dx in range(5):
                        if abs(dx-2)+abs(y-2)<=2:
                            painter.fillRect(x+9+dx,195+y,1,1,QColor(85,204,255))
            if title or not is_primary:
                painter.setPen(QColor(240,240,240));painter.drawText(x+17,203,name)
        if shop:
            painter.drawImage(20,500,QImage(str(ROOT/'vendor/minerva/samples/player-shop/ideal-ratio-weapons-and-a-robe.png')))
        painter.end();return image

    def read(self,images,*,pointer=(1378,152),annotations=(),inventory_only=False,progressive=False):
        if isinstance(images,QImage):images=[images]
        with tempfile.TemporaryDirectory(prefix='lupin-generated-inventory-') as directory:
            requests=[]
            for index,image in enumerate(images):
                path=Path(directory)/f'{index}.png';self.assertTrue(image.save(str(path)))
                requests.append(dict(path=str(path),at_ms=index,tooltip=True,tooltip_retry=True,
                    inventory_only=inventory_only,progressive_tooltip=progressive,progressive_shop=progressive,
                    pointer=dict(zip(('x','y'),pointer)),
                    annotations=[dict(zip(('x','y','width','height'),rect.getRect())) for rect in annotations]))
            result=subprocess.run([str(BINARY)],input=''.join(json.dumps(r)+'\n' for r in requests),
                text=True,capture_output=True,check=True,timeout=30,
                env={**os.environ,'RAYON_NUM_THREADS':'2'})
        values=[json.loads(line) for line in result.stdout.splitlines()]
        if not progressive:self.assertEqual(len(values),len(images))
        else:self.assertGreaterEqual(len(values),len(images))
        self.assertTrue(all('error' not in value for value in values),values)
        return values

    def test_inventory_probe_keeps_primary_identity_and_only_one_partial_phase(self):
        values=self.read(self.frame(shop=True),inventory_only=True,progressive=True)
        self.assertEqual(len(values),2)
        self.assertTrue(values[0]['tooltipPartial']);self.assertTrue(values[0]['shopDeferred'])
        for value in values:
            self.assertEqual(value['tooltipAssociation']['state'],'inventory-primary')
            self.assertEqual(value['tooltip']['found']['name'],'Emerald Staff')
            self.assertFalse(value.get('shopPartial',False))
            self.assertFalse(value['inventoryProbe']['absent'])

    def test_shop_probe_cannot_promote_an_unbound_description_to_inventory(self):
        result=self.read(self.frame(primary=False,shop=True),pointer=(1250,150),inventory_only=True)[0]
        self.assertEqual(result['tooltip'],'none')
        self.assertTrue(result['inventoryProbe']['absent'])
        self.assertIsNotNone(result['shop'])

    def test_delayed_description_does_not_become_a_permanent_negative_source(self):
        before,after=self.read([self.frame(primary=False,comparison=False),self.frame()],inventory_only=True)
        self.assertEqual(before['tooltip'],'none');self.assertFalse(before['inventoryProbe']['absent'])
        self.assertEqual(after['tooltip']['found']['name'],'Emerald Staff')

    def test_cold_primary_marker_loss_reads_current_primary_letters_with_and_without_shop(self):
        for shop in (False,True):
            with self.subTest(shop=shop):
                result=self.read(self.frame(marker=False,shop=shop))[0]
                self.assertEqual(result['tooltipAssociation']['state'],'inventory-primary')
                self.assertEqual(result['tooltip']['found']['name'],'Emerald Staff')
                self.assertLess(result['tooltip']['found']['area']['x'],1263)
                if shop:self.assertIsNotNone(result['shop'])

    def test_cold_obscured_source_header_never_prices_the_equipped_comparison(self):
        for marker in (False,True):
            with self.subTest(marker=marker):
                result=self.read(self.frame(header=False,marker=marker))[0]
                self.assertEqual(result['tooltipAssociation']['state'],'rejected')
                self.assertEqual(result['tooltip'],'none')

    def test_partly_hidden_primary_marker_does_not_change_the_item_role(self):
        for covered in (1,2,4):
            with self.subTest(covered=covered):
                image=self.frame();painter=QPainter(image)
                painter.fillRect(1033,195,covered,5,QColor(30,30,70));painter.end()
                result=self.read(image)[0]
                self.assertEqual(result['tooltipAssociation']['state'],'inventory-primary')
                self.assertEqual(result['tooltip']['found']['name'],'Emerald Staff')

    def test_marker_and_cap_loss_keeps_ambiguous_bodies_out_of_generic_ocr(self):
        image=self.frame(marker=False);painter=QPainter(image)
        for x in (1024,1263):painter.fillRect(x,180,236,3,QColor(30,30,70))
        painter.end();result=self.read(image)[0]
        self.assertEqual(result['tooltipAssociation']['state'],'rejected')
        self.assertEqual(result['tooltip'],'none')

    def test_marker_and_primary_title_loss_never_borrows_a_previous_name(self):
        before,after=self.read([self.frame(),self.frame(marker=False,title=False)])
        self.assertEqual(before['tooltip']['found']['name'],'Emerald Staff')
        self.assertEqual(after['tooltip'],'none')

    def test_a_genuine_single_equipped_item_remains_readable_with_a_shop_open(self):
        result=self.read(self.frame(primary=False,shop=True),pointer=(1250,150))[0]
        self.assertEqual(result['tooltipAssociation']['state'],'normal')
        self.assertEqual(result['tooltip']['found']['name'],'Mithril Pole Arm')
        self.assertIsNotNone(result['shop'])

    def test_a_single_remote_linked_item_keeps_its_existing_pixel_only_path(self):
        result=self.read(self.frame(comparison=False,shop=True),pointer=(20,50))[0]
        self.assertEqual(result['tooltip']['found']['name'],'Emerald Staff')
        self.assertTrue(result['tooltip']['found'].get('pinned'))

    def test_interior_rails_do_not_truncate_the_primary_or_comparison(self):
        image=self.frame(shop=True);p=QPainter(image)
        for x in (1194,1423):
            p.fillRect(x,184,3,224,QColor(45,45,80))
            p.fillRect(x+1,184,1,224,QColor(95,95,130))
        p.end();result=self.read(image)[0]
        self.assertEqual(result['tooltip']['found']['name'],'Emerald Staff')
        self.assertEqual(result['tooltipAssociation']['panel']['width'],236)
        self.assertEqual(result['tooltipAssociation']['comparison']['width'],236)
        from price_lens.tooltip_association import TooltipAssociation
        proof=TooltipAssociation.read(result['tooltipAssociation'],result['tooltip']['found'],image,pointer=(1378,152))
        self.assertIsNotNone(proof);self.assertTrue(proof.matches(image,(1378,152)))

    def test_owned_labels_do_not_erase_the_native_border_or_supply_an_item_title(self):
        from PySide6.QtCore import QRect
        from price_lens.tooltip_association import TooltipAssociation
        image=self.frame(shop=True)
        hidden=[QRect(1012,y,36,35) for y in (225,270,315,360,405)]
        p=QPainter(image)
        for rect in hidden:p.fillRect(rect,QColor('#171c26'))
        p.end();result=self.read(image,annotations=hidden)[0]
        self.assertEqual(result['tooltipAssociation']['state'],'inventory-primary')
        self.assertEqual(result['tooltip']['found']['name'],'Emerald Staff')
        proof=TooltipAssociation.read(result['tooltipAssociation'],result['tooltip']['found'],image,exclude=hidden)
        self.assertIsNotNone(proof);self.assertTrue(proof.matches(image,(1378,152),exclude=hidden))
        # Cover the native title with our own readable item name. The text may
        # not be promoted into this inventory cell's identity by OCR.
        title=QRect(1040,188,210,30);hidden.append(title);p=QPainter(image)
        p.fillRect(title,QColor('#171c26'));p.setFont(self.font);p.setPen(QColor('white'))
        p.drawText(1041,203,'Mithril Pole Arm');p.end()
        result=self.read(image,annotations=hidden)[0]
        self.assertFalse(isinstance(result['tooltip'],dict) and result['tooltip'].get('found',{}).get('name')=='Mithril Pole Arm')

    def test_new_item_tab_and_gold_rim_keep_the_same_independently_bound_primary(self):
        from price_lens.tooltip_association import TooltipAssociation
        image=self.frame();p=QPainter(image)
        for x,y,w,h in ((1372,137,32,1),(1372,168,32,1),(1372,137,1,32),(1403,137,1,32)):
            p.fillRect(x,y,w,h,QColor(255,153,0))
        p.end();after=image.copy();p=QPainter(after)
        p.setOpacity(.6);p.fillRect(1299,112,29,19,QColor('white'));p.setOpacity(1)
        for x,y,w,h in ((1372,137,32,1),(1372,168,32,1),(1372,137,1,32),(1403,137,1,32)):
            p.fillRect(x,y,w,h,QColor(255,221,0))
        p.end();results=self.read([image,after])
        for frame,result in zip((image,after),results):
            self.assertEqual(result['tooltipAssociation']['sourceTab'],0)
            proof=TooltipAssociation.read(result['tooltipAssociation'],result['tooltip']['found'],frame,pointer=(1378,152))
            self.assertIsNotNone(proof);self.assertIsNotNone(proof.header)
            self.assertTrue(proof.matches(image,(1378,152)));self.assertTrue(proof.matches(after,(1378,152)))
            changed=after.copy();changed.setPixelColor(1375,139,QColor('red'))
            self.assertFalse(proof.matches(changed,(1378,152)))

    def test_owner_line_is_separate_from_the_primary_item_title(self):
        image=self.frame(shop=True);p=QPainter(image);p.setFont(self.font)
        p.fillRect(1028,184,228,54,QColor(30,30,70))
        p.setPen(QColor(225,180,50));p.drawText(1090,203,"Owner's")
        for y in range(5):
            for dx in range(5):
                if abs(dx-2)+abs(y-2)<=2:p.fillRect(1033+dx,221+y,1,1,QColor(85,204,255))
        p.setPen(QColor(240,240,240));p.drawText(1041,229,'Emerald Staff');p.end()
        result=self.read(image)[0]
        self.assertEqual(result['tooltip']['found']['name'],'Emerald Staff')
        self.assertEqual(result['tooltipAssociation']['panel']['y'],180)
        self.assertGreaterEqual(result['tooltip']['found']['area']['y'],215)

    def test_single_inventory_items_have_current_slot_and_frame_proofs(self):
        image=self.frame(primary=False,shop=True);result=self.read(image)[0]
        association=result['tooltipAssociation']
        self.assertEqual(association['state'],'inventory-primary')
        self.assertEqual(association['version'],3);self.assertEqual(association['layout'],'single')
        self.assertIsNone(association['comparison'])
        self.assertEqual(result['tooltip']['found']['name'],'Mithril Pole Arm')
        from price_lens.tooltip_association import TooltipAssociation
        proof=TooltipAssociation.read(association,result['tooltip']['found'],image,pointer=(1378,152))
        self.assertIsNotNone(proof);self.assertTrue(proof.matches(image,(1378,152)))

    def test_single_items_bind_on_every_inventory_tab_with_or_without_a_shop(self):
        from price_lens.tooltip_association import TooltipAssociation
        for tab,name in enumerate(('Emerald Staff','Red Potion','Relaxer','Bronze Ore','Power Elixir','White Potion')):
            for shop in (False,True):
                with self.subTest(tab=tab,shop=shop):
                    image=self.frame(primary=False,tab=tab,single_name=name,shop=shop)
                    values=self.read(image,inventory_only=shop,progressive=True)
                    for result in values:
                        self.assertEqual(result['tooltipAssociation']['state'],'inventory-primary')
                        self.assertEqual(result['tooltipAssociation']['sourceTab'],tab)
                        self.assertEqual(result['tooltipAssociation']['layout'],'single')
                        self.assertEqual(result['tooltip']['found']['name'],name)
                        proof=TooltipAssociation.read(result['tooltipAssociation'],result['tooltip']['found'],image,pointer=(1378,152))
                        self.assertIsNotNone(proof);self.assertTrue(proof.matches(image,(1378,152)))
                    if shop:
                        self.assertTrue(values[0]['tooltipPartial']);self.assertFalse(values[0]['inventoryProbe']['absent'])

    def test_newly_supported_tabs_still_require_current_inventory_controls(self):
        for tab in (1,2,3,5):
            with self.subTest(tab=tab):
                good=self.frame(primary=False,tab=tab,single_name='Red Potion',shop=True)
                bad=good.copy();painter=QPainter(bad)
                painter.fillRect(1293+190,95,8,10,QColor('#283749'));painter.end()
                before,after=self.read([good,bad],inventory_only=True)
                self.assertEqual(before['tooltipAssociation']['state'],'inventory-primary')
                self.assertNotEqual(after['tooltipAssociation']['state'],'inventory-primary')
                self.assertEqual(after['tooltip'],'none')

    def test_marker_title_cache_reuses_only_complete_current_ink_and_rebases_its_area(self):
        from PySide6.QtCore import QPoint,QRect
        original=self.frame(primary=False,tab=1,single_name='Red Potion')
        background=original.copy();p=QPainter(background)
        p.fillRect(1468,187,18,18,QColor(45,40,80));p.end()
        moved=original.copy();p=QPainter(moved);pane=QRect(1263,180,236,240)
        p.fillRect(pane,QColor('#142314'));p.drawImage(pane.topLeft()+QPoint(-2,3),original.copy(pane));p.end()
        other=self.frame(primary=False,tab=1,single_name='White Potion')
        bad=original.copy();p=QPainter(bad);p.fillRect(1483,95,8,10,QColor('#283749'));p.end()
        values=self.read([original,background,moved,other,original,bad],inventory_only=True)
        for index,name in enumerate(('Red Potion','Red Potion','Red Potion','White Potion','Red Potion')):
            self.assertEqual(values[index]['tooltip']['found']['name'],name)
        self.assertEqual([v.get('tooltipCacheHit',False) for v in values],[False,True,True,False,True,False])
        old=values[0]['tooltip']['found']['area'];new=values[2]['tooltip']['found']['area']
        self.assertEqual(new,{**old,'x':old['x']-2,'y':old['y']+3})
        self.assertEqual(values[-1]['tooltip'],'none')

    def test_scaled_native_pair_proofs_are_accepted_by_the_frontend(self):
        from price_lens.tooltip_association import TooltipAssociation
        original=self.frame()
        for scale in (1.25,1.5,2.0):
            with self.subTest(scale=scale):
                image=original.scaled(round(original.width()*scale),round(original.height()*scale),
                    Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.SmoothTransformation)
                pointer=(round(1378*scale),round(152*scale));result=self.read(image,pointer=pointer)[0]
                self.assertEqual(result['tooltipAssociation']['state'],'inventory-primary')
                self.assertIsInstance(result.get('tooltip'),dict)
                proof=TooltipAssociation.read(result['tooltipAssociation'],result['tooltip']['found'],image,pointer=pointer)
                self.assertIsNotNone(proof);self.assertTrue(proof.matches(image,pointer))


if __name__=='__main__':unittest.main()

"""Native NPC structure and routing, independent of any live capture state."""
from pathlib import Path
import unittest

from PySide6.QtCore import QRect,Qt
from PySide6.QtGui import QColor,QImage,QPainter

from price_lens.npc_shop import find_npc_shop,suppress_npc_prices


class NpcShopTests(unittest.TestCase):
    def overlapping_inventory(self):
        from test_tooltip_association import TooltipAssociationTests
        from test_inventory_pixels import header
        from price_lens.tooltip_association import TooltipAssociation
        raw,value,found=TooltipAssociationTests().v3()
        image=QImage(1300,1100,QImage.Format.Format_RGBA8888);image.fill(QColor('#4a5430'))
        painter=QPainter(image);painter.drawImage(450,0,self.example())
        for key in ('source','panel','comparison'):
            area=value[key];rect=QRect(*(area[k] for k in ('x','y','width','height')))
            painter.drawImage(rect.x(),rect.y()+300,raw.copy(rect))
        rgb=header();heading=QImage(rgb.tobytes(),207,45,207*3,QImage.Format.Format_RGB888).copy()
        painter.drawImage(600,380,heading);painter.end()
        def shifted(rect):return {**rect,'y':rect['y']+300}
        value={**value,'sourceTab':0,**{key:shifted(value[key]) for key in ('source','slot','panel','comparison','cursor','pointer')},
               'guards':[shifted(rect) for rect in value['guards']]}
        found={**found,'area':shifted(found['area'])};pointer=(627,440)
        proof=TooltipAssociation.read(value,found,image,pointer=pointer)
        self.assertIsNotNone(proof);self.assertIsNotNone(proof.header)
        self.assertTrue(proof.matches(image,pointer))
        return image,value,found,pointer,proof

    def example(self,scale=1):
        image=QImage(800,600,QImage.Format.Format_RGBA8888);image.fill(QColor('#223344'))
        painter=QPainter(image)
        painter.fillRect(95,100,462,376,QColor('#e0e0d8'))
        for x in (250,480):painter.fillRect(x,134,66,14,QColor('#ed983a'))
        painter.fillRect(250,114,66,14,QColor('#94be33'))
        painter.fillRect(456,165,90,12,QColor('white'))
        painter.fillRect(104,216,444,3,QColor('#c40000'))
        painter.fillRect(105,197,48,16,QColor('#e96680'))
        painter.fillRect(335,197,35,16,QColor('#e96680'))
        for x,w in ((208,98),(436,100)):painter.fillRect(x,108,w,3,QColor('#b6b6b6'))
        painter.end()
        if scale!=1:image=image.scaled(round(800*scale),round(600*scale),Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.FastTransformation)
        return image

    def test_empty_lists_and_each_native_scale_are_excluded(self):
        for scale in (.75,1,1.25,1.5,2):
            with self.subTest(scale=scale):
                image=self.example(scale);npc=find_npc_shop(image)
                self.assertIsNotNone(npc)
                self.assertTrue(npc.matches(image))
                self.assertTrue(npc.contains((round(145*scale),round(265*scale))))

    def test_all_buy_back_and_right_tab_transitions_keep_the_same_npc(self):
        original=self.example();npc=find_npc_shop(original)
        for left in ('All','Buy Back'):
            for right in range(4):
                for populated in (False,True):
                    with self.subTest(left=left,right=right,populated=populated):
                        image=original.copy();painter=QPainter(image)
                        painter.fillRect(105,197,106,16,QColor('#b6b6b6'))
                        painter.fillRect(105 if left=='All' else 157,197,48,16,QColor('#e96680'))
                        painter.fillRect(335,197,172,16,QColor('#b6b6b6'))
                        painter.fillRect(335+right*42,197,35,16,QColor('#e96680'))
                        if populated:
                            painter.fillRect(330,230,207,230,QColor('#cad5df'))
                            painter.fillRect(370,235,70,7,QColor('black'))
                        painter.end()
                        self.assertTrue(npc.matches(image))
                        self.assertIsNotNone(find_npc_shop(image))

    def test_either_column_can_locate_the_complete_npc_window(self):
        image=self.example()
        for x in (100,330):
            with self.subTest(column=x):
                self.assertIsNotNone(find_npc_shop(image,near=QRect(x,230,199,230)))

    def test_unrelated_orange_scenery_cannot_merge_native_button_rows(self):
        image=self.example();painter=QPainter(image)
        painter.fillRect(600,130,120,41,QColor('#ed983a'));painter.end()
        self.assertIsNotNone(find_npc_shop(image))

    def test_each_independent_control_is_required_and_our_paint_cannot_supply_it(self):
        for rect in (QRect(250,114,66,14),QRect(480,134,66,14),QRect(104,216,444,3),
                     QRect(456,165,90,12),QRect(105,197,204,16),QRect(335,197,172,16),QRect(436,108,100,3)):
            with self.subTest(rect=rect.getRect()):
                image=self.example();painter=QPainter(image);painter.fillRect(rect,QColor('#223344'));painter.end()
                self.assertIsNone(find_npc_shop(image))
                self.assertIsNone(find_npc_shop(self.example(),exclude=(rect,)))

    def test_static_guard_excludes_wallet_numbers_and_list_animations(self):
        image=self.example();npc=find_npc_shop(image)
        changed=image.copy();painter=QPainter(changed)
        painter.fillRect(470,168,60,6,QColor('black'))
        painter.fillRect(100,230,450,230,QColor('#fbab2e'));painter.end()
        self.assertTrue(npc.matches(changed))
        painter=QPainter(changed);painter.fillRect(250,114,66,14,QColor('black'));painter.end()
        self.assertFalse(npc.matches(changed))
        self.assertEqual(npc.state(changed),'unknown')
        changed.fill(QColor('#223344'));self.assertEqual(npc.state(changed),'absent')

    def test_buy_and_sell_lists_and_native_list_tooltips_never_become_prices(self):
        npc=find_npc_shop(self.example())
        for x in (100,330):
            result=dict(shop=dict(area=dict(x=x,y=230,width=199,height=230),rows=[dict(name='Orange Potion')]),
                hover=dict(tooltip=dict(found=dict(name='Orange Potion'))),
                tooltip=dict(found=dict(name='Orange Potion')))
            filtered=suppress_npc_prices(result,npc,(x+50,250))
            self.assertIsNone(filtered['shop']);self.assertIsNone(filtered['hover'])
            self.assertIsNone(filtered['tooltip'])
            self.assertEqual(filtered['tooltipAssociation'],dict(state='rejected'))
            self.assertIsNotNone(result['shop'],'Filtering cannot mutate the submitted reply')

    def test_independent_inventory_and_separate_player_shop_are_not_suppressed(self):
        npc=find_npc_shop(self.example())
        result=dict(shop=dict(area=dict(x=590,y=230,width=199,height=230),rows=[dict(name='Work Gloves')]),
            tooltip=dict(found=dict(name='Work Gloves')))
        self.assertEqual(suppress_npc_prices(result,npc,(650,250)),result)
        independent={**result,'tooltipAssociation':dict(state='inventory-primary')}
        self.assertEqual(suppress_npc_prices(independent,npc,(650,250)),independent)
        self.assertIsNone(suppress_npc_prices(independent,npc,(360,250))['tooltip'],
            'A raw association flag cannot identify an ordinary inventory window')

    def test_player_shop_public_captures_are_never_npc_classified(self):
        samples=Path(__file__).resolve().parents[1]/'vendor/minerva/samples/player-shop'
        for path in samples.glob('*.png'):
            with self.subTest(image=path.name):self.assertIsNone(find_npc_shop(QImage(str(path))))

    def test_verified_inventory_can_overlap_npc_without_becoming_its_sell_list(self):
        image,value,found,pointer,proof=self.overlapping_inventory()
        npc=find_npc_shop(image,near=QRect(550,230,199,230))
        self.assertIsNotNone(npc);self.assertTrue(npc.contains(pointer))
        result=dict(tooltipAssociation=value,tooltip=dict(found=found))
        self.assertEqual(suppress_npc_prices(result,npc,pointer,inventory=proof),result)
        self.assertIsNone(suppress_npc_prices(result,npc,pointer)['tooltip'])

    def test_unknown_is_not_initial_proof_and_closure_releases_the_exclusion(self):
        image=self.example();npc=find_npc_shop(image)
        masks=(QRect(250,114,66,14),)
        self.assertEqual(npc.state(image,masks),'unknown')
        self.assertIsNone(find_npc_shop(image,exclude=masks))
        image.fill(QColor('#223344'))
        self.assertEqual(npc.state(image),'absent')


if __name__=='__main__':unittest.main()

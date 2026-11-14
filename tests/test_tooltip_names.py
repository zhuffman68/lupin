"""Independent OCR must agree on one catalog ID; no nearest-name guessing."""
import unittest
import hashlib
from itertools import product
import numpy as np
from PySide6.QtCore import QRect
from PySide6.QtGui import QImage,QColor
from price_lens.domain import Catalog
from price_lens.tooltip_names import TooltipNames,roles_agree,name_key
from price_lens.domain import Item


class TooltipNameTests(unittest.TestCase):
    @staticmethod
    def original_key(found,image):
        area=found['area'];rect=QRect(*(area[k] for k in ('x','y','width','height')))
        patch=image.copy(rect).convertToFormat(QImage.Format.Format_RGBA8888)
        pixels=bytes(patch.constBits());mask=bytearray()
        for r,g,b,a in zip(pixels[0::4],pixels[1::4],pixels[2::4],pixels[3::4]):
            neutral=r>=150 and abs(r-g)<55 and b-r<100
            coloured=max(r,g,b)>=150 and max(r,g,b)-min(r,g,b)>45
            mask.append(1 if neutral or coloured else 0)
        return found.get('name'),found.get('tier'),rect.width(),rect.height(),hashlib.blake2b(mask,digest_size=12).digest()

    def test_name_masks_match_the_original_at_colour_boundaries_and_for_all_alpha_values(self):
        levels=(0,1,45,46,54,55,99,100,149,150,151,204,205,249,250,255)
        colors=np.array(list(product(levels,repeat=3)),dtype=np.uint8)
        rgba=np.empty((32,128,4),dtype=np.uint8);rgba[:,:,:3]=colors.reshape(32,128,3)
        rgba[:,:,3]=np.arange(4096,dtype=np.uint16).reshape(32,128)%256
        image=QImage(rgba.tobytes(),128,32,128*4,QImage.Format.Format_RGBA8888).copy()
        found=dict(name='Unresolved title',tier='Greater',area=dict(x=0,y=0,width=128,height=32))
        self.assertEqual(name_key(found,image),self.original_key(found,image))

    def test_name_masks_match_on_offset_titles_padded_rgb_rows_and_maximum_width(self):
        rng=np.random.default_rng(907)
        rgb=rng.integers(0,256,(38,731,3),dtype=np.uint8)
        image=QImage(rgb.tobytes(),731,38,731*3,QImage.Format.Format_RGB888).copy()
        for fmt in (QImage.Format.Format_RGB888,QImage.Format.Format_ARGB32_Premultiplied,QImage.Format.Format_RGBA8888):
            frame=image.convertToFormat(fmt)
            for width,height in ((40,8),(151,13),(720,32)):
                with self.subTest(format=fmt,width=width,height=height):
                    found=dict(name='Unknown',area=dict(x=7,y=3,width=width,height=height))
                    self.assertEqual(name_key(found,frame),self.original_key(found,frame))

    def test_name_mask_bounds_and_non_title_changes_keep_the_original_contract(self):
        before=name_key(self.found,self.image)
        changed=self.image.copy();changed.setPixelColor(0,0,QColor('white'))
        self.assertEqual(name_key(self.found,changed),before)
        for width,height in ((39,14),(721,14),(150,7),(150,33)):
            found={**self.found,'area':dict(x=0,y=0,width=width,height=height)}
            self.assertIsNone(name_key(found,self.image))

    def setUp(self):
        self.catalog=Catalog({'items':[{'id':1,'name':'Leaf Earrings','category':'Equipment'},
            {'id':2,'name':'Old Raggedy Cape','category':'Equipment'},
            {'id':3,'name':'Blue Cape','category':'Equipment'}]})
        self.image=QImage(300,100,QImage.Format.Format_RGBA8888);self.image.fill(QColor('#403b6c'))
        self.image.setPixelColor(40,20,QColor('white'))
        self.found={'area':{'x':20,'y':10,'width':150,'height':14},'name':'Leaf Earrins'}
        self.names=TooltipNames()

    def test_exact_second_read_is_reused_only_with_matching_name_pixels(self):
        corrected=self.names.resolve({**self.found,'alternatives':['Leaf Earrings','Leat Earinte']},self.image,self.catalog)
        self.assertEqual(corrected['name'],'Leaf Earrings')
        self.assertEqual(self.names.resolve(self.found,self.image,self.catalog)['name'],'Leaf Earrings')
        self.image.setPixelColor(45,20,QColor('white'))
        self.assertEqual(self.names.resolve(self.found,self.image,self.catalog)['name'],'Leaf Earrins')

    def test_competing_ids_or_no_exact_read_remain_unknown(self):
        for alternatives in (['Leaf Earrings','Blue Cape'],['Leaf Earring'],['Old Raqqedy Cape']):
            found={**self.found,'alternatives':alternatives}
            self.assertEqual(self.names.resolve(found,self.image,self.catalog)['name'],'Leaf Earrins')

    def test_upgrade_count_is_removed_only_for_a_unique_equipment_name(self):
        found={**self.found,'name':'Leaf Earrings (+3)'}
        resolved=self.names.resolve(found,self.image,self.catalog)
        self.assertEqual(resolved['name'],'Leaf Earrings');self.assertEqual(resolved['raw_name'],found['name'])
        catalog=Catalog({'items':[{'id':1,'name':'Screw','category':'Etc'},
            {'id':2,'name':'Cape','category':'Equipment'},{'id':3,'name':'Cape','category':'Equipment'},
            {'id':4,'name':'Leaf Earrings (+3)','category':'Equipment'}]})
        for name in ('Screw (+3)','Cape (+3)','Leaf Earrings (+3)','Leaf Earrings (M)','Leaf Earrings 10%'):
            self.assertEqual(self.names.resolve({**self.found,'name':name},self.image,catalog)['name'],name)

    def test_independent_second_read_can_identify_a_scrolled_title_and_coloured_pixels_invalidate_the_cache(self):
        found={**self.found,'name':'Leaf Earrins (+3)','alternatives':['Leaf Earrings (+3)']}
        result=self.names.resolve(found,self.image,self.catalog)
        self.assertEqual(result['name'],'Leaf Earrings');self.assertEqual(result['raw_name'],'Leaf Earrings (+3)')
        original={**found,'alternatives':[]};self.assertEqual(self.names.resolve(original,self.image,self.catalog)['name'],'Leaf Earrings')
        self.image.setPixelColor(48,20,QColor('#ff9900'))
        self.assertEqual(self.names.resolve(original,self.image,self.catalog)['name'],original['name'])

    def test_second_pass_cannot_change_explicit_stat_tier_color_or_gender(self):
        item=Item(1,'Test',equipment=True,gender='male')
        for before,after in [('Overall DEX Sorol: Greater','Overall LUK Scroll: Greater'),
                             ('Overall DEX Sorol: Greater','Overall DEX Scroll: Lesser'),
                             ('Glove ATK 10%','Glove ATK 60%'),('Red Shlrt','Blue Shirt')]:
            self.assertFalse(roles_agree(before,after,item))
        self.assertFalse(roles_agree('Test Shlrt (F)','Test Shirt',item))
        self.assertTrue(roles_agree('Test Shlrt (M)','Test Shirt',item))

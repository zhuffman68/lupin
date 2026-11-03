"""New-item animation must not loosen item, tab or control identity."""
import unittest
from math import floor

import numpy as np
from PySide6.QtCore import QRect,Qt
from PySide6.QtGui import QRegion,QImage

from price_lens.inventory_pixels import same_header,same_cell,tab_bounds


def header(width=207,tab=0):
    rgb=np.full((floor(45*width/207+.5),width,3),245,dtype=np.uint8)
    rgb[5:13,12:14]=0;rgb[5:13,width-20:width-15]=(51,153,204)
    rect=tab_bounds(width,rgb.shape[0],tab).adjusted(1,1,-1,-1)
    rgb[rect.top():rect.bottom()+1,rect.left():rect.right()+1]=(234,101,129)
    rgb[rect.top()+3:rect.top()+8,rect.left()+5:rect.left()+7]=255
    rgb[rect.top()+4:rect.top()+9,rect.left()+9:rect.left()+11]=(173,104,118)
    return rgb


def pulse(rgb,tab=0):
    new=rgb.copy();rect=tab_bounds(rgb.shape[1],rgb.shape[0],tab).adjusted(1,1,-1,-1)
    key=np.s_[rect.top():rect.bottom()+1,rect.left():rect.right()+1]
    retained=np.linspace(.34,.8,rect.height())[:,None,None]
    new[key]=np.rint(255-(255-rgb[key].astype(float))*retained).astype(np.uint8)
    return new


class InventoryPixelsTests(unittest.TestCase):
    def test_scaled_sprite_and_rounded_corner_antialiasing_keep_the_same_pulse(self):
        before=header();after=pulse(before)
        before[:2,:2]=(20,80,90);after[:2,:2]=(70,120,100)
        before[:2,-2:]=(30,65,100);after[:2,-2:]=(60,80,120)
        def scaled(rgb,width):
            image=QImage(rgb.tobytes(),207,45,207*3,QImage.Format.Format_RGB888)
            image=image.scaled(width,floor(45*width/207+.5),Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation).convertToFormat(QImage.Format.Format_RGBA8888)
            return np.frombuffer(image.constBits(),np.uint8).copy().reshape(image.height(),image.width(),4)[:,:,:3]
        for width in (155,207,259,311,414):
            self.assertTrue(same_header(scaled(before,width),scaled(after,width),0),width)

    def test_pulse_preserves_tab_shape_in_both_directions_at_supported_scales(self):
        for width in (155,207,259,311,414):
            for tab in (0,4):
                before=header(width,tab);after=pulse(before,tab)
                self.assertTrue(same_header(before,after,tab),(width,tab))
                self.assertTrue(same_header(after,before,tab),(width,tab))

    def test_changed_caption_controls_other_tabs_and_selected_letters_fail(self):
        before=header();after=pulse(before)
        for y,x in ((7,12),(7,188),(28,45),(26,11)):
            bad=after.copy();bad[y,x]=(10,240,20)
            self.assertFalse(same_header(before,bad,0),(x,y))
        blank=after.copy();rect=tab_bounds(207,45,0)
        blank[rect.top():rect.bottom()+1,rect.left():rect.right()+1]=255
        self.assertFalse(same_header(before,blank,0))
        self.assertFalse(same_header(before,header(tab=4),0))
        for tab in (-1,6,True,None):self.assertFalse(same_header(before,after,tab))

    def test_whole_header_occluders_and_shape_changes_are_not_white_pulses(self):
        before=header();after=pulse(before)
        shifted=after.copy();rect=tab_bounds(207,45,0)
        shifted[rect.top():rect.bottom()+1,rect.left():rect.right()+1]=np.roll(
            shifted[rect.top():rect.bottom()+1,rect.left():rect.right()+1],3,axis=1)
        self.assertFalse(same_header(before,shifted,0))
        self.assertFalse(same_header(before,np.full_like(before,255),0))

    def cell(self):
        rgba=np.full((32,32,4),255,np.uint8);rgba[:,:,:3]=(222,222,213)
        rgba[4:25,4:18,:3]=(75,80,95)
        rgba[0,:,:3]=(255,153,0);rgba[-1,:,:3]=(255,153,0)
        rgba[:,0,:3]=(255,153,0);rgba[:,-1,:3]=(255,153,0)
        return rgba

    def test_gold_rim_pulses_but_exposed_icon_and_non_gold_rim_stay_exact(self):
        old=self.cell();new=old.copy()
        new[0,:,1]=221;new[:,0,1]=187;visible=QRegion(QRect(0,0,32,32)).subtracted(QRegion(QRect(12,10,32,37)))
        check=lambda a,b:same_cell(a.tobytes(),b.tobytes(),32,32,visible,1)
        self.assertTrue(check(old,new))
        for y,x in ((4,4),(0,2),(5,0)):
            bad=new.copy();bad[y,x]=(255,10,20,255)
            self.assertFalse(check(old,bad),(x,y))
        # Border paint cannot be the only source evidence, even on an exact frame.
        rim_only=QRegion(QRect(0,0,32,32)).subtracted(QRegion(QRect(1,1,30,30)))
        self.assertFalse(same_cell(old.tobytes(),old.tobytes(),32,32,rim_only,1))

    def highlighted_cap(self):
        old=self.cell();new=old.copy()
        old[0,:,:3]=(246,247,231);new[0,:,:3]=(253,158,49)
        old[1,:,:3]=(255,153,0);new[1,:,:3]=(255,204,0)
        # The native rim also blends across an icon tip at the very edge.
        old[0,25,:3]=(102,95,0);new[0,25,:3]=(204,109,0)
        old[0,28,:3]=(136,118,0);new[0,28,:3]=(34,34,0)
        return old,new

    def test_inset_gold_scanline_proves_the_animated_cap_and_blended_fringe(self):
        old,new=self.highlighted_cap()
        for first,second in ((old,new),(new,old)):
            visible=QRegion(QRect(0,0,32,32)).subtracted(QRegion(QRect(2,18,32,37)))
            self.assertTrue(same_cell(first.tobytes(),second.tobytes(),32,32,visible,1))

    def test_animated_cap_keeps_exact_icon_evidence_at_fractional_and_double_scales(self):
        old,new=self.highlighted_cap()
        for size in (24,32,40,48,64):
            def resize(rgba):
                image=QImage(rgba.tobytes(),32,32,128,QImage.Format.Format_RGBA8888)
                image=image.scaled(size,size,Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.FastTransformation).convertToFormat(QImage.Format.Format_RGBA8888)
                return bytes(image.constBits())
            a,b=resize(old),resize(new);visible=QRegion(QRect(0,0,size,size))
            self.assertTrue(same_cell(a,b,size,size,visible,size/32),size)
            bad=bytearray(b);position=(size//2*size+size//2)*4;bad[position:position+4]=b'\x00\xff\x00\xff'
            self.assertFalse(same_cell(a,bytes(bad),size,size,visible,size/32),size)

    def test_fringe_colours_without_an_exposed_native_gold_scanline_are_not_enough(self):
        old,new=self.highlighted_cap();shown=QRegion(QRect(0,0,32,32))
        for keep in (0,5):
            first,second=old.copy(),new.copy()
            first[1,:,:3]=second[1,:,:3]=(222,222,213)
            first[1,:keep,:3]=second[1,:keep,:3]=(255,153,0)
            self.assertFalse(same_cell(first.tobytes(),second.tobytes(),32,32,shown,1))
        hidden=shown.subtracted(QRegion(QRect(0,1,32,1)))
        self.assertFalse(same_cell(old.tobytes(),new.tobytes(),32,32,hidden,1))

    def test_gold_cap_cannot_hide_changed_icon_ink_foreign_paint_or_alpha(self):
        old,new=self.highlighted_cap();visible=QRegion(QRect(0,0,32,32))
        for y,x,color in ((0,7,(0,255,0,255)),(0,7,(220,240,255,255)),(1,7,(255,10,20,255)),
                          (2,7,(255,204,0,255)),(12,9,(255,204,0,255)),
                          (0,7,(253,158,49,120))):
            bad=new.copy();bad[y,x]=color
            self.assertFalse(same_cell(old.tobytes(),bad.tobytes(),32,32,visible,1),(x,y,color))

"""Prepared source geometry cannot become a cross-frame or cross-request proof."""
from dataclasses import replace
import time
import unittest
from unittest.mock import patch
from PySide6.QtCore import QRect
from PySide6.QtGui import QColor,QImage
from price_lens.reader_request import SubmittedRequest
from price_lens.tooltip_geometry import PreparedBounds,prepare_bounds,description_bounds


class PreparedBoundsTests(unittest.TestCase):
    def setUp(self):
        self.image=QImage(800,600,QImage.Format.Format_RGBA8888);self.image.fill(QColor('#443366'))
        self.request=SubmittedRequest('prices',self.image,(100,250),0,1,time.monotonic())
        self.area=dict(x=110,y=190,width=140,height=14);self.bounds=QRect(100,180,200,250)
        self.prepared=PreparedBounds(self.request,QImage(self.image),(),((tuple(self.area.values()),self.bounds.getRect()),))

    def test_exact_source_and_request_return_independent_geometry_values(self):
        ready,bounds=self.prepared.lookup(self.request,QImage(self.image),self.area,())
        self.assertTrue(ready);self.assertEqual(bounds,self.bounds)
        bounds.translate(50,50)
        self.assertEqual(self.prepared.lookup(self.request,self.image,self.area,()),(True,self.bounds))

    def test_different_request_source_title_or_masks_require_fresh_discovery(self):
        changed=self.image.copy();changed.setPixelColor(799,599,QColor('white'))
        for request,image,area,masks in (
            (replace(self.request),self.image,self.area,()),
            (self.request,changed,self.area,()),
            (self.request,self.image,{**self.area,'x':111},()),
            (self.request,self.image,self.area,(QRect(400,400,20,20),)),
        ):
            self.assertEqual(self.prepared.lookup(request,image,area,masks),(False,None))

    def test_cropped_source_can_match_equal_pixels_without_borrowing_another_request(self):
        request=replace(self.request,crop=(30,40,400,300));source=request.source_image()
        prepared=PreparedBounds(request,source,(),self.prepared.entries)
        self.assertEqual(prepared.lookup(request,request.source_image(),self.area,()),(True,self.bounds))
        self.assertEqual(prepared.lookup(self.request,source,self.area,()),(False,None))

    def test_verified_missing_geometry_does_not_restart_discovery_on_the_gui(self):
        prepared=replace(self.prepared,entries=((tuple(self.area.values()),None),))
        with patch('price_lens.tooltip_geometry._framed_bounds',side_effect=AssertionError('Repeated source discovery')):
            self.assertIsNone(description_bounds(self.image,self.area,prepared=prepared,request=self.request))

    def test_preparation_is_bounded_and_deduplicates_titles_with_the_original_masks(self):
        request=replace(self.request,annotations=((10,20,30,40),))
        found=dict(name='Generated title',area=self.area)
        result=dict(tooltip=dict(found=found),hover=dict(tooltip=dict(found=found)))
        with patch('price_lens.tooltip_geometry.description_bounds',return_value=self.bounds) as discover:
            prepared=prepare_bounds(request,self.image,result)
            self.assertEqual(discover.call_count,1)
            self.assertEqual(discover.call_args.args[2],(QRect(10,20,30,40),))
            self.assertEqual(len(prepared.entries),1)
            for state in ('inventory-primary','rejected'):
                self.assertIsNone(prepare_bounds(request,self.image,{**result,'tooltipAssociation':dict(state=state)}))
            self.assertEqual(discover.call_count,1)

    def test_explicit_native_panel_uses_ordinary_validation_without_legacy_preparation(self):
        with patch('price_lens.tooltip_geometry.description_bounds',side_effect=AssertionError('Unneeded legacy geometry')):
            self.assertIsNone(prepare_bounds(self.request,self.image,dict(
                tooltip=dict(found=dict(name='Generated title',area=self.area)),tooltipPanel=dict(version=1))))

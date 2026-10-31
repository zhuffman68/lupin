"""Pure annotation placement: no QApplication, capture or desktop windows."""
import unittest
from PySide6.QtCore import QPoint,QRect
from price_lens.annotation_geometry import label_rectangle


class AnnotationGeometryTests(unittest.TestCase):
    def row(self,**extra):
        return dict(x=430,y=310,_width=230,kind='item',bounds=[0,0,800,600],**extra)

    def test_negative_monitor_origin_keeps_proof_footprints_in_local_coordinates(self):
        row=self.row(follow_pointer=[-1500,340],_cursor_offset=(10,10),pointer_region=[-1920,40,800,600],
            avoid_regions=[[420,290,260,100]])
        box=label_rectangle(row,QPoint(-1500,340),QRect(0,0,800,600),QPoint(-1920,40))
        self.assertIsNotNone(box);self.assertTrue(QRect(0,0,800,600).contains(box))
        self.assertFalse(box.intersects(QRect(*row['avoid_regions'][0])))

    def test_unplaceable_item_is_absent_instead_of_covering_its_source(self):
        row=self.row(avoid_regions=[[0,0,800,600]])
        self.assertIsNone(label_rectangle(row,QPoint(),QRect(0,0,800,600),QPoint()))

    def test_pointer_jump_still_invalidates_a_previously_safe_placement(self):
        row=self.row(follow_pointer=[400,300],_cursor_offset=(30,10),pointer_region=[0,0,800,600],
            avoid_regions=[[0,0,20,20]])
        self.assertIsNotNone(label_rectangle(row,QPoint(405,305),QRect(0,0,800,600),QPoint()))
        self.assertIsNone(label_rectangle(row,QPoint(470,305),QRect(0,0,800,600),QPoint()))

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

    def test_primary_description_wins_over_the_space_above_inventory(self):
        row=dict(x=904,y=278,_width=350,kind='item',bounds=[0,32,1383,798],
            description_box=[895,306,236,237],comparison_box=[1133,306,236,189],
            avoid_regions=[[1134,187,207,285],[895,306,236,237],[1133,306,236,189]])
        box=label_rectangle(row,QPoint(),QRect(0,0,1920,1080),QPoint())
        self.assertEqual(box.bottom(),297);self.assertGreater(box.top(),187)
        self.assertLessEqual(box.right(),1129)
        self.assertTrue(all(not box.intersects(QRect(*r)) for r in row['avoid_regions']))

    def test_description_near_the_top_uses_an_adjacent_safe_fallback(self):
        row=dict(x=420,y=40,_width=230,kind='item',bounds=[0,0,800,600],
            description_box=[400,35,236,300],avoid_regions=[[400,35,236,300]])
        box=label_rectangle(row,QPoint(),QRect(0,0,800,600),QPoint())
        self.assertIsNotNone(box);self.assertFalse(box.intersects(QRect(*row['description_box'])))
        self.assertGreaterEqual(box.y(),35);self.assertLess(box.right(),400)

    def test_primary_anchor_follows_pointer_without_moving_inventory_protection(self):
        row=dict(x=410,y=300,_width=230,kind='item',bounds=[0,0,900,700],
            description_box=[400,350,236,260],avoid_regions=[[650,100,207,285],[400,350,236,260]],
            follow_pointer=[650,330],_cursor_offset=(-240,-30),pointer_region=[0,0,900,700])
        a=label_rectangle(row,QPoint(650,330),QRect(0,0,900,700),QPoint())
        b=label_rectangle(row,QPoint(655,334),QRect(0,0,900,700),QPoint())
        self.assertEqual((b.x()-a.x(),b.y()-a.y()),(5,4))

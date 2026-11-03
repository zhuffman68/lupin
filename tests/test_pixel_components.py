import unittest
import numpy as np
from price_lens.pixel_components import colour_components


class PixelComponentTests(unittest.TestCase):
    def test_separate_controls_keep_their_boxes_at_the_same_vertical_position(self):
        mask=np.zeros((80,300),bool);mask[10:24,10:76]=True;mask[10:24,230:296]=True
        mask[1:50,110:180]=True
        self.assertEqual(sorted(colour_components(mask)),[[10,10,75,23],[110,1,179,49],[230,10,295,23]])

    def test_fragments_join_transitively_and_pathological_work_is_bounded(self):
        mask=np.zeros((6,12),bool);mask[0,:3]=True;mask[0,6:9]=True;mask[1,:9]=True
        self.assertEqual(colour_components(mask),[[0,0,8,1]])
        self.assertEqual(colour_components(np.eye(20,dtype=bool),max_runs=10),[])


if __name__=='__main__':unittest.main()

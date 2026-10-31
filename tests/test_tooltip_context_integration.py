"""Native v2 description proofs through the UI, with captured fixtures only."""
from copy import deepcopy
import time
import unittest

from PySide6.QtCore import QRect
from PySide6.QtGui import QColor,QImage,QPainter

import test_ui_context as ui_fixtures


class TooltipContextIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ui_fixtures.ContextUiTests.setUpClass()

    def setUp(self):
        self.fixture=ui_fixtures.ContextUiTests(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.addCleanup(self.fixture.tearDown)
        self.window=self.fixture.window
        geometry=self.window.screens[self.window.screen_index].geometry()
        dpr=self.window.screens[self.window.screen_index].devicePixelRatio()
        self.size=(round(geometry.width()*dpr),round(geometry.height()*dpr))
        self.window.reader.shop_context=None
        self.window.reader.pointer=(340,190)
        self.window.reader.image=self.frame()
        self.window.reader.submitted_image=self.window.reader.image.copy()
        self.window.reader.game_area=self.window.reader.image.rect()

    def frame(self,point=(340,190),offset=(0,0)):
        image=QImage(*self.size,QImage.Format.Format_RGBA8888);image.fill(QColor('#24384b'))
        painter=QPainter(image)
        painter.fillRect(point[0]+offset[0],point[1]+offset[1],8,12,QColor('white'))
        painter.end();return image

    def reading(self):
        return {'atMs':int(time.monotonic()*1000),'shop':None,'hover':None,
                'pointerAtRead':[340,190],
                'tooltip':{'found':{'name':'Example Hat','area':dict(x=58,y=231,width=180,height=12)}},
                'tooltipAssociation':{'state':'inventory-primary','version':2,'token':'inventory:tab:slot',
                    'sourceKind':'inventory','layout':'primary-left',
                    'source':dict(x=300,y=150,width=230,height=300),
                    'slot':dict(x=324,y=174,width=36,height=36),
                    'panel':dict(x=50,y=220,width=240,height=330),
                    'comparison':dict(x=292,y=220,width=240,height=300),
                    'pointer':dict(x=340,y=190),'cursor':dict(x=334,y=184,width=32,height=36),
                    'guards':[dict(x=300,y=150,width=230,height=20),
                              dict(x=50,y=262,width=1,height=12),dict(x=287,y=262,width=1,height=12),
                              dict(x=292,y=262,width=1,height=12),dict(x=529,y=262,width=1,height=12)]}}

    def test_current_source_change_clears_primary_even_with_unchanged_description_pixels(self):
        w=self.window;w.on_reading(self.reading())
        self.assertIsNotNone(w.tooltip_context)
        changed=w.reader.image.copy();changed.setPixelColor(326,176,QColor('red'))
        w.reader.image=changed;w.on_image(changed)
        self.assertIsNone(w.tooltip_result);self.assertIsNone(w.tooltip_context)
        self.assertFalse(any(row.get('kind')=='item' for row in w.overlay.rows))

    def test_late_native_reply_checks_the_latest_source_before_showing_a_card(self):
        w=self.window;reply=self.reading()
        changed=w.reader.image.copy();changed.setPixelColor(326,176,QColor('red'))
        w.reader.image=changed
        w.on_reading(reply)
        self.assertIsNone(w.tooltip_result);self.assertIsNone(w.tooltip_context)

    def test_same_cell_cursor_motion_keeps_the_source_card_and_its_proofs(self):
        w=self.window;reply=self.reading();w.on_reading(reply)
        self.assertIsNotNone(w.tooltip_result)
        w.reader.image=self.frame((343,192));w.reader.pointer=(343,192)
        w.on_image(w.reader.image)
        self.assertEqual(w.tooltip_result['name'],'Example Hat')
        # A reply submitted before the small cursor motion remains valid only
        # because visible cell/name/frame evidence is still current.
        w.on_reading(reply)
        self.assertEqual(w.tooltip_context.token,'inventory:tab:slot')

    def test_manual_crop_keeps_proof_and_annotation_protection_in_their_coordinates(self):
        w=self.window;offset=(40,30)
        w.reader.crop=QRect(*offset,800,600)
        w.reader.image=self.frame(offset=offset);w.reader.submitted_image=w.reader.image.copy()
        w.reader.pointer=(340+offset[0],190+offset[1])
        reply=deepcopy(self.reading());reply['pointerAtRead']=list(w.reader.pointer)
        w.on_reading(reply)
        self.assertIsNotNone(w.tooltip_result)
        self.assertEqual(w.tooltip_context.slot,QRect(324,174,36,36))
        annotation=next(row for row in w.overlay.rows if row.get('kind')=='item')
        geometry=w.screens[w.screen_index].geometry()
        sx=geometry.width()/w.reader.image.width();sy=geometry.height()/w.reader.image.height()
        self.assertIn([round(340*sx),round(180*sy),round(230*sx),round(300*sy)],annotation['avoid_regions'])
        self.assertIn('bounds',annotation)


if __name__=='__main__':unittest.main()

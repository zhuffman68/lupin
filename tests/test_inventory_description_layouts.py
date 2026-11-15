"""Real reader titles reach the actual canvas for fitted inventory layouts.

Generated native frames, fake prices/media, private Qt surfaces and an ordinary
pointer value only. No OS capture, input or game access is involved.
"""
from copy import deepcopy
import json
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtCore import QPoint,QCoreApplication,QEvent
from PySide6.QtGui import QImage

from price_lens.annotations import AnnotationWindow
from price_lens.domain import Catalog
import test_ui_context as ui
import test_inventory_tooltip_reader as native_fixtures


@unittest.skipUnless(native_fixtures.BINARY.is_file(),'Build the screen reader first')
class InventoryDescriptionLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        native_fixtures.InventoryTooltipReaderTests.setUpClass();ui.ContextUiTests.setUpClass()
        native=native_fixtures.InventoryTooltipReaderTests();cls.pointer=(1378,152)
        cls.names=('Emerald Staff','Emerald Staff','Emerald Staff','Overall DEX Greater')
        cls.frames=(native.frame(shop=True),
            native.frame(primary_rect=(863,180,400,300),comparison_rect=(1266,180,232,240),shop=True),
            native.frame(primary_rect=(1024,280,236,200),comparison_rect=(1263,180,236,300),shop=True),
            native.frame(primary=False,comparison_rect=(899,180,600,250),tab=1,
                         single_name=cls.names[-1],shop=True))
        cls.results=native.read(cls.frames,inventory_only=True,retry=False)

    def test_compared_and_wide_inventory_items_reach_the_canvas_without_covering_their_proofs(self):
        for source,result,name in zip(self.frames,self.results,self.names):
            with self.subTest(name=name,layout=result['tooltipAssociation'].get('panel')):
                fixture=ui.ContextUiTests(methodName='runTest');fixture.setUp()
                canvas=None
                try:
                    window=fixture.window;frame=QImage(source)
                    window.screens=[SimpleNamespace(geometry=frame.rect,devicePixelRatio=lambda:1,name=lambda:'Fixture')]
                    window.screen_index=0;window.last_screen=time.time()
                    window.reader.image=frame;window.reader.submitted_image=QImage(source)
                    window.reader.pointer=self.pointer;window.reader.game_area=frame.rect()
                    window.on_catalog(Catalog({'items':[dict(id=1,name='Emerald Staff'),
                        dict(id=2,name='Mithril Pole Arm'),dict(id=3,name='Overall DEX Greater')],'scrolls':[]}))
                    reply=deepcopy(result);reply.update(pointerAtRead=list(self.pointer),_shop_deferred=True)
                    window.on_reading(reply)
                    self.assertEqual(window.tooltip_result['name'],name)
                    rows=[row for row in window.overlay.rows if row.get('kind')=='item']
                    self.assertEqual([row['name'] for row in rows],[name])
                    self.assertEqual(rows[0]['item_id'],3 if name=='Overall DEX Greater' else 1)
                    canvas=AnnotationWindow(start_listener=False)
                    with patch('price_lens.annotations.QCursor.pos',return_value=QPoint(*self.pointer)):
                        canvas.read_command(json.dumps(dict(geometry=[0,0,frame.width(),frame.height()],
                            hover_enabled=True,rows=rows)))
                    self.assertEqual(len(canvas.rows),1)
                    box=canvas.label_rect(canvas.rows[0],QPoint(*self.pointer))
                    self.assertIsNotNone(box);self.assertTrue(frame.rect().contains(box))
                    context=window.tooltip_context
                    for native in (context.source,context.panel,context.comparison):
                        if native is not None:self.assertFalse(box.intersects(native))
                finally:
                    if canvas is not None:
                        canvas.pointer_timer.stop();canvas.watchdog.stop();canvas.close();canvas.deleteLater()
                    fixture.tearDown();fixture.doCleanups()
                    QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)

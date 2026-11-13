"""Non-equipment source admission through native OCR, UI and actual painting."""
from copy import deepcopy
import json
from types import SimpleNamespace
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QPoint,QCoreApplication,QEvent
from PySide6.QtGui import QColor,QImage,QPainter

from price_lens.annotations import AnnotationWindow
from price_lens.domain import Catalog
from price_lens.capture import PixelReader
from price_lens.reader_request import SubmittedRequest
from price_lens.tooltip_association import TooltipAssociation
import test_inventory_tooltip_reader as native_fixtures
import test_ui_context as ui


@unittest.skipUnless(native_fixtures.BINARY.is_file(),'Build the screen reader first')
class NonEquipmentInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        native_fixtures.InventoryTooltipReaderTests.setUpClass()
        ui.ContextUiTests.setUpClass()

    def test_capture_admits_the_first_moving_pane_only_with_current_source_and_title(self):
        native=native_fixtures.InventoryTooltipReaderTests();point=(1378,152)
        source=native.frame(primary=False,tab=1,single_name='Red Potion')
        raw=native.read(source)[0]
        proof=TooltipAssociation.from_result(raw,source,pointer=point)
        self.assertIsNotNone(proof)
        for changed_source in (False,True):
            with self.subTest(changed_source=changed_source):
                latest=QImage(source);painter=QPainter(latest)
                painter.fillRect(proof.panel,QColor('#142314'))
                painter.drawImage(proof.panel.topLeft()+QPoint(-2,3),source.copy(proof.panel));painter.end()
                if changed_source:latest.setPixelColor(proof.slot.left()+5,proof.slot.top()+2,QColor('red'))
                reader=PixelReader(native_fixtures.ROOT);reader.timer.stop();reader.auto_enabled=False
                try:
                    now=time.monotonic();reader.image=latest;reader.pointer=(point[0]-2,point[1]+3)
                    reader.last_frame=now;reader.image_sequence=reader.submitted_sequence=1
                    request=SubmittedRequest('prices',source,point,1,reader.generation,now,shop_epoch=reader.shop_browsing.epoch)
                    reader.active_request=reader.submitted_request=request
                    result={**deepcopy(raw),'atMs':int(now*1000)};accepted=[];reader.reading.connect(accepted.append)
                    with patch('price_lens.capture.QTimer.singleShot'),patch.object(reader.process,'readAllStandardOutput',return_value=(json.dumps(result)+'\n').encode()):
                        reader.on_output()
                    self.assertEqual(len(accepted),1)
                    if changed_source:
                        self.assertEqual(accepted[0]['tooltipAssociation']['state'],'rejected')
                        self.assertIsNone(reader.tooltip_association)
                    else:
                        self.assertEqual(accepted[0]['tooltipAssociation']['state'],'inventory-primary')
                        self.assertTrue(accepted[0]['_tooltip_context'].matches(source,point))
                        self.assertTrue(reader.tooltip_association.matches(latest,reader.pointer))
                        self.assertEqual(reader.tooltip_association.panel,proof.panel.translated(-2,3))
                finally:
                    reader.close();reader.deleteLater()
                    QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
                    ui.ContextUiTests.app.processEvents()

    def test_non_equipment_cards_paint_and_survive_missed_reads_until_the_source_changes(self):
        native=native_fixtures.InventoryTooltipReaderTests();point=(1378,152)
        cases=((1,'Red Potion'),(1,'Overall DEX Greater'),(2,'Relaxer'),(3,'Bronze Ore'),(5,'White Potion'))
        for tab,name in cases:
            for shop in (False,True):
                with self.subTest(tab=tab,name=name,shop=shop):
                    frame=native.frame(primary=False,tab=tab,single_name=name,shop=shop)
                    result=native.read(frame,inventory_only=shop)[0]
                    self.assertEqual(result['tooltipAssociation']['state'],'inventory-primary')
                    self.assertEqual(result['tooltip']['found']['name'],name)
                    fixture=ui.ContextUiTests();fixture.setUp()
                    canvas=AnnotationWindow(start_listener=False)
                    try:
                        w=fixture.window
                        w.screens=[SimpleNamespace(geometry=frame.rect,devicePixelRatio=lambda:1,name=lambda:'Fixture')]
                        w.screen_index=0;w.reader.pointer=point;w.reader.game_area=frame.rect()
                        w.reader.image=w.reader.submitted_image=frame
                        w.on_catalog(Catalog({'items':[dict(id=100,name=name)],'scrolls':[]}))
                        result={**result,'pointerAtRead':list(point)}
                        w.last_screen=time.time();w.on_reading(result)

                        def paint():
                            with patch('price_lens.annotations.QCursor.pos',return_value=QPoint(*point)):
                                canvas.read_command(json.dumps(dict(geometry=[0,0,frame.width(),frame.height()],
                                    rows=w.overlay.rows,hover_enabled=True,reduce_motion=True)))
                                items=[row for row in canvas.rows if row.get('kind')=='item']
                                if not items:return items
                                self.assertEqual(len(items),1)
                                rectangle=canvas.label_rect(items[0],QPoint(*point))
                                self.assertIsNotNone(rectangle)
                                image=canvas.grab().toImage()
                                self.assertTrue(image.rect().contains(rectangle))
                                self.assertGreater(image.pixelColor(rectangle.center()).alpha(),200)
                                return items

                        first=paint();self.assertEqual(first[0]['item_id'],100)
                        self.assertTrue(first[0]['source_bound'])
                        missing={**deepcopy(result),'_shop_deferred':True,'shop':None,'hover':None,
                                 'tooltip':{'found':None},'tooltipAssociation':{'state':'rejected'}}
                        w.on_reading(missing)
                        self.assertIs(paint()[0],first[0])
                        self.assertEqual(w.tooltip_result['name'],name)
                        changed=QImage(frame);slot=w.tooltip_context.slot
                        changed.setPixelColor(slot.left()+5,slot.top()+2,QColor('red'))
                        w.reader.image=changed;w.reader.last_frame=time.monotonic();w.on_image(changed)
                        self.assertIsNone(w.tooltip_result);self.assertEqual(paint(),[])
                    finally:
                        canvas.pointer_timer.stop();canvas.watchdog.stop();canvas.close();canvas.deleteLater()
                        fixture.tearDown();fixture.doCleanups()

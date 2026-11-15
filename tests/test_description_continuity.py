"""A currently proved blue description owns its price, independently of OCR cadence."""
from copy import deepcopy
import unittest

from PySide6.QtCore import QRect,QPoint
from PySide6.QtGui import QColor,QImage

from price_lens.tooltip_association import TooltipAssociation
from price_lens.tooltip_geometry import TooltipReference


class DescriptionContinuityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from test_inventory_tooltip_reader import InventoryTooltipReaderTests
        InventoryTooltipReaderTests.setUpClass()
        fixture=InventoryTooltipReaderTests()
        cls.image=fixture.frame(shop=True);cls.pointer=(1378,152)
        cls.result=fixture.read(cls.image)[0]
        cls.found=cls.result['tooltip']['found']
        cls.context=TooltipAssociation.from_result(cls.result,cls.image,pointer=cls.pointer)
        assert cls.context is not None and cls.context.matches(cls.image,cls.pointer)

    def reference(self):
        reference=TooltipReference()
        reference.observe(deepcopy(self.found),self.image,self.pointer,context=self.context,now=0)
        return reference

    def test_inventory_keeps_its_current_price_through_missing_ocr_and_metadata(self):
        reference=self.reference()
        for second in (1,5,30,300):
            held=reference.observe(None,QImage(self.image),self.pointer,context=None,now=second)
            self.assertIsNotNone(held)
            self.assertEqual(held['name'],'Emerald Staff');self.assertIs(reference.context,self.context)

    def test_a_long_ocr_miss_is_not_a_reason_to_retire_a_current_blue_window(self):
        reference=self.reference()
        self.assertIsNotNone(reference.observe(None,self.image,self.pointer,context=self.context,now=60))

    def test_pointer_leaving_the_source_cell_retires_old_identity_even_if_title_is_visible(self):
        reference=self.reference()
        self.assertIsNone(reference.observe(None,self.image,(self.pointer[0]+36,self.pointer[1]),now=1))

    def test_changed_source_or_closed_description_cannot_be_held(self):
        for source in (True,False):
            reference=self.reference();changed=QImage(self.image)
            if source:
                changed.setPixelColor(self.context.slot.left()+5,self.context.slot.top()+2,QColor('red'))
            else:
                from PySide6.QtGui import QPainter
                p=QPainter(changed);p.fillRect(self.context.panel,QColor('#142314'));p.end()
            self.assertIsNone(reference.observe(None,changed,self.pointer,now=1))

    def test_shop_ownership_and_disabled_reading_still_clear_the_description_reference(self):
        reference=self.reference()
        self.assertIsNone(reference.observe(None,self.image,self.pointer,allow=False,now=1))

    def test_rejection_diagnostics_reuse_the_exact_same_current_frame_check(self):
        from unittest.mock import patch
        proof=self.context
        for reason,point in (('cell',(proof.slot.left()+5,proof.slot.top()+2)),
                             ('header',(proof.source.left()+12,proof.source.top()+7))):
            with self.subTest(reason=reason):
                changed=QImage(self.image);changed.setPixelColor(*point,QColor('red'))
                self.assertFalse(proof.matches(changed,self.pointer))
                with patch.object(TooltipAssociation,'_matches_current',side_effect=AssertionError('Do not repeat proof work for diagnostics')):
                    self.assertEqual(proof.failure_reason(changed,self.pointer),reason)

    def test_generic_blue_description_is_held_by_its_title_proof_without_a_short_timer(self):
        reference=TooltipReference()
        reference.observe(deepcopy(self.found),self.image,self.pointer,title=self.context.title,now=0)
        self.assertIsNotNone(reference.observe(None,self.image,self.pointer,now=60))

    def test_linked_blue_window_does_not_depend_on_the_pointer_remaining_near_it(self):
        reference=TooltipReference();found={**self.found,'pinned':True}
        reference.observe(found,self.image,self.pointer,title=self.context.title,now=0)
        self.assertIsNotNone(reference.observe(None,self.image,(20,20),now=60))

    def test_title_changes_cannot_keep_a_previous_generic_price(self):
        reference=TooltipReference()
        reference.observe(deepcopy(self.found),self.image,self.pointer,title=self.context.title,now=0)
        changed=QImage(self.image);rect=QRect(*self.context.title.rect)
        point=next((x,y) for y in range(rect.top(),rect.bottom()+1) for x in range(rect.left(),rect.right()+1)
                   if min(changed.pixelColor(x,y).getRgb()[:3])>230)
        changed.setPixelColor(*point,QColor('#142314'))
        self.assertIsNone(reference.observe(None,changed,self.pointer,now=1))

    def test_pointer_driven_pane_motion_reanchors_without_repeating_identity_ocr(self):
        from PySide6.QtGui import QPainter
        reference=self.reference();source=self.image
        for dx,dy in ((-2,3),(-4,4),(-5,6)):
            changed=QImage(source);p=QPainter(changed)
            for panel in (self.context.panel,self.context.comparison):p.fillRect(panel,QColor('#142314'))
            for panel in (self.context.panel,self.context.comparison):p.drawImage(panel.topLeft()+QPoint(dx,dy),source.copy(panel))
            p.end();point=(self.pointer[0]+dx,self.pointer[1]+dy)
            self.assertTrue(self.context.contains_pointer(point))
            held=reference.observe(None,changed,point,now=10+dx)
            self.assertIsNotNone(held)
            self.assertEqual(held['name'],'Emerald Staff')
            self.assertEqual(reference.context.panel,self.context.panel.translated(dx,dy))
            self.assertTrue(reference.context.matches(changed,point))
            self.assertEqual(reference.context.token,self.context.token)

    def test_moving_popup_cannot_borrow_identity_from_a_changed_inventory_cell(self):
        from PySide6.QtGui import QPainter
        from PySide6.QtCore import QPoint
        reference=self.reference();changed=QImage(self.image);p=QPainter(changed)
        for panel in (self.context.panel,self.context.comparison):p.fillRect(panel,QColor('#142314'))
        for panel in (self.context.panel,self.context.comparison):p.drawImage(panel.topLeft()+QPoint(-2,3),self.image.copy(panel))
        p.end();point=(self.pointer[0]-2,self.pointer[1]+3)
        self.assertIsNotNone(self.context.at_current_position(changed,point))
        changed.setPixelColor(self.context.slot.left()+5,self.context.slot.top()+2,QColor('red'))
        self.assertIsNone(reference.observe(None,changed,point,now=10))

    def move_panels(self,primary_offset,comparison_offset):
        from PySide6.QtGui import QPainter
        changed=QImage(self.image);painter=QPainter(changed)
        for panel in (self.context.panel,self.context.comparison):painter.fillRect(panel,QColor('#142314'))
        for panel,offset in ((self.context.panel,primary_offset),(self.context.comparison,comparison_offset)):
            painter.drawImage(panel.topLeft()+QPoint(*offset),self.image.copy(panel))
        painter.end();return changed

    def test_a_comparison_can_clamp_independently_without_losing_the_hovered_price(self):
        for primary,comparison in (((-2,3),(0,3)),((0,3),(-2,3)),
                                   ((-2,3),(-2,0)),((-2,0),(-2,3)),((0,0),(-2,3))):
            with self.subTest(primary=primary,comparison=comparison):
                reference=self.reference();changed=self.move_panels(primary,comparison)
                point=(self.pointer[0]-2,self.pointer[1]+3)
                held=reference.observe(None,changed,point,now=20)
                self.assertIsNotNone(held);self.assertEqual(held['name'],'Emerald Staff')
                self.assertEqual(reference.context.panel,self.context.panel.translated(*primary))
                self.assertEqual(reference.context.comparison,self.context.comparison.translated(*comparison))
                self.assertTrue(reference.context.matches(changed,point))

    def test_independent_pane_motion_keeps_source_title_and_pair_separation_checks(self):
        for field in ('source','header','title','seam','mask'):
            with self.subTest(field=field):
                point=(self.pointer[0]-2,self.pointer[1]+3)
                reference=self.reference();changed=self.move_panels((-2,3),(0,3))
                if field=='source':changed.setPixelColor(self.context.slot.left()+5,self.context.slot.top()+2,QColor('red'))
                elif field=='header':changed.setPixelColor(self.context.source.left()+12,self.context.source.top()+7,QColor('red'))
                elif field=='title':
                    rect=QRect(*self.context.title.rect).translated(-2,3)
                    pixel=next((x,y) for y in range(rect.top(),rect.bottom()+1) for x in range(rect.left(),rect.right()+1)
                               if min(changed.pixelColor(x,y).getRgb()[:3])>230)
                    changed.setPixelColor(*pixel,QColor('#142314'))
                elif field=='seam':
                    changed=self.move_panels((-10,3),(0,3));point=(self.pointer[0]-10,self.pointer[1]+3)
                masks=[object()] if field=='mask' else ()
                self.assertIsNone(reference.current(changed,point,exclude=masks))

    def test_independent_pane_reanchoring_checks_each_position_a_bounded_number_of_times(self):
        from unittest.mock import patch
        from price_lens.tooltip_geometry import verified_frame
        changed=self.move_panels((-2,3),(0,3));point=(self.pointer[0]-2,self.pointer[1]+3)
        with patch('price_lens.tooltip_association.verified_frame',wraps=verified_frame) as frames:
            current=self.context.at_current_position(changed,point)
            self.assertIsNotNone(current)
            self.assertLessEqual(frames.call_count,12)

    def test_shared_pane_motion_does_not_probe_other_clamps_or_repeat_its_completed_proof(self):
        from unittest.mock import patch
        from price_lens.tooltip_geometry import verified_frame
        changed=self.move_panels((-2,3),(-2,3));point=(self.pointer[0]-2,self.pointer[1]+3)
        with patch('price_lens.tooltip_association.verified_frame',wraps=verified_frame) as frames:
            current=self.context.at_current_position(changed,point)
            self.assertIsNotNone(current);self.assertLessEqual(frames.call_count,4)
            calls=frames.call_count
            self.assertTrue(current.matches(changed,point));self.assertEqual(frames.call_count,calls)
            changed.setPixelColor(self.context.slot.left()+5,self.context.slot.top()+2,QColor('red'))
            self.assertFalse(current.matches(changed,point))

    def test_real_native_identity_survives_a_failed_next_read_through_the_gui(self):
        import time
        import test_ui_context as ui
        from price_lens.domain import Catalog
        ui.ContextUiTests.setUpClass()
        test=ui.ContextUiTests();test.setUp()
        try:
            from types import SimpleNamespace
            window=test.window;frame=QImage(self.image)
            window.screens=[SimpleNamespace(geometry=lambda:frame.rect(),devicePixelRatio=lambda:1,name=lambda:'Fixture')]
            window.screen_index=0
            window.reader.image=window.reader.submitted_image=frame
            window.reader.pointer=self.pointer;window.reader.game_area=frame.rect()
            window.on_catalog(Catalog({'items':[dict(id=1,name='Emerald Staff'),dict(id=2,name='Mithril Pole Arm')],'scrolls':[]}))
            reading=deepcopy(self.result);reading.update(pointerAtRead=list(self.pointer),_shop_deferred=True,shop=None,hover=None)
            window.last_screen=time.time();window.on_reading(reading)
            self.assertIsNotNone(window.tooltip_result)
            self.assertEqual([r['item_id'] for r in window.overlay.rows if r.get('kind')=='item'],[1])
            missing={**reading,'tooltip':{'found':None},'tooltipAssociation':{'state':'rejected'}}
            window.on_reading(missing)
            self.assertEqual(window.tooltip_result['name'],'Emerald Staff')
            self.assertEqual([r['item_id'] for r in window.overlay.rows if r.get('kind')=='item'],[1])
            wrong_guess=deepcopy(reading);wrong_guess['tooltip']['found']['name']='Mithril Pole Arm'
            window.on_reading(wrong_guess)
            self.assertEqual(window.tooltip_result['name'],'Emerald Staff')
            self.assertEqual([r['item_id'] for r in window.overlay.rows if r.get('kind')=='item'],[1])
            changed=QImage(frame);changed.setPixelColor(self.context.slot.left()+5,self.context.slot.top()+2,QColor('red'))
            window.reader.image=changed;window.reader.last_frame=time.monotonic();window.on_image(changed)
            self.assertIsNone(window.tooltip_result)
            self.assertFalse(any(r.get('kind')=='item' for r in window.overlay.rows))
        finally:test.tearDown();test.doCleanups()

    def test_first_inventory_reply_can_follow_a_current_proved_pane_without_repeating_ocr(self):
        import time
        from types import SimpleNamespace
        from PySide6.QtGui import QPainter
        import test_ui_context as ui
        from price_lens.domain import Catalog
        ui.ContextUiTests.setUpClass()
        for changed_source in (False,True):
            with self.subTest(changed_source=changed_source):
                test=ui.ContextUiTests();test.setUp()
                try:
                    frame=QImage(self.image);p=QPainter(frame)
                    for pane in (self.context.panel,self.context.comparison):p.fillRect(pane,QColor('#142314'))
                    for pane in (self.context.panel,self.context.comparison):p.drawImage(pane.topLeft()+QPoint(-2,3),self.image.copy(pane))
                    p.end();point=(self.pointer[0]-2,self.pointer[1]+3)
                    if changed_source:frame.setPixelColor(self.context.slot.left()+5,self.context.slot.top()+2,QColor('red'))
                    w=test.window;w.screens=[SimpleNamespace(geometry=frame.rect,devicePixelRatio=lambda:1,name=lambda:'Fixture')]
                    w.screen_index=0;w.reader.image=frame;w.reader.submitted_image=QImage(self.image)
                    w.reader.pointer=point;w.reader.game_area=frame.rect();w.last_screen=time.time()
                    w.on_catalog(Catalog({'items':[dict(id=1,name='Emerald Staff')],'scrolls':[]}))
                    reply=deepcopy(self.result);reply.update(pointerAtRead=list(self.pointer),_shop_deferred=True,shop=None,hover=None)
                    w.on_reading(reply)
                    if changed_source:
                        self.assertIsNone(w.tooltip_result)
                        self.assertFalse(any(row.get('kind')=='item' for row in w.overlay.rows))
                    else:
                        self.assertIsNotNone(w.tooltip_result)
                        self.assertEqual(w.tooltip_result['name'],'Emerald Staff')
                        self.assertEqual(w.tooltip_context.panel,self.context.panel.translated(-2,3))
                        self.assertEqual(w.tooltip_result['_pointer'],list(point))
                        self.assertEqual([row['item_id'] for row in w.overlay.rows if row.get('kind')=='item'],[1])
                finally:test.tearDown();test.doCleanups()

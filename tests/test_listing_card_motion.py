"""A new shop listing must not replay the animation of existing cards."""
import time,unittest
from unittest.mock import patch

import numpy as np
from PySide6.QtCore import QRect
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest

import test_ui_context as fixture
from price_lens.card_list_motion import ListingFrame
from price_lens.domain import Catalog,Quote


class ListingCardMotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.ContextUiTests.setUpClass.__func__(cls)

    def setUp(self):
        fixture.ContextUiTests.setUp(self)
        self.app.setProperty('reduceMotion',False)
        self.w=self.window;self.w.timer.stop();self.w.resize(520,840);self.w.show();self.app.processEvents()
        self.names={1:'Example Hat',2:'Example Cape',3:'Example Gloves'}
        self.w.on_catalog(Catalog({'items':[dict(id=key,name=name) for key,name in self.names.items()]}))
        now=time.time()
        self.w.quotes={key:Quote(key,1200,now,now,20,'Fixture','','24h') for key in self.names}
        self.w.service.cached_values=dict(self.w.quotes)

    def tearDown(self):fixture.ContextUiTests.tearDown(self)

    def show_rows(self,identities):
        self.w.rows=[dict(name=self.names[key],price=dict(quantity=1,mesos=100+key*20),
                         area=dict(x=340,y=220+index*50,width=180,height=40),
                         shop_page=1,shop_slot=(40,20+index*50,180,40)) for index,key in enumerate(identities)]
        self.w.tooltip_result=None;self.w.render()

    def settled(self,identities):
        self.show_rows(identities);QTest.qWait(230);self.w.card_area.finish();self.app.processEvents()

    def rect(self,key):return self.w.screen_card_frames()[(False,key,0)]

    def sample(self,rect):
        image=self.w.card_area.grab().toImage()
        ratio=image.devicePixelRatio()
        physical=QRect(round(rect.x()*ratio),round(rect.y()*ratio),round(rect.width()*ratio),round(rect.height()*ratio))
        return image.copy(physical).convertToFormat(QImage.Format.Format_RGBA8888)

    def same_pixels(self,actual,expected):
        self.assertEqual(actual.size(),expected.size())
        # Alpha blending of identical opaque colors can round an edge channel
        # by one. Displaced/doubled text changes hundreds of channels by >100.
        a=np.frombuffer(actual.constBits(),np.uint8).astype(np.int16)
        b=np.frombuffer(expected.constBits(),np.uint8).astype(np.int16)
        self.assertLessEqual(int(np.max(np.abs(a-b))),1)

    def test_appending_only_reveals_the_new_card_and_keeps_existing_pixels(self):
        self.settled([1]);rect=self.rect(1);before=self.sample(rect);start=self.w.card_area.height()
        old=self.w.card_views[(False,1,0)];self.show_rows([1,2]);area=self.w.card_area
        self.assertIsInstance(area.outgoing,ListingFrame);self.assertIs(self.w.card_views[(False,1,0)],old)
        self.assertEqual(area.animation.duration(),180);area.animation.pause();heights=[]
        for ms in (0,18,36,54,72,90,108,126,144,162,179):
            area.animation.setCurrentTime(ms);self.app.processEvents();heights.append(area.height())
            self.same_pixels(self.sample(rect),before)
        self.assertEqual(heights,sorted(heights));self.assertGreater(area.height(),start)
        self.assertGreater(len(set(heights)),5)
        area.finish();self.assertIsNone(area.outgoing);self.assertTrue(area.content.isVisible())

    def test_inserting_above_moves_the_existing_card_without_doubled_text(self):
        self.settled([1]);old_rect=self.rect(1);before=self.sample(old_rect)
        self.show_rows([2,1]);area=self.w.card_area;frame=area.outgoing;target=self.rect(1)
        self.assertIsInstance(frame,ListingFrame);area.animation.pause();positions=[]
        for ms in (0,36,72,108,144,179):
            area.animation.setCurrentTime(ms);self.app.processEvents()
            rect=frame.item_rect((False,1,0));positions.append(rect.y())
            self.same_pixels(self.sample(rect),before)
        self.assertEqual(positions,sorted(positions));self.assertGreater(positions[-1],old_rect.y())
        self.assertLessEqual(positions[-1],target.y())

    def test_another_listing_mid_transition_starts_from_the_visible_frame(self):
        self.settled([1]);self.show_rows([1,2]);area=self.w.card_area
        area.animation.pause();area.animation.setCurrentTime(90);self.app.processEvents()
        before=area.grab().toImage();height=area.height()
        self.show_rows([1,2,3]);area.animation.pause();area.animation.setCurrentTime(0);self.app.processEvents()
        self.assertEqual(area.height(),height);self.assertIsInstance(area.outgoing,ListingFrame)
        self.same_pixels(area.grab().toImage(),before)

    def test_quote_delivery_refreshes_one_destination_without_restarting_motion(self):
        self.settled([1]);before=self.sample(self.rect(1));self.show_rows([1,2]);area=self.w.card_area
        frame=area.outgoing;area.animation.pause();area.animation.setCurrentTime(90)
        now=time.time();self.w.service.deliver_quote(2,Quote(2,1800,now,now,20,'Fixture','','24h'))
        self.app.processEvents()
        self.assertIs(area.outgoing,frame);self.assertEqual(area.animation.currentTime(),90)
        self.assertIn('1,800',self.w.card_views[(False,2,0)].fields['market'].text())
        self.same_pixels(self.sample(self.rect(1)),before)

    def test_retiring_a_listing_moves_the_remaining_cards_up_without_flashing(self):
        self.settled([1,2,3]);before=self.sample(self.rect(3));first=self.sample(self.rect(1))
        self.w.card_sightings.discard(False)  # The separate grace-period checks cover its expiry.
        self.show_rows([1,3]);area=self.w.card_area;frame=area.outgoing
        self.assertIsInstance(frame,ListingFrame);area.animation.pause();positions=[]
        for ms in (0,36,72,108,144,179):
            area.animation.setCurrentTime(ms);self.app.processEvents()
            rect=frame.item_rect((False,3,0));positions.append(rect.y())
            self.same_pixels(self.sample(rect),before);self.same_pixels(self.sample(self.rect(1)),first)
        self.assertEqual(positions,sorted(positions,reverse=True));self.assertGreater(positions[0],positions[-1])

    def test_inventory_overlay_changes_leave_one_copy_of_each_shop_card(self):
        w = self.w
        screen = w.screens[w.screen_index]
        w.reader.image = QImage(screen.size() * screen.devicePixelRatio(), QImage.Format.Format_RGB32)
        w.reader.image.fill(0)
        w.last_screen = time.time()
        key = (False, 1, 0)
        with patch('price_lens.ui.time.time', return_value=w.last_screen):
            self.settled([1])
            shop_card = w.card_views[key]
            original = self.sample(self.rect(1).adjusted(3, 3, -3, -3))
            switches = (('Example Cape', 179), ('Example Gloves', 90), ('Example Cape', 179), (None, 179))
            for index, (name, cutoff) in enumerate(switches):
                with self.subTest(description=name, step=index):
                    if name:
                        w.tooltip_result = dict(name=name, area=dict(x=100, y=100, width=180, height=25),
                                                _pointer=(105, 105))
                    else:
                        w.tooltip_result = None
                        # Grace and history timing are covered separately.
                        w.card_sightings.discard(True)
                    w.render()
                    self.assertEqual([row['kind'] for row in w.overlay.rows].count('item'), int(bool(name)))
                    self.assertIs(w.card_views[key], shop_card)
                    area = w.card_area
                    self.assertEqual(area.animation.duration(), 180)
                    frame = area.outgoing
                    self.assertIsInstance(frame, ListingFrame)
                    self.assertIsNotNone(frame.morph)
                    area.animation.pause()
                    positions = []
                    for ms in (0, 36, 72, 90, 108, 144, 179):
                        if ms > cutoff:
                            break
                        area.animation.setCurrentTime(ms)
                        self.app.processEvents()
                        rect = frame.item_rect(key)
                        positions.append(rect.y())
                        self.same_pixels(self.sample(rect.adjusted(3, 3, -3, -3)), original)
                    if index == 0:
                        self.assertEqual(positions, sorted(positions))
                        self.assertGreater(positions[-1], positions[0])
                    if name is None:
                        self.assertEqual(positions, sorted(positions, reverse=True))
                        self.assertLess(positions[-1], positions[0])
                    if cutoff == 179:
                        area.finish()
                        self.app.processEvents()

    def test_reduced_motion_does_not_retain_a_listing_frame(self):
        self.settled([1]);self.app.setProperty('reduceMotion',True);self.show_rows([1,2]);area=self.w.card_area
        self.assertIsNone(area.outgoing);self.assertEqual(area.height(),area.full_height)
        self.assertEqual(area.animation.state(),area.animation.State.Stopped)


if __name__=='__main__':unittest.main()

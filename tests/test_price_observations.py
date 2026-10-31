"""Widget-free observation acceptance and retirement from generated native pixels."""
from copy import deepcopy
import unittest

from PySide6.QtCore import QCoreApplication,QRect
from PySide6.QtGui import QColor,QImage,QPainter

from price_lens.domain import Catalog
from price_lens.price_observations import PriceObservations
from price_lens.shop_browsing import ShopBrowsing


class PriceObservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.state=PriceObservations(catalog=Catalog({'items':[dict(id=1,name='Example Hat')]}))
        self.state.browsing=ShopBrowsing(identity=self.state.shop_identity)
        self.addCleanup(self.state.browsing.timer.stop)
        self.image=QImage(800,600,QImage.Format.Format_RGBA8888);self.image.fill(QColor('#cad5df'))
        painter=QPainter(self.image)
        painter.fillRect(104,154,24,27,QColor('#992211'))
        painter.fillRect(145,155,80,6,QColor('black'))
        painter.fillRect(145,174,50,6,QColor('black'));painter.end()
        self.area=QRect(100,150,199,260);self.point=(180,160)
        self.shop=dict(area=dict(zip(('x','y','width','height'),self.area.getRect())),rows=[
            dict(name='Example Hat',price=dict(quantity=1,mesos=100),area=dict(x=137,y=150,width=162,height=35))])

    def observe(self,image=None,latest=None,**kwargs):
        image=self.image if image is None else image
        return self.state.observe_shop(deepcopy(self.shop),image,image if latest is None else latest,
            pointer=self.point,read_point=self.point,**kwargs)

    def test_only_fresh_matching_source_becomes_an_accepted_offer(self):
        read=self.observe()
        self.assertTrue(read.changed);self.assertFalse(read.retry)
        self.assertEqual(self.state.rows[0]['_item_id'],1)
        changed=self.image.copy();changed.setPixelColor(220,176,QColor('white'))
        read=self.observe(latest=changed)
        self.assertTrue(read.retry);self.assertEqual(self.state.rows,[])
        self.assertFalse(self.state.shop_open)

    def test_source_retirement_and_proven_viewport_change_keep_separate_authority(self):
        self.observe();page=self.state.shop_rows.page_revision;epoch=self.state.browsing.epoch
        changed=self.image.copy();changed.setPixelColor(220,176,QColor('white'))
        frame=self.state.validate_frame(changed,pointer=self.point,shop_context=self.area)
        self.assertTrue(frame.retired);self.assertEqual(self.state.rows,[])
        self.assertEqual(self.state.browsing.epoch,epoch);self.assertFalse(self.state.browsing.active())
        self.assertTrue(self.state.shop_rows.rows,'Recovery cache is separate from a live offer')
        self.state.viewport_changed()
        self.assertGreater(self.state.shop_rows.page_revision,page)
        self.assertEqual(self.state.shop_rows.rows,{})

    def test_known_description_occlusion_preserves_reference_but_never_current_offer(self):
        self.observe();panel=QRect(200,158,100,160)
        latest=self.image.copy();painter=QPainter(latest);painter.fillRect(panel,QColor('#464b78'));painter.end()
        self.state.shop_tooltip_rect=panel
        read=self.observe(latest=latest,panel=panel,source_exclude=[panel])
        self.assertFalse(read.retry);self.assertTrue(self.state.rows)
        self.assertIsNone(self.state.rows[0]['price']);self.assertTrue(self.state.rows[0]['reference_only'])
        self.assertEqual(self.state.rows[0]['name'],'Example Hat')

    def test_our_annotation_changes_are_never_native_source_contradictions(self):
        self.observe();annotation=QRect(210,151,70,25)
        latest=self.image.copy();painter=QPainter(latest);painter.fillRect(annotation,QColor('#171c25'));painter.end()
        frame=self.state.validate_frame(latest,pointer=self.point,shop_context=self.area,
            exclude=[annotation],source_exclusions=lambda panel:[annotation])
        self.assertFalse(frame.retired);self.assertEqual(self.state.rows[0]['price']['mesos'],100)

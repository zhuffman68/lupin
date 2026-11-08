"""Verified portal coordinates, compact map interaction and navigation."""
import hashlib
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QPoint,QPointF,Qt
from PySide6.QtGui import QColor,QImage,QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QToolTip

from price_lens.reference_geometry import MapGeometry,PORTALS,RENDERS,verified_portals,preview_png
from price_lens.reference_maps import MapPreview
from price_lens.reference_data import ReferenceStore
from test_reference import documents,generation,allow_fixture
from test_reference_ui import ANIMATION,FakeMedia
import test_reference_ui as fixtures


def portal(**values):
    return {**dict(name='east',type=2,x=6,y=6,dest_map_id=101,dest_portal='west'),**values}


def canonical(point):
    return {**{key:value for key,value in point.items() if key!='dest_map_id'},'dest_map':str(point['dest_map_id'])}


class PortalGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.store=ReferenceStore(Path(self.folder.name)/'reference.sqlite')
        self.digest=hashlib.md5(ANIMATION).hexdigest()
        self.row=dict(id=100,render_url='https://osmsdataexplorer.com/data/maps/'+self.digest+'.webp',portals=[portal()])
        self.calls=[]
        def fetch_json(url):
            self.calls.append(url)
            return {'000000100':[canonical(portal())]} if url==PORTALS else {'000000100':self.digest}
        self.service=MapGeometry(self.store,fetch_json=fetch_json,fetch_bytes=lambda url:self.bytes(url))
        self.addCleanup(self.service.close)

    def bytes(self,url):self.calls.append(url);return ANIMATION

    def settle(self):
        deadline=time.monotonic()+3
        while self.service.pending and time.monotonic()<deadline:QTest.qWait(5)
        self.assertIsNone(self.service.pending)

    def test_single_portal_uses_published_render_coordinates_without_guessing_spawn_alignment(self):
        self.service.select(self.row);self.settle();proof=self.service.cached(self.row)
        self.assertEqual(proof['portals'],[portal()]);self.assertEqual(proof['anchors'],0)
        self.assertFalse(proof['spawns_verified']);self.assertFalse(proof['projection_verified'])
        self.assertTrue(proof['preview']);self.assertFalse(self.service.preview(self.row).isNull())
        self.service.select(self.row);self.assertIsNone(self.service.pending)
        self.assertEqual(self.calls,[PORTALS,RENDERS,self.row['render_url']])

    def test_manifest_change_cannot_place_current_portals_on_a_different_render(self):
        self.service.fetch_json=lambda url:({'000000100':[canonical(portal())]} if url==PORTALS else {'000000100':'a'*32})
        self.service.select(self.row);self.settle();self.assertIsNone(self.service.cached(self.row))
        self.assertEqual(self.calls,[])
        self.service.select(self.row);self.assertIsNone(self.service.pending)

    def test_deleted_preview_is_regenerated_without_redownloading_both_indexes(self):
        self.service.select(self.row);self.settle()
        next(self.service.preview_folder.glob('*.png')).unlink()
        self.service.select(self.row);self.settle()
        self.assertEqual(self.calls.count(PORTALS),1);self.assertEqual(self.calls.count(RENDERS),1)
        self.assertEqual(self.calls.count(self.row['render_url']),2);self.assertFalse(self.service.preview(self.row).isNull())

    def test_ambiguous_changed_scripted_and_unlinked_exits_never_get_a_destination(self):
        point=portal();row=dict(portals=[point])
        self.assertEqual(verified_portals(row,[canonical(point)]),[point])
        for candidates in ([canonical(point),canonical(point)],[canonical({**point,'dest_map_id':102})],
                           [{**canonical(point),'dest_portal':'other'}],[{**canonical(point),'x':False}]):
            self.assertEqual(verified_portals(row,candidates),[])
        for point in (portal(type=6),portal(type=True),portal(dest_map_id=999999999),portal(dest_map_id=True),portal(name='')):
            self.assertEqual(verified_portals(dict(portals=[point]),[canonical(point)]),[])
        hidden=portal(type=3)
        self.assertEqual(verified_portals(dict(portals=[hidden]),[canonical(hidden)]),[hidden])

    def test_invalid_or_large_native_data_is_not_decoded_into_a_preview(self):
        self.assertIsNone(preview_png(b'not a map'))
        with patch('price_lens.reference_geometry.QImageReader') as Reader:
            from PySide6.QtCore import QSize
            Reader.return_value.size.return_value=QSize(6000,4000)
            Reader.return_value.supportsOption.return_value=False
            self.assertIsNone(preview_png(ANIMATION));Reader.return_value.read.assert_not_called()

    def test_thumbnail_and_current_coordinate_cache_remain_bounded(self):
        self.service.preview_folder.mkdir()
        for index in range(70):(self.service.preview_folder/(str(index)+'.png')).write_bytes(b'x')
        from price_lens.http_json import RequestToken
        self.assertTrue(self.service.save_preview(self.row,ANIMATION,RequestToken()))
        self.assertLessEqual(len(list(self.service.preview_folder.glob('*.png'))),64)


class MapInteractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.image=QImage(200,100,QImage.Format.Format_RGB32);self.image.fill(QColor('#577456'))
        owner=self
        class Media(FakeMedia):
            def image(self,url):return owner.image
        self.row=dict(id=100,minimap_url='fixture',mobs=[dict(mob_id=13,x=50,y=50)])
        self.view=MapPreview(Media(),self.row);self.view.resize(420,156)
        self.point=portal(x=150,y=50)
        self.proof=dict(width=200,height=100,dx=0,dy=0,projection_verified=True,portals=[self.point])
        self.targets={101:dict(name='Mushroom Garden',target=('maps',101))}
        self.view.set_geometry(self.proof,{13:'Green Mushroom'},self.targets)
        self.view.show();self.app.processEvents();self.view.grab()
        self.addCleanup(self.view.close)

    def test_portal_and_monster_have_independent_names_and_click_targets(self):
        maps=[];monsters=[];self.view.map_chosen.connect(maps.append);self.view.chosen.connect(monsters.append)
        center,point,_=self.view.portal_markers[0]
        QTest.mouseMove(self.view,center.toPoint());self.app.processEvents()
        self.assertIn('Mushroom Garden',QToolTip.text())
        QTest.mouseClick(self.view,Qt.MouseButton.LeftButton,pos=center.toPoint())
        center,identity=self.view.markers[0];QTest.mouseClick(self.view,Qt.MouseButton.LeftButton,pos=center.toPoint())
        self.assertEqual(maps,[101]);self.assertEqual(monsters,[13])

    def test_unconfirmed_and_same_map_destinations_never_open_another_entry(self):
        chosen=[];self.view.map_chosen.connect(chosen.append)
        self.view.set_geometry(self.proof,{},{});self.view.grab()
        QTest.mouseClick(self.view,Qt.MouseButton.LeftButton,pos=self.view.portal_markers[0][0].toPoint())
        proof={**self.proof,'portals':[portal(x=150,y=50,dest_map_id=100)]}
        self.view.set_geometry(proof,{}, {100:dict(name='Current map',target=('maps',100))});self.view.grab()
        QTest.mouseClick(self.view,Qt.MouseButton.LeftButton,pos=self.view.portal_markers[0][0].toPoint())
        self.assertEqual(chosen,[])

    def test_layer_controls_toggle_only_their_own_markers_and_restore_with_the_view(self):
        self.view.spawns_button.setChecked(False);self.view.grab()
        self.assertEqual(self.view.markers,[]);self.assertEqual(len(self.view.portal_markers),1)
        self.view.portals_button.setChecked(False);self.view.grab();self.assertEqual(self.view.portal_markers,[])
        state=self.view.view_state();self.view.spawns_button.setChecked(True);self.view.restore_view(state)
        self.assertFalse(self.view.spawns_button.isChecked());self.assertFalse(self.view.portals_button.isChecked())

    def test_wheel_keeps_the_point_under_cursor_fixed_and_fit_clears_pan(self):
        self.view.zoom_at(3)
        anchor=self.view.viewport_rect().center()+QPointF(30,0);old=self.view.target_rect()
        normalized=(anchor.x()-old.left())/old.width()
        event=QWheelEvent(anchor,QPointF(self.view.mapToGlobal(anchor.toPoint())),QPoint(),QPoint(0,120),
            Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.NoScrollPhase,False)
        QApplication.sendEvent(self.view,event);self.app.processEvents()
        self.assertGreater(self.view.zoom,1)
        new=self.view.target_rect();self.assertAlmostEqual((anchor.x()-new.left())/new.width(),normalized)
        QTest.mouseClick(self.view.fit_button,Qt.MouseButton.LeftButton)
        self.assertEqual(self.view.zoom,1);self.assertEqual(self.view.pan,QPointF())
        self.assertFalse(self.view.zoom_out.isEnabled())

    def test_dragging_pans_without_opening_a_portal_and_clamps_inside_the_view(self):
        self.view.zoom_at(4);self.view.grab();chosen=[];self.view.map_chosen.connect(chosen.append)
        start=self.view.viewport_rect().center().toPoint();end=start+QPoint(35,15)
        QTest.mousePress(self.view,Qt.MouseButton.LeftButton,pos=start)
        QTest.mouseMove(self.view,end,20);QTest.mouseRelease(self.view,Qt.MouseButton.LeftButton,pos=end)
        self.assertNotEqual(self.view.pan,QPointF());self.assertEqual(chosen,[])
        self.view.zoom_at(100);self.assertEqual(self.view.zoom,self.view.MAX_ZOOM)
        self.view.pan=QPointF(1e6,-1e6);self.view.clamp_pan()
        target=self.view.target_rect();viewport=self.view.viewport_rect()
        self.assertLessEqual(target.left(),viewport.left());self.assertGreaterEqual(target.right(),viewport.right())
        self.assertLessEqual(target.top(),viewport.top());self.assertGreaterEqual(target.bottom(),viewport.bottom())

    def test_markers_follow_zoom_and_geometry_loss_clears_old_targets(self):
        center=self.view.portal_markers[0][0]
        self.view.zoom_at(1.5);self.view.grab()
        self.assertNotEqual(center,self.view.portal_markers[0][0])
        self.assertIsNotNone(self.view.portal_at(self.view.portal_markers[0][0]))
        self.view.set_geometry(None);self.assertIsNone(self.view.portal_at(center))
        self.view.grab();self.assertEqual(self.view.portal_markers,[]);self.assertEqual(self.view.markers,[])

    def test_unverified_minimap_gets_no_markers_until_a_verified_render_preview_arrives(self):
        proof={**self.proof,'projection_verified':False,'preview':True}
        self.view.set_geometry(proof,{},self.targets);self.view.grab();self.assertEqual(self.view.portal_markers,[])
        self.view.set_geometry(proof,{},self.targets,self.image);self.view.grab();self.assertEqual(len(self.view.portal_markers),1)

    def test_tall_map_zoom_reveals_more_detail_without_changing_panel_height(self):
        self.image=QImage(40,400,QImage.Format.Format_RGB32);self.image.fill(QColor('#577456'))
        self.view.set_geometry(None);self.view.fit();before=self.view.target_rect();height=self.view.height()
        QTest.mouseClick(self.view.zoom_in,Qt.MouseButton.LeftButton)
        after=self.view.target_rect();self.assertGreater(after.width(),before.width());self.assertEqual(self.view.height(),height)
        state=self.view.view_state();self.view.fit();self.view.restore_view(state);self.assertEqual(self.view.zoom,state['zoom'])
        self.view.restore_view(dict(zoom=float('nan'),x=0,y=0));self.assertEqual(self.view.zoom,state['zoom'])


class PortalNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):fixtures.DatabaseUiTests.setUp(self)
    def tearDown(self):fixtures.DatabaseUiTests.tearDown(self)

    def test_destination_click_and_back_restore_the_original_map_zoom_and_tab(self):
        docs=documents();point=portal(x=60,y=50)
        docs['maps.json'][0]['portals']=[point]
        docs['maps.json'].append(dict(id=101,name='Garden Exit',region='Victoria Island',exits=[100]))
        self.service.store.replace(*generation(docs));allow_fixture(self.service.store)
        image=QImage(100,100,QImage.Format.Format_RGB32);image.fill(QColor('#577456'))
        self.media.image=lambda url:image
        proof=dict(width=100,height=100,dx=0,dy=0,projection_verified=True,portals=[point])
        with patch.object(self.service.geometry,'select'),patch.object(self.service.geometry,'cached',side_effect=lambda row:proof if row['id']==100 else None):
            self.panel.open(('maps',100));self.app.processEvents();detail=self.panel.detail
            self.panel.geometry_updated(100)
            detail.map_preview.zoom_at(1.5);self.app.processEvents();detail.map_preview.grab()
            center=detail.map_preview.portal_markers[0][0];detail.tabs.setCurrentIndex(1)
            QTest.mouseClick(detail.map_preview,Qt.MouseButton.LeftButton,pos=center.toPoint())
            self.assertEqual(self.panel.selected.key,('maps',101))
            self.panel.go_back();self.app.processEvents()
            self.assertEqual(self.panel.selected.key,('maps',100))
            self.assertEqual(self.panel.detail.tabs.currentIndex(),1)
            self.assertEqual(self.panel.detail.map_preview.zoom,1.5)

"""Age ticks keep market captions steady while their digits roll."""
import unittest

from PySide6.QtCore import QCoreApplication,QEvent
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from price_lens.search import PriceSearch


def message(checked='31s',published='1h 46m',retry='29s'):
    return ('1,422 market prices cached · checked '+checked+' ago\n'
            'source snapshot old · published '+published+' ago · retry in '+retry)


class MarketStatusMotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.app.setProperty('reduceMotion',False)
        self.panel=PriceSearch();self.panel.resize(460,700);self.panel.show()
        self.panel.set_market_status(message(),True);self.app.processEvents()
        status=self.panel.market_status
        if getattr(status,'_reveal',None):status._reveal.setCurrentTime(85)
        self.app.processEvents()

    def tearDown(self):
        self.panel.timer.stop();self.panel.close();self.panel.deleteLater()
        self.app.setProperty('reduceMotion',False)
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.app.processEvents()

    def test_multiline_age_tick_keeps_caption_pixels_and_row_geometry(self):
        status=self.panel.market_status;rows=tuple(status.lines)
        geometry=[row.geometry() for row in rows]
        before=[row.grab().toImage().copy(0,0,130,row.height()) for row in rows]
        self.panel.set_market_status(message('32s',retry='28s'),True)
        self.assertEqual(tuple(status.lines),rows)
        for row,expected in zip(rows,before):
            self.assertEqual(row.animation.state(),row.animation.State.Running)
            row.animation.setCurrentTime(80)
            self.assertEqual(row.grab().toImage().copy(0,0,130,row.height()),expected)
            row.animation.setCurrentTime(160)
            self.assertEqual(row.grab().toImage().copy(0,0,130,row.height()),expected)
        self.app.processEvents()
        self.assertEqual([row.geometry() for row in rows],geometry)

    def test_unit_boundary_rolls_without_fading_the_static_prefix(self):
        status=self.panel.market_status;row=status.lines[0]
        self.panel.set_market_status(message('59s'),True);row.animation.setCurrentTime(160)
        before=row.grab().toImage().copy(0,0,130,row.height())
        self.panel.set_market_status(message('1m'),True)
        self.assertEqual(row.animation.state(),row.animation.State.Running)
        row.animation.setCurrentTime(80)
        self.assertEqual(row.grab().toImage().copy(0,0,130,row.height()),before)
        self.assertIs(row,status.lines[0])

    def test_hidden_and_reduced_motion_updates_do_no_animation_work(self):
        status=self.panel.market_status
        self.panel.set_market_status(message('32s'),True)
        self.panel.hide()
        self.assertTrue(all(row.animation.state()==row.animation.State.Stopped for row in status.lines))
        self.panel.set_market_status(message('33s'),True)
        self.assertTrue(all(row.roll.progress==1 for row in status.lines))
        self.app.setProperty('reduceMotion',True);self.panel.show();self.app.processEvents()
        self.panel.set_market_status(message('34s'),True)
        self.assertTrue(all(row.animation.state()==row.animation.State.Stopped for row in status.lines))
        self.assertTrue(all(row.roll.progress==1 for row in status.lines))

    def test_long_diagnostic_wraps_and_the_same_message_can_change_warning_colour(self):
        text='The market source could not be loaded; saved prices are kept. '+('Please retry later. '*8)
        self.panel.set_market_status(text,True);self.app.processEvents()
        row=self.panel.market_status.lines[0]
        self.assertGreater(row.height(),row.fontMetrics().height())
        self.assertLessEqual(row.width(),self.panel.width())
        warning=row.palette().color(QPalette.ColorRole.WindowText)
        self.panel.set_market_status(text,False);self.app.processEvents()
        self.assertIs(row,self.panel.market_status.lines[0])
        self.assertNotEqual(row.palette().color(QPalette.ColorRole.WindowText),warning)
        self.assertEqual(self.panel.market_status.text(),text)

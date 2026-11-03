"""Arrival fixtures through production capture admission and the tracking panel."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from price_lens.capture import PixelReader
from price_lens.experience_ui import ExperiencePanel
from test_experience import payload
from test_tracking_identity import proof


class TrackingDeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.now=1000.0
        self.clock=patch('price_lens.capture.time.monotonic',lambda:self.now)
        self.clock.start()
        self.panel=ExperiencePanel(Path(self.folder.name)/'tracking.sqlite')
        self.panel.set_connected(True);self.panel.start()
        self.panel.feed({'atMs':1_000_000,'experience':{**payload(),'nameProof':proof()}})
        self.metrics=self.panel.metrics
        self.capture=SimpleNamespace(tracking_ready=True,experience_enabled=True,pickups_enabled=True,
            generation=3,tracking_epoch=self.panel.tracking_epoch,pickup_covered_at=0,metrics=self.metrics,
            experience=SimpleNamespace(emit=self.panel.feed),
            pickup_status=SimpleNamespace(emit=self.panel.set_pickup_issue))

    def tearDown(self):
        self.panel.close_session();self.panel.deleteLater();self.app.processEvents()
        self.clock.stop();self.folder.cleanup()

    def deliver(self,at,pickups,**fields):
        packet={'atMs':round(at*1000),'captureGeneration':3,'trackingEpoch':self.capture.tracking_epoch,
                'pickupsRead':True,'pickupNameProof':proof(),'pickups':pickups,**fields}
        PixelReader.on_pickup_result(self.capture,packet)

    def test_annotated_scroll_fade_burst_survives_live_exp_confirmation_and_deliveries(self):
        trace=json.loads((Path(__file__).parent/'fixtures/pickup-burst.json').read_text())
        self.now+=.05
        self.panel.feed({'atMs':round(self.now*1000),'experience':{**payload(100,20000,30),'nameProof':proof()}})
        self.assertIsNotNone(self.panel.tracker.candidate)
        for frame in trace['frames']:
            at=1000+frame['atMs']/1000;self.now=at+.05
            self.deliver(at,frame['pickups'])
            self.deliver(at,frame['pickups'])
        self.assertEqual(self.panel.mesos.gain,trace['expected_gain'])
        self.assertIsNotNone(self.panel.tracker.candidate)
        self.assertEqual(self.metrics.counts['pickup.delivered'],2*len(trace['frames']))
        self.assertEqual(self.metrics.counts['pickup.accepted'],2*len(trace['frames']))

    def test_stale_and_foreign_session_results_never_reach_the_arrival_ledger(self):
        empty={'valid':True,'state':'empty','lines':[]}
        self.now=1002
        self.deliver(1000,empty)
        self.deliver(1002,empty,trackingEpoch=self.capture.tracking_epoch-1)
        self.deliver(1002,empty,captureGeneration=2)
        self.assertFalse(self.panel.mesos.observed)
        self.assertEqual(self.panel.pickup_issue,'late_frame')
        for reason in ('late_frame','old_session','old_capture'):
            self.assertEqual(self.metrics.counts['pickup.'+reason],1)
        self.deliver(1002,empty)
        self.assertTrue(self.panel.mesos.observed)
        self.assertEqual(self.panel.pickup_issue,'')

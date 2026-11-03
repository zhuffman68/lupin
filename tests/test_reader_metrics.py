"""Diagnostics must be bounded, numeric and independent of captured text."""
import json
import os
from pathlib import Path
import tempfile
import unittest

from price_lens.reader_metrics import ReaderMetrics


class ReaderMetricsTests(unittest.TestCase):
    def test_long_stream_retains_only_bounded_samples_and_fixed_size_event_set(self):
        metrics=ReaderMetrics()
        for i in range(1000):metrics.record('pickup.delivered',duration_ms=i,age_ms=i/2)
        self.assertEqual(metrics.counts['pickup.delivered'],1000)
        self.assertEqual(len(metrics.samples),metrics.MAX_SAMPLES)
        for i in range(100):metrics.record(f'event_{i}')
        self.assertEqual(len(metrics.counts),metrics.MAX_EVENTS)
        snapshot=metrics.snapshot();snapshot['counts'].clear()
        self.assertEqual(len(metrics.counts),metrics.MAX_EVENTS)

    def test_invalid_names_and_nonfinite_or_nonnumeric_values_never_enter_diagnostics(self):
        metrics=ReaderMetrics()
        metrics.record('some chat text');metrics.record('x'*65)
        metrics.record('pickup.delivered',duration_ms='private',age_ms=float('nan'))
        metrics.record('pickup.delivered',duration_ms=True,age_ms=-1)
        self.assertEqual(metrics.snapshot(),{'counts':{'pickup.delivered':2},'samples':[]})
        self.assertNotIn('private',json.dumps(metrics.snapshot()))

    def test_optional_export_is_atomic_private_and_nonfatal_on_a_missing_directory(self):
        metrics=ReaderMetrics();metrics.record('pickup.delivered',age_ms=25)
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'reader.json'
            self.assertTrue(metrics.write(target))
            self.assertEqual(json.loads(target.read_text()),metrics.snapshot())
            if os.name!='nt':self.assertEqual(target.stat().st_mode&0o777,0o600)
            self.assertEqual(list(Path(folder).glob('.lupin-reader-*')),[])
            self.assertFalse(metrics.write(Path(folder)/'missing'/'reader.json'))
            self.assertEqual(metrics.counts['diagnostics.write_failed'],1)

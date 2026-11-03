"""Bounded, local numeric diagnostics; never retain OCR text or captured pixels."""
from collections import Counter, deque
import json
import math
from pathlib import Path
import re
import tempfile


class ReaderMetrics:
    MAX_EVENTS = 64
    MAX_SAMPLES = 240

    def __init__(self):
        self.counts = Counter()
        self.samples = deque(maxlen=self.MAX_SAMPLES)

    def record(self, event, *, duration_ms=None, age_ms=None):
        # Callers use fixed event codes. Bound even an accidental dynamic caller.
        if (not isinstance(event, str) or not re.fullmatch(r"[a-z0-9_.]{1,64}", event)
                or event not in self.counts and len(self.counts) >= self.MAX_EVENTS):
            return
        self.counts[event] += 1
        sample = {"event": event}
        for key, value in (("duration_ms", duration_ms), ("age_ms", age_ms)):
            if type(value) in (int, float) and math.isfinite(value) and value >= 0:
                sample[key] = round(value, 3)
        if len(sample) > 1:
            self.samples.append(sample)

    def snapshot(self):
        return {"counts": dict(self.counts), "samples": [dict(sample) for sample in self.samples]}

    def write(self, path):
        """Optional developer export; ordinary runs do no diagnostics file I/O."""
        target=Path(path);temporary=None
        try:
            with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=target.parent,
                    prefix='.lupin-reader-',delete=False) as stream:
                temporary=Path(stream.name)
                json.dump(self.snapshot(),stream)
                stream.write('\n')
            temporary.replace(target)
            return True
        except OSError:
            self.record('diagnostics.write_failed')
            return False
        finally:
            if temporary is not None:
                try:temporary.unlink(missing_ok=True)
                except OSError:pass

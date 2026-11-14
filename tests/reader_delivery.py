"""Finish an explicitly supplied reply without submitting another fixture read."""
import time
from unittest.mock import patch
from PySide6.QtTest import QTest


def finish_source_check(reader):
    deadline=time.monotonic()+3
    with patch.object(reader,'scan'):
        while (reader.source_check.busy or reader.source_check.ready is not None) and time.monotonic()<deadline:
            QTest.qWait(2)
    if reader.source_check.busy or reader.source_check.ready is not None:
        raise AssertionError('Source classification did not finish')

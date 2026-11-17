"""Short-lived arrivals survive a busy worker without replaying old contexts."""
import unittest

from PySide6.QtGui import QColor, QImage

from price_lens.pickup_capture import PickupFrames


class Worker:
    def __init__(self):
        self.pending = False
        self.ready = True
        self.requests = []

    def submit(self, *frame):
        if not self.ready:
            return False
        self.requests.append(frame)
        self.pending = True
        return True


class PickupFramesTests(unittest.TestCase):
    def setUp(self):
        self.frames = PickupFrames()
        self.worker = Worker()

    def add(self, at, *, generation=3, epoch=7):
        image = QImage(256, 128, QImage.Format.Format_RGBA8888)
        image.fill(QColor('#172634'))
        self.frames.add(image, at, generation, epoch, {'captured': at})
        return image

    def test_busy_worker_keeps_intermediate_arrivals_in_capture_order(self):
        self.worker.pending = True
        for at in (10, 10.15, 10.3):
            self.add(at)
            self.assertFalse(self.frames.submit(self.worker, 10.4, 3, 7))
        for at in (10, 10.15, 10.3):
            self.worker.pending = False
            self.assertTrue(self.frames.submit(self.worker, 10.5, 3, 7))
            self.assertEqual(self.worker.requests[-1][1], at)
            self.assertEqual(self.worker.requests[-1][-1], {'captured': at})
        self.assertFalse(self.frames.frames)

    def test_late_foreign_and_covered_frames_cannot_reach_worker(self):
        self.add(9.0)
        self.add(10.0, generation=2)
        self.add(10.1, epoch=6)
        self.add(10.2)
        self.add(10.3)
        self.assertTrue(self.frames.submit(self.worker, 10.5, 3, 7, covered_at=10200))
        self.assertEqual([frame[1] for frame in self.worker.requests], [10.3])
        self.worker.pending = False
        self.add(10.6)
        self.assertFalse(self.frames.submit(self.worker, 11.6, 3, 7))
        self.assertEqual(len(self.worker.requests), 1)

    def test_duplicates_old_captures_and_excess_backlog_stay_bounded(self):
        for _ in range(100):
            self.add(10)
        self.add(9.9)
        self.assertEqual(len(self.frames.frames), 1)
        for index in range(100):
            self.add(10.01 + index*.001)
            self.assertLessEqual(len(self.frames.frames), PickupFrames.MAX_FRAMES)
        self.assertEqual(len(self.frames.frames), PickupFrames.MAX_FRAMES)
        self.assertAlmostEqual(self.frames.frames[0][1], 10.104)

    def test_starting_worker_does_not_drop_the_first_valid_frame(self):
        self.add(10)
        self.worker.ready = False
        self.assertFalse(self.frames.submit(self.worker, 10.1, 3, 7))
        self.assertEqual(len(self.frames.frames), 1)
        self.worker.ready = True
        self.assertTrue(self.frames.submit(self.worker, 10.2, 3, 7))
        self.assertEqual(self.worker.requests[0][1], 10)

    def test_crop_owns_its_pixels_and_clear_revokes_every_queued_frame(self):
        image = self.add(10)
        image.fill(QColor('red'))
        self.assertTrue(self.frames.submit(self.worker, 10.1, 3, 7))
        self.assertEqual(self.worker.requests[0][0].pixelColor(0, 0), QColor('#172634'))
        self.add(10.2)
        self.frames.clear()
        self.assertFalse(self.frames.frames)
        self.assertIsNone(self.frames.latest)
        self.assertIsNone(self.frames.submitted_at)

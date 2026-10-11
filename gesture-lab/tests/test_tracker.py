"""Scheduling tests run without a camera, MediaPipe, NumPy or OpenCV."""
import argparse
from contextlib import contextmanager
import threading
import time
import unittest

from tracker import LatestInference, register_arguments


class LatestInferenceTests(unittest.TestCase):
    def test_only_newest_pending_frame_runs_while_inference_is_busy(self):
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        calls, lifecycle = [], []

        @contextmanager
        def factory():
            lifecycle.append(("open", threading.get_ident()))
            yield object()
            lifecycle.append(("close", threading.get_ident()))

        def infer(model, frame, timestamp):
            calls.append(frame)
            if frame == 1:
                entered.set()
                self.assertTrue(release.wait(2))
            else:
                finished.set()
            return [frame]

        worker = LatestInference(factory, infer, threading.Event())
        worker.start()
        try:
            stamp = int(time.monotonic() * 1000)
            worker.submit((1, stamp, 1, "gray1"))
            self.assertTrue(entered.wait(2))
            for seq in range(2, 31):
                worker.submit((seq, stamp + seq, seq, f"gray{seq}"))
            self.assertIsNone(worker.newest_after(0))
            self.assertEqual(worker.dropped, 28)
            release.set()
            self.assertTrue(finished.wait(2))
        finally:
            release.set()
            worker.close()
        self.assertEqual(calls, [1, 30])
        result = worker.newest_after(1)
        self.assertEqual(result["sequence"], 30)
        self.assertEqual(result["gray"], "gray30")
        self.assertEqual(result["detections"], [30])
        self.assertIsNone(worker.newest_after(30))
        self.assertEqual([item[0] for item in lifecycle], ["open", "close"])
        self.assertEqual(lifecycle[0][1], lifecycle[1][1])
        self.assertNotEqual(lifecycle[0][1], threading.get_ident())

    def test_expired_pending_image_is_discarded_before_inference(self):
        called = []

        @contextmanager
        def factory():
            yield None

        worker = LatestInference(factory, lambda *args: called.append(args), threading.Event())
        # Queue before startup: a stale camera image must never reach MediaPipe.
        worker.submit((1, int(time.monotonic() * 1000) - 1000, 1, None))
        worker.start()
        try:
            self.assertTrue(worker.ready.wait(2))
            deadline = time.monotonic() + 2
            while worker.pending is not None and time.monotonic() < deadline:
                time.sleep(0.001)
            self.assertIsNone(worker.pending)
            self.assertEqual(called, [])
        finally:
            worker.close()

    def test_model_failure_reaches_caller_and_closes_worker(self):
        @contextmanager
        def factory():
            raise ValueError("model unavailable")
            yield

        worker = LatestInference(factory, None, threading.Event())
        worker.start()
        worker.thread.join(2)
        with self.assertRaisesRegex(RuntimeError, "model unavailable"):
            worker.newest_after(0)
        worker.close()
        self.assertFalse(worker.thread.is_alive())

    def test_default_single_hand_and_optional_two_hands(self):
        parser = argparse.ArgumentParser()
        register_arguments(parser)
        defaults = parser.parse_args([])
        self.assertEqual(defaults.max_hands, 1)
        self.assertEqual(defaults.processing_width, 640)
        self.assertEqual(parser.parse_args(["--max-hands", "2"]).max_hands, 2)


if __name__ == "__main__":
    unittest.main()

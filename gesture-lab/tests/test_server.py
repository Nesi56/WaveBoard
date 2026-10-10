"""Latest-only bridge state; no sockets or camera packages are needed."""

import unittest
from unittest.mock import patch

from server import LatestState


class LatestStateTests(unittest.TestCase):
    def test_stale_frames_are_not_replayed(self):
        state = LatestState()
        frame = {"type": "frame", "seq": 1}
        with patch("server.time.monotonic", return_value=10):
            state.publish(frame)
        with patch("server.time.monotonic", return_value=10.49):
            self.assertEqual(state.snapshot()[2], frame)
        with patch("server.time.monotonic", return_value=10.5):
            self.assertIsNone(state.snapshot()[2])

    def test_new_frame_overwrites_old_frame(self):
        state = LatestState()
        with patch("server.time.monotonic", return_value=10):
            state.publish({"type": "frame", "seq": 1})
            state.publish({"type": "frame", "seq": 2})
            version, _, frame = state.snapshot()
        self.assertEqual(version, 2)
        self.assertEqual(frame["seq"], 2)

    def test_status_persists_after_frames_expire(self):
        state = LatestState()
        status = {"type": "status", "level": "error", "message": "Camera unavailable"}
        with patch("server.time.monotonic", return_value=10):
            state.publish({"type": "frame", "seq": 1})
            state.publish(status)
        with patch("server.time.monotonic", return_value=20):
            _, latest_status, frame = state.snapshot()
        self.assertEqual(latest_status, status)
        self.assertIsNone(frame)

    def test_error_status_immediately_invalidates_latest_frame(self):
        state = LatestState()
        with patch("server.time.monotonic", return_value=10):
            state.publish({"type": "frame", "seq": 1, "gesture": {"mode": "grab"}})
            state.publish({"type": "status", "level": "error", "message": "Camera disconnected"})
            _, status, frame = state.snapshot()
        self.assertEqual(status["level"], "error")
        self.assertIsNone(frame)

    def test_nonfinite_json_is_rejected_without_changing_state(self):
        state = LatestState()
        for invalid in (float("nan"), float("inf"), -float("inf")):
            with self.subTest(value=invalid):
                with self.assertRaises(ValueError):
                    state.publish({"type": "frame", "hands": [{"point": [0.5, invalid]}]})
        self.assertEqual(state.version, 0)
        self.assertIsNone(state.frame)


if __name__ == "__main__":
    unittest.main()

"""Latest-only bridge state and the localhost stream; no camera packages are needed."""

import asyncio
import json
import socket
import threading
import unittest
from unittest.mock import patch

import server
from server import LatestState, loopback_hosts


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


class LocalhostStreamTests(unittest.TestCase):
    def test_loopback_hosts_without_ipv6_is_ipv4_only(self):
        with patch("server.socket.socket", side_effect=OSError(97, "Address family not supported")):
            self.assertEqual(loopback_hosts(), ["127.0.0.1"])

    def test_workspace_page_on_localhost_receives_the_stream(self):
        from websockets.sync.client import connect

        with socket.socket() as finder:
            finder.bind(("127.0.0.1", 0))
            port = finder.getsockname()[1]
        state, stop, ready = LatestState(), threading.Event(), threading.Event()

        def run_bridge():
            async def main():
                task = asyncio.ensure_future(server.bridge(state, stop))
                await asyncio.sleep(0.3)
                ready.set()
                await task
            asyncio.run(main())

        with patch.object(server, "BRIDGE_PORT", port):
            thread = threading.Thread(target=run_bridge, daemon=True)
            thread.start()
            self.assertTrue(ready.wait(5))
            try:
                with connect(f"ws://localhost:{port}", origin="http://localhost:8765", open_timeout=5) as page:
                    self.assertEqual(json.loads(page.recv(timeout=5))["type"], "status")
            finally:
                stop.set()
                thread.join(timeout=5)

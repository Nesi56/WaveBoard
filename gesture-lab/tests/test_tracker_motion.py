"""Real sparse optical-flow regressions with deterministic synthetic images.

Uses the OpenCV/NumPy already installed by gesture-lab/setup.sh. Skips only these
image tests when running the pure-Python gesture suite outside that environment.
"""
import copy
import argparse
from contextlib import contextmanager
import sys
import threading
import time
import types
import unittest
from unittest.mock import patch

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = np = None

from hand_pointer import HandPointer
from tracker_motion import HandMotionBridge
import tracker


def hand():
    points = [[0.5, 0.5, 0.0] for _ in range(21)]
    for i, xy in {0: (.5, .72), 1: (.32, .6), 5: (.35, .35),
                  9: (.48, .3), 13: (.62, .35), 17: (.67, .55),
                  4: (.45, .3), 8: (.55, .3)}.items():
        points[i][:2] = xy
    return {"id": "right-1", "landmarks": points, "palm": [.5, .5],
            "observed": True, "pinches": {"index": False, "middle": False, "ring": False, "pinky": False},
            "fingers": {"index": True, "middle": False, "ring": False, "pinky": False}}


@unittest.skipIf(cv2 is None, "requires OpenCV and NumPy from the tracker environment")
class HandMotionTests(unittest.TestCase):
    def setUp(self):
        cv2.setNumThreads(1)
        self.gray = np.random.default_rng(19).integers(0, 256, (240, 320), dtype=np.uint8)
        self.gray = cv2.GaussianBlur(self.gray, (3, 3), 0)
        self.bridge = HandMotionBridge(cv2, np)
        self.bridge.advance(self.gray, 0)
        self.bridge.observe([hand()], self.gray, 0)

    def shifted(self, x, y=0):
        return cv2.warpAffine(self.gray, np.float32([[1, 0, x], [0, 1, y]]), (320, 240))

    def test_camera_frames_move_hand_between_landmark_detections(self):
        original = copy.deepcopy(hand())
        for frame in range(1, 10):
            self.bridge.advance(self.shifted(frame * 4, frame * 2), frame * 33)
            tracked = self.bridge.hands()[0]
            self.assertFalse(tracked["observed"])
            self.assertFalse(tracked["predicted"])
            self.assertEqual(tracked["tracking_source"], "flow")
            self.assertAlmostEqual(tracked["palm"][0], .5 + frame * 4 / 320, delta=.003)
            self.assertAlmostEqual(tracked["palm"][1], .5 + frame * 2 / 240, delta=.003)
            self.assertEqual(tracked["pinches"], original["pinches"])

    def test_delayed_ai_result_replays_motion_to_current_camera_frame(self):
        for frame in range(1, 6):
            self.bridge.advance(self.shifted(frame * 5), frame * 33)
        self.bridge.observe([hand()], self.gray, 0)
        result = self.bridge.hands()[0]
        self.assertTrue(result["observed"])
        self.assertEqual(result["tracking_age_ms"], 165)
        self.assertAlmostEqual(result["palm"][0], .5 + 25 / 320, delta=.003)
        # No duplicate application of the same history on the next camera frame.
        self.bridge.advance(self.shifted(30), 198)
        self.assertAlmostEqual(self.bridge.hands()[0]["palm"][0], .5 + 30 / 320, delta=.003)

    def test_missing_detection_preserves_motion_but_observation_expires(self):
        for frame in range(1, 14):
            self.bridge.advance(self.shifted(frame * 2), frame * 33)
            self.bridge.observe([], self.shifted(frame * 2), frame * 33)
            self.assertEqual(len(self.bridge.hands()), 1)
        self.bridge.advance(self.shifted(28), 462)
        self.assertEqual(self.bridge.hands(), [])

    def test_occlusion_freezes_then_expires_without_dragging_background(self):
        before = self.bridge.hands()[0]["palm"][:]
        self.bridge.advance(np.zeros_like(self.gray), 33)
        held = self.bridge.hands()[0]
        self.assertTrue(held["predicted"])
        self.assertEqual(held["tracking_source"], "held")
        self.assertEqual(held["palm"], before)
        self.bridge.advance(self.shifted(100), 100)
        self.assertEqual(self.bridge.hands()[0]["palm"], before)
        self.bridge.advance(self.gray, 231)
        self.assertEqual(self.bridge.hands(), [])

    def test_held_engine_records_do_not_refresh_old_model_observations(self):
        held = {**hand(), "observed": False, "predicted": True}
        self.bridge.advance(self.shifted(4), 33)
        self.bridge.observe([held], self.shifted(4), 33)
        self.assertEqual(self.bridge.hands()[0]["observation_timestamp"], 0)

    def test_camera_resolution_change_discards_incompatible_history(self):
        self.bridge.advance(np.zeros((120, 160), dtype=np.uint8), 33)
        self.assertEqual(self.bridge.hands(), [])
        self.bridge.observe([hand()], self.gray, 0)
        self.assertEqual(self.bridge.hands(), [])

    def test_identity_changes_replace_old_tracks_within_hand_limit(self):
        for frame in range(1, 6):
            image = self.shifted(frame * 2)
            self.bridge.advance(image, frame * 33)
            new = {**hand(), "id": f"right-{frame + 1}"}
            self.bridge.observe([new], image, frame * 33)
            self.assertEqual([h["id"] for h in self.bridge.hands()], [new["id"]])

    def test_two_hand_mode_is_bounded_during_identity_churn(self):
        bridge = HandMotionBridge(cv2, np, max_hands=2)
        for frame in range(6):
            bridge.advance(self.gray, frame * 33)
            bridge.observe([{**hand(), "id": f"hand-{frame * 2 + i}"} for i in range(2)],
                           self.gray, frame * 33)
            self.assertEqual({h["id"] for h in bridge.hands()},
                             {f"hand-{frame * 2}", f"hand-{frame * 2 + 1}"})

    def test_future_observation_cannot_seed_negative_age_or_wrong_image(self):
        self.bridge.observe([{**hand(), "id": "future"}], self.gray, 33)
        self.assertEqual([h["id"] for h in self.bridge.hands()], ["right-1"])

    def test_flow_continues_pressed_drag_but_expiration_cancels(self):
        pressed = hand()
        pressed["pinches"]["index"] = True
        self.bridge.observe([pressed], self.gray, 0)
        pointer = HandPointer(reach=0, smoothing=False)
        first = pointer.update(self.bridge.hands(), 0, 4 / 3)
        self.assertTrue(first["down"])
        self.bridge.advance(self.shifted(20), 33)
        moved = pointer.update(self.bridge.hands(), 33, 4 / 3)
        self.assertTrue(moved["down"])
        self.assertGreater(moved["x"], first["x"])
        self.assertFalse(moved["observed"])
        self.bridge.advance(self.shifted(22), 462)
        lost = pointer.update(self.bridge.hands(), 462, 4 / 3)
        self.assertFalse(lost["down"])
        self.assertFalse(lost["visible"])
        self.assertTrue(lost["cancelled"])

    def test_slow_inference_does_not_block_camera_rate_pointer_output(self):
        """Exercise the complete worker with 30Hz capture and ~7Hz inference."""
        parser = argparse.ArgumentParser()
        tracker.register_arguments(parser)
        stop, released = threading.Event(), threading.Event()
        frames, statuses = [], []
        image = cv2.cvtColor(self.gray, cv2.COLOR_GRAY2BGR)

        class Camera:
            def read(self):
                stop.wait(1 / 30)
                return True, image.copy()

            def release(self):
                released.set()

        @contextmanager
        def model(options):
            yield object()

        def detect(*args):
            time.sleep(.14)
            return [{"handedness": "Right", "landmarks": hand()["landmarks"]}], args[4]

        def publish(packet):
            if packet["type"] == "frame":
                frames.append(packet)
                if len(frames) >= 45:
                    stop.set()
            else:
                statuses.append(packet)

        vision = types.ModuleType("mediapipe.tasks.python.vision")
        vision.HandLandmarker = types.SimpleNamespace(create_from_options=model)
        python = types.ModuleType("mediapipe.tasks.python")
        python.vision = vision
        tasks = types.ModuleType("mediapipe.tasks")
        tasks.python = python
        mp = types.ModuleType("mediapipe")
        mp.tasks = tasks
        modules = {"mediapipe": mp, "mediapipe.tasks": tasks,
                   "mediapipe.tasks.python": python, "mediapipe.tasks.python.vision": vision}
        camera_info = {"width": 320, "height": 240, "negotiated_fps": 30, "requested_fps": 30}
        with patch.dict(sys.modules, modules), patch.object(tracker, "landmarker_options", return_value=None), \
                patch.object(tracker, "open_camera", return_value=(Camera(), camera_info)), \
                patch.object(tracker, "detect_hands", side_effect=detect):
            worker = threading.Thread(target=tracker.run, args=(stop, publish, parser.parse_args([])), daemon=True)
            worker.start()
            worker.join(5)
            stop.set()
            worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertTrue(released.is_set())
        self.assertEqual([p for p in statuses if p.get("level") == "error"], [])
        self.assertEqual(len(frames), 45)
        fresh = [p for p in frames if p["pointer"]["observed"]]
        flowing = [p for p in frames if p["pointer"]["tracking_source"] == "flow"]
        self.assertGreater(len(fresh), 3)
        self.assertGreater(len(flowing), len(fresh) * 2)
        self.assertTrue(all(not p["pointer"]["down"] for p in frames))
        self.assertGreater(frames[-1]["tracking_fps"], frames[-1]["inference_fps"] * 2)
        print(f"\nSynthetic slow-model pipeline: {frames[-1]['tracking_fps']} pointer updates/s, "
              f"{frames[-1]['inference_fps']} model observations/s; "
              f"{len(flowing)} measured-flow packets, {len(fresh)} fresh observations")


if __name__ == "__main__":
    unittest.main()

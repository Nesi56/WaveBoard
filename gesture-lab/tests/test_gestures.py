"""Run from project root: python -m unittest discover -s tests -v"""

import json
import math
from pathlib import Path
import unittest

from gestures import FINGERS, TIPS, GestureEngine, HandIdentities, PinchState, finger_states, pinch_ratios


def open_points():
    points = [[0.0, 0.0, 0.0] for _ in range(21)]
    points[1:5] = [[-0.5, 0.2, 0], [-0.85, 0.45, 0], [-1.15, 0.65, 0], [-1.45, 0.85, 0]]
    for start, x in ((5, -0.4), (9, 0), (13, 0.3), (17, 0.6)):
        for offset in range(4):
            points[start + offset] = [x, 1 + offset * 0.5, 0]
    return points


def fake_hand(identity="left-1", pinch=None, opened=True, x=0.3):
    points = [[x, 0.5, 0.0] for _ in range(21)]
    return {"id": identity, "landmarks": points,
            "fingers": {name: opened for name in FINGERS},
            "pinches": {name: name == pinch for name in TIPS},
            "palm": [x, 0.5], "roll": 0.25}


class FingerGeometryTests(unittest.TestCase):
    def test_all_five_fingers_and_rotation_invariance(self):
        points = open_points()
        self.assertTrue(all(finger_states(points).values()))
        angle = 1.7
        rotated = [[x * math.cos(angle) - y * math.sin(angle),
                    x * math.sin(angle) + y * math.cos(angle), z] for x, y, z in points]
        self.assertEqual(finger_states(points), finger_states(rotated))

    def test_curled_index_does_not_hide_other_fingers(self):
        points = open_points()
        points[7] = [-0.4, 1.5, 0.5]
        points[8] = [-0.4, 1.0, 0.6]
        states = finger_states(points)
        self.assertFalse(states["index"])
        self.assertTrue(states["middle"])
        self.assertTrue(states["thumb"])

    def test_straight_but_adducted_thumb_is_not_open_palm(self):
        points = open_points()
        points[1:5] = [[-0.4, 0.1, 0], [-0.3, 0.4, 0], [-0.2, 0.7, 0], [-0.1, 1, 0]]
        self.assertFalse(finger_states(points)["thumb"])

    def test_pixel_aspect_ratio_does_not_change_pinch_distance(self):
        points = [[0.5, 0.5, 0] for _ in range(21)]
        points[0], points[9] = [0.5, 0.7, 0], [0.5, 0.5, 0]
        points[4], points[8] = [0.5, 0.4, 0], [0.52, 0.4, 0]
        wide = [[p[0] / 2, p[1], p[2]] for p in points]
        self.assertAlmostEqual(pinch_ratios(points, 1)["index"], pinch_ratios(wide, 2)["index"])


class RealLandmarkTests(unittest.TestCase):
    def test_mediapipe_sample_hands(self):
        fixture = json.loads((Path(__file__).parent / "fixtures" / "mediapipe_sample_hands.json").read_text())
        for hand in fixture["hands"]:
            with self.subTest(image=hand["image"]):
                states = finger_states(hand["world_landmarks"])
                self.assertEqual({name for name, on in states.items() if on}, set(hand["extended"]))


class PinchTests(unittest.TestCase):
    def test_hysteresis_requires_close_start_and_wider_release(self):
        state = PinchState()
        self.assertFalse(state.update({"index": 0.20}, 0)["index"])
        self.assertFalse(state.update({"index": 0.14}, 10)["index"])
        self.assertTrue(state.update({"index": 0.14}, 60)["index"])
        self.assertTrue(state.update({"index": 0.20}, 70)["index"])
        self.assertTrue(state.update({"index": 0.26}, 80)["index"])
        self.assertFalse(state.update({"index": 0.26}, 130)["index"])

    def test_nearest_pinch_wins_and_is_mutually_exclusive(self):
        state = PinchState()
        ratios = {"index": 0.12, "middle": 0.09, "ring": 0.5, "pinky": 0.6}
        state.update(ratios, 0)
        actual = state.update(ratios, 60)
        self.assertTrue(actual["middle"])
        self.assertEqual(sum(actual.values()), 1)

    def test_brief_threshold_noise_does_not_activate(self):
        state = PinchState()
        state.update({"index": 0.10}, 0)
        state.update({"index": 0.30}, 40)
        self.assertFalse(state.update({"index": 0.30}, 200)["index"])


class IdentityTests(unittest.TestCase):
    @staticmethod
    def detection(label, x):
        return {"handedness": label, "landmarks": [[x, 0.5, 0] for _ in range(21)]}

    def test_detector_order_does_not_change_ids(self):
        identities = HandIdentities()
        first = identities.assign([self.detection("Left", 0.2), self.detection("Right", 0.8)])
        second = identities.assign([self.detection("Right", 0.77), self.detection("Left", 0.22)])
        self.assertEqual([t.identity for t in second], [first[1].identity, first[0].identity])

    def test_missing_hand_loses_pinch_and_gets_new_identity(self):
        identities = HandIdentities()
        first = identities.assign([self.detection("Left", 0.2)])[0]
        first.pinch.active = "index"
        identities.assign([])
        again = identities.assign([self.detection("Left", 0.2)])[0]
        self.assertNotEqual(first.identity, again.identity)
        self.assertIsNone(again.pinch.active)

    def test_handedness_flicker_does_not_change_nearby_identity(self):
        identities = HandIdentities()
        first = identities.assign([self.detection("Left", 0.2)])[0]
        again = identities.assign([self.detection("Right", 0.21)])[0]
        self.assertEqual(first.identity, again.identity)


class GestureTests(unittest.TestCase):
    def test_held_discrete_gesture_has_one_event(self):
        engine = GestureEngine()
        hand = fake_hand(pinch="ring")
        self.assertEqual(engine.update_pose([hand], 0)["mode"], "hover")
        self.assertEqual(engine.update_pose([hand], 299)["mode"], "hover")
        triggered = engine.update_pose([hand], 300)
        self.assertEqual(triggered["mode"], "next_part")
        self.assertEqual(engine.update_pose([hand], 3000)["event_id"], triggered["event_id"])
        engine.update_pose([fake_hand()], 3100)
        engine.update_pose([hand], 3200)
        repeated = engine.update_pose([hand], 3500)
        self.assertEqual(repeated["mode"], "next_part")
        self.assertGreater(repeated["event_id"], triggered["event_id"])

    def test_reset_requires_full_hold(self):
        engine = GestureEngine()
        hand = fake_hand(pinch="pinky")
        engine.update_pose([hand], 0)
        self.assertEqual(engine.update_pose([hand], 699)["mode"], "hover")
        self.assertEqual(engine.update_pose([hand], 700)["mode"], "reset")

    def test_two_index_pinches_take_priority_over_grab(self):
        engine = GestureEngine()
        hands = [fake_hand("left-1", "index", x=0.2), fake_hand("right-2", "index", x=0.8)]
        engine.update_pose(hands, 0)
        result = engine.update_pose(hands, 100, aspect_ratio=2)
        self.assertEqual(result["mode"], "zoom")
        self.assertAlmostEqual(result["distance"], 1.2)
        self.assertEqual(result["cursor"], [0.5, 0.5])

    def test_mismatched_two_hand_pinches_do_not_trigger_discrete_action(self):
        engine = GestureEngine()
        hands = [fake_hand("left-1", "index"), fake_hand("right-2", "pinky")]
        engine.update_pose(hands, 0)
        self.assertEqual(engine.update_pose(hands, 2000)["mode"], "hover")

    def test_two_open_palms_explode_but_one_open_palm_does_not(self):
        engine = GestureEngine()
        hands = [fake_hand("left-1"), fake_hand("right-2")]
        engine.update_pose(hands, 0)
        self.assertEqual(engine.update_pose(hands, 100)["mode"], "explode")
        self.assertEqual(engine.update_pose(hands[:1], 110)["mode"], "hover")

    def test_two_to_one_hand_requires_fresh_baseline_event(self):
        engine = GestureEngine()
        hands = [fake_hand("left-1", "index"), fake_hand("right-2", "index")]
        engine.update_pose(hands, 0)
        zoom = engine.update_pose(hands, 100)
        pending = engine.update_pose(hands[:1], 120)
        self.assertEqual(pending["mode"], "hover")
        grab = engine.update_pose(hands[:1], 220)
        self.assertEqual(grab["mode"], "grab")
        self.assertNotEqual(grab["event_id"], zoom["event_id"])

    def test_lost_hands_immediately_idle_and_cancel_pending_hold(self):
        engine = GestureEngine()
        hand = fake_hand(pinch="pinky")
        engine.update_pose([hand], 0)
        lost = engine.update_pose([], 600)
        self.assertEqual(lost["mode"], "idle")
        self.assertIsNone(lost["cursor"])
        engine.update_pose([hand], 650)
        self.assertEqual(engine.update_pose([hand], 800)["mode"], "hover")

    def test_participant_change_rearms_action(self):
        engine = GestureEngine()
        first, second = fake_hand("left-1", "middle"), fake_hand("right-2", "middle")
        engine.update_pose([first], 0)
        before = engine.update_pose([first], 100)
        self.assertEqual(before["mode"], "rotate")
        self.assertEqual(engine.update_pose([second], 110)["mode"], "hover")
        after = engine.update_pose([second], 210)
        self.assertEqual(after["mode"], "rotate")
        self.assertGreater(after["event_id"], before["event_id"])

    def test_fist_idles(self):
        self.assertEqual(GestureEngine().update_pose([fake_hand(opened=False)], 0)["mode"], "idle")

    def test_duplicate_input_timestamp_rejected(self):
        engine = GestureEngine()
        engine.process([], 100)
        with self.assertRaises(ValueError):
            engine.process([], 100)

    def test_capture_stall_discards_old_hand_identity_and_action(self):
        engine = GestureEngine()
        detection = IdentityTests.detection("Left", 0.2)
        first, _ = engine.process([detection], 0)
        engine._set_mode("grab", [first[0]["id"]])
        previous_event = engine.event_id
        resumed, gesture = engine.process([detection], 600)
        self.assertNotEqual(resumed[0]["id"], first[0]["id"])
        self.assertNotEqual(gesture["mode"], "grab")
        self.assertGreater(gesture["event_id"], previous_event)


if __name__ == "__main__":
    unittest.main()

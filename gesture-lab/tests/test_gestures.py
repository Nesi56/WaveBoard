"""Run from project root: python -m unittest discover -s tests -v"""

import json
import math
from pathlib import Path
import unittest

from gestures import FINGERS, TIPS, HandEngine, HandIdentities, PinchState, finger_states, hand_pose, pinch_ratios


def open_points():
    points = [[0.0, 0.0, 0.0] for _ in range(21)]
    points[1:5] = [[-0.5, 0.2, 0], [-0.85, 0.45, 0], [-1.15, 0.65, 0], [-1.45, 0.85, 0]]
    for start, x in ((5, -0.4), (9, 0), (13, 0.3), (17, 0.6)):
        for offset in range(4):
            points[start + offset] = [x, 1 + offset * 0.5, 0]
    return points


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

    def test_palm_width_supports_pinch_when_wrist_is_foreshortened(self):
        points = [[0.5, 0.5, 0] for _ in range(21)]
        points[0], points[9] = [0.5, 0.61, 0], [0.5, 0.6, 0]
        points[5], points[17] = [0.4, 0.6, 0], [0.6, 0.6, 0]
        points[4], points[8] = [0.48, 0.4, 0], [0.515, 0.4, 0]
        self.assertLess(pinch_ratios(points, 1)["index"], PinchState().on)
        enlarged = [[0.2 + value * 2 for value in point] for point in points]
        self.assertAlmostEqual(pinch_ratios(points, 1)["index"], pinch_ratios(enlarged, 1)["index"])

    def test_depth_correction_is_bounded_when_model_depth_is_noisy(self):
        points = [[0.5, 0.5, 0] for _ in range(21)]
        points[0], points[9] = [0.5, 0.7, 0], [0.5, 0.5, 10]
        points[4], points[8] = [0.3, 0.4, 0], [0.5, 0.4, 0]
        self.assertGreater(pinch_ratios(points, 1)["index"], PinchState().off)


class RealLandmarkTests(unittest.TestCase):
    def test_mediapipe_sample_hands(self):
        fixture = json.loads((Path(__file__).parent / "fixtures" / "mediapipe_sample_hands.json").read_text())
        for hand in fixture["hands"]:
            with self.subTest(image=hand["image"]):
                states = finger_states(hand["world_landmarks"])
                self.assertEqual({name for name, on in states.items() if on}, set(hand["extended"]))
                expected = "peace" if hand["image"] == "victory.jpg" else "point" if hand["image"] == "pointing_up.jpg" else None
                self.assertEqual(hand_pose(states), expected)

    def test_pointing_and_peace_poses_ignore_thumb_but_not_an_index_pinch(self):
        fingers = {name: name == "index" for name in FINGERS}
        self.assertEqual(hand_pose(fingers), "point")
        fingers["thumb"] = True
        self.assertEqual(hand_pose(fingers), "point")
        fingers["middle"] = True
        self.assertEqual(hand_pose(fingers), "peace")
        self.assertIsNone(hand_pose(fingers, index_pinched=True))
        fingers["ring"] = True
        self.assertIsNone(hand_pose(fingers))


class PinchTests(unittest.TestCase):
    def test_hysteresis_requires_close_start_and_wider_release(self):
        state = PinchState()
        self.assertFalse(state.update({"index": 0.24}, 0)["index"])
        self.assertFalse(state.update({"index": 0.21}, 10)["index"])
        self.assertTrue(state.update({"index": 0.25}, 50)["index"])
        self.assertTrue(state.update({"index": 0.30}, 70)["index"])
        self.assertTrue(state.update({"index": 0.35}, 80)["index"])
        self.assertTrue(state.update({"index": 0.35}, 140)["index"])
        self.assertFalse(state.update({"index": 0.35}, 160)["index"])

    def test_index_pinch_takes_priority_and_is_mutually_exclusive(self):
        state = PinchState()
        ratios = {"index": 0.12, "middle": 0.09, "ring": 0.5, "pinky": 0.6}
        state.update(ratios, 0)
        actual = state.update(ratios, 60)
        self.assertTrue(actual["index"])
        self.assertEqual(sum(actual.values()), 1)

    def test_nearby_middle_finger_cannot_steal_a_held_index_pinch(self):
        state = PinchState()
        state.update({"index": 0.20, "middle": 0.5}, 0)
        state.update({"index": 0.20, "middle": 0.5}, 40)
        self.assertTrue(state.update({"index": 0.30, "middle": 0.01}, 80)["index"])
        self.assertTrue(state.update({"index": 0.30, "middle": 0.01}, 240)["index"])

    def test_index_opening_rearms_even_when_thumb_rests_on_middle_finger(self):
        state = PinchState(needs_release=True)
        state.update({"index": 0.6, "middle": 0.01}, 0)
        self.assertFalse(state.needs_release)
        state.update({"index": 0.20, "middle": 0.01}, 40)
        self.assertTrue(state.update({"index": 0.20, "middle": 0.01}, 80)["index"])

    def test_short_release_noise_does_not_split_a_drag_into_clicks(self):
        state = PinchState()
        state.update({"index": 0.20}, 0)
        state.update({"index": 0.20}, 40)
        state.update({"index": 0.5}, 60)
        self.assertTrue(state.update({"index": 0.5}, 120)["index"])
        self.assertTrue(state.update({"index": 0.25}, 130)["index"])

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

    def test_briefly_missing_hand_keeps_identity_and_active_pinch(self):
        identities = HandIdentities()
        first = identities.assign([self.detection("Left", 0.2)])[0]
        first.pinch.active = "index"
        identities.assign([])
        again = identities.assign([self.detection("Left", 0.2)])[0]
        self.assertEqual(first.identity, again.identity)
        self.assertEqual(again.pinch.active, "index")
        self.assertTrue(again.reacquired)

    def test_long_missing_hand_gets_new_identity_and_pinch_state(self):
        identities = HandIdentities()
        first = identities.assign([self.detection("Left", 0.2)], 0)[0]
        first.pinch.active = "index"
        identities.assign([], 100)
        again = identities.assign([self.detection("Left", 0.2)], 450)[0]
        self.assertNotEqual(first.identity, again.identity)
        self.assertIsNone(again.pinch.active)

    def test_fast_motion_after_missed_detection_preserves_identity(self):
        identities = HandIdentities()
        first = identities.assign([self.detection("Left", 0.15)], 0)[0]
        identities.assign([self.detection("Left", 0.35)], 100)
        identities.assign([], 200)
        again = identities.assign([self.detection("Left", 0.8)], 300)[0]
        self.assertEqual(first.identity, again.identity)

    def test_motion_prediction_preserves_ids_when_same_label_hands_cross(self):
        identities = HandIdentities()
        first = identities.assign([self.detection("Left", 0.2), self.detection("Left", 0.8)], 0)
        identities.assign([self.detection("Left", 0.4), self.detection("Left", 0.6)], 100)
        crossed = identities.assign([self.detection("Left", 0.4), self.detection("Left", 0.6)], 200)
        self.assertEqual([t.identity for t in crossed], [first[1].identity, first[0].identity])

    def test_handedness_flicker_does_not_change_nearby_identity(self):
        identities = HandIdentities()
        first = identities.assign([self.detection("Left", 0.2)])[0]
        again = identities.assign([self.detection("Right", 0.21)])[0]
        self.assertEqual(first.identity, again.identity)


class HandEngineTests(unittest.TestCase):
    @staticmethod
    def pinch_detection(closed):
        points = [[0.5, 0.5, 0] for _ in range(21)]
        points[0] = [0.5, 0.7, 0]
        points[4], points[8] = [0.5, 0.4, 0], [0.51 if closed else 0.6, 0.4, 0]
        return {"handedness": "Left", "landmarks": points}

    def test_records_have_stable_ids_fingers_and_debounced_pinches(self):
        engine = HandEngine()
        detection = IdentityTests.detection("Left", 0.2)
        first = engine.process([detection], 0)[0]
        second = engine.process([detection], 40)[0]
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(set(second["fingers"]), set(FINGERS))
        self.assertEqual(set(second["pinches"]), set(TIPS))
        self.assertEqual(second["palm"], [0.2, 0.5])

    def test_duplicate_input_timestamp_rejected(self):
        engine = HandEngine()
        engine.process([], 100)
        with self.assertRaises(ValueError):
            engine.process([], 100)

    def test_capture_stall_discards_old_hand_identity(self):
        engine = HandEngine()
        detection = IdentityTests.detection("Left", 0.2)
        first = engine.process([detection], 0)
        resumed = engine.process([detection], 600)
        self.assertNotEqual(resumed[0]["id"], first[0]["id"])

    def test_dropout_holds_visual_without_refreshing_observation(self):
        engine = HandEngine()
        first = engine.process([self.pinch_detection(False)], 0)[0]
        held = engine.process([], 150)[0]
        self.assertEqual(held["id"], first["id"])
        self.assertEqual(held["landmarks"], first["landmarks"])
        self.assertFalse(held["observed"])
        self.assertTrue(held["predicted"])
        self.assertEqual(held["tracking_age_ms"], 150)
        self.assertEqual(engine.process([], 250), [])

    def test_unconfirmed_pinch_cannot_complete_during_dropout(self):
        engine = HandEngine()
        engine.process([self.pinch_detection(True)], 0)
        engine.process([], 40)
        returned = engine.process([self.pinch_detection(True)], 140)[0]
        self.assertFalse(returned["pinches"]["index"])
        self.assertFalse(engine.process([self.pinch_detection(True)], 200)[0]["pinches"]["index"])
        engine.process([self.pinch_detection(False)], 230)
        engine.process([self.pinch_detection(True)], 260)
        self.assertTrue(engine.process([self.pinch_detection(True)], 320)[0]["pinches"]["index"])

    def test_release_while_missing_cancels_instead_of_completing_tap(self):
        engine = HandEngine()
        engine.process([self.pinch_detection(True)], 0)
        self.assertTrue(engine.process([self.pinch_detection(True)], 60)[0]["pinches"]["index"])
        engine.process([], 100)
        returned = engine.process([self.pinch_detection(False)], 180)[0]
        self.assertFalse(returned["pinches"]["index"])
        self.assertTrue(returned["interaction_cancelled"])


if __name__ == "__main__":
    unittest.main()

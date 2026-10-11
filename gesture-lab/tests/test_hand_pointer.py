"""Run from project root: python -m unittest discover -s tests -v"""

import unittest

from hand_pointer import SCREEN, HandPointer, OneEuro, ScreenMap, SwipeDetector

FINGERS_OPEN = dict(thumb=True, index=True, middle=True, ring=True, pinky=True)
FINGERS_RELAXED = dict(thumb=False, index=True, middle=False, ring=False, pinky=False)


def hand(identity, x, y, pinch=False, fingers=FINGERS_RELAXED):
    """Mirrored, normalized camera coordinates; thumb and index tips meet at (x, y)."""
    landmarks = [[x, y + 0.1, 0.0] for _ in range(21)]
    landmarks[4] = [x - 0.005, y, 0.0]
    landmarks[8] = [x + 0.005, y, 0.0]
    return {"id": identity, "landmarks": landmarks, "fingers": dict(fingers),
            "pinches": {"index": pinch, "middle": False, "ring": False, "pinky": False}, "palm": [x, y + 0.1]}


def pointer(**kwargs):
    return HandPointer(reach=0.0, smoothing=False, **kwargs)


class HandPointerTests(unittest.TestCase):
    def test_hover_maps_camera_to_screen(self):
        result = pointer().update([hand("a", 0.25, 0.5)], 0)
        self.assertTrue(result["visible"])
        self.assertFalse(result["down"])
        self.assertAlmostEqual(result["x"], 0.25)
        self.assertAlmostEqual(result["y"], 0.5)

    def test_reach_margin_lets_the_cursor_reach_the_edges(self):
        result = HandPointer(reach=0.1, smoothing=False).update([hand("a", 0.1, 0.9)], 0)
        self.assertAlmostEqual(result["x"], 0.0)
        self.assertAlmostEqual(result["y"], 1.0)

    def test_no_hands_hides_the_pointer(self):
        result = pointer().update([], 0)
        self.assertFalse(result["visible"])
        self.assertIsNone(result["x"])

    def test_small_movement_during_a_pinch_stays_a_tap(self):
        tracker = pointer()
        tracker.update([hand("a", 0.5, 0.5)], 0)
        pressed = tracker.update([hand("a", 0.5, 0.5, pinch=True)], 30)
        wobble = tracker.update([hand("a", 0.5 + 15 / SCREEN[0], 0.5, pinch=True)], 60)
        self.assertTrue(pressed["down"])
        self.assertEqual((wobble["x"], wobble["y"]), (pressed["x"], pressed["y"]))
        released = tracker.update([hand("a", 0.5 + 15 / SCREEN[0], 0.5)], 90)
        self.assertFalse(released["down"])

    def test_larger_movement_during_a_pinch_drags(self):
        tracker = pointer()
        tracker.update([hand("a", 0.5, 0.5, pinch=True)], 0)
        dragged = tracker.update([hand("a", 0.6, 0.5, pinch=True)], 30)
        self.assertTrue(dragged["down"])
        self.assertAlmostEqual(dragged["x"], 0.6)
        back = tracker.update([hand("a", 0.5 + 10 / SCREEN[0], 0.5, pinch=True)], 60)
        self.assertAlmostEqual(back["x"], 0.5 + 10 / SCREEN[0])  # no snapping back once dragging

    def test_pinching_hand_takes_over_but_not_during_a_press(self):
        tracker = pointer()
        tracker.update([hand("a", 0.2, 0.5), hand("b", 0.8, 0.5)], 0)
        self.assertEqual(tracker.primary, "a")
        tracker.update([hand("a", 0.2, 0.5), hand("b", 0.8, 0.5, pinch=True)], 30)
        self.assertEqual(tracker.primary, "b")
        held = tracker.update([hand("a", 0.2, 0.5, pinch=True), hand("b", 0.8, 0.5, pinch=True)], 60)
        self.assertEqual(held["hand"], "b")

    def test_open_palm_swipe_is_counted_once(self):
        tracker = pointer()
        ids = set()
        for i, t in enumerate(range(0, 400, 33)):
            result = tracker.update([hand("a", 0.8 - i * 0.05, 0.5, fingers=FINGERS_OPEN)], t)
            ids.add(result["swipe_id"])
        self.assertEqual(result["swipe_id"], 1)
        self.assertEqual(result["swipe"], -1)
        self.assertEqual(ids, {0, 1})

    def test_slow_drift_or_pinching_is_not_a_swipe(self):
        tracker = pointer()
        for i, t in enumerate(range(0, 2000, 33)):
            result = tracker.update([hand("a", 0.8 - i * 0.003, 0.5, fingers=FINGERS_OPEN)], t)
        self.assertEqual(result["swipe_id"], 0)
        for i, t in enumerate(range(2000, 2400, 33)):
            result = tracker.update([hand("a", 0.8 - i * 0.05, 0.5, pinch=True, fingers=FINGERS_OPEN)], t)
        self.assertEqual(result["swipe_id"], 0)


class SkeletonTests(unittest.TestCase):
    def test_every_hand_gets_21_screen_points_and_a_primary_flag(self):
        result = pointer().update([hand("a", 0.25, 0.5), hand("b", 0.75, 0.5)], 0)
        self.assertEqual([h["id"] for h in result["hands"]], ["a", "b"])
        self.assertTrue(all(len(h["points"]) == 21 for h in result["hands"]))
        self.assertEqual([h["primary"] for h in result["hands"]], [True, False])
        self.assertAlmostEqual(result["hands"][0]["points"][8][0], 0.255, places=3)

    def test_skeleton_uses_the_same_mapping_as_the_cursor(self):
        tracker = HandPointer(reach=0.1, smoothing=False)
        result = tracker.update([hand("a", 0.1, 0.5)], 0)
        thumb, index = result["hands"][0]["points"][4], result["hands"][0]["points"][8]
        self.assertAlmostEqual((thumb[0] + index[0]) / 2, result["x"], places=3)
        self.assertAlmostEqual(thumb[1], result["y"], places=3)

    def test_pinch_is_marked_on_the_skeleton(self):
        result = pointer().update([hand("a", 0.5, 0.5, pinch=True)], 0)
        self.assertTrue(result["hands"][0]["pinch"])

    def test_smoothing_steadies_jittery_joints(self):
        tracker = HandPointer(reach=0.0)
        xs = []
        for i in range(60):
            wobble = (3 if i % 2 else -3) / SCREEN[0]
            xs.append(tracker.update([hand("a", 0.5 + wobble, 0.5)], i * 33)["hands"][0]["points"][0][0])
        self.assertLess((max(xs[30:]) - min(xs[30:])) * SCREEN[0], 2)

    def test_lost_hand_drops_its_skeleton(self):
        tracker = pointer()
        tracker.update([hand("a", 0.5, 0.5)], 0)
        self.assertEqual(tracker.update([], 33)["hands"], [])


class UtilityTests(unittest.TestCase):
    def test_screen_map_crops_camera_border(self):
        screen_map = ScreenMap((1280, 720), (1280, 720), margin=0.1)
        self.assertEqual(screen_map.crop, (128, 72, 1024, 576))
        self.assertEqual(screen_map.to_screen(0.5, 0.5), (640, 360))
        self.assertEqual(screen_map.to_screen(0.1, 0.1), (0, 0))

    def test_screen_map_matches_projector_aspect(self):
        screen_map = ScreenMap((1280, 720), (1024, 768), margin=0.1)
        x, y, w, h = screen_map.crop
        self.assertAlmostEqual(w / h, 4 / 3, places=2)
        self.assertLessEqual(h, 720 * 0.8 + 1)

    def test_one_euro_smooths_jitter_and_follows_motion(self):
        steady = OneEuro()
        values = [steady(100 + (3 if i % 2 else -3), i / 30) for i in range(60)]
        self.assertLess(max(values[30:]) - min(values[30:]), 3)
        moving = OneEuro()
        for i in range(30):
            last = moving(i * 40.0, i / 30)
        self.assertGreater(last, 29 * 40 - 40)

    def test_swipe_detector_needs_a_fast_horizontal_move(self):
        detector = SwipeDetector(distance=200)
        self.assertIsNone(detector.update((800, 300), 0))
        self.assertEqual(detector.update((550, 320), 200), (-1, (800, 300)))
        self.assertIsNone(detector.update((300, 600), 300))  # history was cleared; mostly vertical anyway


if __name__ == "__main__":
    unittest.main()

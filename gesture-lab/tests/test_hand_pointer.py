"""Run from project root: python -m unittest discover -s tests -v"""

import unittest

from hand_pointer import SCREEN, HandPointer

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


if __name__ == "__main__":
    unittest.main()

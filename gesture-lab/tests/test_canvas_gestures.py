"""Run from project root: python -m unittest discover -s tests -v"""

import json
from pathlib import Path
import unittest

from canvas_gestures import (CanvasStudio, Hand, OneEuro, Rect, ScreenMap, StablePose, classify,
                             frame_rect, snap_aspect)
from gestures import finger_states

SHAPES = {
    "point": dict(thumb=False, index=True, middle=False, ring=False, pinky=False),
    "frame": dict(thumb=True, index=True, middle=False, ring=False, pinky=False),
    "open": dict(thumb=True, index=True, middle=True, ring=True, pinky=True),
    "fist": dict(thumb=False, index=False, middle=False, ring=False, pinky=False),
}


def hand(identity, shape="fist", at=(0.0, 0.0), pinch=None):
    """A hand with every landmark at one point; enough for cursor, pinch and palm positions."""
    return Hand(identity, [at] * 21, dict(SHAPES[shape]),
                {name: name == pinch for name in ("index", "middle", "ring", "pinky")})


def l_hand(identity, web, index_dir, thumb_dir, length=60):
    points = [web] * 21
    points[4] = (web[0] + thumb_dir[0] * length, web[1] + thumb_dir[1] * length)
    points[8] = (web[0] + index_dir[0] * length, web[1] + index_dir[1] * length)
    return Hand(identity, points, dict(SHAPES["frame"]), {n: False for n in ("index", "middle", "ring", "pinky")})


def diagonal_frame(x0, y0, x1, y1):
    """Left hand at the lower-left corner, right hand at the upper-right corner."""
    return [l_hand("left-1", (x0, y1), (0, -1), (1, 0)), l_hand("right-2", (x1, y0), (0, 1), (-1, 0))]


def studio(**kwargs):
    return CanvasStudio(1280, 720, slide_count=5, smoothing=False, **kwargs)


def run(board, frames):
    """frames: iterable of (t, hands); returns the last overlay."""
    overlay = None
    for t, hands in frames:
        overlay = board.update(hands, t)
    return overlay


class GeometryTests(unittest.TestCase):
    def test_pose_classification(self):
        self.assertEqual(classify(hand("a", "point")), "point")
        self.assertEqual(classify(hand("a", "frame")), "frame")
        self.assertEqual(classify(hand("a", "open")), "open")
        self.assertEqual(classify(hand("a", "fist")), "fist")
        self.assertEqual(classify(hand("a", "frame", pinch="middle")), "pinch:middle")

    def test_poses_of_real_mediapipe_hands(self):
        fixture = json.loads((Path(__file__).parent / "fixtures" / "mediapipe_sample_hands.json").read_text())
        for sample in fixture["hands"]:
            with self.subTest(image=sample["image"]):
                real = Hand("a", [p[:2] for p in sample["landmarks"]], finger_states(sample["world_landmarks"]),
                            {n: False for n in ("index", "middle", "ring", "pinky")})
                self.assertEqual(classify(real), sample["canvas_pose"])

    def test_frame_rect_diagonal_and_upright(self):
        rect = frame_rect(diagonal_frame(300, 200, 800, 500))
        self.assertEqual((rect.x, rect.y, rect.w, rect.h), (300, 200, 500, 300))
        # Upright "director" frame: index fingers up, thumbs pointing at each other.
        upright = [l_hand("a", (300, 500), (0, -1), (1, 0), 120), l_hand("b", (700, 500), (0, -1), (-1, 0), 120)]
        rect = frame_rect(upright)
        self.assertEqual((rect.x, rect.y, rect.w, rect.h), (300, 380, 400, 120))

    def test_snap_aspect_keeps_centre_and_area(self):
        snapped = snap_aspect(Rect(100, 100, 530, 300))
        self.assertAlmostEqual(snapped.w / snapped.h, 16 / 9)
        self.assertAlmostEqual(snapped.w * snapped.h, 530 * 300)
        self.assertAlmostEqual(snapped.center[0], 365)
        free = snap_aspect(Rect(0, 0, 700, 300))
        self.assertEqual((free.w, free.h), (700, 300))

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

    def test_stable_pose_ignores_brief_flicker(self):
        pose = StablePose(hold_ms=100)
        pose.update("point", 0)
        self.assertEqual(pose.update("point", 100), "point")
        pose.update("other", 130)
        self.assertEqual(pose.update("point", 160), "point")
        pose.update("fist", 200)
        self.assertEqual(pose.update("fist", 299), "point")
        self.assertEqual(pose.update("fist", 300), "fist")
        self.assertEqual(pose.changed_at, 200)


class FramingTests(unittest.TestCase):
    def frame_and_stretch(self, board):
        small, large = (500, 300, 700, 450), (200, 150, 900, 600)
        run(board, [(t, diagonal_frame(*small)) for t in range(0, 600, 50)])
        steps = 6
        for i in range(1, steps + 1):
            rect = [a + (b - a) * i / steps for a, b in zip(small, large)]
            board.update(diagonal_frame(*rect), 600 + i * 50)
        for t in range(950, 1100, 50):
            board.update(diagonal_frame(*large), t)

    def test_hold_then_stretch_then_relax_places_canvas(self):
        board = studio()
        self.assertIsNotNone(run(board, [(t, diagonal_frame(500, 300, 700, 450)) for t in range(0, 500, 50)])["ghost"])
        self.frame_and_stretch(board)
        forming = board.canvases[-1]
        self.assertTrue(forming.forming)
        # Relaxing moves the fingertips; the canvas keeps the size it had before.
        run(board, [(1100, [hand("left-1", "fist", (500, 400)), hand("right-2", "fist", (520, 380))]),
                    (1150, [hand("left-1", "fist", (500, 400)), hand("right-2", "fist", (520, 380))]),
                    (1200, [hand("left-1", "fist", (500, 400)), hand("right-2", "fist", (520, 380))])])
        self.assertFalse(forming.forming)
        self.assertEqual((forming.rect.x, forming.rect.y, forming.rect.w, forming.rect.h), (200, 150, 700, 450))
        self.assertEqual(forming.content, "lens:neon")
        self.assertEqual(board.focus, forming.id)

    def test_releasing_before_the_ring_fills_creates_nothing(self):
        board = studio()
        run(board, [(t, diagonal_frame(400, 200, 800, 500)) for t in range(0, 400, 50)])
        run(board, [(t, [hand("left-1", "fist"), hand("right-2", "fist")]) for t in range(400, 600, 50)])
        self.assertEqual(board.canvases, [])

    def test_squeezing_hands_together_cancels(self):
        board = studio()
        run(board, [(t, diagonal_frame(400, 200, 800, 500)) for t in range(0, 700, 50)])
        self.assertEqual(len(board.canvases), 1)
        run(board, [(t, diagonal_frame(600, 330, 640, 350)) for t in range(700, 900, 50)])
        run(board, [(t, [hand("left-1", "fist"), hand("right-2", "fist")]) for t in range(900, 1100, 50)])
        self.assertEqual(board.canvases, [])

    def test_losing_a_hand_places_the_live_canvas(self):
        board = studio()
        run(board, [(t, diagonal_frame(300, 200, 800, 500)) for t in range(0, 800, 50)])
        run(board, [(800, [hand("left-1", "fist")])])
        self.assertEqual(len(board.canvases), 1)
        self.assertFalse(board.canvases[0].forming)

    def test_one_l_hand_does_not_frame(self):
        board = studio()
        run(board, [(t, diagonal_frame(300, 200, 800, 500)[:1]) for t in range(0, 1000, 50)])
        self.assertEqual(board.canvases, [])

    def test_recent_stroke_from_forming_the_l_is_removed(self):
        board = studio()
        canvas = board.add_canvas(Rect(100, 100, 1000, 500), "board")
        run(board, [(t, [hand("left-1", "point", (300 + t, 400))]) for t in range(0, 250, 50)])
        self.assertEqual(len(canvas.strokes()), 1)
        run(board, [(t, diagonal_frame(300, 200, 800, 500)) for t in range(250, 450, 50)])
        self.assertEqual(canvas.strokes(), [])


class ManipulationTests(unittest.TestCase):
    def test_pinch_moves_canvas_with_hand(self):
        board = studio()
        canvas = board.add_canvas(Rect(400, 200, 400, 300), "board")
        run(board, [(0, [hand("a", "fist", (500, 300), pinch="index")]),
                    (50, [hand("a", "fist", (600, 350), pinch="index")])])
        self.assertEqual((canvas.rect.x, canvas.rect.y), (500, 250))

    def test_pinch_just_outside_the_border_still_grabs(self):
        board = studio()
        canvas = board.add_canvas(Rect(400, 200, 400, 300), "board")
        run(board, [(0, [hand("a", "fist", (390, 300), pinch="index")]),
                    (50, [hand("a", "fist", (290, 300), pinch="index")])])
        self.assertEqual(canvas.rect.x, 300)

    def test_pinch_on_empty_space_grabs_nothing(self):
        board = studio()
        canvas = board.add_canvas(Rect(400, 200, 400, 300), "board")
        run(board, [(0, [hand("a", "fist", (100, 100), pinch="index")]),
                    (50, [hand("a", "fist", (500, 300), pinch="index")]),
                    (100, [hand("a", "fist", (700, 400), pinch="index")])])
        self.assertEqual((canvas.rect.x, canvas.rect.y), (400, 200))

    def test_two_hand_pinch_stretches_each_axis(self):
        board = studio()
        canvas = board.add_canvas(Rect(400, 200, 400, 300), "board")
        run(board, [(0, [hand("a", "fist", (450, 250), pinch="index"), hand("b", "fist", (750, 450), pinch="index")]),
                    (50, [hand("a", "fist", (450, 250), pinch="index"), hand("b", "fist", (850, 550), pinch="index")])])
        self.assertAlmostEqual(canvas.rect.w, 400 * 400 / 300)
        self.assertAlmostEqual(canvas.rect.h, 300 * 300 / 200)
        self.assertAlmostEqual(canvas.rect.x + canvas.rect.w / 2, 650)
        self.assertAlmostEqual(canvas.rect.y + canvas.rect.h / 2, 400)

    def test_level_hands_stretch_height_with_distance(self):
        board = studio()
        canvas = board.add_canvas(Rect(400, 200, 400, 300), "board")
        run(board, [(0, [hand("a", "fist", (450, 350), pinch="index"), hand("b", "fist", (750, 350), pinch="index")]),
                    (50, [hand("a", "fist", (300, 350), pinch="index"), hand("b", "fist", (900, 350), pinch="index")])])
        self.assertAlmostEqual(canvas.rect.w, 800)
        self.assertAlmostEqual(canvas.rect.h, 600)

    def test_releasing_one_hand_of_a_stretch_continues_as_move_without_jump(self):
        board = studio()
        canvas = board.add_canvas(Rect(400, 200, 400, 300), "board")
        run(board, [(0, [hand("a", "fist", (450, 250), pinch="index"), hand("b", "fist", (750, 450), pinch="index")]),
                    (50, [hand("a", "fist", (450, 250), pinch="index"), hand("b", "fist", (850, 550), pinch="index")]),
                    (100, [hand("a", "fist", (450, 250), pinch="index"), hand("b", "fist", (850, 550))])])
        before = canvas.rect.copy()
        run(board, [(150, [hand("a", "fist", (450, 250), pinch="index"), hand("b", "fist", (850, 550))]),
                    (200, [hand("a", "fist", (470, 260), pinch="index"), hand("b", "fist", (850, 550))])])
        self.assertAlmostEqual(canvas.rect.x, before.x + 20)
        self.assertAlmostEqual(canvas.rect.w, before.w)

    def test_dropping_on_the_bin_deletes(self):
        board = studio()
        canvas = board.add_canvas(Rect(400, 200, 400, 300), "board")
        bin_centre = board.trash[0]
        overlay = run(board, [(0, [hand("a", "fist", (500, 300), pinch="index")]),
                              (50, [hand("a", "fist", bin_centre, pinch="index")])])
        self.assertTrue(overlay["trash"]["visible"])
        self.assertTrue(overlay["trash"]["hot"])
        run(board, [(100, [hand("a", "fist", bin_centre)])])
        self.assertNotIn(canvas, board.canvases)

    def test_grab_raises_canvas_to_top(self):
        board = studio()
        bottom = board.add_canvas(Rect(100, 100, 400, 300), "board")
        board.add_canvas(Rect(600, 100, 400, 300), "board")
        run(board, [(0, [hand("a", "fist", (200, 200), pinch="index")])])
        self.assertIs(board.canvases[-1], bottom)


class DrawingTests(unittest.TestCase):
    def test_pointing_draws_in_canvas_coordinates(self):
        board = studio()
        canvas = board.add_canvas(Rect(200, 100, 800, 400), "board")
        run(board, [(t, [hand("a", "point", (300 + t, 300))]) for t in range(0, 500, 50)])
        stroke = canvas.strokes()[0]
        self.assertEqual(stroke.points[0], ((400 - 200) / 800, 0.5))
        canvas.rect = Rect(0, 0, 1600, 800)  # ink stretches with its canvas
        self.assertEqual(canvas.rect.screen(stroke.points[0]), (400, 400))

    def test_pose_change_trims_the_stroke_tail(self):
        board = studio()
        canvas = board.add_canvas(Rect(0, 0, 1280, 720), "board")
        run(board, [(t, [hand("a", "point", (100 + t, 300))]) for t in range(0, 500, 50)])
        # The finger curls while the classifier waits: these points are not kept.
        run(board, [(t, [hand("a", "fist", (100 + t, 380))]) for t in range(500, 650, 50)])
        stroke = canvas.strokes()[0]
        self.assertTrue(all(time < 460 for time in stroke.times))
        self.assertEqual(len(stroke.points), len(stroke.times))

    def test_pointing_outside_canvases_draws_nothing(self):
        board = studio()
        canvas = board.add_canvas(Rect(600, 400, 200, 200), "board")
        run(board, [(t, [hand("a", "point", (100, 100))]) for t in range(0, 300, 50)])
        self.assertEqual(canvas.ink, {})

    def test_pointing_at_slides_is_a_laser_pointer_until_a_pen_is_chosen(self):
        board = studio()
        slides = board.add_canvas(Rect(0, 0, 1280, 720), "slides")
        overlay = run(board, [(t, [hand("a", "point", (300 + t, 300))]) for t in range(0, 400, 50)])
        self.assertEqual(slides.ink, {})
        laser = overlay["cursors"][0]["laser"]
        self.assertEqual(laser[-1], (650, 300))
        self.assertLessEqual(len(laser), 6)  # only the last quarter second
        board.next_tool()
        run(board, [(t, [hand("a", "point", (300 + t, 300))]) for t in range(400, 700, 50)])
        self.assertEqual(len(slides.strokes()), 1)

    def test_pinky_pinch_cycles_laser_and_pens(self):
        board = studio()
        run(board, [(0, [hand("a", "fist", (500, 300), pinch="pinky")])])
        self.assertEqual((board.laser, board.ink), (False, 0))
        for _ in range(5):
            board.next_tool()
        self.assertEqual((board.laser, board.ink), (False, 5))
        board.next_tool()
        self.assertEqual((board.laser, board.ink), (True, 0))

    def test_slides_keep_ink_per_page(self):
        board = studio()
        board.laser = False
        slides = board.add_canvas(Rect(0, 0, 1280, 720), "slides")
        run(board, [(t, [hand("a", "point", (300 + t, 300))]) for t in range(0, 300, 50)])
        self.assertEqual(len(slides.strokes()), 1)
        board.turn_page(slides, 1)
        self.assertEqual(slides.strokes(), [])
        board.turn_page(slides, -1)
        self.assertEqual(len(slides.strokes()), 1)

    def test_ring_pinch_undoes(self):
        board = studio()
        canvas = board.add_canvas(Rect(0, 0, 1280, 720), "board")
        run(board, [(t, [hand("a", "point", (300 + t, 300))]) for t in range(0, 300, 50)])
        run(board, [(300, [hand("a", "fist", (500, 300), pinch="ring")])])
        self.assertEqual(canvas.strokes(), [])


class ContentTests(unittest.TestCase):
    def test_middle_pinch_cycles_canvas_content(self):
        board = studio()
        canvas = board.add_canvas(Rect(400, 200, 400, 300), "board")
        run(board, [(0, [hand("a", "fist", (500, 300), pinch="middle")]),
                    (50, [hand("a", "fist", (500, 300), pinch="middle")])])
        self.assertEqual(canvas.content, "lens:neon")  # once per pinch, not once per frame

    def test_middle_pinch_on_empty_space_changes_new_canvas_content(self):
        board = studio()
        run(board, [(0, [hand("a", "fist", (50, 50), pinch="middle")])])
        self.assertEqual(board.new_content, "lens:thermal")

    def test_without_slides_slides_are_skipped(self):
        board = CanvasStudio(1280, 720, slide_count=0, smoothing=False)
        canvas = board.add_canvas(Rect(0, 0, 100, 100), "slides")
        self.assertEqual(canvas.content, "board")
        board.cycle_content(canvas, -1)
        self.assertEqual(canvas.content, "lens:magnify")
        board.cycle_content(canvas, 1)
        self.assertEqual(canvas.content, "board")

    def test_open_palm_swipe_turns_slides_once(self):
        board = studio()
        slides = board.add_canvas(Rect(100, 100, 1000, 500), "slides")
        swipe_left = [(t, [hand("a", "open", (900 - (t - 100) * 1.5, 350))]) for t in range(0, 400, 33)]
        run(board, swipe_left)
        self.assertEqual(slides.page, 1)
        swipe_right = [(t, [hand("a", "open", (300 + (t - 1500) * 1.5, 350))]) for t in range(1500, 1900, 33)]
        run(board, swipe_right)
        self.assertEqual(slides.page, 0)

    def test_slow_palm_drift_is_not_a_swipe(self):
        board = studio()
        slides = board.add_canvas(Rect(100, 100, 1000, 500), "slides")
        run(board, [(t, [hand("a", "open", (900 - t * 0.3, 350))]) for t in range(0, 2000, 33)])
        self.assertEqual(slides.page, 0)

    def test_paused_studio_ignores_gestures(self):
        board = studio()
        canvas = board.add_canvas(Rect(400, 200, 400, 300), "board")
        board.paused = True
        overlay = run(board, [(0, [hand("a", "fist", (500, 300), pinch="index")]),
                              (50, [hand("a", "fist", (700, 400), pinch="index")])])
        self.assertEqual((canvas.rect.x, canvas.rect.y), (400, 200))
        self.assertEqual(overlay["mode"], "Gestures paused")


if __name__ == "__main__":
    unittest.main()

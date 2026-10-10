"""Renders Canvas Studio frames off-screen; skipped where OpenCV/NumPy are not installed."""

import importlib.util
import unittest

HAVE_VISION = all(importlib.util.find_spec(name) for name in ("cv2", "numpy"))

if HAVE_VISION:
    import numpy as np

    import canvas_studio
    from canvas_gestures import CONTENTS, CanvasStudio, Hand, Rect

STATS = {"capture": 30.0, "tracking": 24.0, "render": 24.0}


@unittest.skipUnless(HAVE_VISION, "needs OpenCV and NumPy")
class RenderTests(unittest.TestCase):
    def setUp(self):
        self.size = (1280, 720)
        self.deck = canvas_studio.SlideDeck(None, self.size)
        self.studio = CanvasStudio(*self.size, slide_count=len(self.deck), smoothing=False)
        self.renderer = canvas_studio.Renderer(self.size, self.deck)
        gradient = np.linspace(0, 255, self.size[0], dtype=np.uint8)
        self.camera = np.dstack([np.tile(gradient, (self.size[1], 1))] * 3)

    def compose(self, hands=(), camera=True):
        overlay = self.studio.update(list(hands), 1000)
        return self.renderer.compose(self.studio, overlay, self.camera if camera else None,
                                     list(hands), 1000, STATS)

    def test_every_content_renders_including_off_screen_canvases(self):
        for index, content in enumerate(CONTENTS):
            canvas = self.studio.add_canvas(Rect(-150 + index * 200, 400 + index * 30, 300, 200), content)
            stroke = self.studio.start_stroke(canvas, (canvas.rect.x + 160, canvas.rect.y + 20), 0)
            stroke.points.append((0.9, 0.9))
        for camera in (True, False):
            image = self.compose(camera=camera)
            self.assertEqual(image.shape, (720, 1280, 3))
            self.assertEqual(image.dtype, np.uint8)

    def test_overlays_render(self):
        point = Hand("left-1", [(640.0, 360.0)] * 21, dict(thumb=False, index=True, middle=False, ring=False,
                                                           pinky=False), {n: False for n in ("index", "middle", "ring", "pinky")})
        self.studio.add_canvas(Rect(-50, -50, 2000, 1000), "lens:magnify")
        self.compose([point])
        image = self.compose([point])
        self.assertEqual(image.shape, (720, 1280, 3))

    def test_sample_slides_fit_other_screen_sizes(self):
        for size in ((1024, 768), (1920, 1080), (640, 480)):
            slides = canvas_studio.sample_slides(size)
            self.assertTrue(all(slide.shape == (size[1], size[0], 3) for slide in slides))

    def test_keyboard_shortcuts(self):
        canvas = self.studio.add_canvas(Rect(100, 100, 400, 300), "slides")
        canvas_studio.handle_key(65363, self.studio, self.renderer, None)   # GTK right arrow
        canvas_studio.handle_key(16777239, self.studio, self.renderer, None)  # Qt page down
        self.assertEqual(canvas.page, 2)
        canvas_studio.handle_key(ord("c"), self.studio, self.renderer, None)
        self.assertEqual(canvas.content, "board")
        canvas_studio.handle_key(ord("n"), self.studio, self.renderer, None)
        self.assertEqual(len(self.studio.canvases), 2)
        self.assertFalse(canvas_studio.handle_key(ord("q"), self.studio, self.renderer, None))
        self.assertFalse(canvas_studio.handle_key(27, self.studio, self.renderer, None))
        # GTK Home and Insert end in the bytes for "P" and "c"; they must not act as letters.
        for key in (65360, 65379):
            self.assertTrue(canvas_studio.handle_key(key, self.studio, self.renderer, None))
        self.assertFalse(self.studio.paused)
        self.assertEqual(canvas.content, "board")

    def test_slide_folder_uses_natural_order(self):
        import tempfile
        from pathlib import Path

        import cv2
        with tempfile.TemporaryDirectory() as folder:
            for number in (10, 2, 1):
                image = np.full((90, 160, 3), number * 20, np.uint8)
                cv2.imwrite(str(Path(folder) / f"slide-{number}.png"), image)
            deck = canvas_studio.SlideDeck(folder, self.size)
            self.assertEqual([int(image[0, 0, 0]) for image in deck.images], [20, 40, 200])


if __name__ == "__main__":
    unittest.main()

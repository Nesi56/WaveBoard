"""Projected border detection, including mirrored and perspective camera views."""

import unittest

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = np = None

from projection import MARKER_CENTERS, ProjectionDetector, decode_payload, marker_payload, _variants


class MarkerCodeTests(unittest.TestCase):
    def test_ids_survive_every_rotation_and_reflection_with_one_bad_cell(self):
        for identity in range(4):
            for variant in _variants(marker_payload(identity)):
                for damaged_cell in range(-1, 16):
                    bits = list(variant)
                    if damaged_cell >= 0:
                        bits[damaged_cell] ^= 1
                    self.assertEqual(decode_payload([bits[i:i + 4] for i in range(0, 16, 4)]), identity)

    def test_plain_and_malformed_squares_are_not_markers(self):
        self.assertIsNone(decode_payload([[0] * 4 for _ in range(4)]))
        self.assertIsNone(decode_payload([[1] * 4 for _ in range(4)]))
        self.assertIsNone(decode_payload([[0]]))


@unittest.skipIf(cv2 is None, "requires OpenCV and NumPy from the tracker environment")
class ProjectionImageTests(unittest.TestCase):
    def setUp(self):
        cv2.setNumThreads(1)
        self.detector = ProjectionDetector(cv2, np)

    def scene(self, omit=(), width=1000, height=700):
        image = np.full((height, width), 155, np.uint8)
        for identity, (nx, ny) in enumerate(MARKER_CENTERS):
            if identity in omit:
                continue
            grid = np.ones((8, 8), np.uint8) * 255
            grid[1:7, 1:7] = 0
            grid[2:6, 2:6] = np.array(marker_payload(identity), np.uint8) * 255
            marker = np.repeat(np.repeat(grid, 10, axis=0), 10, axis=1)
            x, y = round(nx * width) - 40, round(ny * height) - 40
            image[y:y + 80, x:x + 80] = marker
        return image

    def assert_markers_close(self, markers, expected, tolerance=.004):
        self.assertEqual({marker["id"] for marker in markers}, set(expected))
        for marker in markers:
            for actual, target in zip(marker["center"], expected[marker["id"]]):
                self.assertAlmostEqual(actual, target, delta=tolerance)

    def test_detects_mirrored_projection_and_all_four_corner_ids(self):
        image = self.scene()
        self.assert_markers_close(self.detector.detect(image), dict(enumerate(MARKER_CENTERS)))
        self.assert_markers_close(self.detector.detect(cv2.flip(image, 1)),
                                  {i: (1 - x, y) for i, (x, y) in enumerate(MARKER_CENTERS)})

    def test_perspective_warp_blur_and_reduced_projector_contrast(self):
        source = np.float32([[0, 0], [1000, 0], [1000, 700], [0, 700]])
        target = np.float32([[140, 60], [1070, 140], [980, 790], [40, 630]])
        matrix = cv2.getPerspectiveTransform(source, target)
        image = cv2.warpPerspective(self.scene(), matrix, (1200, 850), borderValue=85)
        image = cv2.GaussianBlur(image, (3, 3), .6)
        image = (image.astype(np.float32) * .6 + 40).astype(np.uint8)
        projected = cv2.perspectiveTransform(np.float32([[[x * 1000, y * 700] for x, y in MARKER_CENTERS]]), matrix)[0]
        expected = {i: (float(p[0]) / 1200, float(p[1]) / 850) for i, p in enumerate(projected)}
        self.assert_markers_close(self.detector.detect(image), expected)

    def test_no_markers_and_partial_visibility_never_invent_corners(self):
        self.assertEqual(self.detector.detect(np.full((480, 640), 128, np.uint8)), [])
        self.assert_markers_close(self.detector.detect(self.scene(omit=(1, 3))),
                                  {i: MARKER_CENTERS[i] for i in (0, 2)})

    def test_duplicate_id_is_ambiguous(self):
        image = self.scene()
        image[300:380, 400:480] = image[16:96, 20:100]
        self.assertEqual({m["id"] for m in self.detector.detect(image)}, {1, 2, 3})

    def test_scan_timestamp_changes_only_when_a_new_measurement_runs(self):
        image = self.scene()
        first = self.detector.update(image, 1000)
        absent = np.zeros_like(image)
        self.assertIs(self.detector.update(absent, 1200), first)
        next_packet = self.detector.update(absent, 1500)
        self.assertEqual(next_packet, {"markers": [], "timestamp": 1500})
        # A backwards timestamp or changed camera resolution cannot reuse data.
        self.assertEqual(self.detector.update(absent, 1400)["timestamp"], 1400)
        self.assertEqual(self.detector.update(absent[:400], 1450)["timestamp"], 1450)


if __name__ == "__main__":
    unittest.main()

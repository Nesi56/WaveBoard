"""Recognize WaveBoard's four projected border markers with existing OpenCV.

Each marker is a 6 x 6 square: a black one-cell border surrounds a 4 x 4
payload. A white one-cell quiet zone surrounds the square. Payload bits are
row-major, high bit first, with 1 = white. The frontend owns marker placement
and calibration; this module only reports measured marker centers in the same
normalized, mirrored camera coordinates used by hand landmarks.
"""

import math


# Keep these identical to web/projection.js. Dihedral variants of different
# IDs differ in at least five bits, including horizontally mirrored views.
MARKER_CODES = (0x0F34, 0xF1A0, 0x393B, 0xC704)
MARKER_CENTERS = ((.06, .08), (.94, .08), (.94, .92), (.06, .92))


def marker_payload(identity):
    code = MARKER_CODES[identity]
    return [[(code >> (15 - row * 4 - col)) & 1 for col in range(4)] for row in range(4)]


def _variants(payload):
    for reflected in (False, True):
        rows = [row[::-1] if reflected else row[:] for row in payload]
        for _ in range(4):
            yield tuple(cell for row in rows for cell in row)
            rows = [list(row) for row in zip(*rows[::-1])]


_CODES = tuple((identity, code) for identity in range(4) for code in _variants(marker_payload(identity)))


def decode_payload(payload):
    """Return the unique ID within one bad cell, independent of view orientation."""
    bits = tuple(cell for row in payload for cell in row)
    if len(bits) != 16 or any(bit not in (0, 1) for bit in bits):
        return None
    matches = {identity for identity, code in _CODES if sum(a != b for a, b in zip(bits, code)) <= 1}
    return next(iter(matches)) if len(matches) == 1 else None


class ProjectionDetector:
    """A bounded 2 Hz scan; partial detections never fabricate missing corners.

    OpenCV and NumPy are injected just like HandMotionBridge, so importing the
    tracker and running the pure-Python tests does not require camera packages.
    Scans reuse the small grayscale processing image instead of a capture copy.
    """

    def __init__(self, cv2, np, interval_ms=500):
        self.cv2, self.np = cv2, np
        self.interval_ms = interval_ms
        self._last_scan = None
        self._shape = None
        self._packet = {"markers": [], "timestamp": None}

    @property
    def packet(self):
        """Last completed observation; readers never see a partly scanned frame."""
        return self._packet

    def update(self, gray, timestamp):
        shape = gray.shape[:2]
        if self._last_scan is not None and self._shape == shape and \
                0 <= timestamp - self._last_scan < self.interval_ms:
            return self._packet
        self._last_scan, self._shape = timestamp, shape
        self._packet = {"markers": self.detect(gray), "timestamp": timestamp}
        return self._packet

    def detect(self, gray):
        cv2, np = self.cv2, self.np
        height, width = gray.shape[:2]
        if min(width, height) < 24:
            return []
        # Local thresholding handles projector falloff; Otsu also handles small
        # markers whose black border is wider than an adaptive neighborhood.
        masks = [cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1],
                 cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY_INV, 31, 7)]
        candidates = []
        for mask in masks:
            contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
            for contour in contours:
                area = cv2.contourArea(contour)
                if not 18 ** 2 <= area <= width * height * .15:
                    continue
                perimeter = cv2.arcLength(contour, True)
                polygon = cv2.approxPolyDP(contour, .025 * perimeter, True)
                if len(polygon) != 4 or not cv2.isContourConvex(polygon):
                    continue
                corners = polygon.reshape(4, 2).astype(np.float32)
                center = corners.mean(axis=0)
                # Only cyclic ordering matters because payload decoding accepts
                # all rotations and reflections; avoid the usual sum/difference
                # ordering's duplicate corners when the marker rotates 45 deg.
                corners = corners[np.argsort(np.arctan2(corners[:, 1] - center[1], corners[:, 0] - center[0]))]
                lengths = [float(np.linalg.norm(corners[i] - corners[(i + 1) % 4])) for i in range(4)]
                if min(lengths) < 14 or max(lengths) / min(lengths) > 5:
                    continue
                square = np.float32([[0, 0], [59, 0], [59, 59], [0, 59]])
                matrix = cv2.getPerspectiveTransform(corners, square)
                patch = cv2.warpPerspective(gray, matrix, (60, 60))
                # Sample away from each cell edge to tolerate resampling and blur.
                cells = [[float(np.median(patch[y * 10 + 3:y * 10 + 7, x * 10 + 3:x * 10 + 7]))
                          for x in range(6)] for y in range(6)]
                dark = min(cell for row in cells for cell in row)
                light = max(cell for row in cells for cell in row)
                if light - dark < 45:
                    continue
                threshold = (light + dark) / 2
                if any(cells[y][x] >= threshold for y in range(6) for x in range(6)
                       if y in (0, 5) or x in (0, 5)):
                    continue
                payload = [[int(cells[y][x] > threshold) for x in range(1, 5)] for y in range(1, 5)]
                identity = decode_payload(payload)
                if identity is None:
                    continue
                # Perspective projection does not preserve the average of four
                # corners. Project the square's actual center through its inverse.
                inverse = cv2.getPerspectiveTransform(square, corners)
                point = cv2.perspectiveTransform(np.float32([[[29.5, 29.5]]]), inverse)[0, 0]
                candidates.append((identity, (float(point[0]) / width, float(point[1]) / height), area))
        markers = []
        for identity in range(4):
            matches = sorted((candidate for candidate in candidates if candidate[0] == identity),
                             key=lambda candidate: candidate[2], reverse=True)
            if not matches:
                continue
            _, center, area = matches[0]
            # The same contour appears in both thresholds. A second distant
            # marker carrying this ID is ambiguous, so omit that corner entirely.
            if any(math.hypot((other[1][0] - center[0]) * width,
                              (other[1][1] - center[1]) * height) > math.sqrt(area) * .4
                   for other in matches[1:]):
                continue
            markers.append({"id": identity, "center": [round(center[0], 6), round(center[1], 6)]})
        return markers

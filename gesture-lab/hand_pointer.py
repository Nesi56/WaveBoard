"""One touch-style pointer from tracked hands, for the WaveBoard browser workspace.

The workspace (web/ at the repository root, served by ``python -m waveboard``)
accepts input through window.WaveBoardInput. server.py adds the pointer computed
here to every tracking frame, and web/hands.js turns it into browser input:

  hand in view ............ cursor between the thumb and index fingertips
  thumb + index pinch ..... touch: press, drag, release (a quick pinch is a tap)
  open palm swipe ......... left / right arrow key (Home cards, slides)

Pure Python, like canvas_gestures, so it is tested without a camera.
"""

from canvas_gestures import PointFilter, ScreenMap, SwipeDetector, distance, midpoint

# Smoothing and thresholds work in these virtual pixels; the output is 0..1.
SCREEN = (1280, 720)


class HandPointer:
    press_radius = 26          # px: a pinch that moves less than this is a tap, not a drag
    swipe_distance = 0.2 * SCREEN[0]
    swipe_cooldown_ms = 800

    def __init__(self, reach=0.12, smoothing=True):
        self.reach = reach
        self.smoothing = smoothing
        self.primary = None
        self.down = False
        self.swipe_id = 0
        self.swipe_direction = 0
        self._filter = None
        self._anchor = None
        self._map = None
        self._swipes = {}
        self._last_swipe = -10 ** 9

    def update(self, hands, timestamp, aspect_ratio=16 / 9):
        """hands: GestureEngine hand records (mirrored, normalized landmarks). Returns a JSON-safe dict."""
        size = (round(SCREEN[1] * aspect_ratio), SCREEN[1])
        if self._map is None or self._map.camera_size != size:
            self._map = ScreenMap(size, SCREEN, self.reach)
        self._detect_swipes(hands, timestamp)

        primary = next((h for h in hands if h["id"] == self.primary), None)
        if primary is None or (not self.down and not primary["pinches"]["index"]):
            # Keep following one hand; a hand that starts pinching takes over.
            primary = next((h for h in hands if h["pinches"]["index"]), None) or primary or (hands[0] if hands else None)
        if primary is None:
            self.primary, self.down, self._anchor, self._filter = None, False, None, None
            return self._packet(None)
        if primary["id"] != self.primary:
            self.primary, self.down, self._anchor = primary["id"], False, None
            self._filter = PointFilter(self.smoothing)

        landmarks = primary["landmarks"]
        # Between thumb and index tips: it barely moves when the fingers close, so
        # the cursor does not jump at the moment of a pinch.
        point = self._filter(self._map.to_screen(*midpoint(landmarks[4], landmarks[8])), timestamp)
        down = bool(primary["pinches"]["index"])
        if down and not self.down:
            self._anchor = point
        elif not down:
            self._anchor = None
        self.down = down
        if self._anchor is not None:
            if distance(point, self._anchor) <= self.press_radius:
                point = self._anchor
            else:
                self._anchor = None  # a drag: follow the hand from now on
        return self._packet(point)

    def _detect_swipes(self, hands, timestamp):
        present = {hand["id"] for hand in hands}
        self._swipes = {hand_id: swipe for hand_id, swipe in self._swipes.items() if hand_id in present}
        for hand in hands:
            detector = self._swipes.setdefault(hand["id"], SwipeDetector(self.swipe_distance))
            fingers = hand["fingers"]
            if not (fingers["index"] and fingers["middle"] and fingers["ring"] and fingers["pinky"]) \
                    or any(hand["pinches"].values()):
                detector.reset()
                continue
            swipe = detector.update(self._map.to_screen(*hand["palm"][:2]), timestamp,
                                    armed=timestamp - self._last_swipe >= self.swipe_cooldown_ms)
            if swipe:
                self._last_swipe = timestamp
                self.swipe_id += 1
                self.swipe_direction = swipe[0]

    def _packet(self, point):
        packet = {"visible": point is not None, "x": None, "y": None, "down": self.down, "hand": self.primary,
                  "swipe_id": self.swipe_id, "swipe": self.swipe_direction}
        if point is not None:
            packet["x"] = min(max(point[0] / SCREEN[0], 0.0), 1.0)
            packet["y"] = min(max(point[1] / SCREEN[1], 0.0), 1.0)
        return packet

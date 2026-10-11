"""Hand pointer and skeleton for the WaveBoard workspace, from tracked hands.

The workspace (web/ at the repository root, served by ``python -m waveboard``)
accepts input through window.WaveBoardInput. tracker.py adds what is computed
here to every tracking frame, and web/hands.js draws the skeletons and turns the
pointer into browser input:

  hands in view ........... skeletons drawn over the workspace (no camera image)
  primary hand ............ cursor between the thumb and index fingertips
  thumb + index pinch ..... touch: press, drag, release (a quick pinch is a tap)
  open palm swipe ......... left / right arrow key (Home cards, slides)

Pure Python, so it is tested without a camera.
"""

from collections import deque
import math

# Smoothing and thresholds work in these virtual pixels; the output is 0..1.
SCREEN = (1280, 720)


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def midpoint(a, b):
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


class ScreenMap:
    """Map the centre of the camera image onto the screen.

    A margin of the camera image is ignored so a hand can reach the screen edges
    without leaving the camera's view. The cropped region has the screen's aspect
    ratio, so hand movements are not stretched on screen.
    """

    def __init__(self, camera_size, screen_size, margin=0.12):
        cam_w, cam_h = camera_size
        screen_w, screen_h = screen_size
        margin = min(max(margin, 0.0), 0.3)
        usable_w, usable_h = cam_w * (1 - 2 * margin), cam_h * (1 - 2 * margin)
        aspect = screen_w / screen_h
        if usable_w / usable_h > aspect:
            w, h = usable_h * aspect, usable_h
        else:
            w, h = usable_w, usable_w / aspect
        self.camera_size, self.screen_size = (cam_w, cam_h), (screen_w, screen_h)
        self.crop = (round((cam_w - w) / 2), round((cam_h - h) / 2), round(w), round(h))
        self.scale = (screen_w / self.crop[2], screen_h / self.crop[3])

    def to_screen(self, nx, ny):
        """Normalized camera coordinates (mirrored, 0..1) -> screen pixels."""
        x0, y0 = self.crop[:2]
        return ((nx * self.camera_size[0] - x0) * self.scale[0], (ny * self.camera_size[1] - y0) * self.scale[1])


class OneEuro:
    """One Euro filter (Casiez et al., CHI 2012): steady at rest, little lag when moving fast."""

    def __init__(self, min_cutoff=1.4, beta=0.012, d_cutoff=1.0):
        self.min_cutoff, self.beta, self.d_cutoff = min_cutoff, beta, d_cutoff
        self.value = None
        self.speed = 0.0
        self.time = None

    @staticmethod
    def _alpha(cutoff, dt):
        return 1.0 / (1.0 + 1.0 / (2 * math.pi * cutoff * dt))

    def __call__(self, value, seconds):
        if self.value is None:
            self.value, self.time = value, seconds
            return value
        dt = seconds - self.time
        if dt <= 0:
            return self.value
        a_d = self._alpha(self.d_cutoff, dt)
        self.speed = a_d * (value - self.value) / dt + (1 - a_d) * self.speed
        a = self._alpha(self.min_cutoff + self.beta * abs(self.speed), dt)
        self.value = a * value + (1 - a) * self.value
        self.time = seconds
        return self.value


class PointFilter:
    def __init__(self, enabled=True):
        self.enabled = enabled
        self.axes = (OneEuro(), OneEuro())

    def __call__(self, point, t_ms):
        if not self.enabled:
            return (point[0], point[1])
        return (self.axes[0](point[0], t_ms / 1000), self.axes[1](point[1], t_ms / 1000))


class SwipeDetector:
    """A fast, mostly horizontal movement of one point (an open palm)."""

    def __init__(self, distance, window_ms=350):
        self.distance, self.window_ms = distance, window_ms
        self.history = deque()

    def reset(self):
        self.history.clear()

    def update(self, point, t, armed=True):
        """Returns (direction, start point) once per swipe, direction -1 = moved left; else None."""
        self.history.append((t, point))
        while t - self.history[0][0] > self.window_ms:
            self.history.popleft()
        start = self.history[0][1]
        dx, dy = point[0] - start[0], point[1] - start[1]
        if armed and abs(dx) >= self.distance and abs(dy) <= 0.6 * abs(dx):
            self.history.clear()
            return (-1 if dx < 0 else 1), start
        return None


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
        self._joint_filters = {}
        self._skeletons = []
        self._last_swipe = -10 ** 9

    def update(self, hands, timestamp, aspect_ratio=16 / 9):
        """hands: HandEngine hand records (mirrored, normalized landmarks). Returns a JSON-safe dict."""
        size = (round(SCREEN[1] * aspect_ratio), SCREEN[1])
        if self._map is None or self._map.camera_size != size:
            self._map = ScreenMap(size, SCREEN, self.reach)
        self._detect_swipes(hands, timestamp)
        self._update_skeletons(hands, timestamp)

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

    def _update_skeletons(self, hands, timestamp):
        """All 21 joints of every hand, smoothed and mapped to the screen like the cursor."""
        present = {hand["id"] for hand in hands}
        self._joint_filters = {hand_id: f for hand_id, f in self._joint_filters.items() if hand_id in present}
        self._skeletons = []
        for hand in hands:
            filters = self._joint_filters.setdefault(hand["id"], [PointFilter(self.smoothing) for _ in range(21)])
            points = [f(self._map.to_screen(p[0], p[1]), timestamp) for f, p in zip(filters, hand["landmarks"])]
            self._skeletons.append({"id": hand["id"], "pinch": bool(hand["pinches"]["index"]),
                                    "points": [[round(x / SCREEN[0], 4), round(y / SCREEN[1], 4)] for x, y in points]})

    def _packet(self, point):
        packet = {"visible": point is not None, "x": None, "y": None, "down": self.down, "hand": self.primary,
                  "swipe_id": self.swipe_id, "swipe": self.swipe_direction,
                  "hands": [{**skeleton, "primary": skeleton["id"] == self.primary} for skeleton in self._skeletons]}
        if point is not None:
            packet["x"] = min(max(point[0] / SCREEN[0], 0.0), 1.0)
            packet["y"] = min(max(point[1] / SCREEN[1], 0.0), 1.0)
        return packet

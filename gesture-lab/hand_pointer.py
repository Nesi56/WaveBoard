"""Hand pointer and skeleton for the WaveBoard workspace, from tracked hands.

The local desktop workspace (web/ at the repository root)
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

    def to_camera(self, x, y):
        """Screen pixels -> mirrored camera coordinates, without cropping or clamping."""
        x0, y0 = self.crop[:2]
        return ((x / self.scale[0] + x0) / self.camera_size[0],
                (y / self.scale[1] + y0) / self.camera_size[1])


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
    hold_ms = 220
    observation_limit_ms = 450

    def __init__(self, reach=0.12, smoothing=True, max_hands=2):
        if max_hands not in (1, 2):
            raise ValueError("max_hands must be 1 or 2")
        self.reach = reach
        self.smoothing = smoothing
        self.max_hands = max_hands
        self.primary = None
        self.down = False
        self.swipe_id = 0
        self.swipe_direction = 0
        self._camera_swipe = None
        self._filter = None
        self._anchor = None
        self._map = None
        self._swipes = {}
        self._joint_filters = {}
        self._skeletons = []
        self._last_swipe = -10 ** 9
        self._last_hands = {}
        self._point = None
        self._cancelled = False
        self._require_release = False
        self._had_gap = False
        self._tracking = {}
        self._last_update = None

    def _prepare_hands(self, hands, timestamp):
        """Keep measured flow separate from frozen visuals and gesture evidence."""
        current = []
        present = set()
        for source in hands:
            hand = dict(source)
            observed = bool(hand.get("observed", not hand.get("predicted", False)))
            age = max(0, hand.get("tracking_age_ms", 0))
            observation = hand.get("observation_timestamp", timestamp - age)
            age = max(age, timestamp - observation)
            flow = hand.get("tracking_source") == "flow" and not hand.get("predicted", False)
            if age >= self.observation_limit_ms:
                continue
            if observed or flow:
                hand.update(observed=observed, predicted=False, motion_tracked=True,
                            tracking_age_ms=age, observation_timestamp=observation)
                self._last_hands[hand["id"]] = (timestamp, hand)
                current.append(hand)
                present.add(hand["id"])
        for identity, (last_motion, hand) in list(self._last_hands.items()):
            age = timestamp - hand["observation_timestamp"]
            if timestamp - last_motion > self.hold_ms or age >= self.observation_limit_ms:
                del self._last_hands[identity]
                continue
            if identity not in present:
                current.append({**hand, "observed": False, "predicted": True,
                                "motion_tracked": False, "tracking_source": "held",
                                "tracking_age_ms": age, "interaction_cancelled": False})
        # Repeated detector identity changes must not accumulate ghost skeletons
        # beyond the configured hand count. Prefer current evidence over holds;
        # retaining the primary breaks ties without overriding fresh detections.
        current.sort(key=lambda hand: (0 if hand["observed"] else 1 if hand["motion_tracked"] else 2,
                                       hand["id"] != self.primary, hand["tracking_age_ms"]))
        selected, identities = [], set()
        for hand in current:
            if hand["id"] in identities:
                continue
            selected.append(hand)
            identities.add(hand["id"])
            if len(selected) == self.max_hands:
                break
        self._last_hands = {hand["id"]: self._last_hands[hand["id"]] if hand["predicted"] else (timestamp, hand)
                            for hand in selected}
        return selected

    def _cancel_press(self):
        if self.down:
            self._cancelled = True
            self._require_release = True
        self.down, self._anchor = False, None

    def update(self, hands, timestamp, aspect_ratio=16 / 9):
        """hands: HandEngine hand records (mirrored, normalized landmarks). Returns a JSON-safe dict."""
        self._cancelled = False
        if self._last_update is not None and timestamp - self._last_update >= self.observation_limit_ms:
            # The camera loop may stop producing packets entirely. A fresh
            # result must not silently revive a press that expired meanwhile.
            self._cancel_press()
            self._last_hands.clear()
            self._swipes.clear()
            self._joint_filters.clear()
            self._filter = PointFilter(self.smoothing) if self.primary is not None else None
        self._last_update = timestamp
        hands = self._prepare_hands(hands, timestamp)
        size = (round(SCREEN[1] * aspect_ratio), SCREEN[1])
        if self._map is None or self._map.camera_size != size:
            self._map = ScreenMap(size, SCREEN, self.reach)
        self._detect_swipes(hands, timestamp)
        self._update_skeletons(hands, timestamp)

        primary = next((h for h in hands if h["id"] == self.primary), None)
        if primary is None and self.down:
            self._cancel_press()
        if primary is None or (not self.down and not primary["pinches"]["index"]):
            # Keep following one hand; a hand that starts pinching takes over.
            primary = next((h for h in hands if h["observed"] and h["pinches"]["index"]), None) \
                or primary or (hands[0] if hands else None)
        if primary is None:
            self.primary, self.down, self._anchor, self._filter = None, False, None, None
            self._point, self._tracking, self._had_gap = None, {}, False
            return self._packet(None)
        if primary["id"] != self.primary:
            self.primary, self.down, self._anchor = primary["id"], False, None
            self._filter = PointFilter(self.smoothing)
            self._had_gap = False
        self._tracking = {key: primary.get(key) for key in
                          ("observed", "predicted", "motion_tracked", "tracking_source", "tracking_age_ms")}

        if primary["predicted"]:
            self._had_gap = True
            # Holding a shape prevents flicker without drawing invented strokes.
            return self._packet(self._point)

        landmarks = primary["landmarks"]
        # Between thumb and index tips: it barely moves when the fingers close, so
        # the cursor does not jump at the moment of a pinch.
        point = self._filter(self._map.to_screen(*midpoint(landmarks[4], landmarks[8])), timestamp)
        down = self.down
        if primary["observed"]:
            if primary.get("interaction_cancelled") or \
                    (self._had_gap and self.down and not primary["pinches"]["index"]):
                self._cancel_press()
            if self._require_release and primary.get("pinch_released", not any(primary["pinches"].values())):
                self._require_release = False
            down = bool(primary["pinches"]["index"]) and not self._require_release and not self._cancelled
            self._had_gap = False
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
        self._point = point
        return self._packet(point)

    def _detect_swipes(self, hands, timestamp):
        present = {hand["id"] for hand in hands}
        self._swipes = {hand_id: swipe for hand_id, swipe in self._swipes.items() if hand_id in present}
        for hand in hands:
            detector = self._swipes.setdefault(hand["id"], SwipeDetector(self.swipe_distance))
            if not hand["observed"]:
                if hand["predicted"]:
                    detector.reset()
                continue
            fingers = hand["fingers"]
            if not (fingers["index"] and fingers["middle"] and fingers["ring"] and fingers["pinky"]) \
                    or any(hand["pinches"].values()) or hand.get("reacquired", False):
                detector.reset()
                continue
            point = self._map.to_screen(*hand["palm"][:2])
            swipe = detector.update(point, timestamp,
                                    armed=timestamp - self._last_swipe >= self.swipe_cooldown_ms)
            if swipe:
                self._last_swipe = timestamp
                self.swipe_id += 1
                self.swipe_direction = swipe[0]
                self._camera_swipe = [list(self._map.to_camera(*endpoint)) for endpoint in (swipe[1], point)]

    def _update_skeletons(self, hands, timestamp):
        """All 21 joints of every hand, smoothed and mapped to the screen like the cursor."""
        present = {hand["id"] for hand in hands}
        self._joint_filters = {hand_id: f for hand_id, f in self._joint_filters.items() if hand_id in present}
        previous = {skeleton["id"]: skeleton for skeleton in self._skeletons}
        self._skeletons = []
        for hand in hands:
            filters = self._joint_filters.setdefault(hand["id"], [PointFilter(self.smoothing) for _ in range(21)])
            if hand["predicted"] and hand["id"] in previous:
                points = previous[hand["id"]]["points"]
                camera_points = previous[hand["id"]]["camera_points"]
            else:
                filtered = [f(self._map.to_screen(p[0], p[1]), timestamp) for f, p in zip(filters, hand["landmarks"])]
                points = [[round(x / SCREEN[0], 4), round(y / SCREEN[1], 4)] for x, y in filtered]
                # Preserve the same filtering while exposing the entire camera
                # image for projection calibration, including beyond the crop.
                camera_points = [[round(value, 6) for value in self._map.to_camera(x, y)]
                                 for x, y in filtered]
            self._skeletons.append({"id": hand["id"], "pinch": bool(hand["pinches"]["index"]),
                                    "observed": hand["observed"], "predicted": hand["predicted"],
                                    "motion_tracked": hand["motion_tracked"],
                                    "tracking_age_ms": hand["tracking_age_ms"],
                                    "points": points, "camera_points": camera_points})

    def _packet(self, point):
        packet = {"visible": point is not None, "x": None, "y": None,
                  "camera_x": None, "camera_y": None, "down": self.down, "hand": self.primary,
                  "swipe_id": self.swipe_id, "swipe": self.swipe_direction,
                  "camera_swipe": self._camera_swipe,
                  "observed": False, "predicted": False, "motion_tracked": False,
                  "tracking_age_ms": 0, "tracking_source": "lost", "cancelled": self._cancelled,
                  **self._tracking,
                  "hands": [{**skeleton, "primary": skeleton["id"] == self.primary} for skeleton in self._skeletons]}
        if point is not None:
            packet["camera_x"], packet["camera_y"] = self._map.to_camera(*point)
            packet["x"] = min(max(point[0] / SCREEN[0], 0.0), 1.0)
            packet["y"] = min(max(point[1] / SCREEN[1], 0.0), 1.0)
        return packet

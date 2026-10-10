"""Canvas gestures for WaveBoard: frame, stretch, move, draw and swipe.

Pure Python with no camera libraries, so the state machine can be tested with
synthetic hands. All positions are screen pixels: the app maps camera
landmarks onto the projected screen (ScreenMap) before calling
CanvasStudio.update(), which keeps distances equal along x and y.

  Both hands in an L (thumb + index out) .. frame a new canvas; pull apart to
                                            stretch it, relax both hands to place it
  Thumb + index pinch on a canvas ......... move it; pinch it with both hands to stretch
  Point with the index finger ............. draw on a whiteboard; laser pointer on slides
                                            and lenses (or draw there too with a pen tool)
  Thumb + middle pinch .................... change what the canvas shows
  Thumb + ring pinch ...................... undo the last stroke
  Thumb + pinky pinch ..................... next tool: laser pointer, then each ink colour
  Open palm swipe left / right ............ next / previous slide
"""

import math
from collections import deque
from dataclasses import dataclass, field

CONTENTS = ("slides", "board", "lens:neon", "lens:thermal", "lens:pixel", "lens:xray", "lens:magnify")
CONTENT_NAMES = {
    "slides": "Slides", "board": "Whiteboard", "lens:neon": "Neon edges lens",
    "lens:thermal": "Thermal lens", "lens:pixel": "Pixel lens", "lens:xray": "X-ray lens",
    "lens:magnify": "Magnifier lens",
}
INK_COLORS = ("yellow", "red", "cyan", "green", "white", "black")

THUMB_MCP, THUMB_TIP, INDEX_MCP, INDEX_TIP = 2, 4, 5, 8
PINCH_TIPS = {"index": 8, "middle": 12, "ring": 16, "pinky": 20}
PALM = (0, 5, 9, 13, 17)


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def midpoint(a, b):
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


@dataclass
class Rect:
    x: float
    y: float
    w: float
    h: float

    @classmethod
    def around(cls, points):
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        return cls(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))

    @property
    def center(self):
        return (self.x + self.w / 2, self.y + self.h / 2)

    def contains(self, point, margin=0.0):
        return (self.x - margin <= point[0] <= self.x + self.w + margin
                and self.y - margin <= point[1] <= self.y + self.h + margin)

    def local(self, point):
        """Screen pixels -> canvas-relative (0..1, 0..1)."""
        return ((point[0] - self.x) / max(self.w, 1e-6), (point[1] - self.y) / max(self.h, 1e-6))

    def screen(self, uv):
        return (self.x + uv[0] * self.w, self.y + uv[1] * self.h)

    def copy(self):
        return Rect(self.x, self.y, self.w, self.h)


def snap_aspect(rect, ratios=(16 / 9, 4 / 3, 1.0), tolerance=0.07):
    """Snap a nearly 16:9, 4:3 or square rectangle to the exact ratio, keeping centre and area."""
    if rect.w <= 0 or rect.h <= 0:
        return rect.copy()
    aspect = rect.w / rect.h
    for ratio in ratios:
        if abs(aspect / ratio - 1) <= tolerance:
            area = rect.w * rect.h
            w, h = math.sqrt(area * ratio), math.sqrt(area / ratio)
            cx, cy = rect.center
            return Rect(cx - w / 2, cy - h / 2, w, h)
    return rect.copy()


class ScreenMap:
    """Map the centre of the camera image onto the screen.

    A margin of the camera image is ignored so a hand can reach the screen edges
    without leaving the camera's view. The cropped region has the screen's aspect
    ratio, so the camera background, lenses and hand positions stay aligned.
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


@dataclass
class Hand:
    """One tracked hand, already in screen pixels."""
    id: str
    points: list   # 21 (x, y) landmarks
    fingers: dict  # thumb/index/middle/ring/pinky -> extended
    pinches: dict  # index/middle/ring/pinky -> active thumb pinch


def classify(hand):
    """Instant pose name. Pinches win; an L needs the thumb out, pointing needs it tucked."""
    for name in PINCH_TIPS:
        if hand.pinches.get(name):
            return f"pinch:{name}"
    f = hand.fingers
    others_folded = not (f["middle"] or f["ring"] or f["pinky"])
    if f["index"] and others_folded:
        return "frame" if f["thumb"] else "point"
    if f["index"] and f["middle"] and f["ring"] and f["pinky"]:
        return "open"
    if not (f["index"] or f["middle"] or f["ring"] or f["pinky"]):
        return "fist"
    return "other"


def frame_rect(hands):
    """Rectangle framed by two L-shaped hands.

    The box around both thumb tips, index tips and thumb webs works for the
    diagonal frame (hands at opposite corners) and for the upright "director"
    frame (both index fingers up, thumbs pointing at each other).
    """
    points = []
    for hand in hands:
        p = hand.points
        points += [p[THUMB_TIP], p[INDEX_TIP], midpoint(p[THUMB_MCP], p[INDEX_MCP])]
    return Rect.around(points)


class StablePose:
    """A new pose must persist hold_ms before it replaces the stable pose.

    Pinches already have hysteresis and debouncing in gestures.PinchState, so
    changes into or out of a pinch apply at once.
    """

    def __init__(self, hold_ms=100):
        self.hold_ms = hold_ms
        self.stable = "none"
        self.candidate = None
        self.since = 0
        self.changed_at = 0  # first sighting of the pose that is now stable

    def update(self, raw, t):
        if raw == self.stable:
            self.candidate = None
            return self.stable
        if raw != self.candidate:
            self.candidate, self.since = raw, t
        hold = 0 if raw.startswith("pinch") or self.stable.startswith("pinch") else self.hold_ms
        if t - self.since >= hold:
            self.stable, self.changed_at, self.candidate = raw, self.since, None
        return self.stable


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


@dataclass
class Stroke:
    color: str
    points: list = field(default_factory=list)  # canvas-relative (u, v)
    times: list = field(default_factory=list)   # ms, used to trim the end of a stroke


@dataclass
class Canvas:
    id: int
    rect: Rect
    content: str
    page: int = 0
    forming: bool = False
    ink: dict = field(default_factory=dict)  # ink layer -> [Stroke]

    def layer(self):
        """Slides keep separate ink for every page; other contents share one layer."""
        return f"slide-{self.page}" if self.content == "slides" else "free"

    def strokes(self):
        return self.ink.setdefault(self.layer(), [])


@dataclass
class _HandState:
    pose: StablePose
    filters: dict = field(default_factory=dict)
    tip: tuple = (0.0, 0.0)
    pinch_point: tuple = (0.0, 0.0)
    palm: tuple = (0.0, 0.0)
    grab: int | None = None        # canvas id held by an index pinch
    stroke: tuple | None = None    # (canvas id, Stroke)
    swipe: SwipeDetector | None = None
    trail: deque = field(default_factory=deque)  # recent laser pointer positions


@dataclass
class _Manipulation:
    hands: tuple
    rect: Rect     # canvas rectangle when these hands took hold
    points: list   # their pinch points at that moment


@dataclass
class _Framing:
    start: int
    rect: Rect
    filters: tuple
    canvas: int | None = None
    history: deque = field(default_factory=deque)


class CanvasStudio:
    charge_ms = 450          # hold an L-L frame this long before the canvas appears
    pose_hold_ms = 100
    commit_lookback_ms = 60  # place the canvas where it was just before the hands relaxed
    stray_stroke_ms = 400    # strokes this young are removed when a frame starts
    swipe_window_ms = 350
    swipe_cooldown_ms = 800
    laser_trail_ms = 250

    def __init__(self, width, height, slide_count=0, new_content="lens:neon", smoothing=True):
        self.width, self.height = width, height
        self.slide_count = slide_count
        self.new_content = new_content
        self.smoothing = smoothing
        self.canvases = []  # drawing order: last is on top
        self.focus = None
        self.ink = 0
        # Presenters point at slides while talking, so pointing there is a laser
        # pointer until a pen is chosen. Whiteboards always take ink.
        self.laser = True
        self.paused = False
        self.now = 0
        self.messages = deque(maxlen=4)
        self.min_size = (0.08 * width, 0.08 * height)
        self.trash = ((width / 2, height * 0.9), height * 0.075)
        self.swipe_distance = 0.18 * width
        self._hands = {}
        self._manipulations = {}
        self._framing = None
        self._last_swipe = -10 ** 9
        self._next_id = 1

    # ---- canvas operations shared by gestures, mouse and keyboard ----

    def notify(self, text):
        self.messages.append((self.now, text))

    def message(self, t, duration_ms=1800):
        if self.messages and t - self.messages[-1][0] <= duration_ms:
            return self.messages[-1][1]
        return None

    def tick(self, t):
        self.now = max(self.now, t)

    def get(self, canvas_id):
        return next((c for c in self.canvases if c.id == canvas_id), None)

    def canvas_at(self, point, margin=0.0):
        for canvas in reversed(self.canvases):
            if not canvas.forming and canvas.rect.contains(point, margin):
                return canvas
        return None

    def focused(self):
        return self.get(self.focus) or (self.canvases[-1] if self.canvases else None)

    def add_canvas(self, rect, content=None, forming=False):
        canvas = Canvas(self._next_id, rect.copy(), content or self.new_content, forming=forming)
        if canvas.content == "slides" and not self.slide_count:
            canvas.content = "board"
        self._next_id += 1
        self.canvases.append(canvas)
        if not forming:
            self.focus = canvas.id
        return canvas

    def raise_canvas(self, canvas):
        self.canvases.remove(canvas)
        self.canvases.append(canvas)
        self.focus = canvas.id

    def remove(self, canvas):
        self.canvases = [c for c in self.canvases if c is not canvas]
        self._manipulations.pop(canvas.id, None)
        for state in self._hands.values():
            if state.grab == canvas.id:
                state.grab = None
            if state.stroke and state.stroke[0] == canvas.id:
                state.stroke = None
        if self.focus == canvas.id:
            self.focus = None

    def in_trash(self, point):
        return distance(point, self.trash[0]) <= self.trash[1]

    def _content_options(self):
        return [c for c in CONTENTS if c != "slides" or self.slide_count]

    def cycle_content(self, canvas, step=1):
        options = self._content_options()
        index = options.index(canvas.content) if canvas.content in options else -1
        canvas.content = options[(index + step) % len(options)]
        self.notify(CONTENT_NAMES[canvas.content])

    def cycle_new_content(self, step=1):
        options = self._content_options()
        index = options.index(self.new_content) if self.new_content in options else -1
        self.new_content = options[(index + step) % len(options)]
        self.notify(f"New canvases: {CONTENT_NAMES[self.new_content]}")

    def turn_page(self, canvas, step):
        if canvas.content != "slides" or not self.slide_count:
            return
        page = min(max(canvas.page + step, 0), self.slide_count - 1)
        if page == canvas.page:
            self.notify("Last slide" if step > 0 else "First slide")
        else:
            canvas.page = page
            self.notify(f"Slide {page + 1} / {self.slide_count}")

    def slide_target(self, point=None):
        under = self.canvas_at(point) if point else None
        if under and under.content == "slides":
            return under
        focused = self.get(self.focus)
        if focused and focused.content == "slides":
            return focused
        return next((c for c in reversed(self.canvases) if c.content == "slides"), None)

    def undo(self, canvas):
        strokes = canvas.strokes()
        if strokes:
            strokes.pop()
            self.notify("Undo")
        else:
            self.notify("Nothing to undo")

    def clear(self, canvas):
        canvas.ink.pop(canvas.layer(), None)
        self.notify("Ink cleared")

    def next_tool(self):
        """Laser pointer -> each ink colour -> laser pointer."""
        if self.laser:
            self.laser = False
        elif self.ink == len(INK_COLORS) - 1:
            self.laser, self.ink = True, 0
        else:
            self.ink += 1
        self.notify("Laser pointer (whiteboards still draw)" if self.laser else f"Pen: {INK_COLORS[self.ink]}")

    def draws_on(self, canvas):
        return canvas.content == "board" or not self.laser

    def start_stroke(self, canvas, point, t):
        stroke = Stroke(INK_COLORS[self.ink], [canvas.rect.local(point)], [t])
        canvas.strokes().append(stroke)
        self.focus = canvas.id
        return stroke

    @staticmethod
    def extend_stroke(canvas, stroke, point, t, min_step=2.0):
        if distance(canvas.rect.screen(stroke.points[-1]), point) >= min_step:
            stroke.points.append(canvas.rect.local(point))
            stroke.times.append(t)

    def keep_visible(self, rect, visible=48):
        rect = rect.copy()
        rect.x = min(max(rect.x, visible - rect.w), self.width - visible)
        rect.y = min(max(rect.y, visible - rect.h), self.height - visible)
        return rect

    # ---- hand tracking ----

    def update(self, hands, t):
        """Advance the gesture state with the hands seen at time t (ms). Returns overlay info."""
        self.tick(t)
        present = {hand.id for hand in hands}
        for hand_id in [h for h in self._hands if h not in present]:
            self._drop_hand(hand_id)
        states = []
        for hand in hands:
            state = self._hands.get(hand.id)
            if state is None:
                state = self._hands[hand.id] = _HandState(
                    StablePose(self.pose_hold_ms), swipe=SwipeDetector(self.swipe_distance, self.swipe_window_ms))
            previous = state.pose.stable
            pose = state.pose.update(classify(hand), t)
            self._measure(hand, state, pose, t)
            states.append((hand, state, previous, pose))

        if self.paused:
            self._release_all(t)
        else:
            framing = (len(states) == 2 and all(pose == "frame" for *_, pose in states)
                       and all(state.grab is None for _, state, _, _ in states))
            if framing:
                self._frame(states, t)
            elif self._framing:
                self._finish_frame(states, t)
            if not self._framing:
                for hand, state, previous, pose in states:
                    self._hand_actions(state, previous, pose, t)
                self._apply_manipulations()
        return self._overlay(states, t)

    def _filtered(self, state, name, point, t):
        if name not in state.filters:
            state.filters[name] = PointFilter(self.smoothing)
        return state.filters[name](point, t)

    def _measure(self, hand, state, pose, t):
        p = hand.points
        state.tip = self._filtered(state, "tip", p[INDEX_TIP], t)
        finger = pose.split(":")[1] if pose.startswith("pinch:") else "index"
        state.pinch_point = self._filtered(state, f"pinch-{finger}", midpoint(p[THUMB_TIP], p[PINCH_TIPS[finger]]), t)
        palm = [p[i] for i in PALM]
        state.palm = (sum(q[0] for q in palm) / len(palm), sum(q[1] for q in palm) / len(palm))

    def _drop_hand(self, hand_id):
        # A lost hand keeps its ink and leaves any held canvas where it is.
        state = self._hands.pop(hand_id)
        self._end_stroke(state)

    def _release_all(self, t):
        if self._framing:
            self._finish_frame([], t)
        for state in self._hands.values():
            self._end_stroke(state)
            state.grab = None
            state.swipe.reset()
            state.trail.clear()
        self._manipulations.clear()

    def _hand_actions(self, state, previous, pose, t):
        if pose != previous:
            if previous == "pinch:index":
                self._release_grab(state)
            elif previous == "point":
                self._end_stroke(state, trim_from=state.pose.changed_at - 40)
                state.trail.clear()
            elif previous == "open":
                state.swipe.reset()
            self._start_pose(state, pose)
        if pose == "point":
            self._draw(state, t)
        elif pose == "open":
            self._swipe(state, t)

    def _start_pose(self, state, pose):
        if pose == "pinch:index":
            # A little slack around the border so a pinch on the edge still catches it.
            canvas = self.canvas_at(state.pinch_point, margin=16)
            if canvas:
                state.grab = canvas.id
                self.raise_canvas(canvas)
        elif pose == "pinch:middle":
            canvas = self.canvas_at(state.pinch_point)
            if canvas:
                self.focus = canvas.id
                self.cycle_content(canvas)
            else:
                self.cycle_new_content()
        elif pose == "pinch:ring":
            canvas = self.canvas_at(state.pinch_point) or self.focused()
            if canvas:
                self.undo(canvas)
        elif pose == "pinch:pinky":
            self.next_tool()

    def _release_grab(self, state):
        canvas_id, state.grab = state.grab, None
        if canvas_id is None or any(s.grab == canvas_id for s in self._hands.values()):
            return
        self._manipulations.pop(canvas_id, None)
        canvas = self.get(canvas_id)
        if canvas and self.in_trash(state.pinch_point):
            self.remove(canvas)
            self.notify("Canvas deleted")

    def _apply_manipulations(self):
        holders = {}
        for hand_id, state in sorted(self._hands.items()):
            if state.grab is not None:
                holders.setdefault(state.grab, []).append((hand_id, state.pinch_point))
        for canvas_id in [c for c in self._manipulations if c not in holders]:
            del self._manipulations[canvas_id]
        for canvas_id, entries in holders.items():
            canvas = self.get(canvas_id)
            if canvas is None:
                continue
            entries = entries[:2]
            key = tuple(hand_id for hand_id, _ in entries)
            points = [point for _, point in entries]
            current = self._manipulations.get(canvas_id)
            if current is None or current.hands != key:
                # A hand joined or left: take a fresh baseline so nothing jumps.
                self._manipulations[canvas_id] = _Manipulation(key, canvas.rect.copy(), points)
            elif len(points) == 1:
                start = current.rect
                canvas.rect = self.keep_visible(Rect(start.x + points[0][0] - current.points[0][0],
                                                     start.y + points[0][1] - current.points[0][1],
                                                     start.w, start.h))
            else:
                canvas.rect = self.keep_visible(self._stretched(current, points))

    def _stretched(self, manipulation, points, min_span=40.0):
        """Stretch so the canvas stays glued to both pinch points, independently in x and y.

        If the hands started nearly level (or one above the other), that axis has
        no reliable span and follows the overall distance ratio instead.
        """
        (a0, b0), (a1, b1), start = manipulation.points, points, manipulation.rect
        uniform = distance(a1, b1) / max(distance(a0, b0), 1e-6)
        scales = []
        for axis in (0, 1):
            span0, span1 = b0[axis] - a0[axis], b1[axis] - a1[axis]
            scales.append(span1 / span0 if abs(span0) >= min_span else uniform)
        w = min(max(start.w * max(scales[0], 0.05), 0.04 * self.width), 2.0 * self.width)
        h = min(max(start.h * max(scales[1], 0.05), 0.04 * self.height), 2.0 * self.height)
        u, v = start.local(midpoint(a0, b0))
        m = midpoint(a1, b1)
        return Rect(m[0] - u * w, m[1] - v * h, w, h)

    def _draw(self, state, t):
        if state.stroke:
            canvas_id, stroke = state.stroke
            canvas = self.get(canvas_id)
            if canvas and canvas.rect.contains(state.tip) and self.draws_on(canvas):
                self.extend_stroke(canvas, stroke, state.tip, t)
                return
            self._end_stroke(state)
        canvas = self.canvas_at(state.tip)
        if canvas and self.draws_on(canvas):
            state.stroke = (canvas.id, self.start_stroke(canvas, state.tip, t))
            state.trail.clear()
            return
        state.trail.append((t, state.tip))
        while t - state.trail[0][0] > self.laser_trail_ms:
            state.trail.popleft()

    def _end_stroke(self, state, trim_from=None):
        if not state.stroke:
            return
        canvas_id, stroke = state.stroke
        state.stroke = None
        if trim_from is not None:
            # The fingertip moves while the hand changes pose; drop that tail.
            keep = sum(1 for time in stroke.times if time < trim_from)
            del stroke.points[keep:], stroke.times[keep:]
        if not stroke.points:
            self._delete_stroke(canvas_id, stroke)

    def _delete_stroke(self, canvas_id, stroke):
        canvas = self.get(canvas_id)
        if canvas:
            for strokes in canvas.ink.values():
                strokes[:] = [s for s in strokes if s is not stroke]

    def _swipe(self, state, t):
        swipe = state.swipe.update(state.palm, t, armed=t - self._last_swipe >= self.swipe_cooldown_ms)
        if swipe:
            direction, start = swipe
            self._last_swipe = t
            target = self.slide_target(start)
            if target:
                # Like a touch screen: push the slide left to see the next one.
                self.turn_page(target, -direction)
            else:
                self.notify("Swipe changes slides on a slides canvas")

    def _frame(self, states, t):
        raw = frame_rect([hand for hand, *_ in states])
        if self._framing is None:
            self._framing = _Framing(t, raw, (PointFilter(self.smoothing), PointFilter(self.smoothing)))
            for _, state, _, _ in states:
                # Forming an L can briefly look like pointing; remove marks made just now.
                if state.stroke and t - state.stroke[1].times[0] <= self.stray_stroke_ms:
                    self._delete_stroke(*state.stroke)
                    state.stroke = None
                self._end_stroke(state)
                state.swipe.reset()
        framing = self._framing
        top_left = framing.filters[0]((raw.x, raw.y), t)
        bottom_right = framing.filters[1]((raw.x + raw.w, raw.y + raw.h), t)
        framing.rect = Rect.around([top_left, bottom_right])
        if framing.canvas is None and t - framing.start >= self.charge_ms:
            framing.canvas = self.add_canvas(framing.rect, forming=True).id
        canvas = self.get(framing.canvas) if framing.canvas is not None else None
        if canvas:
            canvas.rect = framing.rect.copy()
            framing.history.append((t, framing.rect.copy()))
            while t - framing.history[0][0] > 600:
                framing.history.popleft()

    def _finish_frame(self, states, t):
        framing, self._framing = self._framing, None
        canvas = self.get(framing.canvas) if framing.canvas is not None else None
        if canvas is None:
            return  # released before the canvas formed: nothing to place
        released = [state.pose.changed_at for _, state, _, pose in states if pose != "frame"]
        if len(states) < 2 or not released:
            released.append(t - self.pose_hold_ms)
        cutoff = min(released) - self.commit_lookback_ms
        rect = framing.history[0][1]
        for time, candidate in framing.history:
            if time <= cutoff:
                rect = candidate
        if rect.w < self.min_size[0] or rect.h < self.min_size[1]:
            self.remove(canvas)
            self.notify("Canvas cancelled")
            return
        canvas.rect = self.keep_visible(snap_aspect(rect))
        canvas.forming = False
        self.focus = canvas.id
        self.notify(f"{CONTENT_NAMES[canvas.content]} placed")

    def _overlay(self, states, t):
        cursors = []
        for hand, state, _, pose in states:
            position = state.pinch_point if pose.startswith("pinch:") else state.palm if pose == "open" else state.tip
            cursors.append({"hand": hand.id, "pose": pose, "pos": position,
                            "grabbing": state.grab is not None, "drawing": state.stroke is not None,
                            "laser": [p for _, p in state.trail] if pose == "point" and self.laser else []})
        framing = self._framing
        ghost = None
        if framing and framing.canvas is None:
            ghost = {"rect": framing.rect.copy(), "progress": min(1.0, (t - framing.start) / self.charge_ms)}
        single = [s for s in self._hands.values()
                  if s.grab is not None and sum(o.grab == s.grab for o in self._hands.values()) == 1]
        trash = {"visible": bool(single), "hot": any(self.in_trash(s.pinch_point) for s in single)}
        return {"cursors": cursors, "ghost": ghost, "trash": trash, "mode": self._mode(states)}

    def _mode(self, states):
        if self.paused:
            return "Gestures paused"
        if self._framing:
            return "Hold the frame..." if self._framing.canvas is None else "Stretch, then relax both hands to place"
        if any(len(m.hands) == 2 for m in self._manipulations.values()):
            return "Stretching"
        if any(state.grab is not None for _, state, _, _ in states):
            return "Moving"
        if any(state.stroke for _, state, _, _ in states):
            return "Drawing"
        return "Ready" if states else "Show your hands"

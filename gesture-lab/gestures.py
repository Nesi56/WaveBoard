"""Finger geometry and debounced gesture state, independent of camera libraries.

Landmarks are mirrored normalized image coordinates. World landmarks, when
available, are used for joint angles so finger extension does not depend on
whether the hand points up, down, or sideways.
"""

import itertools
import math
from dataclasses import dataclass, field

FINGERS = ("thumb", "index", "middle", "ring", "pinky")
TIPS = {"index": 8, "middle": 12, "ring": 16, "pinky": 20}


def distance(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def joint_angle(a, b, c):
    """Angle ABC in degrees; a straight finger has an angle near 180."""
    u = [x - y for x, y in zip(a, b)]
    v = [x - y for x, y in zip(c, b)]
    denom = math.sqrt(sum(x * x for x in u) * sum(x * x for x in v))
    if denom < 1e-12:
        return 0.0
    return math.degrees(math.acos(max(-1.0, min(1.0, sum(x * y for x, y in zip(u, v)) / denom))))


def finger_states(points):
    """Return all five extension states: tip reach for fingers, angles and abduction for the thumb.

    A finger is extended when its tip is clearly farther from the wrist than its
    middle (PIP) joint. MediaPipe's per-joint angles are noisy: in real sample
    images a visibly straight index finger measured 102 degrees at the PIP joint
    when the back of the hand faced the camera. The reach ratio separated
    straight (1.3-1.9) from curled (0.6-0.8) fingers in every sample; see
    tests/fixtures/mediapipe_sample_hands.json.

    These are heuristic pose states, not measured joint angles. Pinch decisions
    are independent of extension states so a bent index finger can still pinch.
    """
    states = {}
    for name, mcp in (("index", 5), ("middle", 9), ("ring", 13), ("pinky", 17)):
        states[name] = distance(points[0], points[mcp + 3]) > distance(points[0], points[mcp + 1]) * 1.12
    palm_width = max(distance(points[5], points[17]), 1e-6)
    states["thumb"] = (
        joint_angle(points[1], points[2], points[3]) > 140
        and joint_angle(points[2], points[3], points[4]) > 150
        and distance(points[4], points[5]) / palm_width > 0.45
    )
    return {name: bool(states[name]) for name in FINGERS}


def image_geometry(landmarks, aspect_ratio):
    """Use frame-height units; normalized x and y otherwise have unequal scales."""
    return [(p[0] * aspect_ratio, p[1], p[2] * aspect_ratio) for p in landmarks]


def pinch_ratios(landmarks, aspect_ratio):
    points = image_geometry(landmarks, aspect_ratio)
    # 2D distances intentionally agree with what the presenter sees on screen.
    palm = max(distance(points[0][:2], points[9][:2]), 1e-6)
    return {name: distance(points[4][:2], points[tip][:2]) / palm for name, tip in TIPS.items()}


@dataclass
class PinchState:
    on: float = 0.15
    off: float = 0.25
    debounce_ms: int = 50
    active: str | None = None
    candidate: str | None = None
    candidate_since: int = 0

    def update(self, ratios, timestamp_ms):
        possible = [name for name, ratio in ratios.items()
                    if ratio < (self.off if name == self.active else self.on)]
        selected = min(possible, key=lambda name: ratios[name]) if possible else None
        if selected != self.candidate:
            self.candidate = selected
            self.candidate_since = timestamp_ms
        if selected != self.active and timestamp_ms - self.candidate_since >= self.debounce_ms:
            self.active = selected
        return {name: name == self.active for name in TIPS}


@dataclass
class Track:
    identity: str
    handedness: str
    palm: list
    pinch: PinchState = field(default_factory=PinchState)


class HandIdentities:
    """Associate by palm proximity and handedness, never by detector array order."""

    def __init__(self):
        self.tracks = {}
        self.next_id = 1

    def assign(self, detections):
        old = list(self.tracks.values())
        palms = [[sum(d["landmarks"][i][axis] for i in (0, 5, 9, 13, 17)) / 5
                  for axis in (0, 1)] for d in detections]
        # Exhaustive assignment is small (at most two hands), and avoids a
        # nearest-neighbor greedy match assigning both detections the wrong hand.
        choices = list(range(len(old))) + [None]
        best, best_cost = None, float("inf")
        for assignment in itertools.product(choices, repeat=len(detections)):
            used = [i for i in assignment if i is not None]
            if len(set(used)) != len(used):
                continue
            cost = 0.0
            for index, previous in enumerate(assignment):
                if previous is None:
                    cost += 0.60
                    continue
                delta = distance(old[previous].palm, palms[index])
                if delta > 0.40:
                    cost += 10
                label = detections[index].get("handedness", "unknown")
                cost += delta + (0.18 if label != old[previous].handedness else 0)
            if cost < best_cost:
                best, best_cost = assignment, cost
        current, result = {}, []
        for i, detection in enumerate(detections):
            previous = best[i] if best is not None else None
            if previous is None:
                label = detection.get("handedness", "unknown")
                identity = f"{label.lower()}-{self.next_id}"
                self.next_id += 1
                track = Track(identity, label, palms[i])
            else:
                track = old[previous]
                track.palm = palms[i]
            current[track.identity] = track
            result.append(track)
        # Missing hands lose pinch state immediately. Reappearance gets a new id.
        self.tracks = current
        return result


class GestureEngine:
    def __init__(self, pose_debounce_ms=100):
        self.identities = HandIdentities()
        self.pose_debounce_ms = pose_debounce_ms
        self.mode = "idle"
        self.participants = ()
        self.event_id = 0
        self.candidate = None
        self.candidate_since = 0
        self.last_timestamp = None

    def _set_mode(self, mode, participants):
        key = tuple(sorted(participants))
        if (mode, key) != (self.mode, self.participants):
            self.mode, self.participants = mode, key
            self.event_id += 1

    def process(self, detections, timestamp_ms, aspect_ratio=16 / 9):
        """Return (public hand records, gesture). Timestamps are monotonic ms."""
        if self.last_timestamp is not None and timestamp_ms <= self.last_timestamp:
            raise ValueError("Gesture timestamps must increase monotonically")
        if self.last_timestamp is not None and timestamp_ms - self.last_timestamp > 500:
            # A stalled camera/inference loop is also a loss of tracking, even
            # if the next detector result contains a hand in the same location.
            self.identities.assign([])
            self.candidate = None
            self._set_mode("idle", ())
        self.last_timestamp = timestamp_ms
        tracks = self.identities.assign(detections)
        hands = []
        for detection, track in zip(detections, tracks):
            landmarks = detection["landmarks"]
            if len(landmarks) != 21:
                raise ValueError("Each hand must contain 21 landmarks")
            points = detection.get("world_landmarks") or image_geometry(landmarks, aspect_ratio)
            states = finger_states(points)
            pinches = track.pinch.update(pinch_ratios(landmarks, aspect_ratio), timestamp_ms)
            wrist, middle = landmarks[0], landmarks[9]
            roll = math.atan2((middle[0] - wrist[0]) * aspect_ratio, wrist[1] - middle[1])
            hands.append({"id": track.identity, "landmarks": landmarks,
                          "fingers": states, "pinches": pinches, "palm": track.palm[:], "roll": roll})
        return hands, self.update_pose(hands, timestamp_ms, aspect_ratio)

    def update_pose(self, hands, timestamp_ms, aspect_ratio=16 / 9):
        """Resolve exclusive modes. Also useful for deterministic state tests."""
        hands = sorted(hands, key=lambda hand: hand["id"])
        pinched = [(h, name) for h in hands for name, active in h["pinches"].items() if active]
        raw, chosen = "hover", hands
        if not hands or all(not any(h["fingers"].values()) and not any(h["pinches"].values()) for h in hands):
            raw, chosen = "idle", []
        elif len(hands) == 2 and all(h["pinches"]["index"] for h in hands):
            raw = "zoom"
        elif len(hands) == 2 and all(all(h["fingers"].values()) and not any(h["pinches"].values()) for h in hands):
            raw = "explode"
        elif len(pinched) == 1:
            chosen = [pinched[0][0]]
            raw = {"index": "grab", "middle": "rotate", "ring": "next_part", "pinky": "reset"}[pinched[0][1]]
        key = (raw, tuple(h["id"] for h in chosen))
        if key != self.candidate:
            self.candidate, self.candidate_since = key, timestamp_ms
        wait = {"next_part": 300, "reset": 700}.get(raw, self.pose_debounce_ms)
        if raw in ("idle", "hover") or timestamp_ms - self.candidate_since >= wait:
            self._set_mode(raw, key[1])
        elif (self.mode, self.participants) != key:
            # Stop the previous action immediately during acquisition of a new
            # pose; the browser must take a fresh baseline on a new event_id.
            self._set_mode("hover" if hands else "idle", tuple(h["id"] for h in hands))
        active = [h for h in hands if h["id"] in self.participants]
        cursor, span, roll = None, None, None
        if active:
            if self.mode in ("zoom", "explode") and len(active) == 2:
                if self.mode == "zoom":
                    anchors = [[(h["landmarks"][4][axis] + h["landmarks"][8][axis]) / 2 for axis in (0, 1)] for h in active]
                else:
                    anchors = [h["palm"] for h in active]
                cursor = [sum(p[axis] for p in anchors) / 2 for axis in (0, 1)]
                # Span in frame-height units: correct for camera aspect ratio.
                span = distance([anchors[0][0] * aspect_ratio, anchors[0][1]],
                                [anchors[1][0] * aspect_ratio, anchors[1][1]])
            else:
                hand = active[0]
                tip = {"grab": 8, "rotate": 12, "next_part": 16, "reset": 20}.get(self.mode, 8)
                cursor = hand["landmarks"][tip][:2]
                roll = hand["roll"]
            cursor = [max(0.0, min(1.0, float(v))) for v in cursor]
        return {"mode": self.mode, "event_id": self.event_id, "cursor": cursor,
                "distance": span, "roll": roll}

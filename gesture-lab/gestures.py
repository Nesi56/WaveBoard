"""Finger geometry, debounced pinches and hand identities, independent of camera libraries.

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


class HandEngine:
    """Detections -> hand records with stable ids, finger states and debounced pinches."""

    def __init__(self):
        self.identities = HandIdentities()
        self.last_timestamp = None

    def process(self, detections, timestamp_ms, aspect_ratio=16 / 9):
        """Return [{id, landmarks, fingers, pinches, palm}]. Timestamps are monotonic ms."""
        if self.last_timestamp is not None and timestamp_ms <= self.last_timestamp:
            raise ValueError("Hand timestamps must increase monotonically")
        if self.last_timestamp is not None and timestamp_ms - self.last_timestamp > 500:
            # A stalled camera or inference loop is also a loss of tracking, even
            # if the next result contains a hand in the same location.
            self.identities.assign([])
        self.last_timestamp = timestamp_ms
        hands = []
        for detection, track in zip(detections, self.identities.assign(detections)):
            landmarks = detection["landmarks"]
            if len(landmarks) != 21:
                raise ValueError("Each hand must contain 21 landmarks")
            points = detection.get("world_landmarks") or image_geometry(landmarks, aspect_ratio)
            hands.append({"id": track.identity, "landmarks": landmarks, "fingers": finger_states(points),
                          "pinches": track.pinch.update(pinch_ratios(landmarks, aspect_ratio), timestamp_ms),
                          "palm": track.palm[:]})
        return hands

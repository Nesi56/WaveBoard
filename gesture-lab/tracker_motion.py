"""Bounded camera-rate motion between expensive hand landmark observations.

Lucas-Kanade tracks textured points inside the palm, checks them in both
directions, then translates the whole hand by their robust median motion.
It deliberately does not infer finger articulation or pinch transitions.
New model observations correct accumulated error at their original camera
frame, replaying a short history to align them with the current image.
"""

from collections import deque


class HandMotionBridge:
    max_observation_age_ms = 450
    max_hold_ms = 220

    def __init__(self, cv2, np, max_hands=1):
        self.cv2, self.np = cv2, np
        self.max_hands = max_hands
        self.history = deque(maxlen=24)
        self.tracks = {}
        self.timestamp = None
        self.gray = None

    def advance(self, gray, timestamp):
        """Append one fresh camera frame and propagate existing hand motion."""
        if self.timestamp is not None and timestamp <= self.timestamp:
            raise ValueError("Motion timestamps must increase")
        if self.gray is not None and self.gray.shape != gray.shape:
            self.history.clear()
            self.tracks.clear()
        for track in self.tracks.values():
            track["fresh"] = False
            if self.gray is not None:
                self._step(track, self.gray, gray, timestamp)
        self.timestamp, self.gray = timestamp, gray
        self.history.append((timestamp, gray))
        while self.history and timestamp - self.history[0][0] > self.max_observation_age_ms:
            self.history.popleft()
        self.tracks = {identity: track for identity, track in self.tracks.items()
                       if timestamp - track["observed_at"] < self.max_observation_age_ms}

    def observe(self, hands, gray, timestamp):
        """Accept only real HandEngine observations, never its held records.

        Gray is the exact image used for inference, which is usually several
        capture frames behind the current frame. Replay keeps movement small
        for optical flow even when MediaPipe takes 140 ms on the device.
        """
        if self.timestamp is None or timestamp > self.timestamp \
                or self.timestamp - timestamp >= self.max_observation_age_ms:
            return
        if gray.shape != self.gray.shape:
            return
        for hand in hands:
            if not hand.get("observed", True):
                continue
            track = {"hand": dict(hand), "points": self._features(gray, hand),
                     "observed_at": timestamp, "motion_at": timestamp,
                     "fresh": True, "valid": True}
            previous = gray
            for frame_time, frame in self.history:
                if frame_time > timestamp:
                    self._step(track, previous, frame, frame_time)
                    previous = frame
            self.tracks[hand["id"]] = track
        # A new identity replaces an old, unobserved one. Otherwise repeated
        # reacquisition could grow the skeleton packet beyond the hand limit.
        self.tracks = dict(sorted(self.tracks.items(), key=lambda pair: pair[1]["observed_at"],
                                  reverse=True)[:self.max_hands])

    def hands(self):
        """Current motion, or a brief explicit hold if optical flow failed."""
        result = []
        for track in self.tracks.values():
            age = self.timestamp - track["observed_at"]
            if age >= self.max_observation_age_ms:
                continue
            if not track["fresh"] and not track["valid"] \
                    and self.timestamp - track["motion_at"] >= self.max_hold_ms:
                continue
            observed = track["fresh"]
            flowing = not observed and track["valid"]
            result.append({**track["hand"], "observed": observed,
                           "predicted": not observed and not flowing,
                           "tracking_source": "detected" if observed else "flow" if flowing else "held",
                           "tracking_age_ms": age, "observation_timestamp": track["observed_at"]})
        return result

    def _features(self, gray, hand):
        cv2, np = self.cv2, self.np
        height, width = gray.shape[:2]
        palm = np.array([[hand["landmarks"][i][0] * width, hand["landmarks"][i][1] * height]
                         for i in (0, 1, 5, 9, 13, 17)], dtype=np.float32)
        if not np.isfinite(palm).all():
            return None
        # Restrict the support to the palm so background features between the
        # fingers cannot pull the cursor away from the teacher's hand.
        mask = np.zeros(gray.shape[:2], dtype=np.uint8)
        hull = cv2.convexHull(np.rint(palm).astype(np.int32))
        cv2.fillConvexPoly(mask, hull, 255)
        points = cv2.goodFeaturesToTrack(gray, maxCorners=32, qualityLevel=0.01,
                                       minDistance=3, mask=mask, blockSize=3)
        return points if points is not None and len(points) >= 5 else None

    def _step(self, track, previous, current, timestamp):
        if not track["valid"]:
            return
        points = track["points"]
        if points is None:
            track["valid"] = False
            return
        cv2, np = self.cv2, self.np
        options = dict(winSize=(21, 21), maxLevel=3,
                       criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 15, 0.03))
        next_points, found, error = cv2.calcOpticalFlowPyrLK(previous, current, points, None, **options)
        if next_points is None or found is None or error is None:
            track["valid"] = False
            return
        back, reverse_found, _ = cv2.calcOpticalFlowPyrLK(current, previous, next_points, None, **options)
        if back is None or reverse_found is None:
            track["valid"] = False
            return
        old = points.reshape(-1, 2)
        new = next_points.reshape(-1, 2)
        height, width = current.shape[:2]
        valid = ((found.reshape(-1) != 0) & (reverse_found.reshape(-1) != 0)
                 & np.isfinite(new).all(axis=1) & np.isfinite(back.reshape(-1, 2)).all(axis=1)
                 & (np.linalg.norm(back.reshape(-1, 2) - old, axis=1) <= 1.5)
                 & (error.reshape(-1) <= 35)
                 & (new[:, 0] >= 0) & (new[:, 0] < width)
                 & (new[:, 1] >= 0) & (new[:, 1] < height))
        if int(valid.sum()) < max(5, int(len(points) * 0.5)):
            track["valid"] = False
            return
        motion = new - old
        shift = np.median(motion[valid], axis=0)
        # Reject points whose motion disagrees with the palm; never propagate
        # NaNs, wild jumps, or a disappearing hand on a matching background.
        valid &= np.linalg.norm(motion - shift, axis=1) <= max(2.0, float(np.linalg.norm(shift)) * 0.3)
        if int(valid.sum()) < 5 or float(np.linalg.norm(shift)) > min(width, height) * 0.35:
            track["valid"] = False
            return
        shift = np.median(motion[valid], axis=0)
        dx, dy = float(shift[0] / width), float(shift[1] / height)
        hand = track["hand"]
        hand["landmarks"] = [[p[0] + dx, p[1] + dy, p[2]] for p in hand["landmarks"]]
        hand["palm"] = [hand["palm"][0] + dx, hand["palm"][1] + dy]
        track["points"] = new[valid].reshape(-1, 1, 2)
        track["motion_at"] = timestamp

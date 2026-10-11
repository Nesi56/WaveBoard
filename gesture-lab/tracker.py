"""MediaPipe camera worker for WaveBoard hand control.

Capture and CPU MediaPipe inference each keep only the newest pending frame.
Sparse, checked optical flow updates hand motion between model observations;
only a new model observation can change a gesture. Camera images stay local.
"""

import argparse
import math
from collections import deque
from pathlib import Path
import sys
import threading
import time

from gestures import HandEngine
from hand_pointer import HandPointer
from tracker_motion import HandMotionBridge


def positive_int(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def confidence(value):
    number = float(value)
    if not 0.05 <= number <= 0.95:
        raise argparse.ArgumentTypeError("must be between 0.05 and 0.95")
    return number


def register_arguments(parser):
    parser.add_argument("--camera", default="0", help="camera index, or a V4L2 path such as /dev/video2 on Linux")
    parser.add_argument("--width", type=positive_int, default=1280, help="requested camera width")
    parser.add_argument("--height", type=positive_int, default=720, help="requested camera height")
    parser.add_argument("--fps", type=positive_int, default=30, help="requested capture FPS; device may negotiate less")
    parser.add_argument("--fourcc", choices=("MJPG", "YUYV"), default="MJPG", help="requested camera pixel format")
    parser.add_argument("--processing-width", type=positive_int, default=640,
                        help="shrink frames to this width before inference; preserves aspect ratio "
                             "(default: 640; use 960 or 1280 for distant hands)")
    parser.add_argument("--detection-confidence", type=confidence, default=0.5,
                        help="hand detection threshold; lower (e.g. 0.35) finds hands farther from the camera, "
                             "but may mistake other objects for hands (default 0.5)")
    parser.add_argument("--presence-confidence", type=confidence, default=0.4,
                        help="landmark presence threshold before palm re-detection (default 0.4)")
    parser.add_argument("--tracking-confidence", type=confidence, default=0.3,
                        help="hand box overlap threshold; lower tolerates faster motion (default 0.3)")
    parser.add_argument("--max-hands", type=int, choices=(1, 2), default=1,
                        help="one teacher hand avoids searching for a second hand every frame (default 1)")
    parser.add_argument("--reach", type=float, default=0.12,
                        help="fraction of each camera edge ignored so hands reach the screen edges (default 0.12)")
    parser.add_argument("--model", type=Path, default=Path(__file__).with_name("hand_landmarker.task"))
    parser.add_argument("--max-frame-age-ms", type=positive_int, default=250, help="discard frames older than this before inference")


class RateMeter:
    def __init__(self):
        self.samples = deque()

    def tick(self, timestamp):
        self.samples.append(timestamp)
        while len(self.samples) > 2 and self.samples[0] < timestamp - 2.0:
            self.samples.popleft()
        if len(self.samples) < 2 or self.samples[-1] <= self.samples[0]:
            return 0.0
        return (len(self.samples) - 1) / (self.samples[-1] - self.samples[0])


class LatestFrameCapture:
    def __init__(self, camera, stop_event):
        self.camera = camera
        self.stop_event = stop_event
        self.done = threading.Event()
        self.condition = threading.Condition()
        self.latest = None
        self.failure = None
        self.sequence = 0
        self.thread = threading.Thread(target=self._capture, name="camera-capture", daemon=True)

    def start(self):
        self.thread.start()

    def _capture(self):
        meter = RateMeter()
        failures = 0
        try:
            while not self.stop_event.is_set() and not self.done.is_set():
                ok, frame = self.camera.read()
                timestamp = time.monotonic()
                if not ok:
                    failures += 1
                    if failures >= 5:
                        raise RuntimeError("Camera stopped supplying frames. Check the USB cable and close other camera apps.")
                    self.done.wait(0.05)
                    continue
                failures = 0
                rate = meter.tick(timestamp)
                with self.condition:
                    self.sequence += 1
                    self.latest = (self.sequence, timestamp, frame, rate)
                    self.condition.notify_all()
        except Exception as exc:
            with self.condition:
                self.failure = str(exc)
                self.condition.notify_all()
        finally:
            # OpenCV capture objects are not generally thread-safe: the thread
            # that reads also releases, including on USB disconnect/read error.
            self.camera.release()

    def next_after(self, sequence, timeout=0.25):
        with self.condition:
            self.condition.wait_for(lambda: self.failure or (self.latest and self.latest[0] > sequence)
                                    or self.stop_event.is_set(), timeout=timeout)
            if self.failure:
                raise RuntimeError(self.failure)
            if self.latest and self.latest[0] > sequence:
                return self.latest
            return None

    def newest(self):
        """The latest sample without waiting, or None before the first frame arrives."""
        with self.condition:
            if self.failure:
                raise RuntimeError(self.failure)
            return self.latest

    def close(self):
        self.done.set()
        self.thread.join(timeout=2.0)
        # If a driver blocks read() indefinitely, leave this daemon thread to
        # process shutdown rather than calling release() concurrently with read.


def open_camera(cv2, args):
    """Open and configure the camera (V4L2 on Linux). Returns (camera, camera_info)."""
    source = int(str(args.camera)) if str(args.camera).isdigit() else str(args.camera)
    # Windows and macOS pick their own camera backend, so the tracker can be tried on a laptop.
    camera = cv2.VideoCapture(source, cv2.CAP_V4L2 if sys.platform.startswith("linux") else cv2.CAP_ANY)
    if not camera.isOpened():
        camera.release()
        raise RuntimeError(f"Cannot open camera {source}. Check --camera, USB connection, and camera permissions.")
    camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*args.fourcc))
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    camera.set(cv2.CAP_PROP_FPS, args.fps)
    camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    negotiated = camera.get(cv2.CAP_PROP_FPS)
    camera_info = {
        "width": int(camera.get(cv2.CAP_PROP_FRAME_WIDTH)),
        "height": int(camera.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        "requested_fps": args.fps,
        "negotiated_fps": round(negotiated, 1) if math.isfinite(negotiated) else 0.0,
    }
    return camera, camera_info


def landmarker_options(python, vision, args):
    model = Path(args.model).expanduser().resolve()
    if not model.is_file():
        raise FileNotFoundError(f"Hand model not found: {model}. Run gesture-lab/setup.sh "
                                "(or python gesture-lab/download_model.py).")
    return vision.HandLandmarkerOptions(
        base_options=python.BaseOptions(model_asset_path=str(model)),
        running_mode=vision.RunningMode.VIDEO,
        num_hands=getattr(args, "max_hands", 1),
        min_hand_detection_confidence=getattr(args, "detection_confidence", 0.5),
        min_hand_presence_confidence=getattr(args, "presence_confidence", 0.4),
        min_tracking_confidence=getattr(args, "tracking_confidence", 0.3),
    )


def detect_hands(cv2, mp, np, landmarker, frame, timestamp, processing_width):
    """Detect hands in an already mirrored BGR frame.

    Returns (detections, inference_frame). Landmarks are normalized to the
    whole frame, so they stay valid for the full-resolution image as well.
    """
    height, width = frame.shape[:2]
    inference_width = min(width, processing_width) if processing_width else width
    if width != inference_width:
        frame = cv2.resize(frame, (inference_width, max(1, round(height * inference_width / width))),
                           interpolation=cv2.INTER_AREA)
    image = mp.Image(image_format=mp.ImageFormat.SRGB,
                     data=np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
    result = landmarker.detect_for_video(image, timestamp)
    detections = []
    for i, landmarks in enumerate(result.hand_landmarks):
        world = result.hand_world_landmarks[i]
        label = result.handedness[i][0].category_name if result.handedness[i] else "unknown"
        detections.append({
            "handedness": label,
            "landmarks": [[float(p.x), float(p.y), float(p.z)] for p in landmarks],
            "world_landmarks": [[float(p.x), float(p.y), float(p.z)] for p in world],
        })
    return detections, frame


class LatestInference:
    """One running inference and one replaceable pending frame, never a queue.

    The worker owns the landmarker context from creation to close. Native
    inference cannot block capture, optical flow, pointer output, or shutdown.
    """

    def __init__(self, factory, infer, stop_event, max_frame_age_ms=250):
        self.factory, self.infer = factory, infer
        self.stop_event = stop_event
        self.max_frame_age_ms = max_frame_age_ms
        self.done = threading.Event()
        self.ready = threading.Event()
        self.condition = threading.Condition()
        self.pending = self.latest = None
        self.failure = None
        self.dropped = 0
        self.thread = threading.Thread(target=self._run, name="hand-inference", daemon=True)

    def start(self):
        self.thread.start()

    def submit(self, sample):
        with self.condition:
            if self.pending is not None:
                self.dropped += 1
            self.pending = sample
            self.condition.notify_all()

    def newest_after(self, sequence):
        with self.condition:
            if self.failure:
                raise RuntimeError(self.failure)
            if self.latest is not None and self.latest["sequence"] > sequence:
                return self.latest
            return None

    def _run(self):
        meter = RateMeter()
        try:
            with self.factory() as landmarker:
                self.ready.set()
                while not self.stop_event.is_set() and not self.done.is_set():
                    with self.condition:
                        self.condition.wait_for(lambda: self.pending is not None or self.done.is_set()
                                                or self.stop_event.is_set(), timeout=0.1)
                        if self.done.is_set() or self.stop_event.is_set():
                            break
                        sample, self.pending = self.pending, None
                    if sample is None:
                        continue
                    sequence, timestamp, frame, gray = sample
                    started = time.monotonic()
                    if started * 1000 - timestamp > self.max_frame_age_ms:
                        continue
                    detections = self.infer(landmarker, frame, timestamp)
                    ended = time.monotonic()
                    result = {"sequence": sequence, "timestamp": timestamp, "gray": gray,
                              "detections": detections, "inference_ms": (ended - started) * 1000,
                              "inference_fps": meter.tick(ended)}
                    with self.condition:
                        self.latest = result
        except Exception as exc:
            with self.condition:
                self.failure = f"{type(exc).__name__}: {exc}"

    def close(self):
        self.done.set()
        with self.condition:
            self.pending = None
            self.condition.notify_all()
        self.thread.join(timeout=2.0)


def prepare_frame(cv2, frame, processing_width):
    """Downsize before flipping/conversion so capture resolution costs less."""
    height, width = frame.shape[:2]
    if processing_width and width > processing_width:
        frame = cv2.resize(frame, (processing_width, max(1, round(height * processing_width / width))),
                           interpolation=cv2.INTER_AREA)
    return cv2.flip(frame, 1)


def run(stop_event, publish, args):
    """Run in a worker thread. publish(packet) must be safe from this thread.

    Emits status dictionaries and frame dictionaries; all values are JSON-safe.
    Exceptions are reported as error statuses and camera resources are released.
    """
    capture = None
    inference = None
    camera = None
    try:
        import cv2
        import mediapipe as mp
        import numpy as np
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision

        # A second OpenCV thread pool competes with MediaPipe on small Jetsons;
        # these 640px preprocessing/LK operations are cheaper on one CPU thread.
        cv2.setNumThreads(1)
        options = landmarker_options(python, vision, args)
        camera, camera_info = open_camera(cv2, args)
        publish({"type": "status", "level": "info", "message":
                 f"Camera reports {camera_info['width']}×{camera_info['height']} at "
                 f"{camera_info['negotiated_fps']:g} FPS (requested {args.fps}). Loading CPU hand tracker."})
        engine, meter = HandEngine(), RateMeter()
        max_hands = getattr(args, "max_hands", 1)
        pointer = HandPointer(reach=min(max(args.reach, 0.0), 0.3), max_hands=max_hands)
        sequence, frame_sequence, inference_sequence, last_timestamp = 0, 0, 0, -1
        processing_width = getattr(args, "processing_width", 640)
        motion = HandMotionBridge(cv2, np, max_hands=max_hands)
        inference = LatestInference(
            lambda: vision.HandLandmarker.create_from_options(options),
            lambda model, frame, stamp: detect_hands(cv2, mp, np, model, frame, stamp, None)[0],
            stop_event, args.max_frame_age_ms)
        inference.start()
        capture = LatestFrameCapture(camera, stop_event)
        capture.start()
        last_frame_received = time.monotonic()
        announced = False
        inference_ms = inference_rate = 0.0
        while not stop_event.is_set():
            sample = capture.next_after(frame_sequence, timeout=0.1)
            # Surface model-load/inference failures even if the camera stalls.
            result = inference.newest_after(inference_sequence)
            if not announced and inference.ready.is_set():
                announced = True
                count = getattr(args, "max_hands", 1)
                publish({"type": "status", "level": "info", "message":
                         f"Hand tracker ready ({count} hand{'s' if count > 1 else ''}). "
                         "Show your hand; point and pinch to select."})
            if sample is None:
                if time.monotonic() - last_frame_received > 5:
                    raise RuntimeError("No camera frames for five seconds. Check USB and the selected capture mode.")
                continue
            frame_sequence, capture_time, frame, capture_rate = sample
            last_frame_received = time.monotonic()
            if (time.monotonic() - capture_time) * 1000 > args.max_frame_age_ms:
                continue
            timestamp = int(capture_time * 1000)
            if timestamp <= last_timestamp:
                continue
            last_timestamp = timestamp
            height, width = frame.shape[:2]
            camera_info.update(width=width, height=height)
            frame = prepare_frame(cv2, frame, processing_width)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            motion.advance(gray, timestamp)
            inference.submit((frame_sequence, timestamp, frame, gray))
            if result is not None:
                inference_sequence = result["sequence"]
                inference_ms, inference_rate = result["inference_ms"], result["inference_fps"]
                if 0 <= timestamp - result["timestamp"] < motion.max_observation_age_ms:
                    observed = engine.process(result["detections"], result["timestamp"], width / height)
                    motion.observe(observed, result["gray"], result["timestamp"])
            hands = motion.hands()
            now = time.monotonic()
            tracking_rate = meter.tick(now)
            sequence += 1
            publish({"type": "frame", "seq": sequence, "timestamp": timestamp,
                     "tracking_fps": round(tracking_rate, 1), "capture_fps": round(capture_rate, 1),
                     "inference_fps": round(inference_rate, 1), "inference_ms": round(inference_ms, 1),
                     "frame_age_ms": round((now - capture_time) * 1000, 1),
                     "processing": {"width": frame.shape[1], "height": frame.shape[0]},
                     "propagated_hands": sum(h["tracking_source"] == "flow" for h in hands),
                     "skipped_inference_frames": inference.dropped,
                     "camera": camera_info.copy(), "pointer": pointer.update(hands, timestamp, width / height)})
    except Exception as exc:
        publish({"type": "status", "level": "error", "message": f"{type(exc).__name__}: {exc}"})
    finally:
        if inference is not None:
            inference.close()
        if capture is not None:
            capture.close()
        elif camera is not None:
            camera.release()


if __name__ == "__main__":
    import json
    import signal
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    next_report = [time.monotonic() + 10]
    def publish(packet):
        print(json.dumps(packet, allow_nan=False), flush=True)
        if packet.get("type") == "status":
            print(packet.get("message", ""), file=sys.stderr, flush=True)
        elif time.monotonic() >= next_report[0]:
            next_report[0] = time.monotonic() + 10
            print(f"Hands {packet['tracking_fps']:.1f} FPS, inference {packet['inference_fps']:.1f} FPS "
                  f"({packet['inference_ms']:.0f} ms), camera {packet['capture_fps']:.1f} FPS, "
                  f"processing {packet['processing']['width']}×{packet['processing']['height']}, "
                  f"flow {packet['propagated_hands']} hand(s)", file=sys.stderr, flush=True)
    parser = argparse.ArgumentParser(description="WaveBoard hand tracker (JSON lines on stdout)")
    register_arguments(parser)
    try:
        run(stop, publish, parser.parse_args())
    except KeyboardInterrupt:
        pass

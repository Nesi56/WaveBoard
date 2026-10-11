"""MediaPipe camera worker for WaveBoard hand control.

The camera capture thread overwrites its single latest frame so slow inference
does not accumulate a delayed queue. MediaPipe runs on CPU in VIDEO mode. The
camera image never leaves this process: each frame publishes only the hand
pointer and skeleton points that web/hands.js draws.
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
    # MediaPipe crops each hand from this image, so full resolution keeps distant
    # hands sharp; it measured about as fast as 640 px.
    parser.add_argument("--processing-width", type=positive_int, default=None,
                        help="shrink frames to this width before inference; preserves aspect ratio "
                             "(default: the full camera frame)")
    parser.add_argument("--detection-confidence", type=confidence, default=0.5,
                        help="hand detection threshold; lower (e.g. 0.35) finds hands farther from the camera, "
                             "but may mistake other objects for hands (default 0.5)")
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
        num_hands=2,
        min_hand_detection_confidence=getattr(args, "detection_confidence", 0.5),
        min_hand_presence_confidence=getattr(args, "detection_confidence", 0.5),
        min_tracking_confidence=0.5,
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


def run(stop_event, publish, args):
    """Run in a worker thread. publish(packet) must be safe from this thread.

    Emits status dictionaries and frame dictionaries; all values are JSON-safe.
    Exceptions are reported as error statuses and camera resources are released.
    """
    capture = None
    camera = None
    try:
        import cv2
        import mediapipe as mp
        import numpy as np
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision

        options = landmarker_options(python, vision, args)
        camera, camera_info = open_camera(cv2, args)
        publish({"type": "status", "level": "info", "message":
                 f"Camera reports {camera_info['width']}×{camera_info['height']} at "
                 f"{camera_info['negotiated_fps']:g} FPS (requested {args.fps}). Loading CPU hand tracker."})
        engine, meter = HandEngine(), RateMeter()
        pointer = HandPointer(reach=min(max(args.reach, 0.0), 0.3))
        sequence, frame_sequence, last_timestamp = 0, 0, -1
        capture = LatestFrameCapture(camera, stop_event)
        capture.start()
        with vision.HandLandmarker.create_from_options(options) as landmarker:
            publish({"type": "status", "level": "info", "message": "Hand tracker ready. Show one or two hands to the camera."})
            last_frame_received = time.monotonic()
            while not stop_event.is_set():
                sample = capture.next_after(frame_sequence)
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
                frame = cv2.flip(frame, 1)
                height, width = frame.shape[:2]
                camera_info.update(width=width, height=height)
                detections, _ = detect_hands(cv2, mp, np, landmarker, frame, timestamp, args.processing_width)
                hands = engine.process(detections, timestamp, width / height)
                tracking_rate = meter.tick(time.monotonic())
                sequence += 1
                publish({"type": "frame", "seq": sequence, "timestamp": timestamp,
                         "tracking_fps": round(tracking_rate, 1), "capture_fps": round(capture_rate, 1),
                         "camera": camera_info.copy(), "pointer": pointer.update(hands, timestamp, width / height)})
    except Exception as exc:
        publish({"type": "status", "level": "error", "message": f"{type(exc).__name__}: {exc}"})
    finally:
        if capture is not None:
            capture.close()
        elif camera is not None:
            camera.release()


if __name__ == "__main__":
    import json
    parser = argparse.ArgumentParser(description="WaveBoard hand tracker (JSON lines on stdout)")
    register_arguments(parser)
    try:
        run(threading.Event(), lambda packet: print(json.dumps(packet), flush=True), parser.parse_args())
    except KeyboardInterrupt:
        pass

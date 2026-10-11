"""MediaPipe camera worker for the local Gesture Lab server.

The camera capture thread overwrites its single latest frame so slow inference
does not accumulate a delayed queue. MediaPipe runs on CPU in VIDEO mode.
"""

import argparse
import math
from collections import deque
from pathlib import Path
import threading
import time

from gestures import GestureEngine
from hand_pointer import HandPointer


def positive_int(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def register_arguments(parser):
    register_camera_arguments(parser)
    parser.add_argument("--max-frame-age-ms", type=positive_int, default=250, help="discard frames older than this before inference")
    parser.add_argument("--preview", action="store_true", help="optional OpenCV camera window (requires a desktop)")
    parser.add_argument("--reach", type=float, default=0.12,
                        help="WaveBoard pointer: fraction of each camera edge ignored so hands reach the screen edges")


def register_camera_arguments(parser):
    parser.add_argument("--camera", default="0", help="V4L2 index or path, e.g. /dev/video0")
    parser.add_argument("--width", type=positive_int, default=1280, help="requested camera width")
    parser.add_argument("--height", type=positive_int, default=720, help="requested camera height")
    parser.add_argument("--fps", type=positive_int, default=30, help="requested capture FPS; device may negotiate less")
    parser.add_argument("--processing-width", type=positive_int, default=640, help="inference width; preserves aspect ratio")
    parser.add_argument("--model", type=Path, default=Path(__file__).with_name("hand_landmarker.task"))
    parser.add_argument("--fourcc", choices=("MJPG", "YUYV"), default="MJPG", help="requested camera pixel format")


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
    """Open and configure the V4L2 camera. Returns (camera, camera_info)."""
    source = int(str(args.camera)) if str(args.camera).isdigit() else str(args.camera)
    camera = cv2.VideoCapture(source, cv2.CAP_V4L2)
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
        raise FileNotFoundError(f"Hand model not found: {model}. Run the model-download step in README.md.")
    return vision.HandLandmarkerOptions(
        base_options=python.BaseOptions(model_asset_path=str(model)),
        running_mode=vision.RunningMode.VIDEO,
        num_hands=2,
        min_hand_detection_confidence=0.6,
        min_hand_presence_confidence=0.6,
        min_tracking_confidence=0.6,
    )


def detect_hands(cv2, mp, np, landmarker, frame, timestamp, processing_width):
    """Detect hands in an already mirrored BGR frame.

    Returns (detections, inference_frame). Landmarks are normalized to the
    whole frame, so they stay valid for the full-resolution image as well.
    """
    height, width = frame.shape[:2]
    inference_width = min(width, processing_width)
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


def _preview(cv2, frame, hands, gesture):
    height, width = frame.shape[:2]
    for hand in hands:
        points = [(int(p[0] * width), int(p[1] * height)) for p in hand["landmarks"]]
        for chain in ((0, 1, 2, 3, 4), (0, 5, 6, 7, 8), (5, 9, 10, 11, 12),
                      (9, 13, 14, 15, 16), (13, 17, 18, 19, 20), (0, 17)):
            for start, end in zip(chain, chain[1:]):
                cv2.line(frame, points[start], points[end], (180, 210, 150), 2)
        for point in points:
            cv2.circle(frame, point, 3, (0, 240, 255), -1)
    cv2.putText(frame, f"{gesture['mode']} | Q: quit", (12, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    cv2.imshow("Gesture Lab - mirrored camera", frame)


def run(stop_event, publish, args):
    """Run in a worker thread. publish(packet) must be safe from this thread.

    Emits status dictionaries and frame dictionaries; all values are JSON-safe.
    Exceptions are reported as error statuses and camera resources are released.
    """
    capture = None
    camera = None
    cv2 = None
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
        engine, meter = GestureEngine(), RateMeter()
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
                detections, frame = detect_hands(cv2, mp, np, landmarker, frame, timestamp, args.processing_width)
                hands, gesture = engine.process(detections, timestamp, width / height)
                tracking_rate = meter.tick(time.monotonic())
                sequence += 1
                publish({"type": "frame", "seq": sequence, "timestamp": timestamp,
                         "tracking_fps": round(tracking_rate, 1), "capture_fps": round(capture_rate, 1),
                         "camera": camera_info.copy(), "hands": hands, "gesture": gesture,
                         "pointer": pointer.update(hands, timestamp, width / height)})
                if args.preview:
                    _preview(cv2, frame, hands, gesture)
                    if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                        stop_event.set()
    except Exception as exc:
        publish({"type": "status", "level": "error", "message": f"{type(exc).__name__}: {exc}"})
    finally:
        if capture is not None:
            capture.close()
        elif camera is not None:
            camera.release()
        if cv2 is not None and args.preview:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    import json
    parser = argparse.ArgumentParser(description="Gesture Lab camera tracker (JSON output)")
    register_arguments(parser)
    try:
        run(threading.Event(), lambda packet: print(json.dumps(packet), flush=True), parser.parse_args())
    except KeyboardInterrupt:
        pass

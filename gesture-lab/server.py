"""Local-only HTTP viewer and latest-state WebSocket bridge for Gesture Lab."""
import argparse
import asyncio
import functools
import json
import signal
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from websockets.asyncio.server import serve

ROOT = Path(__file__).resolve().parent
VIEWER_PORT = 8000
# The WaveBoard workspace (python -m waveboard) serves on 8765, so the bridge uses 8766.
BRIDGE_PORT = 8766
ALLOWED_ORIGINS = [f"http://{host}:{port}" for port in (VIEWER_PORT, 8765) for host in ("127.0.0.1", "localhost")]


class LatestState:
    def __init__(self):
        self.lock = threading.Lock()
        self.version = 0
        self.frame = None
        self.frame_time = 0.0
        self.status = {"type": "status", "level": "info", "message": "Starting hand tracking…"}

    def publish(self, packet):
        # Reject non-finite numbers before they reach browser JSON.parse.
        json.dumps(packet, allow_nan=False)
        with self.lock:
            self.version += 1
            if packet.get("type") == "frame":
                self.frame = packet
                self.frame_time = time.monotonic()
            else:
                self.status = packet
                if packet.get("level") == "error":
                    self.frame = None

    def snapshot(self):
        with self.lock:
            frame = self.frame if time.monotonic() - self.frame_time < 0.5 else None
            return self.version, self.status, frame


class ViewerHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def list_directory(self, path):
        self.send_error(404)
        return None

    def log_message(self, fmt, *args):
        if args and str(args[1] if len(args) > 1 else "") not in ("200", "304"):
            super().log_message(fmt, *args)


async def bridge(state, stop, origins=ALLOWED_ORIGINS):
    async def stream(connection):
        last_version = -1
        last_status = None
        while not stop.is_set():
            version, status, frame = state.snapshot()
            if status != last_status:
                await asyncio.wait_for(connection.send(json.dumps(status)), timeout=1)
                last_status = status
            if version != last_version and frame is not None:
                await asyncio.wait_for(connection.send(json.dumps(frame)), timeout=1)
            last_version = version
            await asyncio.sleep(1 / 60)

    async def handler(connection):
        try:
            await stream(connection)
        except (TimeoutError, ConnectionError):
            pass
        except Exception as exc:
            from websockets.exceptions import ConnectionClosed
            if not isinstance(exc, ConnectionClosed):
                print("Viewer connection ended:", exc)

    # No LAN exposure. Only the locally served UIs can read camera landmarks.
    async with serve(handler, "127.0.0.1", BRIDGE_PORT, origins=origins,
                     max_size=1024, max_queue=1, compression=None):
        while not stop.is_set():
            await asyncio.sleep(0.1)


def main():
    import tracker
    parser = argparse.ArgumentParser(description=__doc__)
    tracker.register_arguments(parser)
    parser.add_argument("--no-camera", action="store_true", help="Test viewer with mouse controls only")
    parser.add_argument("--allow-origin", action="append", default=[], metavar="URL",
                        help="also stream hands to this page origin, e.g. http://127.0.0.1:8770 for "
                             "a WaveBoard workspace on another port; may be repeated")
    args = parser.parse_args()
    state = LatestState()
    stop = threading.Event()
    handler = functools.partial(ViewerHandler, directory=str(ROOT / "web"))
    http = ThreadingHTTPServer(("127.0.0.1", VIEWER_PORT), handler)
    threading.Thread(target=http.serve_forever, daemon=True).start()

    def tracking_worker():
        try:
            tracker.run(stop, state.publish, args)
        except Exception as exc:
            message = f"Hand tracker stopped: {exc}"
            print(message, flush=True)
            state.publish({"type": "status", "level": "error", "message": message})

    if args.no_camera:
        state.publish({"type": "status", "level": "info", "code": "demo",
                       "message": "Mouse demo — camera tracking is off. Restart without --no-camera to use hands."})
    else:
        threading.Thread(target=tracking_worker, daemon=True).start()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    print(f"3D viewer: open http://127.0.0.1:{VIEWER_PORT} in the browser on this Jetson.", flush=True)
    print("Hand control for the WaveBoard workspace (python -m waveboard) is on as well.", flush=True)
    print("Press Ctrl+C here to stop.", flush=True)
    try:
        asyncio.run(bridge(state, stop, ALLOWED_ORIGINS + [o.rstrip("/") for o in args.allow_origin]))
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        http.shutdown()
        http.server_close()


if __name__ == "__main__":
    main()

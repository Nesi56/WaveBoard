"""Hand-tracking stream for the WaveBoard workspace: camera -> MediaPipe -> local WebSocket.

Start it next to ``python -m waveboard`` (or let ``scripts/start-ubuntu.sh --hands``
start both). web/hands.js connects to ws://127.0.0.1:8766, draws the hand skeletons
and turns the pointer into touch input.
"""
import argparse
import asyncio
import json
import signal
import threading
import time

from websockets.asyncio.server import serve

# The WaveBoard workspace (python -m waveboard) serves on 8765, so the stream uses 8766.
BRIDGE_PORT = 8766
ALLOWED_ORIGINS = [f"http://{host}:8765" for host in ("127.0.0.1", "localhost")]


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
                print("Workspace connection ended:", exc)

    # No LAN exposure. Only the local workspace page can read hand positions.
    async with serve(handler, "127.0.0.1", BRIDGE_PORT, origins=origins,
                     max_size=1024, max_queue=1, compression=None):
        while not stop.is_set():
            await asyncio.sleep(0.1)


def main():
    import tracker
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    tracker.register_arguments(parser)
    parser.add_argument("--allow-origin", action="append", default=[], metavar="URL",
                        help="also stream hands to this page origin, e.g. http://127.0.0.1:8770 for "
                             "a WaveBoard workspace on another port; may be repeated")
    args = parser.parse_args()
    state = LatestState()
    stop = threading.Event()
    next_report = [time.monotonic() + 10]

    def publish(packet):
        # A line every 10 s in the log (hands.log under the launcher) for checking speed on the Jetson.
        now = time.monotonic()
        if packet.get("type") == "frame" and now >= next_report[0]:
            next_report[0] = now + 10
            print(f"Tracking {packet['tracking_fps']:.1f} FPS, camera {packet['capture_fps']:.1f} FPS, "
                  f"{len(packet['pointer']['hands'])} hand(s) in view", flush=True)
        elif packet.get("type") == "status":
            print(packet.get("message", ""), flush=True)
        state.publish(packet)

    def tracking_worker():
        try:
            tracker.run(stop, publish, args)
        except Exception as exc:
            message = f"Hand tracker stopped: {exc}"
            print(message, flush=True)
            state.publish({"type": "status", "level": "error", "message": message})

    threading.Thread(target=tracking_worker, daemon=True).start()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    print(f"Hand tracking for the WaveBoard workspace on ws://127.0.0.1:{BRIDGE_PORT}.", flush=True)
    print("Open the workspace (python3 -m waveboard, http://127.0.0.1:8765). Press Ctrl+C here to stop.", flush=True)
    try:
        asyncio.run(bridge(state, stop, ALLOWED_ORIGINS + [o.rstrip("/") for o in args.allow_origin]))
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()


if __name__ == "__main__":
    main()

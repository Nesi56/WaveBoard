"""Bounded JSON-line decoder that coalesces motion, never gesture transitions."""
import json


def reject_constant(_):
    raise ValueError("Hand packets must contain finite numbers")


class HandPacketStream:
    max_line = 65536

    def __init__(self):
        self.pending = bytearray()
        self.discard_line = False
        self.previous_gesture_key = None

    @staticmethod
    def gesture_key(packet):
        pointer = packet.get("pointer")
        if packet.get("type") != "frame" or not isinstance(pointer, dict):
            return None
        return tuple(pointer.get(key) for key in (
            "visible", "down", "hand", "cancelled", "swipe_id", "observed", "motion_tracked", "pose"
        ))

    def feed(self, chunk):
        """Return packets in order, preserving first and last gesture positions.

        QProcess may deliver a pinch and its release in the same read. Keeping
        only the final line loses the click; emitting every old position builds
        avoidable UI work. A transition's first position is its press/release
        location and must survive alongside the run's latest motion. Every
        pressed position survives: skipping an excursion can invent a click or
        erase a stroke. Status, identity and observation changes end a run.
        """
        packets = []
        protected = []
        for fragment in bytes(chunk).splitlines(keepends=True):
            complete = fragment.endswith(b"\n")
            if not self.discard_line:
                self.pending.extend(fragment)
                if len(self.pending) > self.max_line:
                    self.pending.clear()
                    self.discard_line = True
            if not complete:
                continue
            if not self.discard_line:
                try:
                    packet = json.loads(self.pending, parse_constant=reject_constant)
                    if isinstance(packet, dict) and packet.get("type") in {"frame", "status"}:
                        key = self.gesture_key(packet)
                        transition = key is None or key != self.previous_gesture_key
                        if packets and not transition and not key[1] and packet["pointer"].get("pose") != "point" and not protected[-1] \
                                and key == self.gesture_key(packets[-1]):
                            packets[-1] = packet
                        else:
                            packets.append(packet)
                            protected.append(transition)
                        self.previous_gesture_key = key
                except (ValueError, UnicodeDecodeError):
                    pass
            self.pending.clear()
            self.discard_line = False
        return [json.dumps(packet, separators=(",", ":"), allow_nan=False) for packet in packets]

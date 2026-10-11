import json
import unittest

from waveboard.hand_stream import HandPacketStream


def frame(x=0.5, **pointer):
    return {"type": "frame", "pointer": {
        "visible": True, "down": False, "hand": "one", "swipe_id": 0,
        "observed": True, "x": x, **pointer,
    }}


def encode(*packets):
    return b"".join(json.dumps(packet).encode() + b"\n" for packet in packets)


class HandStreamTests(unittest.TestCase):
    def test_pose_changes_survive_motion_coalescing(self):
        packets = [frame(pose="peace"), frame(pose=None), frame(pose="peace"), frame(pose="point")]
        actual = list(map(json.loads, HandPacketStream().feed(encode(*packets))))
        self.assertEqual(actual, packets)

    def test_pointing_excursion_away_from_edge_cannot_be_coalesced(self):
        packets = [frame(0.95, pose="point"), frame(0.5, pose="point"), frame(0.95, pose="point")]
        actual = list(map(json.loads, HandPacketStream().feed(encode(*packets))))
        self.assertEqual(actual, packets)

    def test_batched_press_drag_release_and_hover_keep_transition_coordinates(self):
        stream = HandPacketStream()
        packets = [json.loads(line) for line in stream.feed(encode(
            frame(0.1), frame(0.15), frame(0.2), frame(0.2, down=True),
            frame(0.25, down=True), frame(0.3, down=True),
            frame(0.3, down=False), frame(0.35), frame(0.4),
        ))]
        self.assertEqual([p["pointer"]["down"] for p in packets], [False, False, True, True, True, False, False])
        self.assertEqual([p["pointer"]["x"] for p in packets], [0.1, 0.2, 0.2, 0.25, 0.3, 0.3, 0.4])

    def test_pressed_excursion_cannot_collapse_into_a_click_at_its_origin(self):
        packets = list(map(json.loads, HandPacketStream().feed(encode(
            frame(0.2, down=True), frame(0.8, down=True), frame(0.2, down=True), frame(0.2),
        ))))
        self.assertEqual([p["pointer"]["x"] for p in packets], [0.2, 0.8, 0.2, 0.2])

    def test_same_gesture_run_continues_across_process_reads(self):
        stream = HandPacketStream()
        first = list(map(json.loads, stream.feed(encode(frame(0.1), frame(0.2, down=True)))))
        second = list(map(json.loads, stream.feed(encode(
            frame(0.25, down=True), frame(0.3, down=True),
            frame(0.35, down=False), frame(0.4), frame(0.5),
        ))))
        self.assertEqual([p["pointer"]["x"] for p in first], [0.1, 0.2])
        self.assertEqual([p["pointer"]["x"] for p in second], [0.25, 0.3, 0.35, 0.5])
        self.assertEqual([p["pointer"]["down"] for p in second], [True, True, False, False])

    def test_transition_in_next_read_remains_protected_from_following_motion(self):
        stream = HandPacketStream()
        stream.feed(encode(frame(0.1)))
        press = encode(frame(0.2, down=True))
        self.assertEqual(stream.feed(press[:15]), [])
        packets = list(map(json.loads, stream.feed(press[15:] + encode(
            frame(0.3, down=True), frame(0.4, down=True), frame(0.5, down=False),
        ))))
        self.assertEqual([p["pointer"]["x"] for p in packets], [0.2, 0.3, 0.4, 0.5])

    def test_status_ends_motion_run_even_when_state_matches_afterward(self):
        stream = HandPacketStream()
        stream.feed(encode(frame(0.1)))
        packets = list(map(json.loads, stream.feed(encode(
            {"type": "status", "level": "info", "message": "ready"}, frame(0.2), frame(0.3), frame(0.4),
        ))))
        self.assertEqual(packets[0]["type"], "status")
        self.assertEqual([p["pointer"]["x"] for p in packets[1:]], [0.2, 0.4])

    def test_status_cancellation_and_identity_changes_keep_order(self):
        packets = [frame(), {"type": "status", "level": "error", "message": "camera"},
                   frame(cancelled=True), frame(visible=False), frame(hand="two")]
        actual = list(map(json.loads, HandPacketStream().feed(encode(*packets))))
        self.assertEqual(actual, packets)

    def test_split_lines_and_oversize_lines_recover(self):
        stream = HandPacketStream()
        packet = encode(frame())
        self.assertEqual(stream.feed(packet[:17]), [])
        self.assertEqual(list(map(json.loads, stream.feed(packet[17:]))), [frame()])
        self.assertEqual(stream.feed(b"x" * (stream.max_line + 1)), [])
        self.assertEqual(len(stream.pending), 0)
        self.assertEqual(list(map(json.loads, stream.feed(b"suffix\n" + packet))), [frame()])

    def test_malformed_and_nonfinite_packets_are_rejected(self):
        stream = HandPacketStream()
        data = b'garbage\n[]\n{"type":"frame","pointer":{"x":NaN}}\n' + encode(frame())
        self.assertEqual(list(map(json.loads, stream.feed(data))), [frame()])


if __name__ == "__main__":
    unittest.main()

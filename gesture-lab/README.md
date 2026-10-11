# WaveBoard hand tracking

The camera half of WaveBoard. MediaPipe tracks up to two hands from the webcam on
the Jetson Orin Nano. The WaveBoard workspace (the local desktop interface at the
repository root) then draws them as skeletons and takes your pinches as touches.
The camera image never leaves this process, and nothing is recorded or uploaded:
only hand positions go to the local page.

```text
webcam -> tracker.py (MediaPipe, CPU) -> process pipe -> Qt bridge -> web/hands.js
```

## Set up on the Jetson

```bash
cd ~/WaveBoard
bash gesture-lab/setup.sh
```

Setup uses the active virtual environment, or `~/vision-env`, which it creates when missing
(`sudo apt install python3-venv python3-pip` first). It installs MediaPipe, which brings
OpenCV and NumPy, unless the environment already runs them, in which case it keeps your
versions. It copies your hand-drawing app's
`hand_landmarker.task` or downloads Google's. The launcher runs `~/vision-env/bin/python`;
for another environment, setup prints the `WAVEBOARD_HANDS_PYTHON=...` to use. See [desktop setup](../README.md#install-once-on-the-jetson) for the Qt runtime.

## Run

From the repository root, start the workspace and hand tracking together:

```bash
bash scripts/start-ubuntu.sh
```

After installation, open WaveBoard from Applications. The desktop app runs
`tracker.py` automatically and receives its hand packets through a process pipe.
It does not start a WebSocket service. Closing the window stops the camera worker.
Only one program can use the camera at a time.

| Gesture | Effect in the workspace |
| --- | --- |
| Hands in view | Skeletons over the workspace; a round cursor between thumb and index of the main hand |
| Quick thumb + index pinch | Tap: open a card, press a button, pick a colour |
| Pinch, move, release | Drag: draw on the whiteboard, orbit a 3D model |
| Open palm swiped left / right | Next / previous Home card or slide |

## Getting the most accurate tracking

- **Camera position:** face the presenter from below or beside the projected image, at
  about chest height, with the whole hand in view at your working distance.
- **Light:** even light on the hands from the front. Avoid standing in front of a window
  or a bright projection; a plain background helps.
- **Full resolution:** tracking uses the whole camera frame. MediaPipe crops each hand from
  that image, so distant hands stay sharp, and at 1280×720 it measured about as fast as
  640 px. `--processing-width 640` shrinks frames first if the Jetson needs the speed.
- **Standing farther back:** lower the detection threshold, `--detection-confidence 0.35`
  (default 0.5), and if the camera offers it, capture 1080p with `--width 1920 --height 1080`
  for sharper fingers on small, distant hands; watch the tracking rate in the log. Check the
  camera's modes with `v4l2-ctl --list-formats-ext`. A lower threshold also finds more
  things that are not hands, so only lower it as far as you need.
- **Reaching the edges:** `--reach` (default 0.12) ignores that fraction of each camera
  edge so the cursor can reach the screen edges while your hand stays in view. Raise it if
  you cannot reach the edges; lower it if the cursor feels too fast.
- **Smooth, steady points:** each joint and the cursor go through a One Euro filter, which
  removes jitter when the hand is still and adds little lag when it moves. The browser also
  glides the skeleton between tracking updates.
- **Speed:** the log prints the tracking and camera rates every 10 seconds. Put the Jetson in
  its highest power mode (top-bar power menu; check with `sudo nvpmodel -q`) and run
  `sudo jetson_clocks`.

With the launcher, pass tracker options through `WAVEBOARD_HANDS_ARGS` and read the log in
`/tmp/waveboard-hands.log`:

```bash
WAVEBOARD_HANDS_ARGS="--camera /dev/video2 --detection-confidence 0.35" bash scripts/start-ubuntu.sh
```

## Options

| Option | Default | Purpose |
| --- | --- | --- |
| `--camera` | `0` | Camera index, or on Linux a path such as `/dev/video2` |
| `--width`, `--height`, `--fps` | 1280, 720, 30 | Requested capture mode; the camera may choose less |
| `--fourcc` | `MJPG` | Camera pixel format (`YUYV` for cameras without MJPG) |
| `--processing-width` | full frame | Shrink frames to this width before MediaPipe |
| `--detection-confidence` | 0.5 | Hand detection threshold |
| `--reach` | 0.12 | Camera edge band mapped beyond the screen edges |

Find the camera with `v4l2-ctl --list-devices` (`sudo apt install v4l-utils`).

## Troubleshooting

- **No skeleton appears:** check `/tmp/waveboard-hands.log` (or stderr when running `tracker.py` yourself). It names the camera mode, reports errors, and prints the tracking rate.
- **Camera cannot open:** close other camera apps, find the device with
  `v4l2-ctl --list-devices`, and pass `--camera /dev/videoN`.
- **Model absent or MediaPipe import fails:** run `bash gesture-lab/setup.sh` again; it reports
  which step fails.
- **The cursor jumps between hands:** it follows one hand at a time; another hand only takes
  over when it pinches while the first is not pressing.
- **Taps land beside buttons:** pinch deliberately and hold still for a moment; small
  movements during a pinch are ignored so the tap lands where it started.

## Files and tests

- `tracker.py`: camera capture, MediaPipe settings, and the frames sent to the workspace.
- `gestures.py`: finger extension, pinch detection with hysteresis, and stable hand ids.
- `hand_pointer.py`: screen mapping, smoothing, the touch pointer, swipes, and skeleton points.
- `server.py`: legacy WebSocket adapter, unused by the desktop app.
- `tests/fixtures/mediapipe_sample_hands.json`: real MediaPipe landmarks used in tests.

```bash
python -m unittest discover -s tests -v
```

Hand tracking with a live camera, its speed on the Orin Nano, and the gestures at real
presenting distances still need checking on the device.

# WaveBoard hand tracking

The camera half of WaveBoard. MediaPipe tracks one teacher's hand by default,
with an option for two hands. The WaveBoard workspace (the local desktop interface
at the repository root) draws skeletons and takes your pinches as touches.
The camera image never leaves this process, and nothing is recorded or uploaded:
only hand positions and detected projection-marker coordinates go to the local page.

```text
webcam -> latest frame -> checked palm motion -> process pipe -> Qt -> workspace
                     \-> CPU MediaPipe -> fresh landmarks and gesture evidence
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
| Held pinch moving up / down in a list | Scroll files, folders, or dialog content |
| Pinch and drag the video bar | Seek within the video |
| Open palm swiped left / right | Next / previous Home card or slide |

Pinch the top tab to open the menu. Its controls, file locations, dialog buttons,
contrast checkbox, and on-screen file search keyboard all work with the hand
cursor. The control under the cursor highlights before selection. Open files
through the app's device/USB picker, and use **Files → Import** to copy a file
into the folder currently shown. **Save** writes a PNG directly to
`Pictures/WaveBoard` and shows the saved path. Menu buttons handle fullscreen and
3D zoom; **Settings → Close WaveBoard** closes the app after an on-screen
confirmation. No operating-system file dialog is required during these flows.

## Projector mode

**Settings → Projector mode** combines hand mirroring and projection alignment.
It is off by default, preserving the original backend cursor, skeleton, and
swipe coordinates. Turning it off bypasses projection mapping while keeping a
saved hand calibration for the next time you enable it.

For hands held in the air, enable Projector mode, then use **Menu → Align hands**.
Align hands is available only while Projector mode is on. Four deliberate, stable
pinches measure the index fingertip (`camera_points[8]`) at on-screen targets;
a fifth target validates the center. Stay at your normal working distance and
viewing position. Open the hand between targets. Flow and predicted frames do
not count as samples; identity changes and tracking gaps reset the current hold.
An inconsistent center or collapsed set of targets is rejected.

The resulting camera-to-screen mapping corrects scale, perspective and offset at
that working position. In Projector mode, it takes priority over the corner mapping
for skeletons, swipes and the cursor; the cursor uses the index fingertip with this mode. The
calibration is saved locally with viewport dimensions and camera resolution.
Resize/resolution changes invalidate it. Recalibrate after moving the setup or
changing your standing position. This cannot track changing depth automatically.
The calibration flow consumes all gestures without passing clicks to the workspace.

Before alignment, Projector mode reverses the manual mapping for a camera beside
the projector facing the screen. The skeleton, cursor, and swipes share that
direction. Calibration sets orientation automatically, without a second mirror.

Projector mode displays four distinct corner markers when no hand calibration is
active. For hands near the screen surface, keep the camera beside the projector
with both the hands and the entire projected screen in view. Three steady
detections establish a perspective mapping
from camera coordinates to the projection; status then reads **Aligned to
projection**. The markers stay visible so the mapping can adjust if the setup moves.
Calibration sets orientation automatically and bypasses the manual crop/mirror.
Keep hands near the screen: this flat-surface mapping cannot correct hand depth
or parallax away from the projection plane.

`projection.py` uses the existing OpenCV and NumPy packages, with no extra runtime
dependencies. It detects four 6×6 binary markers with white quiet zones, accepts
rotated and reflected views, and rejects ambiguous duplicate IDs. Scanning runs
at most twice per second in the inference worker, separate from the capture and
pointer loop. Frame packets include marker centers and the actual scan timestamp;
repeated packets cannot count as new calibration evidence. Raw camera coordinates
are also included for the cursor, every skeleton joint, and swipe endpoints.

If markers are briefly hidden, the previous alignment holds for up to 2.5 seconds.
After that, the workspace reports manual alignment and cancels a held gesture.
This timeout applies only to the corner mapping, never a saved hand calibration.
Markers are intentionally hidden while a menu/dialog is open; this pauses corner
scanning and preserves the remaining timeout until the menu closes.
Show an open hand before pressing again. Resizing, camera resolution changes, and
**Recheck corners** clear the corner mapping. Corner calibration is not saved between sessions.
If detection cannot find all corners, improve focus/contrast, move the camera
closer, or use `--processing-width 960` so markers occupy enough camera pixels.

## Tracking speed and accuracy

Camera capture, AI landmark inference, and pointer updates run at different
rates. Capture and inference each retain only the newest pending frame, so a
slow model does not build a long input queue. Between model observations, sparse
optical flow follows textured points inside the palm and translates the hand.
It checks points forward and backward and rejects inconsistent movement.

The default `--max-hands 1` matters for a single presenter: MediaPipe's video
pipeline continues running the palm detector while it has fewer tracked hands
than the configured maximum. Previously, asking for two hands meant searching
for a second hand on each model frame even when only one was needed. Use
`--max-hands 2` when two-hand control is useful. See the
[MediaPipe graph](https://github.com/google-ai-edge/mediapipe/blob/master/mediapipe/tasks/cc/vision/hand_landmarker/hand_landmarker_graph.cc)
for the detector's hand-count condition.

**Settings** shows **Hand updates** separately from **AI detection**. The first
includes camera-based motion between observations; the second counts actual
landmark inference. `/tmp/waveboard-hands.log` also reports camera FPS, inference
duration, processing dimensions, and how many hands use optical flow. These
changes do not establish a measured FPS target for the Jetson; compare both
rates on your own device.

If motion becomes uncertain, the cursor briefly holds its last reliable
position. A hold lasts up to 220 ms; all continued motion expires within 450 ms
of the latest real hand observation. Flow never invents finger articulation,
a new pinch, a release, or a swipe. A press that cannot safely continue is
cancelled, so losing a hand cannot turn into a button click. Show an open hand
before pinching again after a prolonged loss.

- **Camera position:** for projection alignment, face the screen from beside the
  projector and keep all four corner markers visible. For manual control, face
  the presenter with the whole hand in view at your working distance.
- **Light:** even light on the hands from the front. Avoid standing in front of a window
  or a bright projection; a plain background helps.
- **Image size:** the default capture request is 1280×720 at 30 FPS. Frames are
  reduced to 640 pixels wide before mirroring, color conversion, and inference.
  This reduces preprocessing work. Keep the default for nearby hands; use
  `--processing-width 960` or `--processing-width 1280` when distant fingers
  are too small. A larger image can use more CPU time.
- **Standing farther back:** lower the detection threshold, `--detection-confidence 0.35`
  (default 0.5) if needed, and increase `--processing-width` first. If the camera
  offers it, request 1080p with `--width 1920 --height 1080 --processing-width 1280`;
  watch both FPS values in Settings. Check the
  camera's modes with `v4l2-ctl --list-formats-ext`. A lower threshold also finds more
  things that are not hands, so only lower it as far as you need.
- **Fast movement:** `--tracking-confidence 0.3` accepts less overlap between
  successive hand boxes, and `--presence-confidence 0.4` avoids some unnecessary
  re-detection. These are separate from the initial hand detection threshold.
  Motion blur still limits both methods; keep the hand well lit and within view.
- **Reaching the edges:** `--reach` (default 0.12) ignores that fraction of each camera
  edge so the cursor can reach the screen edges while your hand stays in view. Raise it if
  you cannot reach the edges; lower it if the cursor feels too fast.
- **Smooth, steady points:** each joint and the cursor go through a One Euro filter, which
  removes jitter when the hand is still and adds little lag when it moves. The browser also
  glides the skeleton between tracking updates.
- **Low camera FPS:** the requested camera mode may differ from the negotiated
  mode. Check the startup log and try `--width 640 --height 480 --fps 30` if the
  camera or USB connection cannot maintain the default capture rate. Optical
  flow cannot create fresh camera measurements faster than capture supplies them.
- **Low AI detection FPS:** keep one-hand mode, close other CPU-heavy programs,
  and check the Jetson's configured power mode and cooling. A low model rate can
  coexist with higher hand-update FPS; model-confirmed gestures still depend on
  fresh inference results.

With the launcher, pass tracker options through `WAVEBOARD_HANDS_ARGS` and read the log in
`/tmp/waveboard-hands.log`:

```bash
WAVEBOARD_HANDS_ARGS="--camera /dev/video2 --detection-confidence 0.35" bash scripts/start-ubuntu.sh
# Optional two-hand tracking with a larger image for distant hands:
WAVEBOARD_HANDS_ARGS="--max-hands 2 --processing-width 960" bash scripts/start-ubuntu.sh
```

## Options

| Option | Default | Purpose |
| --- | --- | --- |
| `--camera` | `0` | Camera index, or on Linux a path such as `/dev/video2` |
| `--width`, `--height`, `--fps` | 1280, 720, 30 | Requested capture mode; the camera may choose less |
| `--fourcc` | `MJPG` | Camera pixel format (`YUYV` for cameras without MJPG) |
| `--processing-width` | 640 | Resize before mirroring/inference; never enlarge a smaller capture frame |
| `--max-hands` | 1 | Maximum tracked hands; use 2 for two-hand control |
| `--detection-confidence` | 0.5 | Hand detection threshold |
| `--presence-confidence` | 0.4 | Landmark presence threshold before palm re-detection |
| `--tracking-confidence` | 0.3 | Minimum overlap for associating successive hand boxes |
| `--reach` | 0.12 | Camera edge band mapped beyond the screen edges |
| `--max-frame-age-ms` | 250 | Discard old pending frames before starting inference |

Find the camera with `v4l2-ctl --list-devices` (`sudo apt install v4l-utils`).

## Troubleshooting

- **No skeleton appears:** check `/tmp/waveboard-hands.log` (or stderr when running `tracker.py` yourself). It names the camera mode, reports errors, and prints the tracking rate.
- **Camera cannot open:** close other camera apps, find the device with
  `v4l2-ctl --list-devices`, and pass `--camera /dev/videoN`.
- **Model absent or MediaPipe import fails:** run `bash gesture-lab/setup.sh` again; it reports
  which step fails.
- **Only one skeleton appears:** one-hand mode is the faster default. Set
  `--max-hands 2` to allow both hands. The cursor follows one hand at a time;
  another hand can take over when it pinches while the first is not pressing.
- **Taps land beside buttons:** pinch deliberately and hold still for a moment; small
  movements during a pinch are ignored so the tap lands where it started.

## Files and tests

- `tracker.py`: camera capture, MediaPipe settings, and the frames sent to the workspace.
- `tracker_motion.py`: checked sparse optical flow, delayed-result alignment, and bounded motion retention.
- `gestures.py`: finger extension, pinch detection with hysteresis, and stable hand ids.
- `hand_pointer.py`: screen mapping, smoothing, the touch pointer, swipes, and skeleton points.
- `projection.py`: camera detection of the four projection border markers.
- `server.py`: legacy WebSocket adapter, unused by the desktop app.
- `tests/fixtures/mediapipe_sample_hands.json`: real MediaPipe landmarks used in tests.

```bash
python -m unittest discover -s tests -v
```

Run from this `gesture-lab` directory. Motion tests require OpenCV and NumPy in
the test environment; the geometry and pointer tests do not require a camera.

Hand tracking with a live camera, its speed on the Orin Nano, and the gestures at real
presenting distances still need checking on the device.

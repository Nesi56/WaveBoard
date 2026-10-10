# Gesture Lab — hands-on 3D presentations

A local prototype for your Jetson Orin Nano, EMEET webcam, and HDMI projector.
Python tracks two hands, a gesture state machine interprets their fingers, and a
Three.js viewer displays a selectable assembly. You can also use the mouse.

Three things share the same hand tracking:

- **Hand control for the WaveBoard workspace** (the browser interface at the
  repository root): `server.py` also streams a touch-style pointer, so a pinch taps
  and drags and an open-palm swipe changes cards and slides. Start both with
  `bash scripts/start-ubuntu.sh --hands` from the repository root; see the
  [root README](../README.md#controlling-the-workspace-with-your-hands).
- **Canvas Studio** (`canvas_studio.py`, OpenCV): frame a canvas with both hands,
  stretch it like a TouchDesigner hand-tracking demo, then present slides, draw,
  or look through live camera lenses on it. See [Canvas Studio](#canvas-studio-frame-stretch-and-draw).
- **3D viewer** (`server.py` + browser): grab, rotate, zoom and explode a 3D assembly.

`server.py` serves the 3D viewer on port 8000 and streams hands on WebSocket port
8766 (the workspace itself uses 8765), on loopback only.

This builds on the Python environment that already runs your hand-drawing app.
It assumes the **same Orin Nano with Python 3.12** from your earlier setup.
An original Jetson Nano needs a separate dependency compatibility check.

## Start on the Jetson

Clone the WaveBoard repository on the Jetson (or download `gesture-lab.zip` and
extract it). With the folder in `~/WaveBoard/gesture-lab`, run:

```bash
cd ~/WaveBoard/gesture-lab
source ~/vision-env/bin/activate
bash setup.sh
python canvas_studio.py   # Canvas Studio, fullscreen on the projector
python server.py          # or the 3D viewer
```

For the 3D viewer, open **http://127.0.0.1:8000** in a browser on the Jetson. Close other apps that
use the webcam. Setup reuses your existing MediaPipe/OpenCV/NumPy installation
and your drawing app's hand model if it is present. It adds the WebSockets
package; it does not upgrade your working vision libraries.

The Three.js code is bundled, so no Node.js installation or browser CDN is
needed. Once setup is complete, the app works without an internet connection.
Camera images stay in the Python process; only hand coordinates and gesture
states go to the local browser. Nothing is uploaded or recorded.

**Test without the camera:** `python server.py --no-camera`

**See the camera and hand skeleton:** `python server.py --preview`

Stop the server with Ctrl+C in its terminal. The preview window also supports Q.

## 3D viewer gestures

Hold your hands in front of your body, facing the camera, with good light and
visible fingertips. Release one gesture before starting another. Move slowly
while learning the controls.

| Gesture | Action |
| --- | --- |
| Point without pinching | Move the on-screen cursor |
| Thumb + index pinch | Select and drag a component under the cursor; drag empty space to move the whole assembly |
| Thumb + middle pinch | Rotate the assembly by moving the hand; wrist twist adds roll |
| Thumb + ring pinch, hold briefly | Select the next component |
| Thumb + pinky pinch, hold about 0.7 seconds | Reset the view and reassemble |
| Index pinches on both hands; move hands apart/together | Enlarge/shrink the assembly |
| Two open palms with all fingers extended; move hands apart/together | Separate/reassemble the components |
| Relax hands / close fists / leave camera view | Stop manipulation |

The thumb participates in every pinch. The HUD shows the estimated extension
state of **all five fingers on each hand**, plus the complete 21-joint skeleton.
Ring and pinky pinches may take practice; keyboard and mouse controls provide
a fallback while you tune recognition. Finger states are geometric heuristics,
not a general sign-language recognizer.

Zoom and exploded view deliberately require different poses. Pinches have a
tighter start threshold and a looser release threshold to avoid flicker. Discrete
actions trigger once per held gesture. Hand loss cancels active manipulation.

Use the on-screen buttons for reset, gesture pause, projector mode, and fullscreen.
The assembly list selects components. Mouse drag orbits and the wheel zooms.
See the viewer's shortcut help for keyboard equivalents.

## Canvas Studio: frame, stretch and draw

```bash
python canvas_studio.py                       # built-in tutorial slides
python canvas_studio.py --slides ~/my-deck    # your own slides
python canvas_studio.py --no-camera           # mouse and keyboard only
```

Canvas Studio opens fullscreen and draws straight to the projector with OpenCV;
no browser is involved. Drag the window onto the projector display first, or start
with `--windowed` and press **F** once it is there. Press **H** to hide the
gesture guide, **Q** or **Esc** to quit.

### Make a canvas with your hands

1. Make an **L with both hands**: thumb and index finger out, other fingers curled.
   Hold them at opposite corners of the canvas you want (left hand lower-left,
   right hand upper-right), or both upright like a film director framing a shot.
2. A dashed frame follows your hands. **Hold still until the ring fills** (about half a second).
3. The canvas appears and stays glued to your hands. **Pull them apart to stretch it.**
4. **Relax both hands** to place it. It keeps the size it had just before you relaxed,
   so the movement of your fingers as they close does not resize it.
   To cancel, squeeze your hands together before relaxing.

Nearly 16:9, 4:3 or square canvases snap to the exact shape when placed.

### All gestures

| Gesture | Action |
| --- | --- |
| Both hands in an L, hold, pull apart, relax | Frame, stretch and place a new canvas |
| Thumb + index pinch on a canvas | Move it (it comes to the front) |
| Thumb + index pinch with both hands on one canvas | Stretch it; width and height follow your hands separately |
| Pinch-drag a canvas onto the bin at the bottom | Delete it |
| Point with the index finger, thumb tucked in | Draw on a whiteboard; laser pointer on slides and lenses |
| Thumb + pinky pinch | Next tool: laser pointer, then each pen colour (pens draw on slides too) |
| Thumb + ring pinch | Undo the last stroke on that canvas |
| Thumb + middle pinch on a canvas | Change what it shows (see below) |
| Thumb + middle pinch on empty space | Change what new canvases show |
| Open palm swiped left / right | Next / previous slide |

Pointing is a laser pointer on slides by default because presenters point at
slides while they talk; choose a pen with a pinky pinch when you want to annotate.
Ink belongs to its canvas, moves and stretches with it, and slides keep separate
ink for every page. A stroke ends cleanly when you change pose: the classifier waits
about 0.1 s before accepting a new pose, and the points drawn during that wait are removed.

### What a canvas can show

| Content | Description |
| --- | --- |
| Slides | Your deck (or the tutorial), letterboxed to the canvas |
| Whiteboard | Dark board for drawing |
| Neon edges lens | Live camera behind the canvas as glowing outlines |
| Thermal lens | Live camera in heat-map colours |
| Pixel lens | Live camera as large pixels |
| X-ray lens | Inverted bone-tone camera image |
| Magnifier lens | The middle of the canvas region at twice the size; hold an object up to it |

Lenses are aligned with the camera background, so a framed lens looks like a
window revealing an effect over the live image. New framed canvases start as the
neon lens; change that with `--new-canvas board` (or `slides`, `lens:thermal`, …).

### Your own slides

Export one image per slide into a folder (PNG or JPG). Files are shown in natural
name order, so `slide-2.png` comes before `slide-10.png`.

- PowerPoint: *File → Export → Change File Type → PNG*, then choose *All Slides*.
- Google Slides or Keynote: export a PDF, then on the Jetson run
  `sudo apt install poppler-utils` and `pdftoppm -png -r 110 deck.pdf ~/my-deck/slide`.

Arrow keys, Page Up/Down and Space also change slides, so a USB presenter clicker works.

### Keyboard and mouse

| Key | Action |
| --- | --- |
| → ↓ Page Down Space / ← ↑ Page Up | Next / previous slide |
| N | New canvas in the middle of the screen |
| C | Change what the focused canvas shows |
| Z / X | Undo / clear ink on the focused canvas |
| K | Next tool (laser, pen colours) |
| Delete | Delete the focused canvas |
| B | Background: dimmed camera, full camera, plain |
| V | Show or hide the hand skeletons |
| P | Pause gestures |
| S | Save a screenshot to `captures/` |
| F / H / Q | Fullscreen / help / quit |

Mouse: drag empty space to make a canvas, drag a canvas to move it, drag its
lower-right corner to resize, right-drag to draw, scroll to scale.

### Reaching the edges and other options

`--reach 0.12` ignores 12% of each camera edge, so your hands reach the screen edges
without leaving the camera's view. Raise it if you stand far from the camera; lower
it if you stand close. The camera options (`--camera`, `--width`, `--height`, `--fps`,
`--fourcc`, `--processing-width`) are the same as for `server.py`, described below.
`--screen 1280x720` sets the drawing resolution; the window scales it to the
projector, and 1280×720 keeps rendering light on the Jetson.

## Camera setup and FPS

The default capture request is **1280×720 at 30 FPS**, with a proportionally resized
640-pixel-wide frame for hand tracking. The actual camera mode may differ.

EMEET uses the Nova name for several variants. The Nova 4K Dual is advertised
with 1080p60 and 4K30 modes; confirm your actual device instead of assuming every
Nova exposes the same modes on Linux.

```bash
sudo apt install v4l-utils
v4l2-ctl --list-devices
v4l2-ctl -d /dev/video0 --list-formats-ext
```

Replace `/dev/video0` with the EMEET capture device shown in the first command.
If 1920×1080 MJPG at 60 FPS is listed, request it with:

```bash
python server.py --camera /dev/video0 --width 1920 --height 1080 --fps 60
```

For a different camera format, use `--fourcc YUYV`. Do not assume uncompressed
1080p60 is supported just because MJPG supports that mode.

The viewer separates three measurements:

- **Capture FPS:** frames read from the camera.
- **Tracking FPS:** completed hand-tracking updates sent to the viewer.
- **Render FPS:** browser animation frames.

A 60 FPS camera does not guarantee 60 tracking updates per second. Capture keeps
only the newest frame to limit lag. Rendering runs independently of tracking.
The tracker uses MediaPipe's CPU default; this project does not configure CUDA
or TensorRT. Browser graphics acceleration depends on the Jetson browser/driver
installation. No hardware FPS is guaranteed or benchmarked here.

If tracking is slow, try `--processing-width 480`. If small fingers are difficult
to see, try `--processing-width 800`, accepting potentially slower tracking.
Good illumination and less motion blur can help more than capturing at 4K.

## Projector and model files

Connect the projector by HDMI and select it in Ubuntu display settings. Move
the browser window onto that display (or mirror the desktop), then use fullscreen
and projector mode. Position the camera toward the presenter; a projector image
is not required for hand tracking. This is an interactive 3D scene on a flat
projection, not a physical hologram.

The built-in engine is a **conceptual demonstration assembly**, not a validated
engineering design. Use the import control to open your own `.glb` file (up to
50 MB). Export separate, meaningfully named components from your CAD/3D tool.
A single merged mesh cannot automatically become independently movable parts.

Use an uncompressed GLB (or self-contained glTF) with embedded textures and geometry.
The importer accepts 1–500 static mesh components; skinned models are not supported. External resource
URLs and specialized compressed assets are not supported by this starter. The
explosion directions are visual layout heuristics, not mechanical assembly
constraints. Large CAD exports should be simplified before use on the Jetson.

## Tune or extend the app in Vim

```bash
vim gestures.py
```

- `canvas_gestures.py`: Canvas Studio's gesture timing at the top of `CanvasStudio`
  (`charge_ms` hold before a canvas appears, `pose_hold_ms`, swipe distance and
  timing) and `classify()` for which finger pattern means L, point or open palm.
- `canvas_studio.py`: what canvases show (`LENSES`), colours, the help strip and keys.
- `hand_pointer.py`: the workspace pointer — which hand drives it, the tap/drag
  threshold (`press_radius`) and swipe distance; `server.py --reach` sets the edge margin.

- `PinchState.on` and `.off`: start/release distances, divided by palm length.
  Default 0.15/0.25. Lower `on` if pinches trigger too easily; keep `off > on`.
- `finger_states`: a finger is extended when its tip is more than 1.12× as far from
  the wrist as its middle joint; the thumb uses joint angles and abduction. This replaced
  joint-angle thresholds for the four fingers, which marked straight fingers as folded in
  real MediaPipe output (`tests/fixtures/mediapipe_sample_hands.json`).
- `GestureEngine`: gesture priority, hold time, and exclusivity.
- `tracker.py`: camera acquisition and MediaPipe options (`num_hands=2`).
- `web/app.js`: mapping gestures to model transformations.
- `web/styles.css`: viewer appearance.

Camera-based depth is estimated. Fingers overlapping in the image can appear to
touch even when they do not physically touch. Keep fingertips visible; test
across hand sizes, angles, lighting, and presentation distance. Thresholds and
gesture mappings are starting points and need tuning with your actual camera.

## Troubleshooting

- **Model absent:** activate `vision-env`, then run `bash setup.sh` again.
- **MediaPipe import fails:** use the exact environment that runs your drawing
  app. Do not replace working Jetson packages with unrelated desktop wheels.
- **Camera cannot open:** close other camera apps, confirm the capture node with
  `v4l2-ctl --list-devices`, and pass `--camera /dev/videoN`.
- **Viewer works but hands do nothing:** check the status banner, use `--preview`,
  and make sure gestures are not paused. The mouse demo has tracking disabled.
- **Cannot connect:** keep `python server.py` running; open the address on the
  Jetson itself, not another computer. Both servers bind to loopback only.
- **Port in use:** stop the previously launched server before starting another.
- **Canvas Studio window does not open:** start it from the Jetson desktop, not an
  SSH session (or `export DISPLAY=:0` first).
- **The L-frame does not start:** keep both thumbs clearly sticking out and the other
  fingers curled. Each hand's cursor turns into a small L when it is recognised as
  one; the frame starts when both are. Press **V** to see the hand skeletons.
- **Pointing does not draw:** on slides and lenses, pointing is a laser pointer
  until you pick a pen (thumb + pinky pinch, or **K**). Tuck your thumb in;
  an extended thumb makes the hand an L instead of a point.
- **Original Nano rather than Orin:** check `tr -d '\0' </proc/device-tree/model`
  and `python --version`; installation compatibility is not established here.

## Languages, dependencies, and validation

- Python: camera capture, hand tracking, gesture decisions, local server, and
  Canvas Studio's OpenCV rendering.
- JavaScript / Three.js: 3D rendering and interaction.
- HTML/CSS: browser controls and layout.
- Bash: setup convenience script.

Python uses your existing MediaPipe, OpenCV and NumPy, plus `websockets>=14,<18`.
The bundle includes Three.js 0.180.0 and its MIT license under `web/vendor/three`.
The official hand model is reused or downloaded separately by setup.

Run software checks with `python -m unittest discover -s tests -v`. Camera
recognition, real FPS, projector output, and gesture ergonomics must still be
tested on your Jetson; this package is a starter, not a hardware-validated release.
Canvas Studio adds slides and annotation; there is no language model for
questions about the assembly yet.

Checks completed while preparing this package: 26 Python unit tests; Python and
JavaScript syntax checks; local HTTP assets and WebSocket connectivity; rejection
of unrelated WebSocket origins; browser rendering, component selection, pause,
keyboard help, exploded view and presentation layout. The browser's automated
file chooser did not complete, so model import still needs an end-to-end check
with your own GLB. Actual hand tracking was not exercised here.

Canvas Studio checks: unit tests for framing, stretching, moving, deleting, drawing,
swipes and pinch shortcuts; off-screen rendering of every canvas type with OpenCV 4.10
and 5.0; and the full `canvas_studio.py` loop run with real MediaPipe on recorded sample
photos (pointing and fist recognised, laser and pen behaviour confirmed). The L-frame
gesture is covered by unit tests only; it still needs trying with real hands, camera
and projector on the Jetson.

## References

- [MediaPipe hand landmarks and Python API](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/python)
- [MediaPipe GPU support](https://developers.google.com/edge/mediapipe/framework/getting_started/gpu_support)
- [EMEET Nova variants](https://emeet.com/products/webcam-nova)
- [EMEET Nova 4K Dual specifications](https://emeet.com/products/emeet-smartcam-nova-4k-dual)
- [NVIDIA JetPack release details](https://developer.nvidia.com/embedded/jetpack/downloads)
- [Three.js GLTFLoader](https://threejs.org/docs/pages/GLTFLoader.html)

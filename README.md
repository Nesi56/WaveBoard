# WaveBoard

WaveBoard is an offline desktop app for an NVIDIA Jetson, webcam, and projector.
Open **WaveBoard** from the Jetson's Applications menu to draw, explore 3D models,
browse device and USB files, play videos, and present PowerPoint or PDF slides.
Hand tracking turns pinches into taps and drags, with hand skeletons drawn over
the workspace. Camera images are not uploaded or recorded.

## A local app, with no hosting

The normal launcher opens a Qt desktop window. Its bundled HTML/JavaScript interface
is rendered inside the application, rather than in a separately launched browser.
Local resources use an internal `waveboard://app` address. This is a resource identifier,
not a network service: no HTTP server or WebSocket server is started and no network
port is opened by the workspace or tracker. File operations call Python directly
through Qt's in-process WebChannel. Hand tracking runs as an app-managed camera worker
and sends JSON through a process pipe. Closing the app stops that worker.

The desktop window blocks remote resource requests. Libraries, examples, and the
hand model are stored on the device. Internet is needed only for initial installation.

## Install once on the Jetson

If using a downloaded source archive, extract its `WaveBoard` folder and skip the
`git clone` command below. Run the installer from that extracted folder.

Target: Jetson Orin Nano with JetPack 6 / Ubuntu 22.04, a desktop session, USB webcam,
and a projector connected to the display output. Run these commands as your normal
Jetson desktop user, not from a root shell:

```bash
git clone https://github.com/Nesi56/WaveBoard.git ~/WaveBoard
cd ~/WaveBoard
bash scripts/install-jetson.sh
```

For an existing checkout, update it first and run the same installation script.
The script asks for sudo to install Ubuntu's Qt desktop bindings, LibreOffice Impress,
Poppler, and Python environment tools. It prepares the hand tracker and model,
then installs a **WaveBoard** entry in your user's Applications menu. It leaves
this checkout in place; do not move or delete it after installing the launcher.
Qt is installed using Ubuntu packages so it works with JetPack's ARM64 runtime.
There is no Node build, cloud account, web hosting, or browser installation step.

## Use it

1. Connect the webcam and projector.
2. Open **WaveBoard** from Applications.
3. Hold up one hand and move the round cursor onto a control. Pinch thumb and
   index, then release to select; hold a pinch and move to draw or drag.
   Point with only your index finger and hold near the left or right edge to browse Home cards or slides. Move away to stop. Hold a peace sign for 3 seconds to return Home; a ring around the cursor shows the countdown.
4. Pinch the bottom-right three-dot button to open the menu. Its buttons, dialogs, file locations,
   and settings all accept the same hand controls. Pinch and move up or down
   to scroll a list; drag the video bar to seek.
5. Use the menu's **Fullscreen** button to change window mode. To finish, open
   **Settings → Close WaveBoard** and confirm. Keyboard shortcuts remain
   available: **Alt+F4** or **Ctrl+Q** to close, **F11** for fullscreen.

For a camera-free launch or a normal-sized window:

```bash
cd ~/WaveBoard
bash scripts/start-ubuntu.sh --no-hands --windowed
```

You can also launch with `/usr/bin/python3 -m waveboard` from the repository root.
No terminal needs to remain open when using the Applications entry. Hand tracking
starts automatically when `~/vision-env/bin/python` exists; missing setup produces
an explanation and the app remains usable with mouse and touch.

For a different tracker environment or camera:

```bash
WAVEBOARD_HANDS_PYTHON=/path/to/vision-env/bin/python bash scripts/start-ubuntu.sh
WAVEBOARD_HANDS_ARGS="--camera /dev/video2" bash scripts/start-ubuntu.sh
```

For projection alignment, place the camera beside the projector facing the screen,
with the hands and all four projected corners visible. For manual hand control,
the camera can face the presenter. See [hand tracking](gesture-lab/README.md) for tuning.

Tracking now defaults to one teacher's hand and a 640-pixel processing width.
The model runs separately from camera capture, while checked optical flow follows
palm motion between model results. **Settings** shows **Hand updates** and
**AI detection** separately: a smoother cursor does not mean the model runs at
the camera's frame rate. Actual rates depend on the Jetson and camera.

For two hands, or small hands farther from the camera, change the launch options:

```bash
WAVEBOARD_HANDS_ARGS="--max-hands 2 --processing-width 960" bash scripts/start-ubuntu.sh
```

Two hands and a larger processing image can cost more CPU time. During brief
tracking interruptions, the cursor holds its last position and waits for a
reliable observation. A prolonged loss cancels a press instead of clicking a
button accidentally; show an open hand before pinching again.

## Projector controls

Home shows colorful cards for **Whiteboard**, **Slides**, **Files**, **Video**, and **3D** against a dark navy background. Point and hold near either screen edge, or use the arrows to browse. Cards visibly slide as you move through them. Pinch or tap a card to open it. Keyboard arrow keys work too. Settings, calibration, and fullscreen are directly available from Home.

The bottom-right three-dot button opens extra tools, fullscreen, help, and settings. Circular controls along the bottom keep common actions in reach, and coral outlines highlight the control under your hand. The whiteboard has a light dotted canvas and a drawing dock; its color control opens ink and brush-size choices. Save, redo, and clear remain available in the menu. Clearing a board can be undone.

The other utilities share the same dark background and bottom controls. **3D** opens the bundled `Untitled.glb` demo, including its embedded color texture, and exposes zoom and view controls around the model. **Files** shows colored file cards and actual device locations, with a Location chooser on narrower screens. **Video** has playback and seek controls. **Slides** keeps previous/next controls beside the presentation and a counter below it. Home is always one button away.

The local file picker uses large buttons for folders and device/USB locations.
In **Files**, choose the destination folder, then **Import** to copy a file from
another location. **Find file** includes an on-screen keyboard. **Save** exports
the whiteboard directly to a `WaveBoard` folder inside Pictures and displays its
path; other downloads go to `WaveBoard` inside Downloads. Each save receives a
unique filename. A custom `--root` uses that folder's `WaveBoard` subfolder
instead. **3D** includes menu buttons for zooming without a mouse wheel.

## Utilities

| Utility | Available interactions |
| --- | --- |
| 3D space | Open a model, drag to orbit, zoom, reset the view, and inspect a built-in sample. |
| Whiteboard | Draw with a pen or highlighter, erase, undo/redo, clear, and export a PNG. |
| Files | Browse this device, mounted USB drives on Ubuntu, and bundled demo files; open supported files in their viewer. |
| Video player | Open local videos, play/pause, seek, mute/unmute, and use fullscreen. |
| Presentations | Open PowerPoint or PDF files and navigate rendered slides. |

Tap opens controls and items; press and hold exposes details where offered. Drawing and 3D orbiting use a held pointer while moving. With hand tracking, a pinch is the tap and a held pinch is the held pointer.

### Projector mode

Enable **Settings → Projector mode** to mirror the hands and align them with the
projection. It is off by default: with it off, the skeleton and cursor
use the original hand coordinates, without added mirroring or projection mapping.
Turning it off keeps a saved hand calibration for the next time you enable it.

For hands held **in the air**, enable Projector mode, then use **Menu → Align hands**
(also in Settings). Align hands is available only while Projector mode is on.
Enter fullscreen first, stand where you normally work, and keep the same hand
distance and viewing position throughout calibration. Place your index fingertip
over each of the four targets, pinch and hold still until it advances, then open
your hand before moving to the next target. A fifth target checks the center.
The gesture is measured directly from the camera; the old cursor does not need
to reach the target. Calibration pinches do not click or draw on the workspace.

This measures scale and perspective at your working hand position, including an
offset that grows from one side of the screen to the other. The cursor then uses
the same index fingertip as calibration, and every skeleton joint uses the same
mapping. A failed center check asks you to retry without replacing a previous
alignment. **Cancel** or **Escape** leaves the previous alignment intact.

Hand calibration is saved locally and, in Projector mode, takes priority over
screen corner markers. It does not disappear when a marker is covered. **Settings → Reset alignment**
removes it. Resizing the workspace or changing camera resolution clears it;
run **Align hands** again after moving the camera, projector, or your working
position. This is still a mapping at one working depth, not automatic 3D sensing.

The interface uses larger text and controls for 480p projectors: 24–28px interface text
and generous circular buttons. Long menus and Settings scroll instead of
reducing the text size.

Projector mode mirrors the skeleton and cursor together before alignment.
A successful calibration determines orientation itself, so the result is not
mirrored a second time. Edge holds always use the cursor’s final screen position.

Projector mode also shows four black-and-white corner markers when no hand
calibration is active. For hands close to the actual screen surface, the camera
detects their identities and maps the hand positions to the projected area,
correcting position, scale, perspective, and orientation.
Wait for **Aligned to projection**; all four markers must be visible and steady
across three scans. The markers remain visible to track movement of the setup.
Preferences are saved locally, but corner calibration is measured again each
session and after resizing. **Recheck corners** starts a fresh
scan. Corner markers hide behind menus and dialogs while their alignment is held.

Keep the camera close to the projector when using corner markers. Corner detection
aligns to the flat screen: for hands in front of it, use **Align hands** instead.
A camera aimed away from the projection cannot
detect its borders. Good focus and contrast help; if the projected markers are
too small in the camera image, move closer or try `--processing-width 960`.

Briefly covered markers retain the last alignment for up to 2.5 seconds. If they
stay hidden, the status changes and manual mapping resumes. A mapping change
cancels any held pinch; open the hand before pinching again. Hands outside a
calibrated projection cannot click its edges. Manual mapping uses the existing
camera crop and `--reach` margin.

The whiteboard stores its drawing in the app's local Qt profile using
`localStorage`, with a bounded save size. Export a PNG to keep a separate copy.

## Troubleshooting

- **Missing desktop runtime:** `sudo apt install python3-pyqt5.qtwebengine python3-pyqt5.qtwebchannel`.
  The launcher uses `/usr/bin/python3` to see Ubuntu's Qt packages, separately from the
  MediaPipe environment. Set `WAVEBOARD_DESKTOP_PYTHON` only if using another Python
  with the Qt bindings installed.
- **No hand skeleton:** run `bash gesture-lab/setup.sh`, close other camera apps, and
  reopen WaveBoard. Camera diagnostics are written to `/tmp/waveboard-hands.log`.
- **Slow or intermittent hands:** compare **Hand updates** and **AI detection** in
  Settings. Keep the default one-hand mode for one presenter. See
  [tracking speed and accuracy](gesture-lab/README.md#tracking-speed-and-accuracy)
  for capture, image-size, and lighting checks.
- **Slides unavailable:** install `libreoffice-impress` and `poppler-utils`. Conversion
  happens on the Jetson. PowerPoint animations are rendered as static slides.
- **Browser profile:** the desktop app keeps its own persistent Qt profile under the
  user's Qt application-data directory. Drawings from the former browser launcher
  do not automatically transfer; export them as PNG from that browser if needed.

## Development and verification

```bash
python3 -m unittest discover -s tests -v
# Legacy bridge tests need: python3 -m pip install 'websockets>=14,<18'
(cd gesture-lab && python3 -m unittest discover -s tests -v)
node tests/hand-input.test.mjs
node tests/hand-rendering.test.mjs
node tests/hold-gestures.test.mjs
node tests/projection.test.mjs
# With the desktop Qt Python environment and an active display:
python3 tests/check_hand_ui.py
python3 tests/check_desktop_actions.py
```

Tests cover direct local operations, path confinement, duplicate/failed imports,
presentation conversion, gesture continuity, camera-rate motion with a deliberately
slow detector, and the retained legacy HTTP helpers. Optical-flow image tests need
the tracker environment's OpenCV and NumPy. The Qt checks exercise hand-operated
controls, real exports/imports, rendered 3D zoom and closing the application using
isolated temporary files. The default app does
not use those HTTP helpers or `gesture-lab/server.py`; they remain for existing
integration tests and older development integrations.

Desktop startup and the local bridge have been tested on a Linux desktop. Jetson
camera capture, GPU acceleration, projector output, and device-specific video codecs
still require verification on the target hardware.

## Project structure

```text
waveboard/desktop.py      Native Qt window, resource loader, local bridge, camera lifecycle
waveboard/local.py        Direct file and presentation operations without sockets
waveboard/server.py       Shared file/conversion services and legacy HTTP adapter
waveboard/__main__.py     python -m waveboard desktop entry point
web/                     Bundled projector interface and offline 3D libraries
scripts/install-jetson.sh One-time Jetson setup
scripts/install-desktop.py User Applications-menu launcher installation
scripts/start-ubuntu.sh   Desktop launcher
gesture-lab/tracker.py   MediaPipe camera worker, JSON over stdout
gesture-lab/tracker_motion.py Checked optical flow between model observations
```

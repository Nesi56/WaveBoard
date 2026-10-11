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
   Swipe an open palm to browse Home cards or slides.
4. Pinch the top tab to open the menu. Its buttons, dialogs, file locations,
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

Home shows one large card at a time: **Draw**, **3D**, **Files**, **Video**, or **Slides**. Tap the left or right arrow to browse, then tap the card to open it. Keyboard arrow keys also browse the cards.

The tab at the top opens the menu. It contains **Home**, the current utility's extra tools, fullscreen, help, and settings. Controls highlight under the hand cursor. On the drawing board, only the color palette and three brush-size dots stay visible; pen, marker, eraser, undo/redo, save, and clear are in the top menu. Clearing a board can be undone.

The other utilities keep their main content large. **3D** has one Open button, with view options in the top menu. **Files** uses large rows and a Location chooser; import, search, and refresh are in the menu. **Video** has large play/pause and seek controls, with mute in the menu. **Slides** has large previous/next buttons and a slide counter, with Present in the menu.

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

### Hand mirroring and projection alignment

**Settings → Mirror hands** reverses the skeleton, cursor, and horizontal gestures
together. It is on by default for a camera facing the projection. Turn it off if
your camera setup moves the overlay in the wrong direction.

Enable **Settings → Align to projection borders** to show four black-and-white
corner markers. The camera detects their identities and maps the hand positions
to the projected area, correcting position, scale, perspective, and orientation.
Wait for **Aligned to projection**; all four markers must be visible and steady
across three scans. The markers remain visible to track movement of the setup.
Automatic alignment determines orientation itself; the mirror switch applies to
manual alignment. Preferences are saved locally, but calibration is measured
again each session and after resizing. **Recheck corners** starts a fresh scan.

Keep the camera close to the projector and hands close to the projection surface.
This is alignment to a flat screen, not depth sensing: hands far in front of the
screen can still appear offset. A camera aimed away from the projection cannot
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

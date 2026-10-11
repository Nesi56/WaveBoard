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
3. Hold up a hand. Pinch thumb and index to tap; hold a pinch and move to drag.
   Swipe an open palm to browse Home cards or slides.
4. Close with **Alt+F4** or **Ctrl+Q**. **F11** toggles the full screen window.

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

Point the camera toward the presenter at chest height, with even lighting and the
whole hand in view. See [hand tracking](gesture-lab/README.md) for tuning.

## Projector controls

Home shows one large card at a time: **Draw**, **3D**, **Files**, **Video**, or **Slides**. Tap the left or right arrow to browse, then tap the card to open it. Keyboard arrow keys also browse the cards.

The tab at the top opens the menu. It contains **Home**, the current utility's extra tools, fullscreen, help, and settings. On the drawing board, only the color palette and three brush-size dots stay visible; pen, marker, eraser, undo/redo, save, and clear are in the top menu. Clearing a board can be undone.

The other utilities keep their main content large. **3D** has one Open button, with view options in the top menu. **Files** uses large rows and a Location chooser; import, search, and refresh are in the menu. **Video** has large play/pause and seek controls, with mute in the menu. **Slides** has large previous/next buttons and a slide counter, with Present in the menu.

## Utilities

| Utility | Available interactions |
| --- | --- |
| 3D space | Open a model, drag to orbit, zoom, reset the view, and inspect a built-in sample. |
| Whiteboard | Draw with a pen or highlighter, erase, undo/redo, clear, and export a PNG. |
| Files | Browse this device, mounted USB drives on Ubuntu, and bundled demo files; open supported files in their viewer. |
| Video player | Open local videos, play/pause, seek, mute/unmute, and use fullscreen. |
| Presentations | Open PowerPoint or PDF files and navigate rendered slides. |

Tap opens controls and items; press and hold exposes details where offered. Drawing and 3D orbiting use a held pointer while moving. With hand tracking, a pinch is the tap and a held pinch is the held pointer. There is no projector calibration: the camera view is mapped onto the screen with a fixed edge margin.

The whiteboard stores its drawing in the current browser profile using `localStorage`, with a bounded save size. Export a PNG to keep a separate copy. Browser storage is specific to the browser profile and site address: the kiosk profile and your normal desktop browser have separate drawings, as do different ports.

## Troubleshooting

- **Missing desktop runtime:** `sudo apt install python3-pyqt5.qtwebengine python3-pyqt5.qtwebchannel`.
  The launcher uses `/usr/bin/python3` to see Ubuntu's Qt packages, separately from the
  MediaPipe environment. Set `WAVEBOARD_DESKTOP_PYTHON` only if using another Python
  with the Qt bindings installed.
- **No hand skeleton:** run `bash gesture-lab/setup.sh`, close other camera apps, and
  reopen WaveBoard. Camera diagnostics are written to `/tmp/waveboard-hands.log`.
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
```

Tests cover direct local operations, path confinement, duplicate/failed imports,
presentation conversion, and the retained legacy HTTP helpers. The default app does
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
```

# WaveBoard

An all-in-one portable projector for teaching where there is no smartboard: an
NVIDIA Jetson running Ubuntu, a webcam and a projector. Presenters control it
with their hands, with no headset or touch surface needed. Everything runs on the
device without an internet connection.

The repository has two parts that work together:

- **The workspace** (`waveboard/`, `web/`): a touch-friendly projector interface
  with Draw, 3D, Files, Video and Slides (PowerPoint and PDF). It is designed
  around a 480p projector: large controls, short labels, and one task on screen
  at a time. Python serves the machine's files and presentation conversions; a
  local browser displays the menu and utilities.
- **Hand tracking** (`gesture-lab/`): MediaPipe tracks two hands from the webcam
  and the workspace draws them as skeletons over whatever is on screen. Pinch to
  tap and drag, swipe an open palm to change cards and slides. The camera image is
  never shown. See [gesture-lab/README.md](gesture-lab/README.md).

## Quick start on the Jetson

```bash
sudo apt install python3 libreoffice-impress poppler-utils
cd ~/WaveBoard/gesture-lab
source ~/vision-env/bin/activate   # the Python environment with MediaPipe and OpenCV
bash setup.sh                      # adds websockets and the hand model
cd ~/WaveBoard
bash scripts/start-ubuntu.sh --hands
```

The launcher opens the workspace in a Chromium kiosk window and starts hand
tracking alongside it. Add `--firefox` to use Firefox instead (see
[Using Firefox](#using-firefox)). Leave out `--hands` for mouse and touch only.

## Controlling the workspace with your hands

Stand facing the camera with your hands in view. Each hand appears as a skeleton
over the workspace, in its green-on-paper colours (a second hand is drawn lighter),
and a round cursor sits between the thumb and index fingertips of the main hand.

| Gesture | Works like |
| --- | --- |
| Hand in view | Skeleton on screen; moves the cursor |
| Quick thumb + index pinch | A tap: open a card, press a button, pick a colour |
| Pinch, move, release | Touch and drag: draw on the board, orbit a 3D model |
| Open palm swiped left / right | Arrow keys: next / previous Home card or slide |

Small wobbles during a pinch are ignored so that taps land where you aimed;
move further and the pinch becomes a drag. The tracker ignores a band around
the camera's edges (`--reach`, default 12%) so the cursor can reach the screen
edges without your hand leaving the camera's view. For the most accurate tracking
(camera placement, light, standing farther back) see
[gesture-lab/README.md](gesture-lab/README.md#getting-the-most-accurate-tracking).

To run the two halves by hand instead of with the launcher, start
`python3 -m waveboard` in one terminal and `python gesture-lab/server.py` (in
`vision-env`) in another, then open http://127.0.0.1:8765. Ports: the workspace
uses **8765** and the hand-tracking stream **8766**, both on loopback only. If you move the workspace to another port, start the
tracker with `--allow-origin http://127.0.0.1:PORT` (the launcher does this for you).

Hand input reaches the page as synthetic pointer events, which browsers do not
treat as a real user gesture. **Full screen** and **Present** therefore need the
kiosk window (already full screen), F11, or a mouse click; native video controls and
drop-down menus need a mouse, as described in
[Connecting other trackers](#connecting-other-trackers).

## Preview on this computer

From the project directory, start the server:

```powershell
python -m waveboard
```

Open **[http://127.0.0.1:8765](http://127.0.0.1:8765)** in Chrome, Edge, Chromium, or Firefox. Leave the terminal running; use `Ctrl+C` to stop the server. This also works on Ubuntu using `python3 -m waveboard`.

The Python server uses only the standard library. The browser's 3D libraries are included in `web/vendor`, so no Node installation, package build, CDN, or internet connection is required to run the workspace after setup. Python 3.10 or newer is recommended.

For a quick tour, use the Home arrows to find **Files**, tap its card, then choose **Location → Demo files**. The repository includes `welcome.pdf`, `waveboard-demo.webm`, and `wave-sculpture.glb` / `wave-sculpture.obj` to try the presentation, video, and model viewers.

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

## Install on Ubuntu / Jetson

Install the Python runtime and the optional presentation tools:

```bash
sudo apt update
sudo apt install python3 libreoffice-impress poppler-utils
```

Install a Chromium browser using the package method supported by your Ubuntu/JetPack distribution, or Firefox (see [Using Firefox](#using-firefox)). The launcher looks for `chromium`, `chromium-browser`, `google-chrome`, then `firefox`; `--firefox` picks Firefox first, and `WAVEBOARD_BROWSER=/path/to/browser` picks a specific binary. Keep the Jetson's graphics drivers and browser hardware acceleration enabled for the 3D space.

To run in a normal browser tab:

```bash
cd /path/to/WaveBoard
python3 -m waveboard
```

To launch the projector interface in kiosk mode:

```bash
cd /path/to/WaveBoard
bash scripts/start-ubuntu.sh            # add --hands for camera hand control
```

The launcher starts its own server, waits for it to respond, then opens a kiosk window. It keeps a separate browser profile under `${XDG_CACHE_HOME:-$HOME/.cache}/waveboard/` (`chromium-profile` or `firefox-profile`) and server output in the adjacent `server.log`. A snap browser cannot use that hidden folder, so for a snap the profile goes in `~/snap/<name>/common/waveboard-profile` instead. With `--hands` it also starts `gesture-lab/server.py` using `WAVEBOARD_HANDS_PYTHON` (default `~/vision-env/bin/python`) and logs to `hands.log` in the same folder. Close the kiosk with `Alt+F4`; the launcher then stops the server and tracker it started. It does not terminate other Python services or browser processes, install an autostart entry, or change system settings.

An optional desktop-launcher template is provided at [`scripts/waveboard.desktop.example`](scripts/waveboard.desktop.example). Edit its two absolute paths before installing it manually through your desktop environment. Nothing is installed automatically.

### Using Firefox

```bash
bash scripts/start-ubuntu.sh --firefox --hands
```

Firefox runs as its own kiosk instance with a separate profile, so it does not touch
the Firefox you use day to day, and closing the kiosk (`Alt+F4`) stops WaveBoard. Before
each launch the script writes a `user.js` into that profile that turns off welcome,
default-browser and privacy pages, session restore and the fullscreen warning, lets
videos start from hand input, and keeps the hand cursor's connection retrying quickly.
It also sets `MOZ_USE_XINPUT2=1` so a touchscreen sends real touch input on the
Jetson's X11 desktop.

On a Jetson, install Firefox from Mozilla's APT repository rather than the snap that
Ubuntu 22.04 provides. On JetPack 6, snap browsers have been reported to fail to start
after snapd updates, and they cannot use the Jetson's GPU libraries, so they render in
software. Mozilla publishes arm64 builds from Firefox 136 on:

```bash
sudo install -d -m 0755 /etc/apt/keyrings
wget -q https://packages.mozilla.org/apt/repo-signing-key.gpg -O- | sudo tee /etc/apt/keyrings/packages.mozilla.org.asc >/dev/null
echo "deb [signed-by=/etc/apt/keyrings/packages.mozilla.org.asc] https://packages.mozilla.org/apt mozilla main" | sudo tee /etc/apt/sources.list.d/mozilla.list >/dev/null
printf 'Package: *\nPin: origin packages.mozilla.org\nPin-Priority: 1000\n' | sudo tee /etc/apt/preferences.d/mozilla >/dev/null
sudo apt-get update && sudo apt-get install firefox
apt-cache policy firefox   # the installed version should come from packages.mozilla.org
```

If the snap is still installed (`snap list firefox`), remove it with `sudo snap remove firefox`
first. The launcher still works with a snap Firefox, and prints a note when it finds one.

Firefox differences to know about:

- **H.264 video (.mp4):** Firefox plays it through the system FFmpeg. If MP4 files show
  "Cannot play this video", run `sudo apt install libavcodec58`; the launcher prints this
  hint when the library is missing. WebM always works. Firefox decodes video on the CPU on
  a Jetson, so prefer 1080p or lower.
- **MKV files** do not play in Firefox; convert them to MP4 or WebM.
- **3D:** if the 3D studio says graphics are unavailable, open `about:support` in a normal
  Firefox window and check that WebGL 2 is enabled with the NVIDIA Tegra renderer.
- Like Chromium, Firefox only opens the file picker and goes full screen from a real
  mouse, touch or key press, not from hand input; the kiosk window is already full screen.

Hand control, drawing, Home cards and slides were tested end to end in Firefox 136 with
the same checks as Chromium, and the launcher was run with a real Firefox.

## File locations and server options

By default, **This device** opens the current user's home directory. Mounted USB drives are discovered on Ubuntu beneath common locations such as `/media/<user>`, `/run/media/<user>`, `/media`, and `/mnt`. Use the desktop or operating system to mount and safely eject a drive; WaveBoard browses drives that are already mounted. Bundled **Demo files** are a separate location.

Use `--root` to replace the default home/USB locations with selected folders; repeat it to expose multiple folders. The demo location remains available.

```bash
python3 -m waveboard --root "$HOME/Documents" --root /media/yourname/USB
```

The server's command-line options are:

```text
python3 -m waveboard [--host 127.0.0.1] [--port 8765] [--root DIRECTORY]...
```

The kiosk launcher accepts repeated `--root` arguments. Set its port through `WAVEBOARD_PORT`:

```bash
WAVEBOARD_PORT=8770 bash scripts/start-ubuntu.sh --root "$HOME/Documents"
```

Keep the default loopback host for the standalone projector. The server provides access to local files and is intended to run on the same machine as the browser, without a network-facing login system.

## Supported formats and practical limits

**3D:** GLB, OBJ, and STL are supported as single-file imports. Use a GLB with embedded textures and buffers when you need a textured model. Separate OBJ material/texture files and externally referenced model assets are not loaded. Compressed glTF extensions that need additional decoders are not supported. Rendering depends on the Jetson's browser/WebGL support and the size of the model; start with lightweight models.

**Video:** MP4 with H.264 video and WebM are useful starting formats, but the exact video/audio codecs supported depend on the browser and operating-system build. A `.mp4` extension alone does not guarantee playback. Try a representative file on the actual Jetson before using it in a session. See [MDN's media container and codec guide](https://developer.mozilla.org/en-US/docs/Web/Media/Guides/Formats/Containers).

**PowerPoint and PDF:** PPTX/PPT files are converted by LibreOffice to PDF; Poppler renders the pages for slide navigation. PDF files use Poppler directly. Slides are static images: PowerPoint animations, transitions, embedded videos, interactive objects, and presenter notes are not played. Fonts and layout can differ from Microsoft PowerPoint; install the presentation's fonts on the Jetson and review the rendered slides. Conversion is limited to 250 MB per presentation and up to 200 rendered pages. See [LibreOffice's command-line parameter documentation](https://help.libreoffice.org/latest/en-GB/text/shared/guide/start_parameters.html).

On Windows, the menu, file browser, whiteboard, 3D space, and supported videos can be previewed with Python and a browser. Presentation conversion additionally requires the LibreOffice (`libreoffice` or `soffice`) and Poppler (`pdftoppm`) executables on `PATH`. Without those tools the app reports that conversion is unavailable; installing the Ubuntu dependencies on the Jetson enables that feature there.

## Connecting other trackers

Hand tracking from `gesture-lab/` is already connected: `web/hands.js` receives
the tracker's pointer over a local WebSocket (`ws://127.0.0.1:8766`, or the port in
the page's `?hands-port=` parameter) and calls the bridge below. Another tracker
can use the same bridge, or emit OS input instead.

The simplest integration is for the tracking process to emit normal OS mouse or touch input. Map a finger touching the projected surface to pointer-down, movement to pointer-move, and lifting the finger to pointer-up. Calibrate camera/projector coordinates into screen coordinates in the tracking process. A held touch should continue the same pointer rather than repeatedly clicking.

The app also implements a small browser bridge for connecting the tracker. The available page IDs are `home`, `whiteboard`, `models`, `files`, `video`, and `slides`:

```javascript
window.WaveBoardInput.navigate('whiteboard');
window.WaveBoardInput.pointer({ type: 'down', x: 600, y: 350, pointerId: 1 });
window.WaveBoardInput.pointer({ type: 'move', x: 650, y: 390, pointerId: 1 });
window.WaveBoardInput.pointer({ type: 'up', x: 650, y: 390, pointerId: 1 });
// Use type: 'cancel' if the tracker loses the active finger.
```

Coordinates are viewport/client coordinates in CSS pixels, measured from the visible browser content's top-left corner. Convert camera coordinates into this space without multiplying by the device pixel ratio. Use a consistent `pointerId` throughout one contact; use `1` for the primary finger.

The synthetic bridge supports drawing on the canvas, 3D interactions, buttons, and checkboxes. Use OS mouse/touch input for native media controls, select menus, and text interactions.

## Verification

Run the Python backend checks from the project directory, and the hand-tracking
checks from `gesture-lab/` in the environment with MediaPipe and OpenCV:

```bash
python -m unittest discover -s tests -v
cd gesture-lab && python -m unittest discover -s tests -v
```

Hand control of the workspace was checked end to end in headless Chromium and
Firefox 136: synthetic hands went through the real tracker bridge and `web/hands.js`
into this interface. A pinch-tap changed Home cards and opened the board, a pinch-drag
drew a stroke, open-palm swipes changed cards and slides, and the cursor hid when the
hand left. Separately, a recorded photo of two hands went through the real tracker
(MediaPipe) to the workspace, which drew both skeletons on Home, the whiteboard and
slides. The kiosk launcher with `--hands` was run with a stand-in browser: it started
both servers, the bridge accepted the page and refused another origin, and both
servers stopped afterwards. Live camera tracking still needs testing on the Jetson.

The bundled demo PDF, WebM video, and GLB/OBJ models have been exercised in the Windows browser preview. Real PDF rendering through Poppler has also been verified on Windows. LibreOffice is unavailable in this development environment, so real PPT/PPTX conversion still needs verification on the target machine. The Ubuntu launcher has passed Bash syntax checking; kiosk operation, USB mounting, graphics performance, and video codecs need a run on the actual Jetson.

## Project structure

```text
waveboard/server.py       Local HTTP server, file access, video ranges, slide conversion
waveboard/__main__.py     python -m waveboard entry point
web/index.html           Application shell
web/app.js               Navigation, utilities, and input integration
web/hands.js             Hand skeletons and cursor: tracker pointer -> WaveBoardInput
web/styles.css           480p projector layout and large touch controls
web/projector.js         Home carousel and minimal drawing workspace
web/whiteboard.js         Drawing, history, persistence, and PNG export
web/viewer3d.js           Local 3D viewer
web/vendor/              Offline Three.js modules and license notices
web/assets/demo/         Bundled examples
scripts/start-ubuntu.sh  Local-server and Chromium kiosk launcher (--hands adds tracking)
gesture-lab/             Hand tracking: camera, MediaPipe, pointer, skeletons
```

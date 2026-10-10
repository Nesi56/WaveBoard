# WaveBoard

A touch-friendly projector workspace for an NVIDIA Jetson running Ubuntu. The interface is designed around a 480p projector: large controls, short labels, and one task on screen at a time. Python serves the machine's files and presentation conversions; a local browser displays the menu and utilities. A mouse works for development, and the interface accepts ordinary touch and pointer events for later finger-tracking integration.

## Preview on this computer

From the project directory, start the server:

```powershell
python -m waveboard
```

Open **[http://127.0.0.1:8765](http://127.0.0.1:8765)** in Chrome, Edge, or Chromium. Leave the terminal running; use `Ctrl+C` to stop the server. This also works on Ubuntu using `python3 -m waveboard`.

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

Tap opens controls and items; press and hold exposes details where offered. Drawing and 3D orbiting use a held pointer while moving. There is no camera, finger tracking, gesture recognition, or projector calibration in this repository.

The whiteboard stores its drawing in the current browser profile using `localStorage`, with a bounded save size. Export a PNG to keep a separate copy. Browser storage is specific to the browser profile and site address: the kiosk profile and your normal desktop browser have separate drawings, as do different ports.

## Install on Ubuntu / Jetson

Install the Python runtime and the optional presentation tools:

```bash
sudo apt update
sudo apt install python3 libreoffice-impress poppler-utils
```

Install a Chromium browser using the package method supported by your Ubuntu/JetPack distribution. The launcher looks for `chromium`, `chromium-browser`, then `google-chrome`. Keep the Jetson's graphics drivers and browser hardware acceleration enabled for the 3D space.

To run in a normal browser tab:

```bash
cd /path/to/WaveBoard
python3 -m waveboard
```

To launch the projector interface in kiosk mode:

```bash
cd /path/to/WaveBoard
bash scripts/start-ubuntu.sh
```

The launcher starts its own server, waits for it to respond, then opens a Chromium kiosk window. It keeps a separate browser profile under `${XDG_CACHE_HOME:-$HOME/.cache}/waveboard/chromium-profile` and server output in the adjacent `server.log`. Close the kiosk with `Alt+F4`; the launcher then stops the server it started. It does not terminate other Python services or browser processes, install an autostart entry, or change system settings.

An optional desktop-launcher template is provided at [`scripts/waveboard.desktop.example`](scripts/waveboard.desktop.example). Edit its two absolute paths before installing it manually through your desktop environment. Nothing is installed automatically.

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

## Connecting finger tracking later

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

The synthetic bridge supports drawing on the canvas, 3D interactions, buttons, and checkboxes. Use OS mouse/touch input for native media controls, select menus, and text interactions. The tracker-to-browser transport and coordinate calibration remain separate integration work; this app does not yet receive tracking data from a camera or a Python tracking process.

## Verification

Run the Python backend checks from the project directory:

```bash
python -m unittest discover -s tests -v
```

The bundled demo PDF, WebM video, and GLB/OBJ models have been exercised in the Windows browser preview. Real PDF rendering through Poppler has also been verified on Windows. LibreOffice is unavailable in this development environment, so real PPT/PPTX conversion still needs verification on the target machine. The Ubuntu launcher has passed Bash syntax checking; kiosk operation, USB mounting, graphics performance, and video codecs need a run on the actual Jetson.

## Project structure

```text
waveboard/server.py       Local HTTP server, file access, video ranges, slide conversion
waveboard/__main__.py     python -m waveboard entry point
web/index.html           Application shell
web/app.js               Navigation, utilities, and input integration
web/styles.css           480p projector layout and large touch controls
web/projector.js         Home carousel and minimal drawing workspace
web/whiteboard.js         Drawing, history, persistence, and PNG export
web/viewer3d.js           Local 3D viewer
web/vendor/              Offline Three.js modules and license notices
web/assets/demo/         Bundled examples
scripts/start-ubuntu.sh  Local-server and Chromium kiosk launcher
```

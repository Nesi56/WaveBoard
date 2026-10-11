"""Jetson desktop window with a socket-free local resource and camera bridge."""
import argparse
import json
import mimetypes
import os
from pathlib import Path
import shlex
import sys
import tempfile

from .local import LocalWorkspace
from .hand_stream import HandPacketStream
from .server import APIError, MIME_OVERRIDES, PROJECT_DIR, WaveBoardApp


def main():
    parser = argparse.ArgumentParser(description="WaveBoard local desktop app")
    parser.add_argument("--no-hands", action="store_true", help="Use mouse and touch only")
    parser.add_argument("--windowed", action="store_true")
    parser.add_argument("--root", action="append", type=Path, help="Restrict the file browser to this folder")
    args = parser.parse_args()
    try:
        from PyQt5.QtCore import QEvent, QFile, QIODevice, QObject, QProcess, QStandardPaths, Qt, QUrl, pyqtSignal, pyqtSlot
        from PyQt5.QtGui import QIcon, QKeySequence
        from PyQt5.QtWidgets import QApplication, QFileDialog, QShortcut
        from PyQt5.QtWebChannel import QWebChannel
        from PyQt5.QtWebEngineCore import QWebEngineUrlRequestInterceptor, QWebEngineUrlRequestJob, QWebEngineUrlScheme, QWebEngineUrlSchemeHandler
        from PyQt5.QtWebEngineWidgets import QWebEnginePage, QWebEngineProfile, QWebEngineSettings, QWebEngineView
    except ImportError:
        print("Install the desktop runtime: sudo apt install python3-pyqt5.qtwebengine python3-pyqt5.qtwebchannel", file=sys.stderr)
        raise SystemExit(1)

    scheme = QWebEngineUrlScheme(b"waveboard")
    scheme.setSyntax(QWebEngineUrlScheme.Syntax.Host)
    scheme.setFlags(QWebEngineUrlScheme.SecureScheme | QWebEngineUrlScheme.CorsEnabled | QWebEngineUrlScheme.LocalAccessAllowed)
    QWebEngineUrlScheme.registerScheme(scheme)
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    application = QApplication(sys.argv[:1])
    application.setApplicationName("WaveBoard")
    application.setOrganizationName("WaveBoard")
    workspace = WaveBoardApp(roots=args.root)
    local = LocalWorkspace(workspace)

    class Resources(QWebEngineUrlSchemeHandler):
        def requestStarted(self, job):
            try:
                if bytes(job.requestMethod()) != b"GET":
                    raise APIError(403, "Read-only resource.")
                path = local.resource(job.requestUrl().toString())
                stream = QFile(str(path), job)
                if not path.is_file() or not stream.open(QIODevice.ReadOnly):
                    raise APIError(404, "File unavailable.")
                mime = MIME_OVERRIDES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                job.reply(mime.split(";")[0].encode(), stream)
            except (APIError, OSError, ValueError):
                job.fail(QWebEngineUrlRequestJob.UrlNotFound)

    class OfflineOnly(QWebEngineUrlRequestInterceptor):
        def interceptRequest(self, info):
            url = info.requestUrl()
            info.block(not (url.scheme() in {"blob", "data", "qrc"} or (url.scheme() == "waveboard" and url.host() == "app")))

    class Page(QWebEnginePage):
        selected = {}

        def chooseFiles(self, mode, old_files, accepted_types):
            # Keep the actual native selection; never trust a JS-supplied absolute path.
            paths, _ = QFileDialog.getOpenFileNames(view, "Open a file")
            self.selected = {Path(path).name: path for path in paths}
            return paths if mode == QWebEnginePage.FileSelectOpenMultiple else paths[:1]

        def acceptNavigationRequest(self, url, kind, main_frame):
            return not main_frame or (url.scheme() == "waveboard" and url.host() == "app" and url.path() in {"/", "/index.html"})

    view = QWebEngineView()
    view.setWindowTitle("WaveBoard")
    view.setWindowIcon(QIcon(str(workspace.web_dir / "assets/favicon.svg")))
    profile = QWebEngineProfile("waveboard-desktop", view)
    profile.setPersistentStoragePath(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) + "/browser")
    resources = Resources(profile)
    interceptor = OfflineOnly(profile)
    profile.installUrlSchemeHandler(b"waveboard", resources)
    profile.setUrlRequestInterceptor(interceptor)
    page = Page(profile, view)
    view.setPage(page)
    page.settings().setAttribute(QWebEngineSettings.FullScreenSupportEnabled, True)
    page.settings().setAttribute(QWebEngineSettings.PlaybackRequiresUserGesture, False)
    page.fullScreenRequested.connect(lambda request: (request.accept(), view.showFullScreen() if request.toggleOn() else view.showNormal()))

    class Bridge(QObject):
        hands = pyqtSignal(str)
        fullscreenChanged = pyqtSignal(bool)
        saved = pyqtSignal(str)

        @pyqtSlot(bool, result=bool)
        def setFullscreen(self, enabled):
            view.showFullScreen() if enabled else view.showNormal()
            return view.isFullScreen()

        @pyqtSlot(result=bool)
        def isFullscreen(self):
            return view.isFullScreen()

        @pyqtSlot()
        def quit(self):
            view.close()

        def eventFilter(self, watched, event):
            if watched is view and event.type() == QEvent.WindowStateChange:
                self.fullscreenChanged.emit(view.isFullScreen())
            return super().eventFilter(watched, event)

        @pyqtSlot()
        def startHands(self):
            if not args.no_hands and not self.started:
                self.started = True
                executable = os.environ.get("WAVEBOARD_HANDS_PYTHON", str(Path.home() / "vision-env/bin/python"))
                if Path(executable).is_file():
                    tracker.start(executable, ["-u", str(PROJECT_DIR / "gesture-lab/tracker.py"), *shlex.split(os.environ.get("WAVEBOARD_HANDS_ARGS", ""))])
                else:
                    self.hands.emit(json.dumps({"type": "status", "level": "error", "message": "Hand tracking needs setup. Run gesture-lab/setup.sh once, then reopen WaveBoard."}))

        started = False

        @pyqtSlot(str, result=str)
        def request(self, encoded):
            try:
                if len(encoded) > 32768:
                    raise APIError(413, "Local request is too large.")
                data = json.loads(encoded)
                if not isinstance(data, dict) or not isinstance(data.get("url"), str):
                    raise APIError(400, "Invalid local request.")
                if data.get("method", "GET") == "POST" and url_path(data["url"]) == "/api/upload":
                    query = parse_query(data["url"])
                    source = page.selected.pop(query.get("name", [""])[0], None)
                    if not source:
                        raise APIError(400, "Choose a file to import first.")
                    result = local.import_file(data["url"], source)
                else:
                    result = local.request(data["url"], data.get("method", "GET"), data.get("body"))
                return json.dumps({"result": result})
            except (APIError, ValueError, OSError) as exc:
                return json.dumps({"error": str(exc)})

    from urllib.parse import parse_qs, urlsplit
    def url_path(url):
        return urlsplit(url).path
    def parse_query(url):
        return parse_qs(urlsplit(url).query, keep_blank_values=True, max_num_fields=32)

    bridge = Bridge(view)
    view.installEventFilter(bridge)
    channel = QWebChannel(page)
    channel.registerObject("workspace", bridge)
    page.setWebChannel(channel)

    def download(item):
        # A hand-controlled session must not stop at an operating-system dialog.
        # Reserve a unique filename so repeated saves never replace earlier work.
        name = Path(item.suggestedFileName().replace("\\", "/")).name
        suffix = Path(name).suffix[:20]
        stem = Path(name).stem[:100] or "waveboard"
        kind = QStandardPaths.PicturesLocation if suffix.lower() == ".png" else QStandardPaths.DownloadLocation
        base = Path(QStandardPaths.writableLocation(kind) or str(Path.home()))
        if args.root:
            base = args.root[0].expanduser().resolve()
        directory = base / "WaveBoard"
        try:
            directory.mkdir(parents=True, exist_ok=True)
            descriptor, destination = tempfile.mkstemp(prefix=stem + "-", suffix=suffix, dir=directory)
            os.close(descriptor)
        except OSError:
            item.cancel()
            bridge.saved.emit("Could not save the file. Check the device's free space and folder permissions.")
            return
        def finished():
            if item.state() == item.DownloadCompleted:
                bridge.saved.emit("Saved to " + destination)
            else:
                Path(destination).unlink(missing_ok=True)
                bridge.saved.emit("The file could not be saved. Try again.")
        item.finished.connect(finished)
        item.setPath(destination)
        item.accept()
    profile.downloadRequested.connect(download)

    tracker = QProcess(view)
    hand_stream = HandPacketStream()
    closing = [False]
    def read_hands():
        for encoded in hand_stream.feed(bytes(tracker.readAllStandardOutput())):
            bridge.hands.emit(encoded)
    tracker.readyReadStandardOutput.connect(read_hands)
    tracker.setStandardErrorFile(QStandardPaths.writableLocation(QStandardPaths.TempLocation) + "/waveboard-hands.log")
    def tracker_error(*_):
        if not closing[0]:
            bridge.hands.emit(json.dumps({"type": "status", "level": "error", "message": "Hand tracking stopped. Check /tmp/waveboard-hands.log. Mouse and touch still work."}))
    tracker.errorOccurred.connect(tracker_error)
    tracker.finished.connect(lambda code, _: tracker_error() if code else None)

    def close():
        closing[0] = True
        if tracker.state() != QProcess.NotRunning:
            tracker.terminate()
            if not tracker.waitForFinished(3000):
                tracker.kill()
                tracker.waitForFinished(1000)
        workspace.close()
    application.aboutToQuit.connect(close)
    quit_shortcut = QShortcut(QKeySequence("Ctrl+Q"), view)
    quit_shortcut.activated.connect(view.close)
    fullscreen = QShortcut(QKeySequence("F11"), view)
    fullscreen.activated.connect(lambda: view.showNormal() if view.isFullScreen() else view.showFullScreen())
    view.resize(1024, 768)
    view.load(QUrl("waveboard://app/index.html"))
    view.showNormal() if args.windowed else view.showFullScreen()
    result = application.exec_()
    # The profile must outlive its page, including during interpreter shutdown.
    from PyQt5 import sip
    sip.delete(page)
    sip.delete(profile)
    raise SystemExit(result)

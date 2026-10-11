"""Jetson desktop window with a socket-free local resource and camera bridge."""
import argparse
import json
import mimetypes
import os
from pathlib import Path
import shlex
import sys

from .local import LocalWorkspace
from .server import APIError, MIME_OVERRIDES, PROJECT_DIR, WaveBoardApp


def main():
    parser = argparse.ArgumentParser(description="WaveBoard local desktop app")
    parser.add_argument("--no-hands", action="store_true", help="Use mouse and touch only")
    parser.add_argument("--windowed", action="store_true")
    parser.add_argument("--root", action="append", type=Path, help="Restrict the file browser to this folder")
    args = parser.parse_args()
    try:
        from PyQt5.QtCore import QFile, QIODevice, QObject, QProcess, QStandardPaths, Qt, QUrl, pyqtSignal, pyqtSlot
        from PyQt5.QtGui import QIcon, QKeySequence
        from PyQt5.QtWidgets import QApplication, QFileDialog, QMessageBox, QShortcut
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

        @pyqtSlot()
        def startHands(self):
            if not args.no_hands and not self.started:
                self.started = True
                executable = os.environ.get("WAVEBOARD_HANDS_PYTHON", str(Path.home() / "vision-env/bin/python"))
                if Path(executable).is_file():
                    tracker.start(executable, ["-u", str(PROJECT_DIR / "gesture-lab/tracker.py"), *shlex.split(os.environ.get("WAVEBOARD_HANDS_ARGS", ""))])
                else:
                    QMessageBox.information(view, "Hand tracking setup", "Run gesture-lab/setup.sh once to enable hand control. WaveBoard will open with mouse and touch.")

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
    channel = QWebChannel(page)
    channel.registerObject("workspace", bridge)
    page.setWebChannel(channel)

    def download(item):
        destination, _ = QFileDialog.getSaveFileName(view, "Save file", str(Path.home() / item.suggestedFileName()))
        if destination:
            item.setPath(destination)
            item.accept()
        else:
            item.cancel()
    profile.downloadRequested.connect(download)

    tracker = QProcess(view)
    pending = bytearray()
    closing = [False]
    def read_hands():
        pending.extend(bytes(tracker.readAllStandardOutput()))
        latest = None
        while b"\n" in pending:
            line, _, remainder = pending.partition(b"\n")
            pending[:] = remainder
            if len(line) > 65536:
                continue
            try:
                packet = json.loads(line)
                if isinstance(packet, dict) and packet.get("type") in {"frame", "status"}:
                    latest = line.decode()
            except (ValueError, UnicodeDecodeError):
                continue
        if len(pending) > 65536:
            pending.clear()
        if latest:
            bridge.hands.emit(latest)
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

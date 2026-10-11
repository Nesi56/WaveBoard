"""Verify real desktop save, import, rendered zoom, and hand-confirmed quit.

Run with the desktop Python environment: python tests/check_desktop_actions.py
Requires a desktop display and working Qt WebEngine WebGL. All browser data,
fixture files and exports live in a temporary directory and are removed.
"""
import json
import os
from pathlib import Path
import sys
import tempfile


def main():
    project = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(project))
    with tempfile.TemporaryDirectory(prefix="waveboard-actions-") as temporary:
        scratch = Path(temporary)
        os.environ["XDG_DATA_HOME"] = str(scratch / "data")
        os.environ["XDG_CACHE_HOME"] = str(scratch / "cache")
        from PyQt5.QtCore import QTimer
        from PyQt5.QtGui import QImage
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtWebEngineWidgets import QWebEngineView
        from waveboard.desktop import main as desktop_main

        root = scratch / "files"
        (root / "Source").mkdir(parents=True)
        (root / "Destination").mkdir()
        content = b"Lesson imported through the in-app hand picker.\n"
        (root / "Source/lesson-source.txt").write_bytes(content)
        original_exec = QApplication.exec_
        screenshots = {}
        final_result = {}
        armed_quit = [False]
        timed_out = [False]

        def run(application):
            view = next(widget for widget in application.topLevelWidgets() if isinstance(widget, QWebEngineView))

            def js(code, callback=None):
                view.page().runJavaScript(code, callback or (lambda _: None))

            def check(encoded):
                if encoded:
                    result = json.loads(encoded)
                    if result.get("error"):
                        final_result.update(result)
                        application.quit()
                        return
                    capture = result.get("capture")
                    if capture and capture not in screenshots:
                        image = view.grab().toImage()
                        ratio = image.devicePixelRatio()
                        bounds = result["captureBounds"]
                        screenshots[capture] = image.copy(*(round(bounds[key] * ratio) for key in ("x", "y", "width", "height")))
                        js("window.desktopCaptureAcknowledged = " + json.dumps(capture))
                    if result.get("readyToQuit"):
                        final_result.update(result)
                        armed_quit[0] = True
                        # The final action is the real confirmation button. Do
                        # not call application.quit on the successful path.
                        js("window.desktopQuitAcknowledged = true")
                        return
                QTimer.singleShot(100, poll)

            def poll():
                js("JSON.stringify(window.desktopActions)", check)

            def timeout():
                timed_out[0] = True
                application.quit()

            QTimer.singleShot(1600, lambda: js((project / "tests/desktop-actions.browser.js").read_text()))
            QTimer.singleShot(1800, poll)
            QTimer.singleShot(45000, timeout)
            return original_exec()

        QApplication.exec_ = run
        sys.argv = ["waveboard-actions-check", "--no-hands", "--windowed", "--root", str(root)]
        try:
            desktop_main()
        except SystemExit:
            pass

        try:
            if timed_out[0] or not armed_quit[0]:
                raise AssertionError(final_result.get("error") or "Native app did not close through the confirmed hand action")
            checks = final_result["checks"]
            exports = list((root / "WaveBoard").glob("*.png"))
            assert len(exports) == 2, "Expected two unique PNG exports"
            for path in exports:
                image = QImage(str(path))
                assert not image.isNull() and image.width() > 100 and image.height() > 100, "Export is not a readable PNG"
            checks.append("two unique PNG exports are readable images")
            assert (root / "Destination/lesson-source.txt").read_bytes() == content, "Imported bytes differ from source"
            checks.append("imported file bytes match the source")
            assert len(screenshots) == 3 and all(not image.isNull() for image in screenshots.values()), "Missing 3D screenshots"
            assert screenshots["before"] != screenshots["zoom_in"], "Zoom in did not change rendered model"
            assert screenshots["zoom_in"] != screenshots["zoom_out"], "Zoom out did not change rendered model"
            checks.append("Zoom in and Zoom out change the actual 3D canvas rendering")
            checks.append("confirmed hand action closes the native app")
            print(json.dumps({"checks": checks, "error": None}, indent=2), flush=True)
            return 0
        except (AssertionError, KeyError, OSError) as error:
            print(json.dumps({"checks": final_result.get("checks", []), "error": str(error)}, indent=2), flush=True)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Exercise real Qt controls with synthetic hand input, without a camera/server.

Run from any directory with the desktop Python environment:
    python tests/check_hand_ui.py
Requires a desktop display and PyQt5 QtWebEngine/QtWebChannel. All files and
browser storage are isolated in a temporary directory that is removed on exit.
"""
import json
import os
from pathlib import Path
import sys
import tempfile


def main():
    project = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(project))
    with tempfile.TemporaryDirectory(prefix="waveboard-hand-ui-") as temporary:
        scratch = Path(temporary)
        os.environ["XDG_DATA_HOME"] = str(scratch / "data")
        os.environ["XDG_CACHE_HOME"] = str(scratch / "cache")
        from PyQt5.QtCore import QTimer
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtWebEngineWidgets import QWebEngineView
        from waveboard.desktop import main as desktop_main

        root = scratch / "files"
        root.mkdir()
        for index in range(40):
            (root / f"lesson-{index:02}.txt").write_text("Classroom lesson file")
        original_exec = QApplication.exec_
        failed = [True]

        def run(application):
            def js(code, callback=None):
                view = next(widget for widget in application.topLevelWidgets() if isinstance(widget, QWebEngineView))
                view.page().runJavaScript(code, callback or (lambda _: None))

            def start():
                js((project / "tests/hand-ui.browser.js").read_text())

            def check(encoded):
                if encoded:
                    result = json.loads(encoded)
                    if result.get("done"):
                        print(json.dumps(result, indent=2), flush=True)
                        failed[0] = bool(result.get("error"))
                        application.quit()
                        return
                QTimer.singleShot(150, poll)

            def poll():
                js("JSON.stringify(window.handUIResults)", check)

            def timeout():
                print("Hand UI check timed out", file=sys.stderr)
                application.quit()

            QTimer.singleShot(1800, start)
            QTimer.singleShot(2000, poll)
            QTimer.singleShot(30000, timeout)
            return original_exec()

        QApplication.exec_ = run
        sys.argv = ["waveboard-hand-ui-check", "--no-hands", "--windowed", "--root", str(root)]
        try:
            desktop_main()
        except SystemExit:
            pass
        return 1 if failed[0] else 0


if __name__ == "__main__":
    raise SystemExit(main())

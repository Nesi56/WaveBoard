"""Install a user-owned launcher for this checkout; run on the target Jetson."""
import os
from pathlib import Path
import shlex

project = Path(__file__).resolve().parent.parent
data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
launcher = data / "waveboard/launch"
launcher.parent.mkdir(parents=True, exist_ok=True)
launcher.write_text("#!/bin/sh\nexec /bin/bash " + shlex.quote(str(project / "scripts/start-ubuntu.sh")) + ' "$@"\n')
launcher.chmod(0o755)

def desktop_quote(path):
    return '"' + str(path).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%') + '"'

entry = data / "applications/waveboard.desktop"
entry.parent.mkdir(parents=True, exist_ok=True)
entry.write_text("\n".join([
    "[Desktop Entry]", "Type=Application", "Name=WaveBoard",
    "Comment=Offline projector workspace with hand control",
    "Exec=" + desktop_quote(launcher),
    "Icon=" + str(project / "web/assets/favicon.svg"),
    "Terminal=false", "Categories=Education;Graphics;", "StartupNotify=true", "",
]))
print("Installed WaveBoard in the Applications menu. Keep this checkout in place.")

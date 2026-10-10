"""Reuse the drawing app's model or download Google's official hand model."""
from pathlib import Path
import shutil
import urllib.request
import zipfile

URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
target = Path(__file__).resolve().parent / "hand_landmarker.task"
old_model = Path.home() / "hand-drawing" / "hand_landmarker.task"

if not target.exists():
    temporary = target.with_suffix(".download")
    try:
        if old_model.is_file() and zipfile.is_zipfile(old_model):
            print("Reusing your hand-drawing model.")
            shutil.copyfile(old_model, temporary)
        else:
            print("Downloading the official MediaPipe hand model…")
            with urllib.request.urlopen(URL, timeout=60) as source, temporary.open("wb") as dest:
                shutil.copyfileobj(source, dest)
        if not zipfile.is_zipfile(temporary):
            raise RuntimeError("Model download was incomplete. Run setup.sh again.")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
if not zipfile.is_zipfile(target):
    raise SystemExit("hand_landmarker.task is not a valid model bundle. Rename it and rerun setup.sh.")
print("Hand model ready.")

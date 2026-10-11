#!/usr/bin/env bash
# Prepares hand tracking: a Python environment with MediaPipe, OpenCV and websockets,
# and the hand model. Uses the active virtual environment, otherwise ~/vision-env,
# which it creates when missing. scripts/start-ubuntu.sh --hands runs ~/vision-env.
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [ -n "${VIRTUAL_ENV:-}" ]; then
  python=python
else
  env_dir="$HOME/vision-env"
  python="$env_dir/bin/python"
  if ! "$python" -m pip --version >/dev/null 2>&1; then
    echo "Creating the Python environment $env_dir"
    if ! python3 -m venv "$env_dir"; then
      echo 'Install Python environment support first: sudo apt install python3-venv python3-pip'
      exit 1
    fi
  fi
fi
# Keep the hand-tracking libraries that already work on your Jetson.
if ! "$python" -c 'import cv2, mediapipe, numpy; from mediapipe.tasks.python import vision' 2>/dev/null; then
  echo 'Installing MediaPipe, which brings OpenCV and NumPy (a few minutes)…'
  "$python" -m pip install --upgrade pip
  "$python" -m pip install mediapipe
  "$python" -c 'import cv2, mediapipe, numpy; from mediapipe.tasks.python import vision'
fi
"$python" -m pip install 'websockets>=14,<18'
"$python" download_model.py
"$python" -m pip freeze > environment-working.txt
tracker_python="$("$python" -c 'import sys; print(sys.executable)')"
echo
echo 'Setup complete. From the WaveBoard folder start everything with:'
if [ "$tracker_python" = "$HOME/vision-env/bin/python" ]; then
  echo '  bash scripts/start-ubuntu.sh --hands'
else
  echo "  WAVEBOARD_HANDS_PYTHON=$tracker_python bash scripts/start-ubuntu.sh --hands"
fi

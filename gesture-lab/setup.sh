#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [ -z "${VIRTUAL_ENV:-}" ]; then
  echo 'First activate your working environment: source ~/vision-env/bin/activate'
  exit 1
fi
# Keep the hand-tracking libraries that already work on your Jetson.
if ! python -c 'import cv2, mediapipe, numpy; from mediapipe.tasks.python import vision'; then
  echo 'This environment does not have working OpenCV and MediaPipe.'
  echo 'Activate the environment used for your working draw.py and run this script again.'
  exit 1
fi
python -m pip install 'websockets>=14,<18'
python download_model.py
python -m pip freeze > environment-working.txt
echo 'Setup complete. From the WaveBoard folder start everything with: bash scripts/start-ubuntu.sh --hands'

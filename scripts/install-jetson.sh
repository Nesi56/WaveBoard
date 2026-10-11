#!/usr/bin/env bash
# One-time setup on JetPack 6 / Ubuntu 22.04. Run as your desktop user.
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
if [ "$(id -u)" -eq 0 ]; then
  echo 'Run this as your normal desktop user, without sudo; it asks for sudo when needed.' >&2
  exit 1
fi
sudo apt update
sudo apt install -y python3-pyqt5.qtwebengine python3-pyqt5.qtwebchannel python3-venv python3-pip libreoffice-impress poppler-utils
env -u VIRTUAL_ENV bash gesture-lab/setup.sh
/usr/bin/python3 scripts/install-desktop.py
echo 'Setup complete. Open WaveBoard from Applications. Internet is no longer needed.'

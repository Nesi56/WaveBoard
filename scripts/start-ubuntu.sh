#!/usr/bin/env bash
# Launch the local desktop app. No browser, HTTP server, or WebSocket server.
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
args=()
for arg in "$@"; do
  case "$arg" in
    --hands) ;; # Hand control is enabled by default.
    --firefox) ;; # Compatibility with old desktop shortcuts.
    *) args+=("$arg") ;;
  esac
done
exec "${WAVEBOARD_DESKTOP_PYTHON:-/usr/bin/python3}" -m waveboard "${args[@]}"

#!/usr/bin/env bash
# Start WaveBoard's local Python service and an isolated Chromium kiosk window.
set -Eeuo pipefail

waveboard_script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
waveboard_project_dir="$(cd -- "$waveboard_script_dir/.." && pwd)"
waveboard_port="${WAVEBOARD_PORT:-8765}"
waveboard_cache_dir="${XDG_CACHE_HOME:-$HOME/.cache}/waveboard"
waveboard_server_pid=""
waveboard_extra_args=()

usage() {
  printf 'Usage: bash scripts/start-ubuntu.sh [--root /path/to/files]...\n'
  printf 'Set WAVEBOARD_PORT to change the default local port (8765).\n'
}

while (($#)); do
  case "$1" in
    --root)
      if (($# < 2)) || [[ -z "$2" ]]; then
        usage >&2
        exit 2
      fi
      waveboard_extra_args+=(--root "$2")
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ! "$waveboard_port" =~ ^[0-9]{1,5}$ ]] || ((10#$waveboard_port < 1 || 10#$waveboard_port > 65535)); then
  printf 'WAVEBOARD_PORT must be a number from 1 to 65535.\n' >&2
  exit 2
fi
waveboard_port=$((10#$waveboard_port))

if ! command -v python3 >/dev/null 2>&1; then
  printf 'Python 3 is required. Install it with: sudo apt install python3\n' >&2
  exit 1
fi

waveboard_browser=""
for waveboard_candidate in chromium chromium-browser google-chrome; do
  if command -v "$waveboard_candidate" >/dev/null 2>&1; then
    waveboard_browser="$(command -v "$waveboard_candidate")"
    break
  fi
done
if [[ -z "$waveboard_browser" ]]; then
  printf 'Install Chromium or Google Chrome using your Ubuntu distribution packages, then try again.\n' >&2
  exit 1
fi

mkdir -p -- "$waveboard_cache_dir"
cd -- "$waveboard_project_dir"

# Avoid attaching the kiosk to an unrelated service already occupying this port.
python3 - "$waveboard_port" <<'PY'
import socket
import sys

try:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", int(sys.argv[1])))
except OSError as error:
    print(f"Cannot start WaveBoard on port {sys.argv[1]}: {error}", file=sys.stderr)
    print("Close the existing server or select another WAVEBOARD_PORT.", file=sys.stderr)
    raise SystemExit(1)
PY

waveboard_cleanup() {
  if [[ -n "$waveboard_server_pid" ]] && kill -0 "$waveboard_server_pid" 2>/dev/null; then
    kill "$waveboard_server_pid" 2>/dev/null || true
    wait "$waveboard_server_pid" 2>/dev/null || true
  fi
}
trap waveboard_cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

python3 -m waveboard --host 127.0.0.1 --port "$waveboard_port" "${waveboard_extra_args[@]}" >"$waveboard_cache_dir/server.log" 2>&1 &
waveboard_server_pid=$!
waveboard_url="http://127.0.0.1:$waveboard_port"

if ! python3 - "$waveboard_url/api/status" "$waveboard_server_pid" <<'PY'
import json
import os
import sys
import time
import urllib.request

endpoint, server_pid = sys.argv[1], int(sys.argv[2])
for attempt in range(80):
    try:
        os.kill(server_pid, 0)
    except ProcessLookupError:
        raise SystemExit(1)
    try:
        with urllib.request.urlopen(endpoint, timeout=0.4) as response:
            status = json.load(response)
            if response.status == 200 and "roots" in status and "version" in status:
                os.kill(server_pid, 0)
                raise SystemExit(0)
    except (OSError, ValueError):
        pass
    time.sleep(0.15)
raise SystemExit(1)
PY
then
  printf 'WaveBoard did not become ready. Check %s/server.log\n' "$waveboard_cache_dir" >&2
  exit 1
fi

printf 'WaveBoard is ready at %s\n' "$waveboard_url"
printf 'Close the kiosk window (Alt+F4) to stop this launcher and its local server.\n'
"$waveboard_browser" \
  --kiosk \
  --no-first-run \
  --no-default-browser-check \
  --user-data-dir="$waveboard_cache_dir/chromium-profile" \
  "$waveboard_url"

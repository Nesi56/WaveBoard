#!/usr/bin/env bash
# Start WaveBoard's local Python service and an isolated browser kiosk window
# (Chromium, Google Chrome or Firefox).
set -Eeuo pipefail

waveboard_script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
waveboard_project_dir="$(cd -- "$waveboard_script_dir/.." && pwd)"
waveboard_port="${WAVEBOARD_PORT:-8765}"
waveboard_cache_dir="${XDG_CACHE_HOME:-$HOME/.cache}/waveboard"
waveboard_server_pid=""
waveboard_hands=0
waveboard_hands_pid=""
waveboard_firefox=0
waveboard_extra_args=()

usage() {
  printf 'Usage: bash scripts/start-ubuntu.sh [--hands] [--firefox] [--root /path/to/files]...\n'
  printf 'Set WAVEBOARD_PORT to change the default local port (8765).\n'
  printf -- '--hands also starts camera hand control (gesture-lab/server.py) with\n'
  printf 'WAVEBOARD_HANDS_PYTHON, default ~/vision-env/bin/python. Pass tracker options in\n'
  printf 'WAVEBOARD_HANDS_ARGS, e.g. "--camera /dev/video2 --detection-confidence 0.35".\n'
  printf -- '--firefox uses Firefox instead of Chromium. WAVEBOARD_BROWSER=/path/to/browser\n'
  printf 'picks a specific Chromium-family or Firefox binary.\n'
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
    --hands)
      waveboard_hands=1
      shift
      ;;
    --firefox)
      waveboard_firefox=1
      shift
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

waveboard_find_browser() {
  local candidate
  for candidate in "$@"; do
    if command -v -- "$candidate" >/dev/null 2>&1; then
      command -v -- "$candidate"
      return 0
    fi
  done
  return 1
}

# Prints the snap's name when the browser is a snap: /snap/bin/NAME links to
# /usr/bin/snap, and Ubuntu 22.04's /usr/bin/firefox and /usr/bin/chromium-browser
# are small scripts that run /snap/bin/NAME.
waveboard_snap_name() {
  local real
  real="$(readlink -f -- "$1")"
  case "$real" in
    /usr/bin/snap|/snap/*)
      basename -- "$1"
      return 0
      ;;
  esac
  if [[ -f "$real" && "$(head -c 2 -- "$real" 2>/dev/null)" == '#!' ]]; then
    sed -n 's#.*/snap/bin/\([A-Za-z0-9-]*\).*#\1#p' -- "$real" | head -n 1 | grep .
    return
  fi
  return 1
}

if [[ -n "${WAVEBOARD_BROWSER:-}" ]]; then
  if ! waveboard_browser="$(waveboard_find_browser "$WAVEBOARD_BROWSER")"; then
    printf 'WAVEBOARD_BROWSER=%s was not found.\n' "$WAVEBOARD_BROWSER" >&2
    exit 1
  fi
elif ((waveboard_firefox)); then
  if ! waveboard_browser="$(waveboard_find_browser firefox firefox-esr)"; then
    printf 'Firefox was not found. Install it from Mozilla'"'"'s APT repository (see README.md), then try again.\n' >&2
    exit 1
  fi
elif ! waveboard_browser="$(waveboard_find_browser chromium chromium-browser google-chrome firefox firefox-esr)"; then
  printf 'Install Chromium, Google Chrome or Firefox, then try again.\n' >&2
  exit 1
fi
waveboard_browser_kind=chromium
if [[ "$(basename -- "$waveboard_browser")" == *firefox* ]]; then
  waveboard_browser_kind=firefox
fi
# A snap browser cannot use hidden folders such as ~/.cache, only its own ~/snap/NAME.
if waveboard_snap="$(waveboard_snap_name "$waveboard_browser")"; then
  waveboard_profile="$HOME/snap/$waveboard_snap/common/waveboard-profile"
else
  waveboard_snap=""
  waveboard_profile="$waveboard_cache_dir/$waveboard_browser_kind-profile"
fi

mkdir -p -- "$waveboard_cache_dir"
cd -- "$waveboard_project_dir"

# Avoid attaching the kiosk to an unrelated service already occupying this port on
# either localhost address.
python3 - "$waveboard_port" <<'PY'
import errno
import socket
import sys

for family, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
    try:
        with socket.socket(family) as listener:
            # Like the server: closed connections from the last run (TIME_WAIT) do not block
            # the port, while a program still listening on it does.
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind((host, int(sys.argv[1])))
    except OSError as error:
        if family == socket.AF_INET6 and error.errno not in {errno.EADDRINUSE, errno.EACCES}:
            continue  # no IPv6 on this computer
        print(f"Cannot start WaveBoard on localhost port {sys.argv[1]}: {error}", file=sys.stderr)
        print("Close the existing server or select another WAVEBOARD_PORT.", file=sys.stderr)
        raise SystemExit(1)
PY

# Rewritten on every launch: no welcome, default-browser or privacy pages, no session
# restore, quick WebSocket reconnects for the hand cursor, no fullscreen warning, and
# videos that may start from hand input.
waveboard_firefox_prefs() {
  cat <<'PREFS'
// Written by scripts/start-ubuntu.sh before every launch; edits here are replaced.
user_pref("browser.aboutwelcome.enabled", false);
user_pref("browser.preonboarding.enabled", false);
user_pref("browser.startup.homepage_override.mstone", "ignore");
user_pref("startup.homepage_welcome_url", "");
user_pref("startup.homepage_welcome_url.additional", "");
user_pref("startup.homepage_override_url", "");
user_pref("browser.startup.upgradeDialog.enabled", false);
user_pref("browser.shell.checkDefaultBrowser", false);
user_pref("datareporting.policy.dataSubmissionPolicyBypassNotification", true);
user_pref("datareporting.policy.dataSubmissionEnabled", false);
user_pref("datareporting.policy.firstRunURL", "");
user_pref("toolkit.telemetry.reportingpolicy.firstRun", false);
user_pref("termsofuse.bypassNotification", true);
user_pref("browser.sessionstore.resume_from_crash", false);
user_pref("toolkit.startup.max_resumed_crashes", -1);
user_pref("browser.warnOnQuit", false);
user_pref("browser.translations.automaticallyPopup", false);
user_pref("app.update.auto", false);
user_pref("network.websocket.delay-failed-reconnects", false);
user_pref("full-screen-api.warning.timeout", 0);
user_pref("full-screen-api.transition-duration.enter", "0 0");
user_pref("full-screen-api.transition-duration.leave", "0 0");
user_pref("media.autoplay.default", 0);
user_pref("media.autoplay.blocking_policy", 0);
user_pref("media.videocontrols.picture-in-picture.video-toggle.enabled", false);
PREFS
}

waveboard_cleanup() {
  local pid
  for pid in "$waveboard_hands_pid" "$waveboard_server_pid"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done
}
trap waveboard_cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

python3 -m waveboard --host localhost --port "$waveboard_port" "${waveboard_extra_args[@]}" >"$waveboard_cache_dir/server.log" 2>&1 &
waveboard_server_pid=$!
waveboard_url="http://localhost:$waveboard_port"

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

if ((waveboard_hands)); then
  waveboard_hands_python="${WAVEBOARD_HANDS_PYTHON:-$HOME/vision-env/bin/python}"
  if [[ ! -x "$waveboard_hands_python" ]]; then
    waveboard_hands_python="$(command -v python3)"
  fi
  read -r -a waveboard_hands_args <<<"${WAVEBOARD_HANDS_ARGS:-}"
  # Localhost only; --allow-origin lets a page on a WAVEBOARD_PORT other than 8765 connect.
  "$waveboard_hands_python" gesture-lab/server.py --allow-origin "$waveboard_url" \
    --allow-origin "http://127.0.0.1:$waveboard_port" "${waveboard_hands_args[@]}" \
    >"$waveboard_cache_dir/hands.log" 2>&1 &
  waveboard_hands_pid=$!
  printf 'Hand control is starting. If no cursor appears, check %s/hands.log\n' "$waveboard_cache_dir"
fi

mkdir -p -- "$waveboard_profile"
if [[ -n "$waveboard_snap" ]]; then
  printf 'Note: %s is a snap. On JetPack 6 snap browsers may fail to start and cannot use the GPU;\n' "$waveboard_snap"
  printf 'Firefox from Mozilla'"'"'s APT repository avoids both (see README.md).\n'
fi
printf 'Close the kiosk window (Alt+F4) to stop this launcher and its local server.\n'
if [[ "$waveboard_browser_kind" == firefox ]]; then
  waveboard_firefox_prefs >"$waveboard_profile/user.js"
  if [[ -z "$waveboard_snap" ]] && ! { ldconfig -p 2>/dev/null || /sbin/ldconfig -p 2>/dev/null; } | grep -q 'libavcodec\.so'; then
    printf 'Note: Firefox needs FFmpeg for H.264 (.mp4) videos: sudo apt install libavcodec58\n'
  fi
  # --new-instance and a separate profile keep this window apart from any open Firefox,
  # so the command blocks until the kiosk closes. MOZ_USE_XINPUT2 makes Firefox read
  # touchscreens as touch on X11, which JetPack's desktop uses.
  MOZ_USE_XINPUT2=1 "$waveboard_browser" \
    --kiosk \
    --new-instance \
    --no-remote \
    --profile "$waveboard_profile" \
    "$waveboard_url"
else
  "$waveboard_browser" \
    --kiosk \
    --no-first-run \
    --no-default-browser-check \
    --user-data-dir="$waveboard_profile" \
    "$waveboard_url"
fi

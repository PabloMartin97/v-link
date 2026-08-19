#!/usr/bin/env bash

# Atomic, headless updater for V-Link desktop and Lite installations.

set -Eeuo pipefail

readonly REPOSITORY="PabloMartin97/v-link"
readonly -a APP_ITEMS=(
    V-Link.py backend frontend resources requirements.txt Patch.sh Check-Lite.sh Update.sh venv
)
APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_PARENT="$(dirname -- "$APP_DIR")"
TRANSACTION_MARKER="$APP_PARENT/.v-link-update-active"
RECOVERY_HELPER="$APP_PARENT/.local/libexec/v-link-recover-update"
TEMP_DIR=""
BACKUP_DIR=""
KEEPALIVE_PID=""
SWAPPED=false
RECOVERY_PENDING=false
ERROR_LINE=""

log() {
    printf '[V-Link Update] %s\n' "$*"
}

rollback() {
    local item
    local rollback_failed=0
    [[ "$SWAPPED" == true && -d "$BACKUP_DIR" ]] || return 0

    log "Restoring the previous application and Python environment"
    for item in "${APP_ITEMS[@]}"; do
        if [[ -e "$BACKUP_DIR/$item" ]]; then
            rm -rf -- "$APP_DIR/$item" || rollback_failed=1
            mv "$BACKUP_DIR/$item" "$APP_DIR/$item" || rollback_failed=1
        elif [[ -e "$BACKUP_DIR/.new-$item" ]]; then
            rm -rf -- "$APP_DIR/$item" || rollback_failed=1
        fi
    done
    return "$rollback_failed"
}

finish() {
    local status=$?
    trap - EXIT ERR HUP INT TERM
    set +e

    if [[ -n "$KEEPALIVE_PID" ]]; then
        kill "$KEEPALIVE_PID" >/dev/null 2>&1 || true
        wait "$KEEPALIVE_PID" 2>/dev/null || true
    fi

    if ((status != 0)); then
        if [[ -n "$ERROR_LINE" ]]; then
            log "ERROR at line $ERROR_LINE (exit $status)"
        else
            log "ERROR (exit $status)"
        fi
        if [[ "$RECOVERY_PENDING" == true ]]; then
            log "RECOVERY INCOMPLETE; preserving the transaction marker and backup"
            TEMP_DIR=""
        elif rollback; then
            rm -f -- "$TRANSACTION_MARKER"
            flock -u 9 >/dev/null 2>&1 || true
            systemctl --user restart v-link.service >/dev/null 2>&1 || true
        else
            log "ROLLBACK FAILED; recovery files have been preserved at $BACKUP_DIR"
            TEMP_DIR=""
        fi
    fi

    if [[ -n "$TEMP_DIR" && -d "$TEMP_DIR" ]]; then
        rm -rf -- "$TEMP_DIR"
    fi

    exit "$status"
}

on_error() {
    ERROR_LINE="$1"
}

die() {
    log "ERROR: $*"
    return 1
}

command -v flock >/dev/null 2>&1 || die "the flock command is required"
exec 9>"$APP_PARENT/.v-link-update.lock"
flock -n 9 || die "another V-Link update is already running"

trap finish EXIT
trap 'on_error "$LINENO"' ERR
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ -e "$TRANSACTION_MARKER" ]]; then
    RECOVERY_PENDING=true
    [[ -x "$RECOVERY_HELPER" ]] || die "an interrupted update needs recovery, but the recovery helper is unavailable"
    "$RECOVERY_HELPER" --lock-held "$APP_DIR"
    RECOVERY_PENDING=false
fi

if [[ -d "$APP_DIR/.git" ]]; then
    die "refusing to replace a Git checkout; rerun Install-Lite.sh to deploy a separate kiosk runtime"
fi
if [[ -e "$APP_DIR/.v-link-lite-runtime" && ! -x "$RECOVERY_HELPER" ]]; then
    die "the Lite recovery helper is unavailable; rerun Install-Lite.sh before updating"
fi

serial_port() {
    local model
    model="$(tr -d '\0' </proc/device-tree/model 2>/dev/null || true)"
    case "$model" in
        *"Raspberry Pi 5"*) printf '%s\n' /dev/ttyAMA2 ;;
        *"Raspberry Pi 4"*) printf '%s\n' /dev/ttyAMA3 ;;
        *"Raspberry Pi 3"*) printf '%s\n' /dev/serial0 ;;
        *) return 1 ;;
    esac
}

start_rti_keepalive() {
    local port="$1"
    "$APP_DIR/venv/bin/python" - "$port" <<'PY' >/dev/null 2>&1 &
import serial
import sys
import time

while True:
    try:
        with serial.Serial(sys.argv[1], 2400, timeout=1) as connection:
            while True:
                connection.write(bytes([0x40, 0x20, 0x83]))
                time.sleep(1)
    except (OSError, serial.SerialException):
        time.sleep(1)
PY
    KEEPALIVE_PID=$!
}

log "Starting update"
TEMP_DIR="$(mktemp -d "$APP_PARENT/.v-link-update.XXXXXX")"
BACKUP_DIR="$TEMP_DIR/backup"
install -d "$BACKUP_DIR" "$TEMP_DIR/staging" "$TEMP_DIR/wheels"

if PORT="$(serial_port)" && [[ -e "$PORT" ]]; then
    start_rti_keepalive "$PORT"
fi

log "Resolving the latest GitHub release"
curl --fail --silent --show-error --location \
    --retry 3 --connect-timeout 10 --max-time 60 --speed-limit 1024 --speed-time 30 \
    "https://api.github.com/repos/$REPOSITORY/releases/latest" \
    --output "$TEMP_DIR/release.json"

RELEASE_URL="$("$APP_DIR/venv/bin/python" - "$TEMP_DIR/release.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as release_file:
    release = json.load(release_file)

for asset in release.get("assets", []):
    if asset.get("name") == "V-Link.zip":
        print(asset["browser_download_url"])
        break
PY
)"
if [[ -z "$RELEASE_URL" ]]; then
    die "latest release has no V-Link.zip asset"
fi

log "Downloading and validating the release"
curl --fail --show-error --location --retry 3 --connect-timeout 10 \
    --max-time 900 --speed-limit 1024 --speed-time 30 \
    "$RELEASE_URL" --output "$TEMP_DIR/V-Link.zip"
curl --fail --show-error --location --retry 3 --connect-timeout 10 \
    --max-time 120 --speed-limit 32 --speed-time 30 \
    "$RELEASE_URL.sha256" --output "$TEMP_DIR/V-Link.zip.sha256"
(cd "$TEMP_DIR" && sha256sum --check V-Link.zip.sha256)
ZIP_ENTRIES="$(unzip -Z1 "$TEMP_DIR/V-Link.zip")"
if grep -Eq '(^/|(^|/)\.\.(/|$))' <<<"$ZIP_ENTRIES"; then
    die "release archive contains an unsafe path"
fi
unzip -q "$TEMP_DIR/V-Link.zip" -d "$TEMP_DIR/staging"

for required in \
    V-Link.py backend/server.py frontend/dist/index.html requirements.txt Check-Lite.sh Update.sh \
    resources/dtoverlays/v-link.dtbo \
    resources/dtoverlays/mcp2515-can1.dtbo \
    resources/dtoverlays/mcp2515-can2.dtbo; do
    if [[ ! -e "$TEMP_DIR/staging/$required" ]]; then
        die "release is incomplete: missing $required"
    fi
done

# Download and build every dependency before touching the known-working app.
# After this succeeds, installation into the new venv is fully offline.
log "Preparing Python dependency wheels"
"$APP_DIR/venv/bin/python" -m pip wheel \
    --wheel-dir "$TEMP_DIR/wheels" \
    -r "$TEMP_DIR/staging/requirements.txt"

log "Replacing application files"
printf '%s\n%s\n' "$TEMP_DIR" "$APP_DIR" >"$TRANSACTION_MARKER.new"
mv -f "$TRANSACTION_MARKER.new" "$TRANSACTION_MARKER"
SWAPPED=true
for item in "${APP_ITEMS[@]}"; do
    if [[ -e "$APP_DIR/$item" ]]; then
        mv "$APP_DIR/$item" "$BACKUP_DIR/$item"
    fi
    if [[ -e "$TEMP_DIR/staging/$item" ]]; then
        if [[ ! -e "$BACKUP_DIR/$item" ]]; then
            touch "$BACKUP_DIR/.new-$item"
        fi
        mv "$TEMP_DIR/staging/$item" "$APP_DIR/$item"
    fi
done

if [[ ! -e "$BACKUP_DIR/venv" ]]; then
    touch "$BACKUP_DIR/.new-venv"
fi
/usr/bin/python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/python" -m pip install \
    --no-index \
    --find-links "$TEMP_DIR/wheels" \
    -r "$APP_DIR/requirements.txt"
"$APP_DIR/venv/bin/python" -m pip check
"$APP_DIR/venv/bin/python" -c \
    'import flask, flask_socketio, can, serial, eventlet, lgpio, uinput, board, busio; import adafruit_ads1x15.ads1115'
"$APP_DIR/venv/bin/python" "$APP_DIR/V-Link.py" --help >/dev/null
sha256sum "$APP_DIR/requirements.txt" | awk '{print $1}' >"$APP_DIR/venv/.v-link-requirements.sha256"
chmod 0755 "$APP_DIR/V-Link.py" "$APP_DIR/Check-Lite.sh" "$APP_DIR/Update.sh"

rm -f -- "$TRANSACTION_MARKER"
log "Update installed successfully"
sudo /usr/sbin/reboot

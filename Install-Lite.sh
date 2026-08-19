#!/usr/bin/env bash

# V-Link installer for Raspberry Pi OS Lite (Bookworm)
# https://github.com/PabloMartin97/v-link

set -Eeuo pipefail

readonly REPOSITORY="PabloMartin97/v-link"
readonly APP_NAME="v-link"
readonly CONFIG_BEGIN="# BEGIN V-LINK LITE"
readonly CONFIG_END="# END V-LINK LITE"

ASSUME_YES=false
CONFIGURE_HARDWARE=true
REBOOT=true
SOURCE_DIR=""
SOURCE_REF=""
LIN_PORT=""
TARGET_USER="${SUDO_USER:-}"
TEMP_DIR=""
SUDOERS_TEMP=""
BOOT_TEMP=""
CMDLINE_TEMP=""
VENV_WORK=""
VENV_BACKUP=""
VENV_TRANSACTION=false
APP_TRANSACTION=false
APP_CHANGED_PATHS=()
FRONTEND_BUILD_REQUIRED=false
FRONTEND_SOURCE_HASH=""
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

cleanup() {
    local status=$?
    trap - EXIT ERR HUP INT TERM
    set +e

    if ((status != 0)); then
        if [[ -n "$VENV_BACKUP" && -d "$VENV_BACKUP" ]]; then
            rm -rf -- "$APP_DIR/venv"
            mv "$VENV_BACKUP" "$APP_DIR/venv"
        elif [[ "$VENV_TRANSACTION" == true && -n "${APP_DIR:-}" ]]; then
            rm -rf -- "$APP_DIR/venv"
        fi
        if [[ "$APP_TRANSACTION" == true ]]; then
            local index
            for ((index=${#APP_CHANGED_PATHS[@]} - 1; index >= 0; index--)); do
                restore_app_path "${APP_CHANGED_PATHS[index]}"
            done
        fi
    fi

    if [[ -n "$TEMP_DIR" && -d "$TEMP_DIR" ]]; then
        rm -rf -- "$TEMP_DIR"
    fi
    if [[ -n "$SUDOERS_TEMP" && -e "$SUDOERS_TEMP" ]]; then
        rm -f -- "$SUDOERS_TEMP"
    fi
    [[ -z "$BOOT_TEMP" || ! -e "$BOOT_TEMP" ]] || rm -f -- "$BOOT_TEMP"
    [[ -z "$CMDLINE_TEMP" || ! -e "$CMDLINE_TEMP" ]] || rm -f -- "$CMDLINE_TEMP"
    [[ -z "$VENV_WORK" || ! -d "$VENV_WORK" ]] || rm -rf -- "$VENV_WORK"

    exit "$status"
}
trap cleanup EXIT

usage() {
    cat <<'EOF'
Usage: sudo ./Install-Lite.sh [options]

Install V-Link on Raspberry Pi OS Lite (Bookworm) with a minimal Wayland
session, Chromium kiosk, mouse/touch input, PipeWire audio and optional HAT
support.

Options:
  --yes                 Accept all prompts.
  --user USER           User that will run the kiosk (defaults to SUDO_USER).
  --source-dir PATH     Install application files from a local checkout.
  --ref REF             Download, build and install this Git branch or tag.
  --lin-port PATH       Serial device for LIN controls (for example a stable
                        /dev/serial/by-id/... USB-UART path on Pi 3).
  --no-hardware         Skip overlays, CAN, UART, GPIO and udev setup.
  --no-reboot           Do not reboot when installation finishes.
  -h, --help            Show this help.
EOF
}

log() {
    printf '\n[V-Link Lite] %s\n' "$*"
}

die() {
    printf '\n[V-Link Lite] ERROR: %s\n' "$*" >&2
    exit 1
}

confirm() {
    local prompt="$1"
    if [[ "$ASSUME_YES" == true ]]; then
        return 0
    fi

    local reply
    read -r -p "$prompt [y/N]: " reply
    [[ "$reply" =~ ^[Yy]$ ]]
}

validate_source() {
    local source="$1"
    local required

    for required in \
        V-Link.py requirements.txt Check-Lite.sh Update.sh \
        backend/server.py \
        resources/dtoverlays/v-link.dtbo \
        resources/dtoverlays/mcp2515-can1.dtbo \
        resources/dtoverlays/mcp2515-can2.dtbo; do
        [[ -e "$source/$required" ]] || die "source is incomplete: missing $required"
    done

    if [[ ! -f "$source/frontend/dist/index.html" && ! -f "$source/frontend/package.json" ]]; then
        die "source is incomplete: frontend/dist/index.html or frontend/package.json is required"
    fi
}

frontend_source_hash() {
    local source="$1"
    python3 - "$source/frontend" <<'PY'
import hashlib
import sys
from pathlib import Path

root = Path(sys.argv[1])
digest = hashlib.sha256()
for path in sorted(root.rglob('*')):
    relative = path.relative_to(root)
    if not path.is_file() or relative.parts[0] in {'dist', 'node_modules'}:
        continue
    digest.update(relative.as_posix().encode())
    digest.update(b'\0')
    digest.update(hashlib.sha256(path.read_bytes()).digest())
print(digest.hexdigest())
PY
}

restore_app_path() {
    local destination="$1"
    local backup="$destination.v-link-old"
    local absent="$destination.v-link-was-absent"

    if [[ -e "$backup" || -L "$backup" ]]; then
        rm -rf -- "$destination"
        mv "$backup" "$destination"
    elif [[ -e "$absent" ]]; then
        rm -rf -- "$destination"
    fi
    rm -f -- "$absent"
}

begin_app_path() {
    local destination="$1"
    local backup="$destination.v-link-old"
    local absent="$destination.v-link-was-absent"

    # A backup from a killed installer is always the last known-good copy.
    restore_app_path "$destination"
    APP_CHANGED_PATHS+=("$destination")
    if [[ -e "$destination" || -L "$destination" ]]; then
        mv "$destination" "$backup"
    else
        : >"$absent"
    fi
}

install_app_file() {
    local source="$1"
    local destination="$2"
    local mode="$3"
    local parent base staging

    parent="$(dirname -- "$destination")"
    base="$(basename -- "$destination")"
    install -d "$parent"
    staging="$(mktemp "$parent/.${base}.v-link-new.XXXXXX")"
    install -m "$mode" "$source" "$staging"
    begin_app_path "$destination"
    mv "$staging" "$destination"
}

replace_app_directory() {
    local source="$1"
    local destination="$2"
    local parent base staging

    parent="$(dirname -- "$destination")"
    base="$(basename -- "$destination")"
    install -d "$parent"
    staging="$(mktemp -d "$parent/.${base}.v-link-new.XXXXXX")"
    cp -a "$source/." "$staging/"
    begin_app_path "$destination"
    mv "$staging" "$destination"
}

remove_app_path() {
    local destination="$1"
    if [[ -e "$destination" || -L "$destination" ]]; then
        begin_app_path "$destination"
    fi
}

commit_app_transaction() {
    local destination
    for destination in "${APP_CHANGED_PATHS[@]}"; do
        rm -rf -- "$destination.v-link-old"
        rm -f -- "$destination.v-link-was-absent"
    done
    APP_CHANGED_PATHS=()
    APP_TRANSACTION=false
}

on_error() {
    local line="$1"
    local status="$2"
    local command="$3"
    printf '\n[V-Link Lite] Installation failed at line %s (exit %s).\n' "$line" "$status" >&2
    printf '[V-Link Lite] Command: %s\n' "$command" >&2
    printf '[V-Link Lite] Fix the reported error and run the installer again.\n' >&2
}
trap 'on_error "$LINENO" "$?" "$BASH_COMMAND"' ERR
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

while (($#)); do
    case "$1" in
        --yes)
            ASSUME_YES=true
            ;;
        --user)
            (($# >= 2)) || die "--user requires a value"
            TARGET_USER="$2"
            shift
            ;;
        --source-dir)
            (($# >= 2)) || die "--source-dir requires a path"
            SOURCE_DIR="$2"
            shift
            ;;
        --ref)
            (($# >= 2)) || die "--ref requires a branch or tag"
            SOURCE_REF="$2"
            shift
            ;;
        --lin-port)
            (($# >= 2)) || die "--lin-port requires a path"
            LIN_PORT="$2"
            shift
            ;;
        --no-hardware)
            CONFIGURE_HARDWARE=false
            ;;
        --no-reboot)
            REBOOT=false
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            usage >&2
            die "unknown option: $1"
            ;;
    esac
    shift
done

[[ -z "$SOURCE_DIR" || -z "$SOURCE_REF" ]] || \
    die "use either --source-dir or --ref, not both"
[[ -z "$LIN_PORT" || "$CONFIGURE_HARDWARE" == true ]] || \
    die "--lin-port cannot be combined with --no-hardware"
if [[ -n "$LIN_PORT" && ! "$LIN_PORT" =~ ^/dev/[A-Za-z0-9._/+:-]+$ ]]; then
    die "--lin-port must be an absolute /dev path without spaces"
fi

[[ $EUID -eq 0 ]] || die "run this installer with sudo"
command -v flock >/dev/null 2>&1 || die "the util-linux flock command is required"
exec 9>/run/lock/v-link-lite-install.lock
flock -n 9 || die "another V-Link Lite installer is already running"
[[ -r /etc/os-release ]] || die "cannot identify the operating system"

# shellcheck disable=SC1091
source /etc/os-release
[[ "${ID:-}" == "raspbian" || "${ID:-}" == "debian" ]] || \
    die "Raspberry Pi OS or Debian is required (detected: ${ID:-unknown})"
[[ "${VERSION_CODENAME:-}" == "bookworm" ]] || \
    die "this installer targets Bookworm (detected: ${VERSION_CODENAME:-unknown})"

[[ -n "$TARGET_USER" ]] || die "could not determine the kiosk user; pass --user USER"
id "$TARGET_USER" >/dev/null 2>&1 || die "user '$TARGET_USER' does not exist"
[[ "$TARGET_USER" != "root" ]] || die "the kiosk must run as an unprivileged user"

TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
[[ -n "$TARGET_HOME" && -d "$TARGET_HOME" ]] || die "home directory for '$TARGET_USER' was not found"
TARGET_GROUP="$(id -gn "$TARGET_USER")"

APP_DIR="$TARGET_HOME/$APP_NAME"
USER_CONFIG_DIR="$TARGET_HOME/.config"
MODEL="unknown"
RPI_GENERATION=""

if [[ -r /proc/device-tree/model ]]; then
    MODEL="$(tr -d '\0' </proc/device-tree/model)"
    case "$MODEL" in
        *"Raspberry Pi 3"*) RPI_GENERATION=3 ;;
        *"Raspberry Pi 4"*) RPI_GENERATION=4 ;;
        *"Raspberry Pi 5"*) RPI_GENERATION=5 ;;
    esac
fi

[[ -n "$RPI_GENERATION" ]] || die "unsupported Raspberry Pi model '$MODEL' (Pi 3, 4 or 5 required)"
log "Detected $MODEL"

# When launched from a checkout, use it automatically. A standalone copy keeps
# SOURCE_DIR empty and installs a release unless --ref requests source code.
if [[ -z "$SOURCE_DIR" && -z "$SOURCE_REF" && -f "$SCRIPT_DIR/V-Link.py" && -d "$SCRIPT_DIR/frontend" ]]; then
    SOURCE_DIR="$SCRIPT_DIR"
fi

if [[ -n "$SOURCE_DIR" ]]; then
    SOURCE_DIR="$(realpath -e "$SOURCE_DIR")"
    validate_source "$SOURCE_DIR"
    if [[ "$SOURCE_DIR" == "$(realpath -m "$APP_DIR")" ]]; then
        APP_DIR="$TARGET_HOME/v-link-runtime"
        log "Keeping the source checkout intact; the kiosk runtime will be installed at $APP_DIR"
    fi
    if [[ ! -f "$SOURCE_DIR/frontend/dist/index.html" ]]; then
        FRONTEND_BUILD_REQUIRED=true
    elif [[ -f "$SOURCE_DIR/frontend/package.json" ]]; then
        FRONTEND_SOURCE_HASH="$(frontend_source_hash "$SOURCE_DIR")"
        if [[ ! -f "$SOURCE_DIR/frontend/dist/.v-link-source.sha256" ]] || \
           [[ "$(<"$SOURCE_DIR/frontend/dist/.v-link-source.sha256")" != "$FRONTEND_SOURCE_HASH" ]]; then
            FRONTEND_BUILD_REQUIRED=true
        fi
    fi
elif [[ -n "$SOURCE_REF" ]]; then
    FRONTEND_BUILD_REQUIRED=true
fi

UPDATE_MARKER="$TARGET_HOME/.v-link-update-active"
RECOVERY_HELPER="$TARGET_HOME/.local/libexec/v-link-recover-update"
if [[ -e "$UPDATE_MARKER" ]]; then
    [[ -x "$RECOVERY_HELPER" ]] || \
        die "an interrupted update needs recovery, but $RECOVERY_HELPER is unavailable"
    RECOVERY_APP_DIR="$(sed -n '2p' "$UPDATE_MARKER")"
    [[ -n "$RECOVERY_APP_DIR" ]] || RECOVERY_APP_DIR="$APP_DIR"
    case "$RECOVERY_APP_DIR" in
        "$TARGET_HOME"/v-link|"$TARGET_HOME"/v-link-runtime) ;;
        *) die "interrupted update contains an unsafe application path" ;;
    esac
    log "Recovering an interrupted V-Link update before installation"
    runuser -u "$TARGET_USER" -- "$RECOVERY_HELPER" "$RECOVERY_APP_DIR"
fi

ARCHITECTURE="$(dpkg --print-architecture)"
[[ "$ARCHITECTURE" == armhf || "$ARCHITECTURE" == arm64 ]] || \
    die "unsupported architecture '$ARCHITECTURE' (armhf or arm64 required)"

REQUIRED_FREE_KB=1572864
if [[ "$FRONTEND_BUILD_REQUIRED" == true ]]; then
    REQUIRED_FREE_KB=2621440
fi
for storage_path in / "$TARGET_HOME"; do
    AVAILABLE_KB="$(df -Pk "$storage_path" | awk 'NR == 2 {print $4}')"
    [[ "$AVAILABLE_KB" =~ ^[0-9]+$ ]] || die "could not measure free space on $storage_path"
    if ((AVAILABLE_KB < REQUIRED_FREE_KB)); then
        die "not enough free space on $storage_path (need at least $((REQUIRED_FREE_KB / 1024)) MiB)"
    fi
done

# Fail fast on a typo or an unpublished release before spending time in APT.
if command -v curl >/dev/null 2>&1 && command -v python3 >/dev/null 2>&1; then
    if [[ -n "$SOURCE_REF" ]]; then
        log "Checking that GitHub ref '$SOURCE_REF' exists"
        ENCODED_REF="$(python3 - "$SOURCE_REF" <<'PY'
import sys
import urllib.parse
print(urllib.parse.quote(sys.argv[1], safe=''))
PY
)"
        curl --fail --silent --show-error --location --retry 2 \
            --connect-timeout 10 --max-time 60 --speed-limit 128 --speed-time 30 \
            "https://api.github.com/repos/$REPOSITORY/commits/$ENCODED_REF" \
            --output /dev/null || die "GitHub ref '$SOURCE_REF' does not exist or is not reachable"
    elif [[ -z "$SOURCE_DIR" ]]; then
        log "Checking the latest GitHub release assets"
        TEMP_DIR="$(mktemp -d /tmp/v-link-lite.XXXXXX)"
        RELEASE_JSON="$TEMP_DIR/release.json"
        curl --fail --silent --show-error --location --retry 2 \
            --connect-timeout 10 --max-time 60 --speed-limit 128 --speed-time 30 \
            "https://api.github.com/repos/$REPOSITORY/releases/latest" \
            --output "$RELEASE_JSON" || die "no published V-Link release is reachable"
        python3 - "$RELEASE_JSON" <<'PY' || exit 1
import json
import sys

with open(sys.argv[1], encoding='utf-8') as release_file:
    assets = {asset.get('name') for asset in json.load(release_file).get('assets', [])}
missing = {'V-Link.zip', 'V-Link.zip.sha256'} - assets
if missing:
    print(f"[V-Link Lite] ERROR: latest release is missing: {', '.join(sorted(missing))}", file=sys.stderr)
    raise SystemExit(1)
PY
    fi
else
    log "Remote preflight skipped because curl or python3 is unavailable; APT will install it"
fi

log "Installing the minimal Wayland, browser, audio and runtime packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
    labwc wlr-randr lightdm lightdm-gtk-greeter chromium chromium-sandbox rpi-chromium-mods \
    pipewire-audio pipewire pipewire-pulse wireplumber alsa-utils libgl1-mesa-dri \
    dbus-user-session libinput-tools fonts-dejavu fonts-liberation \
    curl unzip ca-certificates python3 python3-dev python3-pip python3-venv \
    libudev-dev build-essential can-utils iproute2

if [[ "$FRONTEND_BUILD_REQUIRED" == true ]]; then
    log "Installing frontend build tools"
    apt-get install -y --no-install-recommends git nodejs npm libusb-1.0-0-dev
fi

systemctl enable lightdm.service
systemctl set-default graphical.target

if [[ -n "$SOURCE_REF" ]]; then
    log "Downloading source ref '$SOURCE_REF' from GitHub"
    TEMP_DIR="$(mktemp -d /tmp/v-link-lite.XXXXXX)"
    chown "$TARGET_USER:$TARGET_GROUP" "$TEMP_DIR"
    runuser -u "$TARGET_USER" -- git \
        -c http.lowSpeedLimit=1024 -c http.lowSpeedTime=30 \
        clone --depth 1 --branch "$SOURCE_REF" \
        "https://github.com/$REPOSITORY.git" "$TEMP_DIR/source"
    SOURCE_DIR="$TEMP_DIR/source"
elif [[ -z "$SOURCE_DIR" ]]; then
    log "Downloading the latest V-Link release"
    if [[ -z "$TEMP_DIR" ]]; then
        TEMP_DIR="$(mktemp -d /tmp/v-link-lite.XXXXXX)"
    fi
    RELEASE_JSON="$TEMP_DIR/release.json"
    if [[ ! -s "$RELEASE_JSON" ]]; then
        curl --fail --silent --show-error --location --retry 3 \
            --connect-timeout 10 --max-time 60 --speed-limit 128 --speed-time 30 \
            "https://api.github.com/repos/$REPOSITORY/releases/latest" \
            --output "$RELEASE_JSON"
    fi
    mapfile -t RELEASE_ASSET_URLS < <(python3 - "$RELEASE_JSON" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as release_file:
    release = json.load(release_file)

assets = {asset.get('name'): asset.get('browser_download_url') for asset in release.get('assets', [])}
for name in ('V-Link.zip', 'V-Link.zip.sha256'):
    if assets.get(name):
        print(assets[name])
PY
)
    [[ "${#RELEASE_ASSET_URLS[@]}" -eq 2 ]] || \
        die "latest GitHub release does not contain V-Link.zip and its checksum"
    RELEASE_URL="${RELEASE_ASSET_URLS[0]}"
    CHECKSUM_URL="${RELEASE_ASSET_URLS[1]}"
    curl --fail --show-error --location --retry 3 --connect-timeout 10 \
        --max-time 900 --speed-limit 1024 --speed-time 30 \
        "$RELEASE_URL" --output "$TEMP_DIR/V-Link.zip"
    curl --fail --show-error --location --retry 3 --connect-timeout 10 \
        --max-time 120 --speed-limit 32 --speed-time 30 \
        "$CHECKSUM_URL" --output "$TEMP_DIR/V-Link.zip.sha256"
    (cd "$TEMP_DIR" && sha256sum --check V-Link.zip.sha256)
    ZIP_ENTRIES="$(unzip -Z1 "$TEMP_DIR/V-Link.zip")"
    if grep -Eq '(^/|(^|/)\.\.(/|$))' <<<"$ZIP_ENTRIES"; then
        die "release archive contains an unsafe path"
    fi
    install -d "$TEMP_DIR/source"
    unzip -q "$TEMP_DIR/V-Link.zip" -d "$TEMP_DIR/source"
    SOURCE_DIR="$TEMP_DIR/source"
fi

SOURCE_DIR="$(realpath -e "$SOURCE_DIR")"
validate_source "$SOURCE_DIR"
if [[ "$FRONTEND_BUILD_REQUIRED" == true ]]; then
    log "Building the frontend (this can take several minutes on a Pi 3)"
    [[ -f "$SOURCE_DIR/frontend/package.json" ]] || die "frontend source is unavailable for the required build"
    chown -R "$TARGET_USER:$TARGET_GROUP" "$SOURCE_DIR/frontend"
    runuser -u "$TARGET_USER" -- bash -c \
        'cd "$1" && export NODE_OPTIONS=--max-old-space-size=768 ELECTRON_SKIP_BINARY_DOWNLOAD=1 && npm ci --legacy-peer-deps --no-audit --no-fund && npm run build' \
        bash "$SOURCE_DIR/frontend"
    FRONTEND_SOURCE_HASH="$(frontend_source_hash "$SOURCE_DIR")"
    runuser -u "$TARGET_USER" -- sh -c 'printf "%s\n" "$1" >"$2"' \
        sh "$FRONTEND_SOURCE_HASH" "$SOURCE_DIR/frontend/dist/.v-link-source.sha256"
else
    log "Using the existing frontend build"
fi

log "Installing V-Link application files"
[[ ! -L "$APP_DIR" ]] || die "$APP_DIR must not be a symbolic link"
install -d -o "$TARGET_USER" -g "$TARGET_GROUP" "$APP_DIR"
SOURCE_IS_APP=false

if [[ "$SOURCE_DIR" == "$(realpath "$APP_DIR")" ]]; then
    SOURCE_IS_APP=true
    log "The checkout is already at $APP_DIR; using it in place"
else
    APP_TRANSACTION=true
    install_app_file "$SOURCE_DIR/V-Link.py" "$APP_DIR/V-Link.py" 0755
    install_app_file "$SOURCE_DIR/requirements.txt" "$APP_DIR/requirements.txt" 0644
    replace_app_directory "$SOURCE_DIR/backend" "$APP_DIR/backend"
    replace_app_directory "$SOURCE_DIR/frontend/dist" "$APP_DIR/frontend/dist"
    replace_app_directory "$SOURCE_DIR/resources/dtoverlays" "$APP_DIR/resources/dtoverlays"
    for optional_file in Update.sh Patch.sh Check-Lite.sh; do
        if [[ -f "$SOURCE_DIR/$optional_file" ]]; then
            install_app_file "$SOURCE_DIR/$optional_file" "$APP_DIR/$optional_file" 0755
        else
            remove_app_path "$APP_DIR/$optional_file"
        fi
    done
fi

if [[ "$SOURCE_IS_APP" != true ]]; then
    chown -R "$TARGET_USER:$TARGET_GROUP" "$APP_DIR"
fi
for executable in V-Link.py Check-Lite.sh Update.sh; do
    if [[ -f "$APP_DIR/$executable" ]]; then
        chmod 0755 "$APP_DIR/$executable"
    fi
done

for required_path in \
    "$APP_DIR/V-Link.py" \
    "$APP_DIR/requirements.txt" \
    "$APP_DIR/Check-Lite.sh" \
    "$APP_DIR/Update.sh" \
    "$APP_DIR/backend/server.py" \
    "$APP_DIR/frontend/dist/index.html"; do
    [[ -e "$required_path" ]] || die "installed application is incomplete: missing $required_path"
done
install -o "$TARGET_USER" -g "$TARGET_GROUP" -m 0644 /dev/null "$APP_DIR/.v-link-lite-runtime"

log "Creating the Python virtual environment"
REQUIREMENTS_HASH="$(sha256sum "$APP_DIR/requirements.txt" | awk '{print $1}')"
VENV_CURRENT=false
VENV_BACKUP="$APP_DIR/.venv.v-link-old"
if [[ -d "$VENV_BACKUP" ]]; then
    log "Recovering the Python environment from an interrupted installation"
    rm -rf -- "$APP_DIR/venv"
    mv "$VENV_BACKUP" "$APP_DIR/venv"
fi
if [[ -x "$APP_DIR/venv/bin/python" && -f "$APP_DIR/venv/.v-link-requirements.sha256" ]] && \
   [[ "$(<"$APP_DIR/venv/.v-link-requirements.sha256")" == "$REQUIREMENTS_HASH" ]] && \
   runuser -u "$TARGET_USER" -- "$APP_DIR/venv/bin/python" -m pip check >/dev/null 2>&1 && \
   runuser -u "$TARGET_USER" -- "$APP_DIR/venv/bin/python" "$APP_DIR/V-Link.py" --help >/dev/null 2>&1; then
    VENV_CURRENT=true
fi

if [[ "$VENV_CURRENT" != true ]]; then
    VENV_WORK="$(mktemp -d "$TARGET_HOME/.v-link-venv.XXXXXX")"
    chown "$TARGET_USER:$TARGET_GROUP" "$VENV_WORK"
    runuser -u "$TARGET_USER" -- python3 -m venv "$VENV_WORK/builder"
    runuser -u "$TARGET_USER" -- "$VENV_WORK/builder/bin/python" -m pip wheel \
        --wheel-dir "$VENV_WORK/wheels" \
        -r "$APP_DIR/requirements.txt"

    if [[ -d "$APP_DIR/venv" ]]; then
        mv "$APP_DIR/venv" "$VENV_BACKUP"
    fi
    VENV_TRANSACTION=true
    runuser -u "$TARGET_USER" -- python3 -m venv "$APP_DIR/venv"
    runuser -u "$TARGET_USER" -- "$APP_DIR/venv/bin/python" -m pip install \
        --no-index --find-links "$VENV_WORK/wheels" \
        -r "$APP_DIR/requirements.txt"
    runuser -u "$TARGET_USER" -- "$APP_DIR/venv/bin/python" -m pip check
    runuser -u "$TARGET_USER" -- "$APP_DIR/venv/bin/python" "$APP_DIR/V-Link.py" --help >/dev/null
    runuser -u "$TARGET_USER" -- sh -c 'printf "%s\n" "$1" >"$2"' \
        sh "$REQUIREMENTS_HASH" "$APP_DIR/venv/.v-link-requirements.sha256"
    rm -rf -- "$VENV_WORK"
    VENV_WORK=""
else
    log "Reusing the verified Python environment"
    VENV_BACKUP=""
fi

log "Granting the kiosk user access to display, input, audio and V-Link hardware"
for group in audio video render input plugdev dialout gpio i2c spi; do
    if getent group "$group" >/dev/null; then
        usermod -aG "$group" "$TARGET_USER"
    fi
done

log "Configuring graphical autologin"
install -d /etc/lightdm/lightdm.conf.d
cat >/etc/lightdm/lightdm.conf.d/50-v-link-lite.conf <<EOF
[Seat:*]
greeter-session=lightdm-gtk-greeter
autologin-user=$TARGET_USER
autologin-user-timeout=0
user-session=labwc
autologin-session=labwc
EOF

install -d -o "$TARGET_USER" -g "$TARGET_GROUP" \
    "$USER_CONFIG_DIR/labwc" "$USER_CONFIG_DIR/systemd/user" \
    "$TARGET_HOME/.local/libexec"

cat >"$TARGET_HOME/.local/libexec/v-link-recover-update" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail

LOCK_HELD=false
if [[ "${1:-}" == --lock-held ]]; then
    LOCK_HELD=true
    shift
fi
[[ "$#" -eq 1 ]]

APP_DIR="$1"
APP_PARENT="$(dirname -- "$APP_DIR")"
MARKER="$APP_PARENT/.v-link-update-active"
readonly -a APP_ITEMS=(
    V-Link.py backend frontend resources requirements.txt Patch.sh Check-Lite.sh Update.sh venv
)

if [[ "$LOCK_HELD" != true ]]; then
    exec 9>"$APP_PARENT/.v-link-update.lock"
    flock -w 30 9
fi
[[ -e "$MARKER" ]] || exit 0

IFS= read -r TRANSACTION_DIR <"$MARKER"
MARKED_APP_DIR="$(sed -n '2p' "$MARKER")"
if [[ -n "$MARKED_APP_DIR" && "$MARKED_APP_DIR" != "$APP_DIR" ]]; then
    printf 'V-Link recovery target mismatch: %s\n' "$MARKED_APP_DIR" >&2
    exit 1
fi
case "$TRANSACTION_DIR" in
    "$APP_PARENT"/.v-link-update.*) ;;
    *) printf 'Unsafe V-Link recovery path: %s\n' "$TRANSACTION_DIR" >&2; exit 1 ;;
esac
BACKUP_DIR="$TRANSACTION_DIR/backup"
[[ -d "$BACKUP_DIR" ]]

for item in "${APP_ITEMS[@]}"; do
    if [[ -e "$BACKUP_DIR/$item" ]]; then
        rm -rf -- "$APP_DIR/$item"
        mv "$BACKUP_DIR/$item" "$APP_DIR/$item"
    elif [[ -e "$BACKUP_DIR/.new-$item" ]]; then
        rm -rf -- "$APP_DIR/$item"
    fi
done

rm -f -- "$MARKER"
rm -rf -- "$TRANSACTION_DIR"
EOF
chown "$TARGET_USER:$TARGET_GROUP" "$TARGET_HOME/.local/libexec/v-link-recover-update"
chmod 0755 "$TARGET_HOME/.local/libexec/v-link-recover-update"

RUNTIME_ARGS=""
if [[ "$CONFIGURE_HARDWARE" != true ]]; then
    RUNTIME_ARGS=" --no-hardware"
fi
LIN_ENVIRONMENT=""
if [[ -n "$LIN_PORT" ]]; then
    LIN_ENVIRONMENT="Environment=VLINK_LIN_PORT=$LIN_PORT"
    if [[ ! -e "$LIN_PORT" ]]; then
        log "WARNING: LIN port $LIN_PORT is not connected yet; the health check will require it after reboot"
    fi
fi

cat >"$USER_CONFIG_DIR/systemd/user/v-link.service" <<EOF
[Unit]
Description=V-Link kiosk application
After=pipewire.service wireplumber.service
Wants=pipewire.service wireplumber.service

[Service]
Type=simple
WorkingDirectory=$APP_DIR
ExecStartPre=$TARGET_HOME/.local/libexec/v-link-recover-update $APP_DIR
ExecStart=$APP_DIR/venv/bin/python $APP_DIR/V-Link.py$RUNTIME_ARGS
Restart=on-failure
RestartSec=3
TimeoutStopSec=20
Environment=PYTHONUNBUFFERED=1
Environment=VLINK_MANAGED_CAN=1
$LIN_ENVIRONMENT

[Install]
WantedBy=default.target
EOF

cat >"$USER_CONFIG_DIR/labwc/autostart" <<'EOF'
# Start V-Link after Wayland, DBus, PipeWire and the user systemd manager exist.
systemctl --user import-environment WAYLAND_DISPLAY DISPLAY XDG_CURRENT_DESKTOP XDG_SESSION_TYPE
systemctl --user start v-link.service &
EOF

chown -R "$TARGET_USER:$TARGET_GROUP" "$USER_CONFIG_DIR/labwc" "$USER_CONFIG_DIR/systemd"
chmod 0644 "$USER_CONFIG_DIR/systemd/user/v-link.service"
chmod 0755 "$USER_CONFIG_DIR/labwc/autostart"

# The settings screen exposes only these two privileged power operations.
SUDOERS_TEMP="$(mktemp /tmp/v-link-sudoers.XXXXXX)"
cat >"$SUDOERS_TEMP" <<EOF
$TARGET_USER ALL=(root) NOPASSWD: /usr/sbin/reboot, /usr/sbin/reboot -h now, /usr/sbin/shutdown -h now
EOF
if [[ "$CONFIGURE_HARDWARE" == true ]]; then
    cat >>"$SUDOERS_TEMP" <<EOF
$TARGET_USER ALL=(root) NOPASSWD: /usr/local/sbin/v-link-can-set can1 125000 can2 250000, /usr/local/sbin/v-link-can-set can1 125000 can2 500000
EOF
fi
chmod 0440 "$SUDOERS_TEMP"
visudo -cf "$SUDOERS_TEMP" >/dev/null
install -o root -g root -m 0440 "$SUDOERS_TEMP" /etc/sudoers.d/v-link-lite
rm -f -- "$SUDOERS_TEMP"
SUDOERS_TEMP=""

if [[ "$CONFIGURE_HARDWARE" == true ]]; then
    log "Configuring the V-Link HAT, CAN, UART and GPIO"
    BOOT_CONFIG=/boot/firmware/config.txt
    OVERLAY_DIR=/boot/firmware/overlays
    [[ -f "$BOOT_CONFIG" && -d "$OVERLAY_DIR" ]] || \
        die "Bookworm boot configuration was not found under /boot/firmware"

    for overlay in v-link.dtbo mcp2515-can1.dtbo mcp2515-can2.dtbo; do
        [[ -s "$APP_DIR/resources/dtoverlays/$overlay" ]] || \
            die "application package is missing hardware overlay $overlay"
        install -m 0644 "$APP_DIR/resources/dtoverlays/$overlay" "$OVERLAY_DIR/$overlay"
    done

    CONFIG_BEGIN_COUNT="$(grep -cFx "$CONFIG_BEGIN" "$BOOT_CONFIG" || true)"
    CONFIG_END_COUNT="$(grep -cFx "$CONFIG_END" "$BOOT_CONFIG" || true)"
    if [[ "$CONFIG_BEGIN_COUNT" != "$CONFIG_END_COUNT" || "$CONFIG_BEGIN_COUNT" -gt 1 ]]; then
        die "$BOOT_CONFIG contains an incomplete or duplicated V-Link block"
    fi

    [[ -e "$BOOT_CONFIG.v-link.bak" ]] || cp "$BOOT_CONFIG" "$BOOT_CONFIG.v-link.bak"
    BOOT_TEMP="$(mktemp "$BOOT_CONFIG.v-link.XXXXXX")"
    if [[ "$CONFIG_BEGIN_COUNT" -eq 1 ]]; then
        sed "\|$CONFIG_BEGIN|,\|$CONFIG_END|d" "$BOOT_CONFIG" >"$BOOT_TEMP"
    else
        cp "$BOOT_CONFIG" "$BOOT_TEMP"
    fi

    {
        printf '\n%s\n' "$CONFIG_BEGIN"
        cat <<'EOF'
[all]
dtparam=spi=on
dtparam=i2c_arm=on
enable_uart=1
disable_poe_fan=1
force_eeprom_read=0
dtoverlay=v-link,cs2_spidev=off
dtoverlay=mcp2515-can1,oscillator=16000000,interrupt=24
dtoverlay=mcp2515-can2,oscillator=16000000,interrupt=22
dtoverlay=gpio-poweroff,gpiopin=0
disable_splash=1
EOF
        case "$RPI_GENERATION" in
            3)
                printf '%s\n' 'dtoverlay=disable-bt'
                ;;
            4)
                printf '%s\n' 'dtoverlay=uart3'
                ;;
            5)
                cat <<'EOF'
dtparam=uart0=on
dtoverlay=uart2-pi5
EOF
                ;;
        esac
        printf '%s\n' "$CONFIG_END"
    } >>"$BOOT_TEMP"
    chmod --reference="$BOOT_CONFIG" "$BOOT_TEMP"
    mv -f "$BOOT_TEMP" "$BOOT_CONFIG"
    BOOT_TEMP=""

    CMDLINE_FILE=/boot/firmware/cmdline.txt
    [[ -f "$CMDLINE_FILE" ]] || die "missing $CMDLINE_FILE"
    case "$RPI_GENERATION" in
        3)
            SERIAL_CONSOLES='serial0|ttyAMA0|ttyS0'
            SERIAL_GETTY_UNITS=(serial0 ttyAMA0 ttyS0)
            ;;
        4)
            SERIAL_CONSOLES='serial0|ttyAMA3|ttyS0'
            SERIAL_GETTY_UNITS=(serial0 ttyAMA3 ttyS0)
            ;;
        5)
            SERIAL_CONSOLES='serial0|ttyAMA0|ttyAMA2'
            SERIAL_GETTY_UNITS=(serial0 ttyAMA0 ttyAMA2)
            ;;
    esac
    [[ -e "$CMDLINE_FILE.v-link.bak" ]] || cp "$CMDLINE_FILE" "$CMDLINE_FILE.v-link.bak"
    CMDLINE_TEMP="$(mktemp "$CMDLINE_FILE.v-link.XXXXXX")"
    sed -E \
        "s/(^| )console=($SERIAL_CONSOLES),[^ ]+//g; s/  +/ /g; s/^ //; s/ $//" \
        "$CMDLINE_FILE" >"$CMDLINE_TEMP"
    if ! awk 'NF { lines++ } END { exit(lines == 1 ? 0 : 1) }' "$CMDLINE_TEMP"; then
        die "refusing to install an invalid multi-line kernel command line"
    fi
    if grep -Eq "(^| )console=($SERIAL_CONSOLES)," "$CMDLINE_TEMP"; then
        die "could not release the V-Link serial ports from the kernel console"
    fi
    chmod --reference="$CMDLINE_FILE" "$CMDLINE_TEMP"
    mv -f "$CMDLINE_TEMP" "$CMDLINE_FILE"
    CMDLINE_TEMP=""
    for serial_unit in "${SERIAL_GETTY_UNITS[@]}"; do
        systemctl mask "serial-getty@$serial_unit.service" >/dev/null 2>&1 || true
    done

    cat >/etc/modules-load.d/v-link.conf <<'EOF'
uinput
i2c-dev
EOF

    cat >/etc/udev/rules.d/42-v-link.rules <<'EOF'
SUBSYSTEM=="usb", ATTR{idVendor}=="1314", ATTR{idProduct}=="152*", MODE="0660", GROUP="plugdev"
KERNEL=="ttyS0", MODE="0660", GROUP="plugdev"
KERNEL=="ttyAMA0", MODE="0660", GROUP="plugdev"
KERNEL=="ttyAMA2", MODE="0660", GROUP="plugdev"
KERNEL=="ttyAMA3", MODE="0660", GROUP="plugdev"
KERNEL=="uinput", MODE="0660", GROUP="plugdev"
EOF

cat >/usr/local/sbin/v-link-can-up <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail

exec 9>/run/lock/v-link-can-config.lock
flock -w 30 9

resolve_spi_interface() {
    local spi_device="$1"
    local interfaces=()
    shopt -s nullglob
    interfaces=("/sys/bus/spi/devices/$spi_device/net/"*)
    shopt -u nullglob
    [[ "${#interfaces[@]}" -eq 1 ]] || return 1
    basename -- "${interfaces[0]}"
}

for attempt in {1..30}; do
    SPI1_INTERFACE="$(resolve_spi_interface spi0.1 2>/dev/null || true)"
    SPI2_INTERFACE="$(resolve_spi_interface spi0.2 2>/dev/null || true)"
    [[ -n "$SPI1_INTERFACE" && -n "$SPI2_INTERFACE" ]] && break
    sleep 1
done
[[ -n "$SPI1_INTERFACE" && -n "$SPI2_INTERFACE" ]]
[[ "$SPI1_INTERFACE" != "$SPI2_INTERFACE" ]]

ip link set dev "$SPI1_INTERFACE" down 2>/dev/null || true
ip link set dev "$SPI2_INTERFACE" down 2>/dev/null || true

# Move both devices out of the kernel can%d namespace before assigning the
# stable names. This avoids can0 -> can1 colliding with an existing can1.
if [[ "$SPI1_INTERFACE" != vlink-spi1 ]]; then
    [[ ! -e /sys/class/net/vlink-spi1 ]]
    ip link set dev "$SPI1_INTERFACE" name vlink-spi1
fi
if [[ "$SPI2_INTERFACE" != vlink-spi2 ]]; then
    [[ ! -e /sys/class/net/vlink-spi2 ]]
    ip link set dev "$SPI2_INTERFACE" name vlink-spi2
fi

[[ ! -e /sys/class/net/can1 ]]
[[ ! -e /sys/class/net/can2 ]]
ip link set dev vlink-spi1 name can1
ip link set dev vlink-spi2 name can2

# Leave both buses DOWN until V-Link has loaded a vehicle profile. Bringing a
# 250 kbit/s vehicle bus up at 500 kbit/s, even briefly, is unsafe and noisy.
ip link set dev can1 down
ip link set dev can2 down
EOF
    chmod 0755 /usr/local/sbin/v-link-can-up

    cat >/usr/local/sbin/v-link-can-set <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail

[[ "$#" -eq 4 ]]
[[ "$1" == can1 && "$2" == 125000 && "$3" == can2 ]]
[[ "$4" == 250000 || "$4" == 500000 ]]

# Ensure stable can1/can2 names exist before applying the selected profile.
/usr/bin/systemctl start v-link-can.service

exec 9>/run/lock/v-link-can-config.lock
flock -w 10 9

[[ "$(basename -- "$(readlink -f /sys/class/net/can1/device)")" == spi0.1 ]]
[[ "$(basename -- "$(readlink -f /sys/class/net/can2/device)")" == spi0.2 ]]

ip link set dev can1 down 2>/dev/null || true
ip link set dev can1 type can bitrate 125000 restart-ms 100
ip link set dev can1 up

ip link set dev can2 down 2>/dev/null || true
ip link set dev can2 type can bitrate "$4" restart-ms 100
ip link set dev can2 up
EOF
    chmod 0755 /usr/local/sbin/v-link-can-set

    cat >/etc/systemd/system/v-link-can.service <<'EOF'
[Unit]
Description=Configure V-Link CAN interfaces
After=systemd-modules-load.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/v-link-can-up
RemainAfterExit=yes
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF
    systemctl enable v-link-can.service
    udevadm control --reload-rules

    if [[ "$RPI_GENERATION" -eq 3 ]]; then
        systemctl disable --now hciuart.service 2>/dev/null || true
        systemctl mask hciuart.service >/dev/null 2>&1 || true
    fi
else
    log "Removing any previously managed V-Link HAT configuration"
    systemctl disable --now v-link-can.service >/dev/null 2>&1 || true
    rm -f -- \
        /etc/systemd/system/v-link-can.service \
        /usr/local/sbin/v-link-can-up \
        /usr/local/sbin/v-link-can-set \
        /etc/modules-load.d/v-link.conf \
        /etc/udev/rules.d/42-v-link.rules

    BOOT_CONFIG=/boot/firmware/config.txt
    if [[ -f "$BOOT_CONFIG" ]]; then
        CONFIG_BEGIN_COUNT="$(grep -cFx "$CONFIG_BEGIN" "$BOOT_CONFIG" || true)"
        CONFIG_END_COUNT="$(grep -cFx "$CONFIG_END" "$BOOT_CONFIG" || true)"
        if [[ "$CONFIG_BEGIN_COUNT" != "$CONFIG_END_COUNT" || "$CONFIG_BEGIN_COUNT" -gt 1 ]]; then
            die "$BOOT_CONFIG contains an incomplete or duplicated V-Link block"
        fi
        if [[ "$CONFIG_BEGIN_COUNT" -eq 1 ]]; then
            [[ -e "$BOOT_CONFIG.v-link.bak" ]] || cp "$BOOT_CONFIG" "$BOOT_CONFIG.v-link.bak"
            BOOT_TEMP="$(mktemp "$BOOT_CONFIG.v-link.XXXXXX")"
            sed "\|$CONFIG_BEGIN|,\|$CONFIG_END|d" "$BOOT_CONFIG" >"$BOOT_TEMP"
            chmod --reference="$BOOT_CONFIG" "$BOOT_TEMP"
            mv -f "$BOOT_TEMP" "$BOOT_CONFIG"
            BOOT_TEMP=""
        fi
    fi
    for overlay in v-link.dtbo mcp2515-can1.dtbo mcp2515-can2.dtbo; do
        rm -f -- "/boot/firmware/overlays/$overlay"
    done

    case "$RPI_GENERATION" in
        3)
            SERIAL_GETTY_UNITS=(serial0 ttyAMA0 ttyS0)
            systemctl unmask hciuart.service >/dev/null 2>&1 || true
            systemctl enable hciuart.service >/dev/null 2>&1 || true
            ;;
        4) SERIAL_GETTY_UNITS=(serial0 ttyAMA3 ttyS0) ;;
        5) SERIAL_GETTY_UNITS=(serial0 ttyAMA0 ttyAMA2) ;;
    esac
    for serial_unit in "${SERIAL_GETTY_UNITS[@]}"; do
        systemctl unmask "serial-getty@$serial_unit.service" >/dev/null 2>&1 || true
    done
    udevadm control --reload-rules
fi

systemctl daemon-reload

log "Running pre-reboot health checks"
[[ -x "$APP_DIR/Check-Lite.sh" ]] || die "installed application is missing executable Check-Lite.sh"
if ! "$APP_DIR/Check-Lite.sh" --user "$TARGET_USER" --pre-reboot; then
    die "installation checks failed; review the failures above before rebooting"
fi

# The new code and venv are now known-good. Only now discard the previous
# application so a failed reinstall always leaves the last working version.
if [[ "$APP_TRANSACTION" == true ]]; then
    commit_app_transaction
fi
if [[ "$VENV_TRANSACTION" == true ]]; then
    rm -rf -- "$VENV_BACKUP"
    VENV_BACKUP=""
    VENV_TRANSACTION=false
fi

log "Installation complete"
printf 'User:        %s\n' "$TARGET_USER"
printf 'Application: %s\n' "$APP_DIR"
printf 'Display:     LightDM + labwc + Chromium kiosk\n'
printf 'Audio:       PipeWire/WirePlumber (select the output with wpctl)\n'
printf 'Logs:        journalctl --user -u v-link.service -f\n'
printf 'Health:      sudo %s/Check-Lite.sh --user %s\n' "$APP_DIR" "$TARGET_USER"
if [[ "$RPI_GENERATION" -eq 3 && "$CONFIGURE_HARDWARE" == true ]]; then
    printf '\nWARNING: Pi 3 integrated Bluetooth is disabled to reserve the reliable UART for RTI.\n'
    if [[ -n "$LIN_PORT" ]]; then
        printf 'LIN steering controls will use the external UART at %s.\n' "$LIN_PORT"
    else
        printf 'P1/T5 simultaneous RTI + LIN is disabled unless you rerun with --lin-port /dev/serial/by-id/....\n'
        printf 'Use a CAN steering-control profile when no external USB-UART is configured.\n'
    fi
fi

if [[ "$REBOOT" == true ]] && confirm "Reboot now to start V-Link?"; then
    systemctl reboot
else
    printf '\nReboot later with: sudo reboot\n'
fi

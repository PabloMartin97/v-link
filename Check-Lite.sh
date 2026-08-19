#!/usr/bin/env bash

# Read-only health check for a V-Link Raspberry Pi OS Lite installation.

set -uo pipefail

TARGET_USER="${SUDO_USER:-${USER:-}}"
PRE_REBOOT=false
FAILURES=0
WARNINGS=0

usage() {
    cat <<'EOF'
Usage: ./Check-Lite.sh [--user USER] [--pre-reboot]

Checks the operating system, graphical session, V-Link installation, Python
environment, audio stack and optional HAT configuration without changing them.
EOF
}

while (($#)); do
    case "$1" in
        --user)
            (($# >= 2)) || { printf 'Missing value for --user\n' >&2; exit 2; }
            TARGET_USER="$2"
            shift
            ;;
        --pre-reboot)
            PRE_REBOOT=true
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            printf 'Unknown option: %s\n' "$1" >&2
            usage >&2
            exit 2
            ;;
    esac
    shift
done

pass() {
    printf '  [PASS] %s\n' "$*"
}

warn() {
    WARNINGS=$((WARNINGS + 1))
    printf '  [WARN] %s\n' "$*"
}

fail() {
    FAILURES=$((FAILURES + 1))
    printf '  [FAIL] %s\n' "$*"
}

check_command() {
    if command -v "$1" >/dev/null 2>&1; then
        pass "command available: $1"
    else
        fail "missing command: $1"
    fi
}

if [[ $EUID -ne 0 ]]; then
    printf 'Run this health check with sudo.\n' >&2
    exit 2
fi

[[ -n "$TARGET_USER" ]] || { printf 'Could not determine the kiosk user. Use --user USER.\n' >&2; exit 2; }
if ! id "$TARGET_USER" >/dev/null 2>&1; then
    printf "User '%s' does not exist.\n" "$TARGET_USER" >&2
    exit 2
fi

TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_FILE="$TARGET_HOME/.config/systemd/user/v-link.service"
CONFIGURED_APP_DIR="$(sed -n 's/^WorkingDirectory=//p' "$SERVICE_FILE" 2>/dev/null | tail -n 1)"
if [[ -n "$CONFIGURED_APP_DIR" && -f "$CONFIGURED_APP_DIR/V-Link.py" ]]; then
    APP_DIR="$CONFIGURED_APP_DIR"
elif [[ -f "$SCRIPT_DIR/V-Link.py" ]]; then
    APP_DIR="$SCRIPT_DIR"
else
    APP_DIR="$TARGET_HOME/v-link"
fi
USER_ID="$(id -u "$TARGET_USER")"
RUNTIME_DIR="/run/user/$USER_ID"
MODEL="unknown"

printf '\nV-Link Lite health check\n'
printf 'User: %s\nApplication: %s\n\n' "$TARGET_USER" "$APP_DIR"

printf 'Base system\n'
if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    source /etc/os-release
    if [[ "${VERSION_CODENAME:-}" == bookworm ]]; then
        pass "Raspberry Pi OS/Debian Bookworm detected"
    else
        fail "expected Bookworm, detected ${VERSION_CODENAME:-unknown}"
    fi
else
    fail "/etc/os-release is unavailable"
fi

if [[ -r /proc/device-tree/model ]]; then
    MODEL="$(tr -d '\0' </proc/device-tree/model)"
    if [[ "$MODEL" =~ Raspberry\ Pi\ [345] ]]; then
        pass "$MODEL"
    else
        fail "unsupported model: $MODEL"
    fi
else
    warn "Raspberry Pi model cannot be read"
fi

for command_name in chromium labwc wlr-randr lightdm pipewire wireplumber wpctl; do
    check_command "$command_name"
done

if [[ "$(systemctl get-default 2>/dev/null)" == graphical.target ]]; then
    pass "default boot target is graphical.target"
else
    fail "default boot target is not graphical.target"
fi

if systemctl is-enabled --quiet lightdm.service; then
    pass "LightDM is enabled"
else
    fail "LightDM is not enabled"
fi

if grep -qsE '^dtoverlay=vc4-kms-v3d([,[:space:]]|$)' /boot/firmware/config.txt; then
    pass "VC4 KMS graphics overlay is configured"
else
    fail "VC4 KMS graphics overlay is not configured"
fi

if [[ "$PRE_REBOOT" == true ]]; then
    warn "runtime display checks deferred until reboot"
elif systemctl is-active --quiet lightdm.service; then
    pass "LightDM is running"
else
    fail "LightDM is not running"
fi

if [[ -f /usr/share/wayland-sessions/labwc.desktop ]]; then
    pass "LightDM labwc session is installed"
else
    fail "missing /usr/share/wayland-sessions/labwc.desktop"
fi

for required_group in audio video render input; do
    if id -nG "$TARGET_USER" | tr ' ' '\n' | grep -qx "$required_group"; then
        pass "$TARGET_USER belongs to $required_group"
    else
        fail "$TARGET_USER is missing group $required_group"
    fi
done

if grep -qs "^autologin-user=$TARGET_USER$" /etc/lightdm/lightdm.conf.d/50-v-link-lite.conf; then
    pass "graphical autologin targets $TARGET_USER"
else
    fail "graphical autologin is not configured for $TARGET_USER"
fi
for session_setting in user-session=labwc autologin-session=labwc; do
    if grep -qs "^$session_setting$" /etc/lightdm/lightdm.conf.d/50-v-link-lite.conf; then
        pass "LightDM has $session_setting"
    else
        fail "LightDM is missing $session_setting"
    fi
done

printf '\nApplication\n'
for required_path in \
    "$APP_DIR/V-Link.py" \
    "$APP_DIR/Check-Lite.sh" \
    "$APP_DIR/Update.sh" \
    "$APP_DIR/backend/server.py" \
    "$APP_DIR/frontend/dist/index.html" \
    "$APP_DIR/.v-link-lite-runtime" \
    "$APP_DIR/venv/bin/python" \
    "$TARGET_HOME/.local/libexec/v-link-recover-update" \
    "$TARGET_HOME/.config/systemd/user/v-link.service" \
    "$TARGET_HOME/.config/labwc/autostart"; do
    if [[ -e "$required_path" ]]; then
        pass "found $required_path"
    else
        fail "missing $required_path"
    fi
done

if grep -qsF "ExecStartPre=$TARGET_HOME/.local/libexec/v-link-recover-update $APP_DIR" \
    "$TARGET_HOME/.config/systemd/user/v-link.service"; then
    pass "interrupted updates are recovered before V-Link starts"
else
    fail "v-link.service is missing interrupted-update recovery"
fi

if [[ -x "$APP_DIR/venv/bin/python" ]]; then
    if runuser -u "$TARGET_USER" -- "$APP_DIR/venv/bin/python" -m pip check >/dev/null 2>&1; then
        pass "Python dependency consistency check"
    else
        fail "pip check reports inconsistent Python dependencies"
    fi

    if runuser -u "$TARGET_USER" -- "$APP_DIR/venv/bin/python" -c \
        'import flask, flask_socketio, can, serial, eventlet, lgpio, uinput, board, busio; import adafruit_ads1x15.ads1115' >/dev/null 2>&1; then
        pass "core Python modules import correctly"
    else
        fail "one or more core Python modules cannot be imported"
    fi

    if runuser -u "$TARGET_USER" -- "$APP_DIR/venv/bin/python" "$APP_DIR/V-Link.py" --help >/dev/null 2>&1; then
        pass "V-Link loads its complete Python import graph"
    else
        fail "V-Link fails during startup imports"
    fi
fi

NO_HARDWARE_RUNTIME=false
if grep -qs -- '--no-hardware' "$TARGET_HOME/.config/systemd/user/v-link.service"; then
    NO_HARDWARE_RUNTIME=true
    pass "v-link.service uses UI-only no-hardware mode"
else
    pass "v-link.service uses the physical hardware runtime"
fi

if [[ "$NO_HARDWARE_RUNTIME" == true ]]; then
    if ! systemctl is-enabled --quiet v-link-can.service 2>/dev/null && \
       ! systemctl is-active --quiet v-link-can.service 2>/dev/null; then
        pass "system CAN setup is disabled in UI-only mode"
    else
        fail "v-link-can.service must be disabled in UI-only mode"
    fi
    if ! grep -qsF '# BEGIN V-LINK LITE' /boot/firmware/config.txt; then
        pass "V-Link HAT boot overlays are disabled in UI-only mode"
    else
        fail "V-Link HAT boot configuration remains active in UI-only mode"
    fi
fi

LIN_PORT="$(sed -n 's/^Environment=VLINK_LIN_PORT=//p' "$TARGET_HOME/.config/systemd/user/v-link.service" 2>/dev/null | tail -n 1)"
if [[ -n "$LIN_PORT" ]]; then
    if [[ "$LIN_PORT" =~ ^/dev/[A-Za-z0-9._/+:-]+$ ]]; then
        pass "external LIN port is configured: $LIN_PORT"
    else
        fail "configured LIN port is not a safe /dev path"
    fi
fi

if [[ "$PRE_REBOOT" != true && -S "$RUNTIME_DIR/bus" ]]; then
    USER_ENV=(env "XDG_RUNTIME_DIR=$RUNTIME_DIR" "DBUS_SESSION_BUS_ADDRESS=unix:path=$RUNTIME_DIR/bus")
    if runuser -u "$TARGET_USER" -- "${USER_ENV[@]}" systemctl --user is-active --quiet v-link.service; then
        pass "v-link.service is running"
    else
        fail "v-link.service is not running"
    fi

    if runuser -u "$TARGET_USER" -- "${USER_ENV[@]}" wpctl status >/dev/null 2>&1; then
        pass "PipeWire audio graph is available"
    else
        fail "PipeWire audio graph is unavailable"
    fi

    if runuser -u "$TARGET_USER" -- "${USER_ENV[@]}" wpctl get-volume @DEFAULT_AUDIO_SINK@ >/dev/null 2>&1; then
        pass "a default PipeWire audio output is selected"
    else
        fail "no default PipeWire audio output is selected"
    fi

    USER_MANAGER_ENV="$(runuser -u "$TARGET_USER" -- "${USER_ENV[@]}" systemctl --user show-environment 2>/dev/null || true)"
    if grep -q '^WAYLAND_DISPLAY=' <<<"$USER_MANAGER_ENV" && \
       grep -q '^XDG_SESSION_TYPE=wayland$' <<<"$USER_MANAGER_ENV"; then
        pass "the user service manager has the Wayland environment"
    else
        fail "the user service manager is missing its Wayland environment"
    fi
elif [[ "$PRE_REBOOT" != true ]]; then
    fail "user runtime bus is unavailable at $RUNTIME_DIR/bus"
fi

if [[ "$PRE_REBOOT" != true ]]; then
    if compgen -G '/dev/dri/card*' >/dev/null; then
        pass "DRM/KMS display device is present"
    else
        fail "no /dev/dri/card* display device is present"
    fi
fi

if [[ "$PRE_REBOOT" == true ]]; then
    warn "Chromium and HTTP checks deferred until reboot"
else
    if pgrep -u "$TARGET_USER" -x chromium >/dev/null 2>&1; then
        pass "Chromium kiosk process is running"
    else
        fail "Chromium kiosk process is not running"
    fi

    HTTP_HEADERS="$(curl --fail --silent --show-error --max-time 3 --dump-header - --output /dev/null http://localhost:4001/ 2>/dev/null || true)"
    if [[ -n "$HTTP_HEADERS" ]]; then
        pass "V-Link frontend responds on http://localhost:4001"
        if grep -qi '^Cross-Origin-Opener-Policy: *same-origin' <<<"$HTTP_HEADERS" && \
           grep -qi '^Cross-Origin-Embedder-Policy: *require-corp' <<<"$HTTP_HEADERS"; then
            pass "frontend enables cross-origin isolation for CarPlay audio"
        else
            fail "frontend is missing COOP/COEP headers required by shared audio buffers"
        fi
    else
        fail "V-Link frontend does not respond on port 4001"
    fi

    SOCKETS_4001="$(ss -ltnH 2>/dev/null | grep -E '(^|[[:space:]])(127\.0\.0\.1|0\.0\.0\.0|\[::\]):4001([[:space:]]|$)' || true)"
    if grep -q '127\.0\.0\.1:4001' <<<"$SOCKETS_4001" && \
       ! grep -Eq '(0\.0\.0\.0|\[::\]):4001' <<<"$SOCKETS_4001"; then
        pass "backend port 4001 is restricted to localhost"
    else
        fail "backend port 4001 is not listening only on localhost"
    fi

    UNTRUSTED_STATUS="$(curl --silent --output /dev/null --max-time 3 \
        --write-out '%{http_code}' \
        --header 'Origin: https://attacker.invalid' \
        'http://localhost:4001/socket.io/?EIO=4&transport=polling' || true)"
    if [[ "$UNTRUSTED_STATUS" == 400 || "$UNTRUSTED_STATUS" == 403 ]]; then
        pass "Socket.IO rejects untrusted browser origins"
    else
        fail "Socket.IO accepted an untrusted browser origin (HTTP $UNTRUSTED_STATUS)"
    fi
fi

if grep -qsF '# BEGIN V-LINK LITE' /boot/firmware/config.txt; then
    printf '\nV-Link HAT\n'
    BEGIN_COUNT="$(grep -cFx '# BEGIN V-LINK LITE' /boot/firmware/config.txt || true)"
    END_COUNT="$(grep -cFx '# END V-LINK LITE' /boot/firmware/config.txt || true)"
    if [[ "$BEGIN_COUNT" -eq 1 && "$END_COUNT" -eq 1 ]]; then
        pass "V-Link boot configuration block is complete"
    else
        fail "V-Link boot configuration block is incomplete or duplicated"
    fi

    for config_line in \
        'dtparam=spi=on' \
        'dtparam=i2c_arm=on' \
        'enable_uart=1' \
        'disable_poe_fan=1' \
        'force_eeprom_read=0' \
        'dtoverlay=v-link,cs2_spidev=off' \
        'dtoverlay=mcp2515-can1,oscillator=16000000,interrupt=24' \
        'dtoverlay=mcp2515-can2,oscillator=16000000,interrupt=22' \
        'dtoverlay=gpio-poweroff,gpiopin=0'; do
        if grep -qsFx "$config_line" /boot/firmware/config.txt; then
            pass "boot config: $config_line"
        else
            fail "missing boot config: $config_line"
        fi
    done

    case "$MODEL" in
        *"Raspberry Pi 3"*)
            GENERATION_CONFIG='dtoverlay=disable-bt'
            SERIAL_CONSOLES='serial0|ttyAMA0|ttyS0'
            EXPECTED_UART=/dev/serial0
            ;;
        *"Raspberry Pi 4"*)
            GENERATION_CONFIG='dtoverlay=uart3'
            SERIAL_CONSOLES='serial0|ttyAMA3|ttyS0'
            EXPECTED_UART=/dev/ttyAMA3
            ;;
        *"Raspberry Pi 5"*)
            GENERATION_CONFIG='dtoverlay=uart2-pi5'
            SERIAL_CONSOLES='serial0|ttyAMA0|ttyAMA2'
            EXPECTED_UART=/dev/ttyAMA2
            ;;
        *)
            GENERATION_CONFIG=''
            SERIAL_CONSOLES='serial0|ttyAMA[0-9]+|ttyS0'
            EXPECTED_UART=''
            ;;
    esac
    if [[ -n "$GENERATION_CONFIG" ]] && grep -qsFx "$GENERATION_CONFIG" /boot/firmware/config.txt; then
        pass "generation-specific boot config: $GENERATION_CONFIG"
    else
        fail "missing generation-specific UART configuration"
    fi
    if [[ "$MODEL" == *"Raspberry Pi 5"* ]]; then
        if grep -qsFx 'dtparam=uart0=on' /boot/firmware/config.txt; then
            pass "Pi 5 UART0 is enabled"
        else
            fail "Pi 5 UART0 is not enabled"
        fi
    fi

    if grep -qsFx 'uinput' /etc/modules-load.d/v-link.conf && \
       grep -qsFx 'i2c-dev' /etc/modules-load.d/v-link.conf; then
        pass "uinput and i2c-dev are configured for boot"
    else
        fail "uinput or i2c-dev is missing from modules-load configuration"
    fi

    for required_group in plugdev dialout gpio i2c spi; do
        if id -nG "$TARGET_USER" | tr ' ' '\n' | grep -qx "$required_group"; then
            pass "$TARGET_USER belongs to $required_group"
        else
            fail "$TARGET_USER is missing hardware group $required_group"
        fi
    done
    for overlay in v-link.dtbo mcp2515-can1.dtbo mcp2515-can2.dtbo; do
        if [[ -f "/boot/firmware/overlays/$overlay" ]]; then
            pass "installed overlay: $overlay"
        else
            fail "missing overlay: $overlay"
        fi
    done

    if systemctl is-enabled --quiet v-link-can.service; then
        pass "v-link-can.service is enabled"
    else
        fail "v-link-can.service is not enabled"
    fi
    if [[ -x /usr/local/sbin/v-link-can-up && -x /usr/local/sbin/v-link-can-set ]]; then
        pass "CAN naming and profile-bitrate helpers are installed"
    else
        fail "a V-Link CAN helper is missing or not executable"
    fi
    if grep -qsF '/usr/local/sbin/v-link-can-set can1 125000 can2 250000' /etc/sudoers.d/v-link-lite && \
       grep -qsF '/usr/local/sbin/v-link-can-set can1 125000 can2 500000' /etc/sudoers.d/v-link-lite; then
        pass "CAN bitrate helper has restricted sudo permissions"
    else
        fail "CAN bitrate helper sudo permissions are incomplete"
    fi

    if grep -Eq "(^| )console=($SERIAL_CONSOLES)," /boot/firmware/cmdline.txt; then
        fail "serial console still owns a V-Link UART"
    else
        pass "serial console is disabled"
    fi

    if [[ "$PRE_REBOOT" == true ]]; then
        warn "CAN, UART and uinput device checks deferred until reboot"
    else
        if systemctl is-active --quiet v-link-can.service; then
            pass "v-link-can.service is active"
        else
            fail "v-link-can.service is not active"
        fi
        if [[ "$(basename -- "$(readlink -f /sys/class/net/can1/device 2>/dev/null || true)")" == spi0.1 ]]; then
            pass "can1 maps to physical SPI device spi0.1"
        else
            fail "can1 does not map to physical SPI device spi0.1"
        fi
        if [[ "$(basename -- "$(readlink -f /sys/class/net/can2/device 2>/dev/null || true)")" == spi0.2 ]]; then
            pass "can2 maps to physical SPI device spi0.2"
        else
            fail "can2 does not map to physical SPI device spi0.2"
        fi
        USER_CAN_CONFIG="$TARGET_HOME/.config/v-link/can.json"
        if [[ -f "$USER_CAN_CONFIG" ]]; then
            CONFIGURED_CAN2_BITRATE="$(python3 - "$USER_CAN_CONFIG" <<'PY' 2>/dev/null || true
import json
import sys

with open(sys.argv[1], encoding='utf-8') as config_file:
    config = json.load(config_file)

for interface in config.get('interfaces', []):
    if interface.get('channel') == 'can2':
        print(int(interface['bitrate']))
        break
PY
)"
            if [[ "$CONFIGURED_CAN2_BITRATE" == 250000 || "$CONFIGURED_CAN2_BITRATE" == 500000 ]]; then
                EXPECTED_CAN2_BITRATE="$CONFIGURED_CAN2_BITRATE"
            else
                fail "saved profile has an invalid can2 bitrate"
                EXPECTED_CAN2_BITRATE=""
            fi
            for interface in can1 can2; do
                if ip -details link show "$interface" 2>/dev/null | grep -qE '<[^>]*UP[^>]*>'; then
                    pass "$interface is present and UP"
                else
                    fail "$interface is missing or DOWN after profile selection"
                fi
            done
            if ip -details link show can1 2>/dev/null | grep -q 'bitrate 125000'; then
                pass "can1 bitrate is 125000"
            else
                fail "can1 bitrate is not 125000"
            fi
            if [[ -n "$EXPECTED_CAN2_BITRATE" ]] && \
               ip -details link show can2 2>/dev/null | grep -q "bitrate $EXPECTED_CAN2_BITRATE"; then
                pass "can2 bitrate matches the profile: $EXPECTED_CAN2_BITRATE"
            else
                fail "can2 bitrate does not match the saved profile"
            fi
        else
            for interface in can1 can2; do
                if ip link show "$interface" >/dev/null 2>&1 && \
                   ! ip link show "$interface" | grep -qE '<[^>]*UP[^>]*>'; then
                    pass "$interface is present and safely DOWN until a profile is selected"
                else
                    fail "$interface must remain DOWN until a vehicle profile is selected"
                fi
            done
        fi
        if [[ -e /dev/uinput ]] && runuser -u "$TARGET_USER" -- test -w /dev/uinput; then
            pass "$TARGET_USER can write to /dev/uinput"
        else
            fail "/dev/uinput is missing or not writable by $TARGET_USER"
        fi
        if [[ -e /dev/i2c-1 ]]; then
            pass "/dev/i2c-1 is present"
        else
            fail "/dev/i2c-1 is missing"
        fi
        if [[ -n "$EXPECTED_UART" && -e "$EXPECTED_UART" ]]; then
            pass "V-Link serial device is present: $EXPECTED_UART"
        else
            fail "V-Link serial device is missing: $EXPECTED_UART"
        fi
        if [[ -n "$LIN_PORT" ]]; then
            if [[ -e "$LIN_PORT" ]] && runuser -u "$TARGET_USER" -- test -r "$LIN_PORT" && \
               runuser -u "$TARGET_USER" -- test -w "$LIN_PORT"; then
                pass "$TARGET_USER can access the external LIN port: $LIN_PORT"
            else
                fail "external LIN port is missing or inaccessible: $LIN_PORT"
            fi
        fi
    fi

    if [[ "$MODEL" == *"Raspberry Pi 3"* ]]; then
        if systemctl is-enabled --quiet hciuart.service 2>/dev/null; then
            fail "hciuart is still enabled and can claim the Pi 3 RTI UART"
        else
            pass "hciuart is disabled for the Pi 3 RTI UART"
        fi
        warn "Pi 3 integrated Bluetooth is unavailable"
        if [[ -z "$LIN_PORT" ]]; then
            warn "Pi 3 simultaneous RTI + LIN SWC requires --lin-port with an external USB-UART"
        fi
    fi
fi

printf '\nResult: %d failure(s), %d warning(s)\n' "$FAILURES" "$WARNINGS"
if ((FAILURES)); then
    exit 1
fi

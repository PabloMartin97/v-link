#!/usr/bin/env bash
# V-Link Lite maintenance UI. Runs as the kiosk user, including from SSH.
set -uo pipefail
umask 077

STARTUP=false
case "${1:-}" in
    '') [[ $# -eq 0 ]] || exit 2 ;;
    --startup) [[ $# -eq 1 ]] || exit 2; STARTUP=true ;;
    *) printf 'Usage: v-link-lite-setup [--startup]\n' >&2; exit 2 ;;
esac
if [[ ! -t 0 || ! -t 1 ]]; then
    printf 'V-Link Lite Setup requires an interactive terminal.\n' >&2
    exit 2
fi
if [[ $EUID -eq 0 ]]; then
    printf 'Run V-Link Lite Setup as the kiosk user, not root.\n' >&2
    exit 2
fi

USER_ID="$(id -u)"
USER_NAME="$(id -un)"
USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6)"
if [[ -z "$USER_HOME" || ! -d "$USER_HOME" ]]; then
    printf 'Could not determine the current user home directory.\n' >&2
    exit 2
fi
RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$USER_ID}"
if [[ ! -d "$RUNTIME_DIR" || ! -O "$RUNTIME_DIR" || \
      "$(stat -c '%a' "$RUNTIME_DIR" 2>/dev/null)" != 700 ]]; then
    RUNTIME_DIR="$USER_HOME/.local/state/v-link-lite-setup"
    if [[ -L "$RUNTIME_DIR" ]]; then
        printf 'Unsafe Setup state directory.\n' >&2
        exit 2
    fi
    install -d -m 0700 "$RUNTIME_DIR" || exit 2
fi
if [[ ! -O "$RUNTIME_DIR" || "$(stat -c '%a' "$RUNTIME_DIR" 2>/dev/null)" != 700 ]]; then
    printf 'Setup runtime directory must be private to this user.\n' >&2
    exit 2
fi
if [[ -S "$RUNTIME_DIR/bus" && -z "${DBUS_SESSION_BUS_ADDRESS:-}" ]]; then
    export DBUS_SESSION_BUS_ADDRESS="unix:path=$RUNTIME_DIR/bus"
fi
if [[ -d "/run/user/$USER_ID" && -O "/run/user/$USER_ID" ]]; then
    export XDG_RUNTIME_DIR="/run/user/$USER_ID"
fi

exec 9>"$RUNTIME_DIR/v-link-lite-setup.lock" || exit 2
if ! flock -n 9; then
    printf 'V-Link Lite Setup is already running.\n' >&2
    [[ "$STARTUP" == true ]] && exit 22
    exit 0
fi
TEMP_FILE="$(mktemp "$RUNTIME_DIR/v-link-lite-setup.XXXXXX")" || exit 2
trap 'rm -f -- "$TEMP_FILE"' EXIT

message() {
    whiptail --title 'V-Link Lite Setup' --msgbox "$1" 15 76
}

menu() {
    whiptail --title 'V-Link Lite Setup' --cancel-button Back \
        --menu "$1" 22 78 12 "${@:2}" 3>&1 1>&2 2>&3
}

view_command() {
    local title="$1"
    shift
    if ! "$@" >"$TEMP_FILE" 2>&1; then
        printf '\nCommand failed or is unavailable in this session.\n' >>"$TEMP_FILE"
    fi
    whiptail --title "$title" --textbox "$TEMP_FILE" 23 90
}

user_service_state() {
    local state
    state="$(systemctl --user is-active "$1" 2>/dev/null)" || true
    printf '%s\n' "${state:-unavailable}"
}

system_service_state() {
    local state
    state="$(systemctl is-active "$1" 2>/dev/null)" || true
    printf '%s\n' "${state:-unavailable}"
}

vlink_state() {
    user_service_state v-link.service
}

network_summary() {
    printf 'NetworkManager devices:\n'
    if command -v nmcli >/dev/null 2>&1; then
        nmcli -f DEVICE,TYPE,STATE,CONNECTION device status 2>&1
    else
        printf 'NetworkManager/nmcli unavailable\n'
    fi
    printf '\nIPv4 addresses:\n'
    ip -brief -4 address show 2>&1 || true
}

network_menu() {
    local choice
    while true; do
        choice="$(menu 'Network' \
            status 'Ethernet, Wi-Fi, connection and IP' \
            configure 'Configure network with nmtui' \
            back 'Back')" || return 0
        case "$choice" in
            status) view_command Network network_summary ;;
            configure)
                if command -v nmtui >/dev/null 2>&1; then
                    clear
                    nmtui || message 'nmtui exited with an error.'
                    view_command Network network_summary
                else
                    message 'nmtui is unavailable. Install NetworkManager TUI support.'
                fi
                ;;
            back) return 0 ;;
        esac
    done
}

audio_ready() {
    if [[ ! -d "/run/user/$USER_ID" || ! -S "/run/user/$USER_ID/bus" ]]; then
        return 1
    fi
    systemctl --user start pipewire.service wireplumber.service >/dev/null 2>&1 || true
    systemctl --user start pipewire-pulse.service >/dev/null 2>&1 || true
    command -v wpctl >/dev/null 2>&1 && timeout 3 wpctl status >/dev/null 2>&1
}

audio_nodes() {
    local kind="$1"
    # pw-dump provides stable JSON; Python's standard library supplies human labels.
    timeout 4 pw-dump 2>/dev/null | python3 -c '
import json, sys
kind = sys.argv[1]
try:
    objects = json.load(sys.stdin)
except (ValueError, OSError):
    raise SystemExit(1)
for obj in objects:
    props = (obj.get("info") or {}).get("props") or {}
    if props.get("media.class") != kind:
        continue
    node_id = obj.get("id")
    if not isinstance(node_id, int):
        continue
    name = next((str(props[key]) for key in
        ("node.description", "node.nick", "device.description", "node.name")
        if props.get(key)), "Audio device")
    print(f"{node_id}\t{name.replace(chr(9), chr(32)).replace(chr(10), chr(32))}")
' "$kind"
}

select_audio_node() {
    local kind="$1" choice line id name
    local -a options=()
    if ! nodes="$(audio_nodes "$kind")"; then
        message 'Unable to enumerate PipeWire audio devices.'
        return
    fi
    while IFS=$'\t' read -r id name; do
        [[ "$id" =~ ^[0-9]+$ ]] || continue
        options+=("$id" "$name")
    done <<<"$nodes"
    if ((${#options[@]} == 0)); then
        message 'No audio devices of this type are available.'
        return
    fi
    choice="$(menu "Select default ${kind#Audio/}" "${options[@]}")" || return
    [[ "$choice" =~ ^[0-9]+$ ]] || return
    if wpctl set-default "$choice"; then
        message 'Default audio device updated.'
    else
        message 'Could not change the default audio device.'
    fi
}

set_audio_volume() {
    local target="$1" value
    value="$(whiptail --title 'V-Link Lite Setup' --inputbox \
        'Volume (0-100 percent):' 10 65 '75' 3>&1 1>&2 2>&3)" || return
    if [[ ! "$value" =~ ^([0-9]|[1-9][0-9]|100)$ ]]; then
        message 'Enter a whole number from 0 to 100.'
        return
    fi
    if wpctl set-volume "$target" "$value%"; then
        message "Volume set to $value%."
    else
        message 'Could not change volume; check that a default device exists.'
    fi
}

test_audio() {
    local result=0
    if command -v pw-play >/dev/null 2>&1 && \
       [[ -r /usr/share/sounds/alsa/Front_Center.wav ]]; then
        timeout 6 pw-play /usr/share/sounds/alsa/Front_Center.wav >"$TEMP_FILE" 2>&1 || result=$?
    elif command -v speaker-test >/dev/null 2>&1; then
        timeout 6 speaker-test -c 2 -t sine -s 1 >"$TEMP_FILE" 2>&1 || result=$?
    else
        message 'No audio test utility is available.'
        return
    fi
    if [[ $result -eq 0 ]]; then
        message 'Audio test completed.'
    else
        message "Audio test could not complete (status $result). See PipeWire status."
    fi
}

audio_menu() {
    local choice
    if ! audio_ready; then
        message 'Audio session unavailable. A running user PipeWire session is required.'
        return
    fi
    while true; do
        choice="$(menu 'Audio' \
            output 'Default output device' input 'Default input device' \
            output_volume 'Output volume' input_volume 'Input volume' \
            test 'Test output' status 'Show PipeWire status' back 'Back')" || return 0
        case "$choice" in
            output) select_audio_node Audio/Sink ;;
            input) select_audio_node Audio/Source ;;
            output_volume) set_audio_volume @DEFAULT_AUDIO_SINK@ ;;
            input_volume) set_audio_volume @DEFAULT_AUDIO_SOURCE@ ;;
            test) test_audio ;;
            status) view_command 'PipeWire status' wpctl status ;;
            back) return 0 ;;
        esac
    done
}

display_status() {
    if [[ -z "${WAYLAND_DISPLAY:-}" || ! -S "${XDG_RUNTIME_DIR:-/nonexistent}/$WAYLAND_DISPLAY" ]]; then
        printf 'Wayland display unavailable in this session.\n'
        return
    fi
    wlr-randr 2>&1 || printf 'Could not query Wayland outputs.\n'
}

storage_status() {
    printf 'Storage devices and mounts:\n'
    lsblk -o NAME,LABEL,FSTYPE,SIZE,TRAN,MOUNTPOINT 2>&1 || true
    printf '\nudisks2: %s\n' "$(system_service_state udisks2.service)"
    if pgrep -u "$USER_ID" -x udiskie >/dev/null 2>&1; then
        printf 'udiskie: running\n'
    else
        printf 'udiskie: not running\n'
    fi
}

vlink_logs() {
    journalctl --user -u v-link.service -n 80 --no-pager 2>&1
}

vlink_menu() {
    local choice action
    while true; do
        if [[ "$STARTUP" == true ]]; then
            choice="$(menu "V-Link starts only after Continue (now: $(vlink_state))" \
                status 'Show service status' logs 'View recent log' back 'Back')" || return 0
        else
            choice="$(menu "V-Link service: $(vlink_state)" \
                start 'Start V-Link' stop 'Stop V-Link' restart 'Restart V-Link' \
                status 'Show service status' logs 'View recent log' back 'Back')" || return 0
        fi
        case "$choice" in
            start|stop|restart)
                action="$choice"
                if systemctl --user "$action" v-link.service >"$TEMP_FILE" 2>&1; then
                    message "V-Link $action completed."
                else
                    message "V-Link $action failed. Check recent logs."
                fi
                ;;
            status) view_command 'V-Link service' systemctl --user status v-link.service --no-pager ;;
            logs) view_command 'V-Link recent log' vlink_logs ;;
            back) return 0 ;;
        esac
    done
}

diagnostics() {
    local internet='unavailable' media_count=0
    if command -v curl >/dev/null 2>&1 && \
       curl --head --silent --fail --output /dev/null \
           --connect-timeout 2 --max-time 3 https://www.debian.org/; then
        internet=OK
    fi
    if command -v findmnt >/dev/null 2>&1; then
        media_count="$(findmnt -rn -o TARGET 2>/dev/null | awk -v u="$USER_NAME" \
            'index($0,"/run/media/" u "/")==1 || index($0,"/media/" u "/")==1 {n++} END {print n+0}')"
    fi
    printf 'NetworkManager: %s\n' "$(system_service_state NetworkManager.service)"
    printf 'Internet: %s\n' "$internet"
    printf 'PipeWire: %s\n' "$(user_service_state pipewire.service)"
    printf 'WirePlumber: %s\n' "$(user_service_state wireplumber.service)"
    if [[ -n "${WAYLAND_DISPLAY:-}" && -S "${XDG_RUNTIME_DIR:-/nonexistent}/$WAYLAND_DISPLAY" ]]; then
        printf 'Wayland: OK\n'
    else
        printf 'Wayland: unavailable\n'
    fi
    printf 'V-Link service: %s\n' "$(vlink_state)"
    if pgrep -u "$USER_ID" -x chromium >/dev/null 2>&1; then
        printf 'Chromium: running\n'
    else
        printf 'Chromium: not running\n'
    fi
    printf 'udisks2: %s\n' "$(system_service_state udisks2.service)"
    if pgrep -u "$USER_ID" -x udiskie >/dev/null 2>&1; then
        printf 'udiskie: running\n'
    else
        printf 'udiskie: not running\n'
    fi
    printf 'Local media mounts: %s\n' "$media_count"
    printf 'IP address: %s\n' "$(ip -o -4 address show scope global 2>/dev/null | awk '{print $4}' | paste -sd, -)"
    printf 'Uptime: %s\n' "$(uptime -p 2>/dev/null || printf 'unavailable')"
}

power_action() {
    local action="$1" code command_path
    case "$action" in
        reboot) code=20; command_path=/usr/sbin/reboot ;;
        shutdown) code=21; command_path=/usr/sbin/shutdown ;;
        *) return 1 ;;
    esac
    if ! whiptail --title 'V-Link Lite Setup' --yesno \
        "Confirm $action?" 10 60; then
        return 0
    fi
    if [[ "$action" == reboot ]]; then
        sudo -n "$command_path" >"$TEMP_FILE" 2>&1
    else
        sudo -n "$command_path" -h now >"$TEMP_FILE" 2>&1
    fi
    if [[ $? -eq 0 ]]; then
        exit "$code"
    fi
    message "Could not $action. Check Lite sudoers permissions."
}

if ! command -v whiptail >/dev/null 2>&1; then
    printf 'V-Link Lite Setup requires whiptail.\n' >&2
    exit 2
fi

while true; do
    choice="$(menu 'Choose a maintenance task' \
        network 'Network' audio 'Audio' display 'Display' storage 'Storage / USB' \
        vlink 'V-Link' diagnostics 'Diagnostics' \
        continue 'Continue to V-Link / Exit Setup' \
        reboot 'Reboot' shutdown 'Shutdown')" || exit 0
    case "$choice" in
        network) network_menu ;;
        audio) audio_menu ;;
        display) view_command Display display_status ;;
        storage) view_command 'Storage / USB' storage_status ;;
        vlink) vlink_menu ;;
        diagnostics) view_command Diagnostics diagnostics ;;
        continue) exit 0 ;;
        reboot|shutdown) power_action "$choice" ;;
    esac
done

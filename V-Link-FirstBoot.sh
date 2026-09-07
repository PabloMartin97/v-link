#!/usr/bin/env bash
set -Eeuo pipefail

# This script is placed on the Raspberry Pi OS Bookworm boot partition by the
# SD preparation helper. It runs in Raspberry Pi Imager's early first-boot
# environment, lets the original Imager firstrun complete, then stages the
# interactive V-Link installer for the next normal boot.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BOOT_ROOT=/boot/firmware
if [[ ! -f "$BOOT_ROOT/cmdline.txt" ]]; then
    BOOT_ROOT=/boot
fi
CONFIG_FILE="$BOOT_ROOT/v-link-firstboot.conf"
if [[ ! -r "$CONFIG_FILE" && -r "$SCRIPT_DIR/v-link-firstboot.conf" ]]; then
    CONFIG_FILE="$SCRIPT_DIR/v-link-firstboot.conf"
fi
INSTALLER_SECOND_BOOT=/boot/firmware/Install-Lite.sh
UNIT=/etc/systemd/system/v-link-firstboot.service

log() {
    printf '[V-Link first boot] %s\n' "$*"
}

die() {
    printf '[V-Link first boot] ERROR: %s\n' "$*" >&2
    exit 1
}

recover_console_on_error() {
    local status=$?
    if ((status != 0)); then
        printf '[V-Link first boot] Falling back to the normal console\n' >&2
        systemctl --no-block isolate multi-user.target >/dev/null 2>&1 || true
    fi
}
trap recover_console_on_error EXIT

ORIGINAL_SYSTEMD_RUN=""
if [[ -r "$CONFIG_FILE" ]]; then
    # The preparation helper writes only a validated absolute /boot path.
    # shellcheck disable=SC1090
    source "$CONFIG_FILE"
fi

# Raspberry Pi Imager's firstrun normally removes its systemd.run arguments.
# Do the same here as a fallback so this bootstrap can never loop forever.
# Bookworm mounts the boot partition at /boot/firmware during a normal boot,
# while the early first-boot environment may expose it directly under /boot.
CMDLINE_FILE="$BOOT_ROOT/cmdline.txt"
[[ -f "$CMDLINE_FILE" ]] || die "could not locate the boot cmdline.txt"
sed -E -i \
    's#(^| )init=/usr/lib/raspberrypi-sys-mods/firstboot##g; s/(^| )systemd\.run=[^ ]+//g; s/(^| )systemd\.run_success_action=[^ ]+//g; s/(^| )systemd\.unit=kernel-command-line\.target//g; s/  +/ /g; s/^ //; s/ $//' \
    "$CMDLINE_FILE"
if grep -Eq '(^| )(init=/usr/lib/raspberrypi-sys-mods/firstboot|systemd\.(run|run_success_action|unit)=)' "$CMDLINE_FILE"; then
    die "could not remove temporary first-boot arguments from $CMDLINE_FILE"
fi

if [[ -n "$ORIGINAL_SYSTEMD_RUN" ]]; then
    case "$ORIGINAL_SYSTEMD_RUN" in
        /boot/*) ;;
        *) die "unsafe original first-run path: $ORIGINAL_SYSTEMD_RUN" ;;
    esac
    ORIGINAL_RUN_FILE="$ORIGINAL_SYSTEMD_RUN"
    if [[ ! -f "$ORIGINAL_RUN_FILE" ]]; then
        ORIGINAL_RUN_FILE="$BOOT_ROOT/${ORIGINAL_SYSTEMD_RUN#/boot/}"
    fi
    if [[ "$ORIGINAL_SYSTEMD_RUN" != /boot/V-Link-FirstBoot.sh && -f "$ORIGINAL_RUN_FILE" ]]; then
        log "Running Raspberry Pi Imager first-run customisation"
        /bin/bash "$ORIGINAL_RUN_FILE"
    fi
fi

TARGET_USER="$(getent passwd 1000 | cut -d: -f1 || true)"
[[ -n "$TARGET_USER" ]] || die "no UID 1000 user exists; configure a username in Raspberry Pi Imager before first boot"

if [[ ! -f "$INSTALLER_SECOND_BOOT" && ! -f "$SCRIPT_DIR/Install-Lite.sh" ]]; then
    die "missing second-boot installer"
fi

cat >"$UNIT" <<EOF
[Unit]
Description=V-Link interactive first-boot installer
After=systemd-user-sessions.service NetworkManager.service
Wants=NetworkManager.service
Conflicts=getty@tty1.service

[Service]
Type=oneshot
ExecStart=$INSTALLER_SECOND_BOOT --first-boot --user $TARGET_USER
StandardInput=tty-force
StandardOutput=tty
StandardError=tty
TTYPath=/dev/tty1
TTYReset=yes
TTYVHangup=yes
TTYVTDisallocate=yes
RemainAfterExit=no
ExecStopPost=-/bin/systemctl --no-block start getty@tty1.service

[Install]
WantedBy=multi-user.target
EOF

systemctl enable v-link-firstboot.service >/dev/null
log "Interactive V-Link installer staged"
log "Continuing into the normal boot; the installer will appear on tty1"
systemctl --no-block isolate multi-user.target

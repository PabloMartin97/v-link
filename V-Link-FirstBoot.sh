#!/usr/bin/env bash
set -Eeuo pipefail

# This script is placed on the Raspberry Pi OS Bookworm boot partition by the
# SD preparation helper. It runs in Raspberry Pi Imager's early first-boot
# environment, lets the original Imager firstrun complete, then stages the
# interactive V-Link installer for the next normal boot.

BOOT_ROOT=/boot
CONFIG_FILE="$BOOT_ROOT/v-link-firstboot.conf"
INSTALLER_SECOND_BOOT=/boot/firmware/Install-Lite.sh
UNIT=/etc/systemd/system/v-link-firstboot.service

log() {
    printf '[V-Link first boot] %s\n' "$*"
}

die() {
    printf '[V-Link first boot] ERROR: %s\n' "$*" >&2
    exit 1
}

ORIGINAL_SYSTEMD_RUN=""
if [[ -r "$CONFIG_FILE" ]]; then
    # The preparation helper writes only a validated absolute /boot path.
    # shellcheck disable=SC1090
    source "$CONFIG_FILE"
fi

if [[ -n "$ORIGINAL_SYSTEMD_RUN" ]]; then
    case "$ORIGINAL_SYSTEMD_RUN" in
        /boot/*) ;;
        *) die "unsafe original first-run path: $ORIGINAL_SYSTEMD_RUN" ;;
    esac
    if [[ "$ORIGINAL_SYSTEMD_RUN" != /boot/V-Link-FirstBoot.sh && -x "$ORIGINAL_SYSTEMD_RUN" ]]; then
        log "Running Raspberry Pi Imager first-run customisation"
        "$ORIGINAL_SYSTEMD_RUN"
    fi
fi

TARGET_USER="$(getent passwd 1000 | cut -d: -f1 || true)"
[[ -n "$TARGET_USER" ]] || die "no UID 1000 user exists; configure a username in Raspberry Pi Imager before first boot"

# Raspberry Pi Imager's firstrun normally removes its systemd.run arguments.
# Do the same here as a fallback so this bootstrap can never loop forever.
if [[ -f "$BOOT_ROOT/cmdline.txt" ]]; then
    sed -E -i \
        's/(^| )systemd\.run=[^ ]+//g; s/(^| )systemd\.run_success_action=[^ ]+//g; s/(^| )systemd\.unit=kernel-command-line\.target//g; s/  +/ /g; s/^ //; s/ $//' \
        "$BOOT_ROOT/cmdline.txt"
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

[Install]
WantedBy=multi-user.target
EOF

systemctl enable v-link-firstboot.service >/dev/null
log "Interactive V-Link installer staged for the next boot"
log "The system will reboot once, then the installer will appear on tty1"

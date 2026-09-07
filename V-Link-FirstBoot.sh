#!/usr/bin/env bash
set -Eeuo pipefail

# This script is called near the end of Raspberry Pi Imager's firstrun.sh. It
# only stages the interactive V-Link installer as a normal systemd service;
# it never changes the kernel target or controls the current boot.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BOOT_ROOT=/boot/firmware
if [[ ! -f "$BOOT_ROOT/cmdline.txt" ]]; then
    BOOT_ROOT=/boot
fi
INSTALLER_SECOND_BOOT=/boot/firmware/Install-Lite.sh
UNIT=/etc/systemd/system/v-link-firstboot.service
WAIT_UNIT=/etc/systemd/system/v-link-firstboot-wait.service
WAIT_HELPER=/usr/local/sbin/v-link-firstboot-wait
INSTALL_HELPER=/usr/local/sbin/v-link-firstboot-installer

log() {
    printf '[V-Link first boot] %s\n' "$*"
}

die() {
    printf '[V-Link first boot] ERROR: %s\n' "$*" >&2
    exit 1
}

RUNNING_FROM_CMDLINE=false
if grep -q 'systemd.run=/boot/V-Link-FirstBoot.sh' /proc/cmdline; then
    RUNNING_FROM_CMDLINE=true
    CMDLINE_FILE="$BOOT_ROOT/cmdline.txt"
    [[ -f "$CMDLINE_FILE" ]] || die "could not locate the boot cmdline.txt"
    sed -E -i \
        's/(^| )systemd\.run=\/boot\/V-Link-FirstBoot\.sh//g; s/(^| )systemd\.run_success_action=[^ ]+//g; s/(^| )systemd\.run_failure_action=[^ ]+//g; s/(^| )systemd\.unit=kernel-command-line\.target//g; s/(^| )systemd\.wants=kernel-command-line\.target//g; s/  +/ /g; s/^ //; s/ $//' \
        "$CMDLINE_FILE"
fi

if [[ ! -f "$INSTALLER_SECOND_BOOT" && ! -f "$SCRIPT_DIR/Install-Lite.sh" ]]; then
    die "missing second-boot installer"
fi

cat >"$INSTALL_HELPER" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail

target_user="$(getent passwd 1000 | cut -d: -f1 || true)"
[[ -n "$target_user" ]] || {
    printf '[V-Link first boot] ERROR: no UID 1000 user exists\n' >&2
    exit 1
}
exec /boot/firmware/Install-Lite.sh --first-boot --user "$target_user"
EOF
chmod 0755 "$INSTALL_HELPER"

cat >"$WAIT_HELPER" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail

while ! getent passwd 1000 >/dev/null; do
    sleep 2
done
while systemctl is-active --quiet userconfig.service; do
    sleep 2
done
exec systemctl --no-block start v-link-firstboot.service
EOF
chmod 0755 "$WAIT_HELPER"

cat >"$UNIT" <<EOF
[Unit]
Description=V-Link interactive first-boot installer
After=systemd-user-sessions.service NetworkManager.service
Wants=NetworkManager.service
Conflicts=getty@tty1.service

[Service]
Type=oneshot
ExecStart=$INSTALL_HELPER
StandardInput=tty-force
StandardOutput=tty
StandardError=tty
TTYPath=/dev/tty1
TTYReset=yes
TTYVHangup=yes
TTYVTDisallocate=yes
RemainAfterExit=no
ExecStopPost=-/bin/systemctl --no-block start getty@tty1.service

EOF

cat >"$WAIT_UNIT" <<EOF
[Unit]
Description=Wait for a local user before starting the V-Link installer
After=systemd-user-sessions.service userconfig.service

[Service]
Type=simple
ExecStart=$WAIT_HELPER
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable v-link-firstboot-wait.service >/dev/null
log "Interactive V-Link installer staged; waiting for a UID 1000 user"
if [[ "$RUNNING_FROM_CMDLINE" == true ]]; then
    log "Rebooting into the normal system to create or detect the local user"
fi

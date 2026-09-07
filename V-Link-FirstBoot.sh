#!/usr/bin/env bash
set -Eeuo pipefail

# This script is called near the end of Raspberry Pi Imager's firstrun.sh, or
# once through systemd.run when Imager did not create a firstrun.sh. It only
# stages the interactive installer for the next normal boot.

readonly V_LINK_FIRST_BOOT_PROTOCOL=2
SYSTEM_ROOT="${V_LINK_FIRST_BOOT_ROOT:-}"
PROC_CMDLINE="${V_LINK_PROC_CMDLINE:-/proc/cmdline}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/cmdline.txt" ]]; then
    BOOT_ROOT="$SCRIPT_DIR"
elif [[ -f /boot/firmware/cmdline.txt ]]; then
    BOOT_ROOT=/boot/firmware
elif [[ -f /boot/cmdline.txt ]]; then
    BOOT_ROOT=/boot
else
    printf '[V-Link first boot] ERROR: could not locate cmdline.txt\n' >&2
    exit 1
fi
INSTALLER_SOURCE="$SCRIPT_DIR/Install-Lite.sh"
INSTALLER_STAGED="$SYSTEM_ROOT/usr/local/libexec/v-link-install-lite"
UNIT="$SYSTEM_ROOT/etc/systemd/system/v-link-firstboot.service"
WAIT_UNIT="$SYSTEM_ROOT/etc/systemd/system/v-link-firstboot-wait.service"
WAIT_HELPER="$SYSTEM_ROOT/usr/local/sbin/v-link-firstboot-wait"
INSTALL_HELPER="$SYSTEM_ROOT/usr/local/sbin/v-link-firstboot-installer"
INSTALL_LOG="$SYSTEM_ROOT/var/log/v-link-firstboot-installer.log"
BOOT_LOG="$BOOT_ROOT/v-link-firstboot.log"

# A read-only boot partition must not prevent the cmdline cleanup attempt.
if : >>"$BOOT_LOG" 2>/dev/null; then
    exec >>"$BOOT_LOG" 2>&1 || true
fi

log() {
    printf '[V-Link first boot] %s\n' "$*"
}

die() {
    printf '[V-Link first boot] ERROR: %s\n' "$*" >&2
    exit 1
}

RUNNING_FROM_CMDLINE=false
if grep -Eq 'systemd\.run=/boot(/firmware)?/V-Link-FirstBoot\.sh' "$PROC_CMDLINE"; then
    RUNNING_FROM_CMDLINE=true
    CMDLINE_FILE="$BOOT_ROOT/cmdline.txt"
    CMDLINE_TEMP="$(mktemp "$BOOT_ROOT/.cmdline.v-link.XXXXXX")"
    sed -E \
        's#(^| )systemd\.run=/boot(/firmware)?/V-Link-FirstBoot\.sh##g; s/(^| )systemd\.run_success_action=[^ ]+//g; s/(^| )systemd\.run_failure_action=[^ ]+//g; s/(^| )systemd\.unit=kernel-command-line\.target//g; s/(^| )systemd\.wants=kernel-command-line\.target//g; s/  +/ /g; s/^ //; s/ $//' \
        "$CMDLINE_FILE" >"$CMDLINE_TEMP"
    if grep -Eq 'systemd\.(run|run_success_action|run_failure_action)=|systemd\.(unit|wants)=kernel-command-line\.target' \
            "$CMDLINE_TEMP"; then
        rm -f -- "$CMDLINE_TEMP"
        die "could not remove temporary first-boot arguments from $CMDLINE_FILE"
    fi
    mv -f "$CMDLINE_TEMP" "$CMDLINE_FILE"
fi

if [[ "$RUNNING_FROM_CMDLINE" == true ]]; then
    log "Temporary kernel command-line arguments removed"
fi

[[ -f "$INSTALLER_SOURCE" ]] || die "missing $INSTALLER_SOURCE"
install -d \
    "$(dirname -- "$INSTALLER_STAGED")" \
    "$(dirname -- "$INSTALL_HELPER")" \
    "$(dirname -- "$UNIT")" \
    "$(dirname -- "$INSTALL_LOG")"
install -m 0755 "$INSTALLER_SOURCE" "$INSTALLER_STAGED"
log "Installer staged at $INSTALLER_STAGED"

cat >"$INSTALL_HELPER" <<EOF
#!/usr/bin/env bash
set -Eeuo pipefail

target_user="\$(getent passwd 1000 | cut -d: -f1 || true)"
[[ -n "\$target_user" ]] || {
    printf '[V-Link first boot] ERROR: no UID 1000 user exists\n' >&2
    exit 1
}
"$INSTALLER_STAGED" --first-boot --user "\$target_user" 2>&1 | \
    tee -a "$INSTALL_LOG"
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
After=systemd-user-sessions.service userconfig.service NetworkManager.service
Wants=NetworkManager.service
Conflicts=getty@tty1.service display-manager.service lightdm.service

[Service]
Type=oneshot
ExecStartPre=-/bin/systemctl stop lightdm.service
ExecStartPre=-/usr/bin/chvt 1
ExecStart=$INSTALL_HELPER
StandardInput=tty-force
StandardOutput=tty
StandardError=tty
TTYPath=/dev/tty1
TTYReset=yes
TTYVHangup=yes
TTYVTDisallocate=no
RemainAfterExit=no
ExecStopPost=-/bin/systemctl --no-block start getty@tty1.service
ExecStopPost=-/usr/bin/chvt 1

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

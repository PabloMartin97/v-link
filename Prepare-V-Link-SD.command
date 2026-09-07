#!/bin/bash
set -Eeuo pipefail

REPOSITORY="PabloMartin97/v-link"
SOURCE_BRANCH="little-os-test"
INSTALLER_NAME="Install-Lite.sh"
BOOTSTRAP_NAME="V-Link-FirstBoot.sh"
CONFIG_NAME="v-link-firstboot.conf"
DEFAULT_BOOT_RUNTIME="/boot/firmware"

pause_and_exit() {
    local status="${1:-0}"
    printf '\nPress Return to close this window...'
    read -r _ || true
    exit "$status"
}

fail() {
    printf '\nERROR: %s\n' "$*" >&2
    pause_and_exit 1
}

printf '\n============================================================\n'
printf '              Prepare SD card for V-Link Lite\n'
printf '============================================================\n\n'
printf 'This helper prepares an already-flashed Raspberry Pi OS Lite\n'
printf 'Bookworm SD card so the V-Link installer starts automatically.\n\n'
printf 'Before continuing, use Raspberry Pi Imager OS Customisation to set:\n'
printf '  - a username and password\n'
printf '  - Wi-Fi credentials if you will not use Ethernet\n'
printf '  - optionally SSH\n\n'

candidates=()
for volume in /Volumes/*; do
    [[ -d "$volume" ]] || continue
    if [[ -f "$volume/cmdline.txt" && -f "$volume/config.txt" ]]; then
        candidates+=("$volume")
    fi
done

((${#candidates[@]} > 0)) || fail "No mounted Raspberry Pi boot partition was found. Reinsert the flashed SD card and try again."

if ((${#candidates[@]} == 1)); then
    BOOT_VOLUME="${candidates[0]}"
else
    printf 'Raspberry Pi boot partitions found:\n'
    for i in "${!candidates[@]}"; do
        printf '  %d) %s\n' "$((i + 1))" "${candidates[i]}"
    done
    while true; do
        printf 'Select the SD boot partition: '
        read -r choice
        if [[ "$choice" =~ ^[0-9]+$ ]] && ((choice >= 1 && choice <= ${#candidates[@]})); then
            BOOT_VOLUME="${candidates[choice - 1]}"
            break
        fi
        printf 'Invalid selection.\n'
    done
fi

printf '\nSelected: %s\n' "$BOOT_VOLUME"

CMDLINE="$BOOT_VOLUME/cmdline.txt"
ALREADY_PREPARED=false
if grep -Eq 'systemd\.run=/boot(/firmware)?/V-Link-FirstBoot\.sh' "$CMDLINE" || \
        [[ -f "$BOOT_VOLUME/$CONFIG_NAME" && -f "$CMDLINE.v-link-prep.bak" ]]; then
    ALREADY_PREPARED=true
    printf '\nUpdating an already prepared V-Link SD card.\n'
fi

TMPDIR_VLINK="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_VLINK"' EXIT

printf '\nDownloading the current V-Link first-boot files...\n'
/usr/bin/curl -fL --retry 3 \
    "https://raw.githubusercontent.com/$REPOSITORY/$SOURCE_BRANCH/$INSTALLER_NAME" \
    -o "$TMPDIR_VLINK/$INSTALLER_NAME" || fail "Could not download $INSTALLER_NAME"
/usr/bin/curl -fL --retry 3 \
    "https://raw.githubusercontent.com/$REPOSITORY/$SOURCE_BRANCH/$BOOTSTRAP_NAME" \
    -o "$TMPDIR_VLINK/$BOOTSTRAP_NAME" || fail "Could not download $BOOTSTRAP_NAME"

[[ -f "$CMDLINE.v-link-prep.bak" ]] || cp "$CMDLINE" "$CMDLINE.v-link-prep.bak"
cp "$TMPDIR_VLINK/$INSTALLER_NAME" "$BOOT_VOLUME/$INSTALLER_NAME"
cp "$TMPDIR_VLINK/$BOOTSTRAP_NAME" "$BOOT_VOLUME/$BOOTSTRAP_NAME"
chmod +x "$BOOT_VOLUME/$INSTALLER_NAME" "$BOOT_VOLUME/$BOOTSTRAP_NAME" 2>/dev/null || true

CMDLINE_TEXT="$(tr -d '\r\n' <"$CMDLINE")"
FIRSTRUN_RUNTIME="$(grep -oE 'systemd\.run=/boot(/firmware)?/firstrun\.sh' "$CMDLINE" | head -n1 | cut -d= -f2- || true)"
if [[ -z "$FIRSTRUN_RUNTIME" ]]; then
    FIRSTRUN_RUNTIME="$DEFAULT_BOOT_RUNTIME/firstrun.sh"
fi
BOOTSTRAP_RUNTIME="$(dirname -- "$FIRSTRUN_RUNTIME")/$BOOTSTRAP_NAME"
CMDLINE_TEXT="$(printf '%s\n' "$CMDLINE_TEXT" | sed -E \
    -e 's/(^| )systemd\.run=[^ ]+//g' \
    -e 's/(^| )systemd\.run_success_action=[^ ]+//g' \
    -e 's/(^| )systemd\.run_failure_action=[^ ]+//g' \
    -e 's/(^| )systemd\.unit=kernel-command-line\.target//g' \
    -e 's/(^| )systemd\.wants=kernel-command-line\.target//g' \
    -e 's/  +/ /g' \
    -e 's/^ //' \
    -e 's/ $//')"

if [[ -f "$BOOT_VOLUME/firstrun.sh" ]]; then
    CMDLINE_TEXT+=" systemd.run=$FIRSTRUN_RUNTIME systemd.run_success_action=reboot systemd.unit=kernel-command-line.target"
elif [[ ! -f "$BOOT_VOLUME/firstrun.sh" ]]; then
    BOOTSTRAP_RUNTIME="$DEFAULT_BOOT_RUNTIME/$BOOTSTRAP_NAME"
    CMDLINE_TEXT+=" systemd.run=$BOOTSTRAP_RUNTIME systemd.run_success_action=reboot systemd.run_failure_action=reboot systemd.unit=kernel-command-line.target"
fi
printf '%s\n' "$CMDLINE_TEXT" >"$CMDLINE"

if [[ -f "$BOOT_VOLUME/firstrun.sh" ]] && \
        ! grep -Eq '^/bin/bash /boot(/firmware)?/V-Link-FirstBoot\.sh$' "$BOOT_VOLUME/firstrun.sh"; then
    FIRSTRUN_TEMP="$TMPDIR_VLINK/firstrun.sh"
    awk -v bootstrap="$BOOTSTRAP_RUNTIME" '
        /^rm -f \/boot(\/firmware)?\/firstrun\.sh$/ && !inserted {
            print "# Stage the V-Link installer for the next normal boot."
            print "/bin/bash " bootstrap
            inserted=1
        }
        { print }
        END { if (!inserted) exit 1 }
    ' "$BOOT_VOLUME/firstrun.sh" >"$FIRSTRUN_TEMP" || \
        fail "Could not add the V-Link hook to Raspberry Pi Imager firstrun.sh"
    cp "$FIRSTRUN_TEMP" "$BOOT_VOLUME/firstrun.sh"
fi

printf '\nSD card prepared successfully.\n\n'
printf 'First boot flow:\n'
printf '  1. Raspberry Pi Imager applies any configured user/network settings.\n'
printf '  2. Without a configured user, Raspberry Pi OS first asks you to create one.\n'
printf '  3. V-Link Lite Installer then opens automatically on the screen.\n'
printf '  4. It checks for Internet, lets you choose the GitHub branch and hardware mode.\n'
printf '  5. After a successful installation the temporary installer removes itself.\n\n'
printf 'You can now eject the SD card and put it in the Raspberry Pi.\n'
pause_and_exit 0

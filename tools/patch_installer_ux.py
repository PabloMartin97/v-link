from pathlib import Path

path = Path('Install-Lite.sh')
text = path.read_text(encoding='utf-8')


def replace_once(old: str, new: str, label: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: expected one match, found {count}')
    text = text.replace(old, new, 1)


replace_once(
    'ASSUME_YES=false\nCONFIGURE_HARDWARE=true\nREBOOT=true\n',
    'ASSUME_YES=false\nCONFIGURE_HARDWARE=true\nHARDWARE_CHOICE_EXPLICIT=false\nSOURCE_CHOICE_EXPLICIT=false\nREBOOT=true\n',
    'state flags',
)

replace_once(
    '''Options:\n  --yes                 Accept all prompts.\n  --user USER           User that will run the kiosk (defaults to SUDO_USER).\n  --source-dir PATH     Install application files from a local checkout.\n  --ref REF             Download, build and install this Git branch or tag.\n  --lin-port PATH       Serial device for LIN controls (for example a stable\n                        /dev/serial/by-id/... USB-UART path on Pi 3).\n  --no-hardware         Skip overlays, CAN, UART, GPIO and udev setup.\n  --no-reboot           Do not reboot when installation finishes.\n  -h, --help            Show this help.\n''',
    '''Options:\n  --yes                 Non-interactive mode; accept defaults/prompts.\n  --user USER           User that will run the kiosk (defaults to SUDO_USER).\n  --source-dir PATH     Install application files from a local checkout.\n  --ref REF             Download, build and install this Git branch or tag.\n  --lin-port PATH       Serial device for LIN controls (for example a stable\n                        /dev/serial/by-id/... USB-UART path on Pi 3).\n  --hardware            Configure V-Link HAT/CAN/UART/GPIO without asking.\n  --no-hardware         UI-only mode; skip overlays, CAN, UART, GPIO and udev.\n  --no-reboot           Do not reboot when installation finishes.\n  -h, --help            Show this help.\n\nWithout --yes, --ref/--source-dir and --hardware/--no-hardware, the installer\nshows an installation plan, asks which hardware mode to use, and can list the\nrepository branches from GitHub for selection.\n''',
    'usage options',
)

confirm_anchor = '''confirm() {\n    local prompt="$1"\n    if [[ "$ASSUME_YES" == true ]]; then\n        return 0\n    fi\n\n    local reply\n    read -r -p "$prompt [y/N]: " reply\n    [[ "$reply" =~ ^[Yy]$ ]]\n}\n\n'''

ux_functions = r'''print_welcome() {
    cat <<'EOF'

============================================================
                    V-Link Lite Installer
============================================================
This installer configures Raspberry Pi OS Lite as a dedicated
V-Link kiosk. You will be shown the source, hardware mode and
important system changes before anything is installed.
EOF
}

fetch_github_branch_names() {
    local url="https://api.github.com/repos/$REPOSITORY/branches?per_page=100"
    local payload=""

    if command -v curl >/dev/null 2>&1; then
        payload="$(curl --fail --silent --show-error --location --retry 2 \
            --connect-timeout 10 --max-time 60 "$url")" || return 1
    elif command -v wget >/dev/null 2>&1; then
        payload="$(wget -qO- --timeout=60 "$url")" || return 1
    elif command -v python3 >/dev/null 2>&1; then
        payload="$(python3 -c 'import sys, urllib.request; print(urllib.request.urlopen(sys.argv[1], timeout=60).read().decode())' "$url")" || return 1
    else
        return 1
    fi

    printf '%s\n' "$payload" \
        | grep -oE '"name"[[:space:]]*:[[:space:]]*"[^"]+"' \
        | sed -E 's/^"name"[[:space:]]*:[[:space:]]*"(.*)"$/\1/' \
        | sort -u
}

select_github_branch() {
    local branches=()
    local choice=""
    local index default_index=""

    log "Loading branches from GitHub"
    mapfile -t branches < <(fetch_github_branch_names || true)

    if ((${#branches[@]} == 0)); then
        printf '\nCould not retrieve the branch list from GitHub.\n'
        read -r -p 'Enter a branch or tag manually: ' SOURCE_REF
        [[ -n "$SOURCE_REF" ]] || die "a GitHub branch or tag is required"
        return
    fi

    printf '\nAvailable GitHub branches:\n'
    for index in "${!branches[@]}"; do
        if [[ "${branches[index]}" == little-os-test ]]; then
            default_index=$((index + 1))
            printf '  %2d) %-36s  [recommended Lite test]\n' "$((index + 1))" "${branches[index]}"
        else
            printf '  %2d) %s\n' "$((index + 1))" "${branches[index]}"
        fi
    done

    while true; do
        if [[ -n "$default_index" ]]; then
            read -r -p "Select branch number [$default_index]: " choice
            [[ -n "$choice" ]] || choice="$default_index"
        else
            read -r -p 'Select branch number: ' choice
        fi

        if [[ "$choice" =~ ^[0-9]+$ ]] && \
           ((choice >= 1 && choice <= ${#branches[@]})); then
            SOURCE_REF="${branches[choice - 1]}"
            return
        fi
        printf 'Please enter a number between 1 and %d.\n' "${#branches[@]}"
    done
}

select_install_source() {
    local local_checkout="$1"
    local choice=""

    printf '\nChoose what V-Link source to install:\n'
    printf '  1) Latest published release  [recommended for normal use]\n'
    printf '  2) GitHub branch             [development / testing]\n'
    if [[ -n "$local_checkout" ]]; then
        printf '  3) This local checkout       [%s]\n' "$local_checkout"
    fi

    while true; do
        read -r -p 'Selection [1]: ' choice
        [[ -n "$choice" ]] || choice=1
        case "$choice" in
            1)
                SOURCE_DIR=""
                SOURCE_REF=""
                return
                ;;
            2)
                select_github_branch
                return
                ;;
            3)
                if [[ -n "$local_checkout" ]]; then
                    SOURCE_DIR="$local_checkout"
                    SOURCE_REF=""
                    return
                fi
                ;;
        esac
        printf 'Invalid selection.\n'
    done
}

select_hardware_mode() {
    local choice=""

    printf '\nWill this Raspberry Pi use the V-Link vehicle hardware/HAT?\n'
    printf '  1) Yes - configure CAN, UART, GPIO, SPI/I2C and device-tree overlays\n'
    printf '  2) No  - UI/CarPlay/media test only; do not touch vehicle hardware setup\n'

    while true; do
        read -r -p 'Selection: ' choice
        case "$choice" in
            1) CONFIGURE_HARDWARE=true; return ;;
            2) CONFIGURE_HARDWARE=false; return ;;
            *) printf 'Please select 1 or 2.\n' ;;
        esac
    done
}

show_install_plan() {
    local source_description
    if [[ -n "$SOURCE_DIR" ]]; then
        source_description="Local checkout: $SOURCE_DIR"
    elif [[ -n "$SOURCE_REF" ]]; then
        source_description="GitHub branch/tag: $SOURCE_REF"
    else
        source_description="Latest published release"
    fi

    printf '\n============================================================\n'
    printf 'Installation plan\n'
    printf '============================================================\n'
    printf 'Source:   %s\n' "$source_description"
    printf 'User:     %s\n' "$TARGET_USER"
    printf 'Hardware: %s\n' "$([[ "$CONFIGURE_HARDWARE" == true ]] && printf 'ENABLED' || printf 'DISABLED')"
    printf 'Reboot:   %s\n' "$([[ "$REBOOT" == true ]] && printf 'yes' || printf 'no')"

    if [[ -n "$SOURCE_REF" ]]; then
        cat <<EOF

DEVELOPMENT WARNING
  You selected '$SOURCE_REF' directly from GitHub. Branch builds may contain
  unfinished or unreviewed changes and the frontend will be built on this Pi.
EOF
    fi

    cat <<'EOF'

The installer will make these major system changes:
  - install a minimal Wayland desktop (labwc + LightDM) and set graphical boot
  - install Chromium kiosk plus PipeWire/WirePlumber audio
  - create a V-Link user systemd service and kiosk autostart
  - install/update the V-Link runtime and Python virtual environment
EOF

    if [[ "$CONFIGURE_HARDWARE" == true ]]; then
        cat <<'EOF'

Hardware mode will ALSO:
  - modify /boot/firmware/config.txt and release serial ports in cmdline.txt
  - install V-Link/CAN device-tree overlays and configure SPI/I2C/UART/GPIO
  - install CAN helper services, udev rules and limited sudo permissions
  - on Raspberry Pi 3, disable the onboard Bluetooth controller for the UART

Backups of the original boot configuration are kept with .v-link.bak suffixes.
EOF
    else
        cat <<'EOF'

UI-only mode will NOT install V-Link CAN/UART/GPIO overlays or change the
managed vehicle hardware configuration.
EOF
    fi

    printf '\n'
}

'''
replace_once(confirm_anchor, confirm_anchor + ux_functions, 'UX helper insertion')

replace_once(
    '''        --no-hardware)\n            CONFIGURE_HARDWARE=false\n            ;;\n''',
    '''        --hardware)\n            CONFIGURE_HARDWARE=true\n            HARDWARE_CHOICE_EXPLICIT=true\n            ;;\n        --no-hardware)\n            CONFIGURE_HARDWARE=false\n            HARDWARE_CHOICE_EXPLICIT=true\n            ;;\n''',
    'hardware option',
)

replace_once(
    '''[[ -z "$SOURCE_DIR" || -z "$SOURCE_REF" ]] || \\\n    die "use either --source-dir or --ref, not both"\n''',
    '''[[ -z "$SOURCE_DIR" || -z "$SOURCE_REF" ]] || \\\n    die "use either --source-dir or --ref, not both"\nif [[ -n "$SOURCE_DIR" || -n "$SOURCE_REF" ]]; then\n    SOURCE_CHOICE_EXPLICIT=true\nfi\n''',
    'source explicit state',
)

old_source = '''# When launched from a checkout, use it automatically. A standalone copy keeps\n# SOURCE_DIR empty and installs a release unless --ref requests source code.\nif [[ -z "$SOURCE_DIR" && -z "$SOURCE_REF" && -f "$SCRIPT_DIR/V-Link.py" && -d "$SCRIPT_DIR/frontend" ]]; then\n    SOURCE_DIR="$SCRIPT_DIR"\nfi\n\n'''

new_source = '''# Detect a local checkout, but in interactive mode let the user choose whether\n# to use it. Non-interactive behavior stays compatible with the old installer.\nLOCAL_SOURCE_CANDIDATE=""\nif [[ -z "$SOURCE_DIR" && -z "$SOURCE_REF" && -f "$SCRIPT_DIR/V-Link.py" && -d "$SCRIPT_DIR/frontend" ]]; then\n    LOCAL_SOURCE_CANDIDATE="$SCRIPT_DIR"\nfi\n\nif [[ "$ASSUME_YES" != true ]]; then\n    print_welcome\n    if [[ "$SOURCE_CHOICE_EXPLICIT" != true ]]; then\n        select_install_source "$LOCAL_SOURCE_CANDIDATE"\n    fi\n    if [[ "$HARDWARE_CHOICE_EXPLICIT" != true ]]; then\n        select_hardware_mode\n    fi\n    show_install_plan\n    confirm "Continue with this installation plan?" || die "installation cancelled by user"\nelif [[ "$SOURCE_CHOICE_EXPLICIT" != true && -n "$LOCAL_SOURCE_CANDIDATE" ]]; then\n    SOURCE_DIR="$LOCAL_SOURCE_CANDIDATE"\nfi\n\n'''
replace_once(old_source, new_source, 'interactive source/hardware plan')

path.write_text(text, encoding='utf-8')

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
    'ASSUME_YES=false\nCONFIGURE_HARDWARE=true\nHARDWARE_CHOICE_EXPLICIT=false\n',
    'ASSUME_YES=false\nCONFIGURE_HARDWARE=true\nFIRST_BOOT_MODE=false\nHARDWARE_CHOICE_EXPLICIT=false\n',
    'first boot state',
)

replace_once(
    '  --no-reboot           Do not reboot when installation finishes.\n  -h, --help            Show this help.\n',
    '  --no-reboot           Do not reboot when installation finishes.\n  --first-boot          First-boot mode used by the prepared-SD launcher.\n  -h, --help            Show this help.\n',
    'usage first boot option',
)

anchor = """print_welcome() {
    cat <<'EOF'

============================================================
                    V-Link Lite Installer
============================================================
This installer configures Raspberry Pi OS Lite as a dedicated
V-Link kiosk. You will be shown the source, hardware mode and
important system changes before anything is installed.
EOF
}

"""

helpers = r'''internet_available() {
    timeout 6 bash -c 'exec 3<>/dev/tcp/api.github.com/443' >/dev/null 2>&1
}

wait_for_internet() {
    local answer=""

    cat <<'EOF'

INTERNET CONNECTION REQUIRED
  V-Link Lite downloads packages and, for development installs, source code
  directly from GitHub. Connect Ethernet or configure Wi-Fi before continuing.
EOF

    while ! internet_available; do
        printf '\nNo Internet connection detected.\n'
        if command -v nmtui >/dev/null 2>&1; then
            printf '  [Enter] Retry   [N] Network/Wi-Fi settings   [Q] Quit\n'
        else
            printf '  [Enter] Retry   [Q] Quit\n'
        fi
        read -r -p '> ' answer
        case "$answer" in
            [Nn])
                if command -v nmtui >/dev/null 2>&1; then
                    nmtui
                else
                    printf 'NetworkManager text UI is not available. Configure Wi-Fi in Raspberry Pi Imager or use Ethernet.\n'
                fi
                ;;
            [Qq]) die "installation cancelled; Internet is required" ;;
            *) ;;
        esac
    done

    printf '\nInternet connection OK.\n'
}

cleanup_first_boot_stage() {
    log "Removing temporary first-boot installer files"
    systemctl disable v-link-firstboot.service >/dev/null 2>&1 || true
    rm -f -- /etc/systemd/system/v-link-firstboot.service
    rm -f -- \
        /boot/firmware/Install-Lite.sh \
        /boot/firmware/V-Link-FirstBoot.sh \
        /boot/firmware/v-link-firstboot.conf \
        /boot/Install-Lite.sh \
        /boot/V-Link-FirstBoot.sh \
        /boot/v-link-firstboot.conf
    systemctl daemon-reload
}

'''
replace_once(anchor, anchor + helpers, 'network and cleanup helpers')

replace_once(
    """        --no-reboot)
            REBOOT=false
            ;;
        -h|--help)
""",
    """        --no-reboot)
            REBOOT=false
            ;;
        --first-boot)
            FIRST_BOOT_MODE=true
            ;;
        -h|--help)
""",
    'parser first boot option',
)

replace_once(
    """if [[ "$ASSUME_YES" != true ]]; then
    print_welcome
    if [[ "$SOURCE_CHOICE_EXPLICIT" != true ]]; then
""",
    """if [[ "$ASSUME_YES" != true ]]; then
    print_welcome
    wait_for_internet
    if [[ "$SOURCE_CHOICE_EXPLICIT" != true ]]; then
""",
    'interactive internet preflight',
)

replace_once(
    """log "Installation complete"
printf 'User:        %s\\n' "$TARGET_USER"
""",
    """if [[ "$FIRST_BOOT_MODE" == true ]]; then
    cleanup_first_boot_stage
fi

log "Installation complete"
printf 'User:        %s\\n' "$TARGET_USER"
""",
    'successful first boot cleanup',
)

path.write_text(text, encoding='utf-8')

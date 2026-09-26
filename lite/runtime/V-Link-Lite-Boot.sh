#!/usr/bin/env bash
# Short graphical entry point for the permanent Lite maintenance screen.
set -uo pipefail

if [[ "${1:-}" != --gate ]]; then
    [[ $# -eq 0 ]] || exit 2
    # foot passes its child's exit status through; 230 means foot itself failed.
    if ! command -v foot >/dev/null 2>&1; then
        printf 'V-Link Lite: foot is unavailable; continuing startup.\n' >&2
        exit 0
    fi
    # The gate only captures S; labwc's persistent swaybg remains the visible
    # splash instead of a second, separately rendered terminal image.
    foot --fullscreen --title='V-Link Lite Boot' --app-id=v-link-lite-boot \
        --override=colors.alpha=0 --override=colors.background=000000 \
        /usr/local/libexec/v-link-lite-boot --gate
    result=$?
    case "$result" in
        20|21|22) exit 1 ;; # Power action or another open Setup: do not launch V-Link.
        230) printf 'V-Link Lite: foot failed; continuing startup.\n' >&2 ;;
    esac
    exit 0
fi

[[ $# -eq 1 ]] || exit 2
[[ -t 0 && -t 1 ]] || exit 0
# Keep the Settings shortcut available during the startup gate without
# changing the splash image or drawing a countdown/prompt over it.
printf '\033[?25l'
for _ in 1 2 3; do
    key=''
    if IFS= read -r -s -n 1 -t 1 key; then
        case "$key" in
            s|S)
                # Setup gets its own normal, opaque terminal; the boot gate
                # stays transparent behind it until Setup exits.
                foot --fullscreen --font=monospace:size=16 \
                    --title='V-Link Lite Setup' --app-id=v-link-lite-setup \
                    /usr/local/bin/v-link-lite-setup --startup
                exit $?
                ;;
        esac
    fi
done
exit 0

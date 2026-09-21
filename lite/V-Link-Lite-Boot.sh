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
    foot --fullscreen --title='V-Link Lite Setup' --app-id=v-link-lite-setup \
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
printf '\033[2J\033[H'
if [[ -r /usr/local/share/v-link-lite/logo.png ]] && command -v chafa >/dev/null 2>&1; then
    printf '\n\n'
    chafa --format sixels --size 40x12 --bg 000000 \
        /usr/local/share/v-link-lite/logo.png || printf '        V-Link Lite\n'
else
    printf '\n        V-Link Lite\n'
fi
printf '\n        Starting V-Link...\n\n        Press S for Settings\n\n'
for remaining in 3 2 1; do
    printf '\r        %s...\033[K' "$remaining"
    key=''
    if IFS= read -r -s -n 1 -t 1 key; then
        case "$key" in
            s|S)
                /usr/local/bin/v-link-lite-setup --startup
                exit $?
                ;;
        esac
    fi
done
printf '\n'
exit 0

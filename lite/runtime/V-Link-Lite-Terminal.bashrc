# V-Link Lite maintenance shell configuration.

_v_link_lite_help() {
    cat <<'EOF'
V-Link Lite terminal commands

  help          Show this help
  help COMMAND  Show Bash help for a shell command
  exit          Return to V-Link Lite Setup
  Ctrl+D        Return to V-Link Lite Setup

After returning to Setup, choose "Continue to V-Link / Exit Setup" to reveal
the running V-Link interface or continue the graphical startup.
EOF
}

help() {
    if (($#)); then
        builtin help "$@"
    else
        _v_link_lite_help
    fi
}

PS1='v-link-lite:\w\$ '
printf '\nV-Link Lite maintenance terminal. Type "help" for return instructions.\n\n'

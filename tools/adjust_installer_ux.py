from pathlib import Path

path = Path('Install-Lite.sh')
text = path.read_text(encoding='utf-8')

old_menu = '''    printf '\\nChoose what V-Link source to install:\\n'\n    printf '  1) Latest published release  [recommended for normal use]\\n'\n    printf '  2) GitHub branch             [development / testing]\\n'\n    if [[ -n "$local_checkout" ]]; then\n        printf '  3) This local checkout       [%s]\\n' "$local_checkout"\n    fi\n\n    while true; do\n        read -r -p 'Selection [1]: ' choice\n        [[ -n "$choice" ]] || choice=1\n        case "$choice" in\n            1)\n                SOURCE_DIR=""\n                SOURCE_REF=""\n                return\n                ;;\n            2)\n                select_github_branch\n                return\n                ;;\n'''
new_menu = '''    printf '\\nChoose what V-Link source to install:\\n'\n    printf '  1) GitHub branch             [recommended for development / testing]\\n'\n    printf '  2) Latest published release  [packaged release, when available]\\n'\n    if [[ -n "$local_checkout" ]]; then\n        printf '  3) This local checkout       [%s]\\n' "$local_checkout"\n    fi\n\n    while true; do\n        read -r -p 'Selection [1]: ' choice\n        [[ -n "$choice" ]] || choice=1\n        case "$choice" in\n            1)\n                select_github_branch\n                return\n                ;;\n            2)\n                SOURCE_DIR=""\n                SOURCE_REF=""\n                return\n                ;;\n'''
if text.count(old_menu) != 1:
    raise RuntimeError('source menu anchor mismatch')
text = text.replace(old_menu, new_menu, 1)

old_post = '''elif [[ "$SOURCE_CHOICE_EXPLICIT" != true && -n "$LOCAL_SOURCE_CANDIDATE" ]]; then\n    SOURCE_DIR="$LOCAL_SOURCE_CANDIDATE"\nfi\n\nif [[ -n "$SOURCE_DIR" ]]; then\n'''
new_post = '''elif [[ "$SOURCE_CHOICE_EXPLICIT" != true && -n "$LOCAL_SOURCE_CANDIDATE" ]]; then\n    SOURCE_DIR="$LOCAL_SOURCE_CANDIDATE"\nfi\n\n[[ -z "$LIN_PORT" || "$CONFIGURE_HARDWARE" == true ]] || \\\n    die "--lin-port requires hardware mode"\n\nif [[ -n "$SOURCE_DIR" ]]; then\n'''
if text.count(old_post) != 1:
    raise RuntimeError('post-selection validation anchor mismatch')
text = text.replace(old_post, new_post, 1)

path.write_text(text, encoding='utf-8')

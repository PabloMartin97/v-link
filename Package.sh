#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_WORK="$(mktemp -d "${TMPDIR:-/tmp}/v-link-package.XXXXXX")"
FRONTEND_STAGE=""
RELEASE_STAGE=""

cleanup() {
    local status=$?
    trap - EXIT
    rm -rf -- "$PACKAGE_WORK"
    [[ -z "$FRONTEND_STAGE" || ! -e "$FRONTEND_STAGE" ]] || rm -rf -- "$FRONTEND_STAGE"
    [[ -z "$RELEASE_STAGE" || ! -e "$RELEASE_STAGE" ]] || rm -rf -- "$RELEASE_STAGE"
    exit "$status"
}
trap cleanup EXIT

publish_directory() {
    local staging="$1"
    local destination="$2"
    local backup="$destination.v-link-package-old"

    # Recover a complete previous directory if an earlier publish was killed.
    if [[ -e "$backup" ]]; then
        rm -rf -- "$destination"
        mv "$backup" "$destination"
    fi
    if [[ -e "$destination" ]]; then
        mv "$destination" "$backup"
    fi
    if mv "$staging" "$destination"; then
        rm -rf -- "$backup"
    else
        [[ ! -e "$backup" ]] || mv "$backup" "$destination"
        return 1
    fi
}

recover_published_directory() {
    local destination="$1"
    local backup="$destination.v-link-package-old"
    if [[ -e "$backup" ]]; then
        rm -rf -- "$destination"
        mv "$backup" "$destination"
    fi
}

echo "V-Link release packager"
recover_published_directory "$SCRIPT_DIR/frontend/dist"
recover_published_directory "$SCRIPT_DIR/dist"
mkdir -p "$PACKAGE_WORK/frontend-source" "$PACKAGE_WORK/release"

# Build against a clean lockfile without deleting the developer's existing
# node_modules, frontend/dist or last known-good release on failure.
tar -C "$SCRIPT_DIR/frontend" \
    --exclude='./node_modules' --exclude='./dist' \
    -cf - . | tar -C "$PACKAGE_WORK/frontend-source" -xf -

echo "Building frontend in an isolated directory..."
(
    cd "$PACKAGE_WORK/frontend-source"
    export ELECTRON_SKIP_BINARY_DOWNLOAD=1
    npm ci --legacy-peer-deps --no-audit --no-fund
    npm run build
)

FRONTEND_HASH="$(python3 - "$SCRIPT_DIR/frontend" <<'PY'
import hashlib
import sys
from pathlib import Path

root = Path(sys.argv[1])
digest = hashlib.sha256()
for path in sorted(root.rglob('*')):
    relative = path.relative_to(root)
    if not path.is_file() or relative.parts[0] in {'dist', 'node_modules'}:
        continue
    digest.update(relative.as_posix().encode())
    digest.update(b'\0')
    digest.update(hashlib.sha256(path.read_bytes()).digest())
print(digest.hexdigest())
PY
)"
printf '%s\n' "$FRONTEND_HASH" >"$PACKAGE_WORK/frontend-source/dist/.v-link-source.sha256"

RELEASE_DIR="$PACKAGE_WORK/release"
mkdir -p "$RELEASE_DIR/frontend/dist" "$RELEASE_DIR/backend" "$RELEASE_DIR/resources/dtoverlays"
cp -R "$PACKAGE_WORK/frontend-source/dist/." "$RELEASE_DIR/frontend/dist/"
cp -R "$SCRIPT_DIR/backend/." "$RELEASE_DIR/backend/"
cp "$SCRIPT_DIR"/resources/dtoverlays/*.dtbo "$RELEASE_DIR/resources/dtoverlays/"
find "$RELEASE_DIR/backend" -type d -name __pycache__ -prune -exec rm -rf -- {} +

cp -p "$SCRIPT_DIR/V-Link.py" "$RELEASE_DIR/V-Link.py"
cp -p "$SCRIPT_DIR/requirements.txt" "$RELEASE_DIR/requirements.txt"
cp -p "$SCRIPT_DIR/Install.sh" "$RELEASE_DIR/Install.sh"
cp -p "$SCRIPT_DIR/Install-Lite.sh" "$RELEASE_DIR/Install-Lite.sh"
cp -p "$SCRIPT_DIR/Uninstall.sh" "$RELEASE_DIR/Uninstall.sh"
cp -p "$SCRIPT_DIR/Update.sh" "$RELEASE_DIR/Update.sh"
cp -p "$SCRIPT_DIR/Patch.sh" "$RELEASE_DIR/Patch.sh"
cp -p "$SCRIPT_DIR/Check-Lite.sh" "$RELEASE_DIR/Check-Lite.sh"

echo "Creating and validating V-Link.zip..."
(
    cd "$RELEASE_DIR"
    zip -r V-Link.zip \
        V-Link.py Patch.sh Check-Lite.sh Update.sh requirements.txt \
        frontend/ backend/ resources/dtoverlays/
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum V-Link.zip >V-Link.zip.sha256
    else
        shasum -a 256 V-Link.zip >V-Link.zip.sha256
    fi

    unzip -tq V-Link.zip
    ZIP_ENTRIES="$(unzip -Z1 V-Link.zip)"
    for required in \
        V-Link.py \
        Check-Lite.sh \
        Update.sh \
        requirements.txt \
        backend/server.py \
        frontend/dist/index.html \
        resources/dtoverlays/v-link.dtbo \
        resources/dtoverlays/mcp2515-can1.dtbo \
        resources/dtoverlays/mcp2515-can2.dtbo; do
        grep -Fxq "$required" <<<"$ZIP_ENTRIES"
    done
)

# Copy into same-filesystem staging directories, then publish complete trees.
FRONTEND_STAGE="$(mktemp -d "$SCRIPT_DIR/frontend/.dist.v-link-new.XXXXXX")"
RELEASE_STAGE="$(mktemp -d "$SCRIPT_DIR/.dist.v-link-new.XXXXXX")"
cp -R "$PACKAGE_WORK/frontend-source/dist/." "$FRONTEND_STAGE/"
cp -R "$RELEASE_DIR/." "$RELEASE_STAGE/"
publish_directory "$FRONTEND_STAGE" "$SCRIPT_DIR/frontend/dist"
publish_directory "$RELEASE_STAGE" "$SCRIPT_DIR/dist"

echo "Release ready in $SCRIPT_DIR/dist"

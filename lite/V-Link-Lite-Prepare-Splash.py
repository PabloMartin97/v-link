#!/usr/bin/env python3
"""Idempotently add the Lite-only splash handoff to the installed HTML."""

import argparse
import os
import stat
import tempfile
from pathlib import Path


BEGIN = "<!-- BEGIN V-LINK LITE SPLASH HANDOFF -->"
END = "<!-- END V-LINK LITE SPLASH HANDOFF -->"
DEFAULT_SCRIPT = Path("/usr/local/share/v-link-lite/handoff.js")


def installed_app_dir():
    unit = Path.home() / ".config/systemd/user/v-link.service"
    for line in unit.read_text(encoding="utf-8").splitlines():
        if line.startswith("WorkingDirectory="):
            return Path(line.partition("=")[2])
    raise ValueError(f"WorkingDirectory is missing from {unit}")


def prepare(index, script):
    if index.is_symlink() or not index.is_file():
        raise ValueError(f"unsafe or missing built HTML: {index}")
    original = index.read_text(encoding="utf-8")
    if original.count(BEGIN) != original.count(END) or original.count(BEGIN) > 1:
        raise ValueError("Lite splash handoff markers are incomplete or duplicated")
    if BEGIN in original:
        start = original.index(BEGIN)
        end = original.index(END, start) + len(END)
        suffix = original[end:]
        if suffix.startswith("\n"):
            suffix = suffix[1:]
        original = original[:start] + suffix
    if original.count("</body>") != 1:
        raise ValueError("installed frontend HTML has no unique closing body tag")

    hook = f"{BEGIN}\n<script>\n{script.read_text(encoding='utf-8')}\n</script>\n{END}\n"
    updated = original.replace("</body>", hook + "</body>")
    if index.read_text(encoding="utf-8") == updated:
        return False

    mode = stat.S_IMODE(index.stat().st_mode)
    fd, temporary = tempfile.mkstemp(prefix=".v-link-lite-splash.", dir=index.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(updated)
        os.chmod(temporary, mode)
        os.replace(temporary, index)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-dir", type=Path)
    parser.add_argument("--script", type=Path, default=DEFAULT_SCRIPT)
    args = parser.parse_args()
    app_dir = args.app_dir or installed_app_dir()
    prepare(app_dir / "frontend/dist/index.html", args.script)


if __name__ == "__main__":
    main()

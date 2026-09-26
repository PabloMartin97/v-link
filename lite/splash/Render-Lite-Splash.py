#!/usr/bin/env python3
"""Render the existing frontend marks for the Lite graphical splash."""

import argparse
import io
import os
import subprocess
import tempfile
from pathlib import Path

from PIL import Image


REFERENCE_HEIGHT = 1080
INSTALLED_LOGO = Path("/usr/local/share/v-link-lite/logo.png")
INSTALLED_SPLASH = Path("/usr/local/share/v-link-lite/splash.png")
MIN_DIMENSION = 240
MAX_DIMENSION = 10000


def render_svg(path, width):
    result = subprocess.run(
        ["rsvg-convert", "--width", str(width), str(path)],
        check=True, capture_output=True, timeout=15,
    )
    return Image.open(io.BytesIO(result.stdout)).convert("RGBA")


def white_mark(image):
    mark = Image.new("RGBA", image.size, "white")
    mark.putalpha(image.getchannel("A"))
    return mark


def build_logo(moose, wordmark):
    """Match the frontend's 20vh / 40vh logo proportions at 1080p."""
    marks = [white_mark(moose), white_mark(wordmark)]
    gap = 16
    logo = Image.new("RGBA", (max(mark.width for mark in marks),
                              sum(mark.height for mark in marks) + gap),
                     (0, 0, 0, 0))
    top = 0
    for mark in marks:
        logo.alpha_composite(mark, ((logo.width - mark.width) // 2, top))
        top += mark.height + gap
    return logo


def build_splash(logo, width, height):
    scale = height / REFERENCE_HEIGHT
    size = (max(1, round(logo.width * scale)), max(1, round(logo.height * scale)))
    if size != logo.size:
        logo = logo.resize(size, Image.Resampling.LANCZOS)
    splash = Image.new("RGB", (width, height), "black")
    splash.paste(logo, ((width - logo.width) // 2,
                        (height - logo.height) // 2), logo)
    return splash


def build_images(moose, wordmark, width=1280, height=720):
    logo = build_logo(moose, wordmark)
    splash = build_splash(logo, width, height)
    return logo, splash


def valid_dimension(value):
    value = int(value)
    if not MIN_DIMENSION <= value <= MAX_DIMENSION:
        raise argparse.ArgumentTypeError(
            f"dimension must be between {MIN_DIMENSION} and {MAX_DIMENSION}")
    return value


def refresh_installed(width, height):
    if INSTALLED_LOGO.is_symlink() or not INSTALLED_LOGO.is_file():
        raise RuntimeError(f"installed Lite logo is missing or unsafe: {INSTALLED_LOGO}")
    if INSTALLED_SPLASH.is_symlink():
        raise RuntimeError(f"installed Lite splash is unsafe: {INSTALLED_SPLASH}")
    if INSTALLED_SPLASH.is_file():
        try:
            with Image.open(INSTALLED_SPLASH) as current:
                if current.format == "PNG" and current.size == (width, height):
                    current.verify()
                    return False
        except (OSError, SyntaxError, ValueError):
            pass

    with Image.open(INSTALLED_LOGO) as source:
        splash = build_splash(source.convert("RGBA"), width, height)
    descriptor, temporary = tempfile.mkstemp(
        prefix=".splash.", suffix=".png", dir=INSTALLED_SPLASH.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            splash.save(output, format="PNG", compress_level=1)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, INSTALLED_SPLASH)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--logos-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--width", type=valid_dimension, default=1280)
    parser.add_argument("--height", type=valid_dimension, default=720)
    parser.add_argument("--refresh-installed", action="store_true")
    args = parser.parse_args()

    if args.refresh_installed:
        if args.logos_dir is not None or args.output_dir is not None:
            parser.error("--refresh-installed cannot be combined with source/output paths")
        refresh_installed(args.width, args.height)
        return
    if args.logos_dir is None or args.output_dir is None:
        parser.error("--logos-dir and --output-dir are required when rendering source assets")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    moose = render_svg(args.logos_dir / "moose.svg", round(REFERENCE_HEIGHT * 0.20))
    wordmark = render_svg(args.logos_dir / "vlink.svg", round(REFERENCE_HEIGHT * 0.40))
    logo, splash = build_images(moose, wordmark, args.width, args.height)
    logo.save(args.output_dir / "logo.png")
    splash.save(args.output_dir / "splash.png")


if __name__ == "__main__":
    main()

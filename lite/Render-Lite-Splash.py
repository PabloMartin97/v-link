#!/usr/bin/env python3
"""Render the existing frontend marks for the Lite boot stages."""

import argparse
import io
import subprocess
from pathlib import Path

from PIL import Image


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


def build_images(moose, wordmark):
    logo = Image.new("RGBA", (400, 240), (0, 0, 0, 0))
    for mark, centre_y in ((moose, 72), (wordmark, 167)):
        mark = white_mark(mark)
        logo.alpha_composite(mark, ((logo.width - mark.width) // 2,
                                    centre_y - mark.height // 2))

    splash = Image.new("RGB", (1280, 720), "black")
    splash.paste(logo, ((splash.width - logo.width) // 2,
                        (splash.height - logo.height) // 2), logo)
    return logo, splash


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--logos-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    moose = render_svg(args.logos_dir / "moose.svg", 160)
    wordmark = render_svg(args.logos_dir / "vlink.svg", 320)
    logo, splash = build_images(moose, wordmark)
    logo.save(args.output_dir / "logo.png")
    splash.save(args.output_dir / "splash.png")
    # Raspberry Pi's early-logo reader requires an uncompressed 24-bit TGA
    # with at most 224 colours. Quantisation keeps the antialiased edges.
    splash.transpose(Image.Transpose.FLIP_TOP_BOTTOM).quantize(colors=64).convert("RGB").save(
        args.output_dir / "splash.tga", format="TGA", compression=None)


if __name__ == "__main__":
    main()

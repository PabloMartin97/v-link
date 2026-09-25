"""Host-side checks for the resolution-matched Lite splash."""

import importlib.util
import tempfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "lite/Render-Lite-Splash.py"
SPEC = importlib.util.spec_from_file_location("v_link_lite_splash", SCRIPT)
SPLASH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SPLASH)


def sample_logo():
    image = Image.new("RGBA", (432, 256), (0, 0, 0, 0))
    image.paste((255, 255, 255, 255), (108, 0, 324, 146))
    image.paste((255, 255, 255, 255), (0, 162, 432, 256))
    return image


def test_splash_uses_requested_resolution_and_centres_frontend_sized_logo():
    splash = SPLASH.build_splash(sample_logo(), 1920, 1080)
    assert splash.size == (1920, 1080)
    assert splash.getpixel((0, 0)) == (0, 0, 0)
    non_black = splash.point(lambda value: 255 if value else 0).getbbox()
    assert non_black == (744, 412, 1176, 668)


def test_logo_scales_with_display_height_like_the_frontend_vh_layout():
    splash = SPLASH.build_splash(sample_logo(), 1280, 720)
    non_black = splash.point(lambda value: 255 if value else 0).getbbox()
    assert non_black == (496, 274, 784, 445)


def test_installed_splash_is_atomic_and_cached_by_effective_size():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        logo = root / "logo.png"
        splash = root / "splash.png"
        sample_logo().save(logo)
        with patch.object(SPLASH, "INSTALLED_LOGO", logo), \
             patch.object(SPLASH, "INSTALLED_SPLASH", splash):
            assert SPLASH.refresh_installed(1920, 1080)
            first = splash.read_bytes()
            assert Image.open(splash).size == (1920, 1080)
            assert not SPLASH.refresh_installed(1920, 1080)
            assert splash.read_bytes() == first
            assert not list(root.glob(".splash.*"))


def test_installed_splash_replaces_a_truncated_matching_png():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        logo = root / "logo.png"
        splash = root / "splash.png"
        sample_logo().save(logo)
        Image.new("RGB", (1920, 1080), "black").save(splash)
        splash.write_bytes(splash.read_bytes()[:24])
        with patch.object(SPLASH, "INSTALLED_LOGO", logo), \
             patch.object(SPLASH, "INSTALLED_SPLASH", splash):
            assert SPLASH.refresh_installed(1920, 1080)
            with Image.open(splash) as rendered:
                rendered.verify()

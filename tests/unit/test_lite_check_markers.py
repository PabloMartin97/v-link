"""The Lite HAT marker must not match the longer splash marker."""

import subprocess
import tempfile
from pathlib import Path


CHECK = Path(__file__).resolve().parents[2] / "lite/Check-Lite.sh"
INSTALL = Path(__file__).resolve().parents[2] / "lite/Install-Lite.sh"
HAT = "# BEGIN V-LINK LITE"
SPLASH = "# BEGIN V-LINK LITE SPLASH"


def detect(marker, content):
    with tempfile.TemporaryDirectory() as directory:
        config = Path(directory) / "config.txt"
        config.write_text(content, encoding="utf-8")
        return subprocess.run(["grep", "-qsFx", marker, str(config)], check=False).returncode == 0


def test_check_lite_uses_exact_hardware_marker_in_both_branches():
    source = CHECK.read_text(encoding="utf-8")
    assert source.count("grep -qsFx '# BEGIN V-LINK LITE' /boot/firmware/config.txt") == 2
    assert "grep -qsF '# BEGIN V-LINK LITE' /boot/firmware/config.txt" not in source


def test_splash_only_is_not_hardware():
    content = f"{SPLASH}\n# END V-LINK LITE SPLASH\n"
    assert not detect(HAT, content)
    assert detect(SPLASH, content)


def test_hardware_only_is_hardware():
    content = f"{HAT}\n# END V-LINK LITE\n"
    assert detect(HAT, content)
    assert not detect(SPLASH, content)


def test_hardware_and_splash_are_independent():
    content = f"{HAT}\n# END V-LINK LITE\n{SPLASH}\n# END V-LINK LITE SPLASH\n"
    assert detect(HAT, content)
    assert detect(SPLASH, content)


def test_replacing_hardware_block_preserves_splash_block():
    source = INSTALL.read_text(encoding="utf-8")
    assert source.count('sed "\\|^${CONFIG_BEGIN}$|,\\|^${CONFIG_END}$|d"') == 2
    content = f"{HAT}\nHAT configuration\n# END V-LINK LITE\n{SPLASH}\nSplash configuration\n# END V-LINK LITE SPLASH\n"
    result = subprocess.run(
        ["sed", r"\|^# BEGIN V-LINK LITE$|,\|^# END V-LINK LITE$|d"],
        input=content, text=True, capture_output=True, check=True,
    )
    assert HAT not in result.stdout.splitlines()
    assert SPLASH in result.stdout.splitlines()
    assert "Splash configuration" in result.stdout

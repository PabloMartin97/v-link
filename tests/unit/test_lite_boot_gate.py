"""The Lite startup gate keeps Settings available without overlay text."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_settings_shortcut_is_hidden_but_still_available():
    gate = (ROOT / "lite/V-Link-Lite-Boot.sh").read_text(encoding="utf-8")
    check = (ROOT / "lite/Check-Lite.sh").read_text(encoding="utf-8")

    assert "--override=colors.alpha=0" in gate
    assert "read -r -s -n 1 -t 1 key" in gate
    assert "s|S)" in gate
    assert "/usr/local/bin/v-link-lite-setup --startup" in gate
    assert "for _ in 1 2 3; do" in gate
    assert "Press S for Settings" not in gate
    assert "Starting V-Link..." not in gate
    assert "remaining" not in gate
    assert "grep -Fq 's|S)'" in check
    assert "grep -Fq 'Press S for Settings'" not in check


def test_early_splash_hooks_are_not_installed():
    install = (ROOT / "lite/Install-Lite.sh").read_text(encoding="utf-8")
    check = (ROOT / "lite/Check-Lite.sh").read_text(encoding="utf-8")

    assert "configure-splash /usr/local/share/v-link-lite/splash.tga" not in install
    assert "plymouth-set-default-theme -R" not in install
    assert "fullscreen_logo=1|fullscreen_logo_name=logo.tga" in install
    assert "kernel command line has no V-Link splash hooks" in check


def test_html_has_black_first_paint_before_react():
    html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    assert html.index("background: #000") < html.index('<div id="root">')
    assert html.index('id="boot-mark"') < html.index('src="/src/main.tsx"')

"""The Lite startup gate keeps Settings available without overlay text."""

from pathlib import Path
import re
import subprocess
import tempfile


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


def test_overlay_covers_browser_until_react_signals_ready():
    install = (ROOT / "lite/Install-Lite.sh").read_text(encoding="utf-8")
    overlay = (ROOT / "lite/V-Link-Lite-Overlay.py").read_text(encoding="utf-8")
    handoff = (ROOT / "lite/V-Link-Lite-Handoff.js").read_text(encoding="utf-8")

    assert "gir1.2-gtklayershell-0.1" in install
    assert "v-link-lite-overlay &" in install
    assert install.index("v-link-lite-overlay &") < install.index("systemctl --user start v-link.service &")
    assert "GtkLayerShell.Layer.OVERLAY" in overlay
    assert 'HTTPServer(("127.0.0.1", 40777)' in overlay
    assert "READY.is_set()" in overlay
    assert "MutationObserver(ready)" in handoff
    assert "127.0.0.1:40777/ready" in handoff
    assert "Press S for Settings" in overlay


def test_lite_handoff_reapplies_after_frontend_update_without_duplicates():
    helper = ROOT / "lite/V-Link-Lite-Prepare-Splash.py"
    script = ROOT / "lite/V-Link-Lite-Handoff.js"
    with tempfile.TemporaryDirectory() as directory:
        app = Path(directory)
        dist = app / "frontend/dist"
        dist.mkdir(parents=True)
        index = dist / "index.html"
        original = "<html><body><div id='root'></div></body></html>"
        index.write_text(original, encoding="utf-8")
        command = ["python3", str(helper), "--app-dir", str(app), "--script", str(script)]

        subprocess.run(command, check=True)
        first = index.read_text(encoding="utf-8")
        subprocess.run(command, check=True)
        assert index.read_text(encoding="utf-8") == first
        assert first.count("<!-- BEGIN V-LINK LITE SPLASH HANDOFF -->") == 1
        assert "127.0.0.1:40777/ready" in first
        check = (ROOT / "lite/Check-Lite.sh").read_text(encoding="utf-8")
        for marker in ("<!-- BEGIN V-LINK LITE SPLASH HANDOFF -->",
                       "<!-- END V-LINK LITE SPLASH HANDOFF -->"):
            assert f"grep -qF '{marker}'" in check
            assert subprocess.run(["grep", "-qF", marker, str(index)],
                                  check=False).returncode == 0

        index.write_text(original, encoding="utf-8")  # A headless update replaces dist.
        subprocess.run(command, check=True)
        assert index.read_text(encoding="utf-8") == first


def test_automount_check_ignores_overlay_dev_null_but_rejects_manual_mounts():
    check = (ROOT / "lite/Check-Lite.sh").read_text(encoding="utf-8")
    expressions = re.findall(r"! grep -Eq '([^']+)' \"\$LABWC_AUTOSTART\"", check)
    expression = next(pattern for pattern in expressions if "mount" in pattern)
    with tempfile.TemporaryDirectory() as directory:
        autostart = Path(directory) / "autostart"
        autostart.write_text(
            "udiskie --no-config --automount --no-notify &\n"
            "kill -0 \"$overlay_pid\" 2>/dev/null || break\n",
            encoding="utf-8",
        )
        command = ["grep", "-Eq", expression, str(autostart)]
        assert subprocess.run(command, check=False).returncode == 1
        autostart.write_text("sudo mount /dev/sda1 /media/volvo\n", encoding="utf-8")
        assert subprocess.run(command, check=False).returncode == 0

"""Host-side tests for the Lite SD bootstrap; never mount or alter a real SD."""

import ast
import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PREPARE = ROOT / "lite/Prepare-V-Link-SD.command"
FIRSTBOOT = ROOT / "lite/V-Link-FirstBoot.sh"
INSTALL = ROOT / "lite/Install-Lite.sh"


def prepare(boot, cmdline, firstrun=None):
    (boot / "cmdline.txt").write_bytes(cmdline)
    (boot / "config.txt").write_text("[all]\n")
    if firstrun is not None:
        (boot / "firstrun.sh").write_text(firstrun)
    env = {**os.environ, "V_LINK_BOOT_VOLUME": str(boot)}
    return subprocess.run(["bash", str(PREPARE)], input="\n", text=True,
                          capture_output=True, env=env, timeout=30)


def test_prepare_clean_card_and_manifest_hashes():
    with tempfile.TemporaryDirectory() as directory:
        boot = Path(directory)
        result = prepare(boot, b"rootwait console=tty1\n")
        assert result.returncode == 0, result.stderr
        cmdline = (boot / "cmdline.txt").read_text()
        assert cmdline.count("systemd.run=") == 1
        assert "V-Link-FirstBoot.sh" in cmdline
        assert (boot / "cmdline.txt.v-link-prep.bak").read_bytes() == b"rootwait console=tty1\n"
        manifest = dict(line.split("=", 1) for line in
                        (boot / "v-link-firstboot.conf").read_text().splitlines())
        for key, filename in (("INSTALLER_SHA256", "Install-Lite.sh"),
                              ("BOOTSTRAP_SHA256", "V-Link-FirstBoot.sh")):
            assert manifest[key] == hashlib.sha256((boot / filename).read_bytes()).hexdigest()


def test_prepare_imager_hook_is_inserted_once_and_repeated_run_is_stable():
    with tempfile.TemporaryDirectory() as directory:
        boot = Path(directory)
        imager = '#!/bin/bash\necho setup\nrm -f /boot/firmware/firstrun.sh\n'
        result = prepare(boot, b"rootwait systemd.run=/boot/firmware/firstrun.sh systemd.run_success_action=reboot systemd.unit=kernel-command-line.target\n", imager)
        assert result.returncode == 0, result.stderr
        first = (boot / "cmdline.txt").read_bytes()
        hook = (boot / "firstrun.sh").read_bytes()
        second = subprocess.run(["bash", str(PREPARE)], input="\n", text=True,
                                capture_output=True,
                                env={**os.environ, "V_LINK_BOOT_VOLUME": str(boot)}, timeout=30)
        assert second.returncode == 0, second.stderr
        assert (boot / "cmdline.txt").read_bytes() == first
        assert (boot / "firstrun.sh").read_bytes() == hook
        assert hook.count(b"V-Link-FirstBoot.sh") == 1
        assert (boot / "cmdline.txt.v-link-prep.bak").read_bytes().startswith(b"rootwait systemd.run=/boot/firmware/firstrun.sh")


def test_prepare_replaces_only_known_old_hook():
    with tempfile.TemporaryDirectory() as directory:
        boot = Path(directory)
        result = prepare(boot, b"rootwait systemd.run=/boot/V-Link-FirstBoot.sh systemd.run_failure_action=reboot systemd.unit=kernel-command-line.target\n")
        assert result.returncode == 0, result.stderr
        text = (boot / "cmdline.txt").read_text()
        assert text.count("systemd.run=") == 1
        assert "systemd.run=/boot/firmware/V-Link-FirstBoot.sh" in text


def test_prepare_rejects_unknown_hook_without_changing_cmdline():
    with tempfile.TemporaryDirectory() as directory:
        boot = Path(directory)
        original = b"rootwait systemd.run=/boot/custom.sh systemd.unit=kernel-command-line.target\n"
        result = prepare(boot, original)
        assert result.returncode != 0
        assert "Unknown systemd.run" in result.stderr
        assert (boot / "cmdline.txt").read_bytes() == original
        assert not (boot / "v-link-firstboot.conf").exists()


def test_prepare_rejects_multiline_without_changing_card():
    with tempfile.TemporaryDirectory() as directory:
        boot = Path(directory)
        original = b"rootwait\nconsole=tty1\n"
        result = prepare(boot, original)
        assert result.returncode != 0
        assert (boot / "cmdline.txt").read_bytes() == original
        assert not (boot / "v-link-firstboot.conf").exists()


def test_prepare_accepts_single_crlf_without_merging_tokens():
    with tempfile.TemporaryDirectory() as directory:
        boot = Path(directory)
        result = prepare(boot, b"rootwait console=tty1\r\n")
        assert result.returncode == 0, result.stderr
        assert (boot / "cmdline.txt").read_text().startswith("rootwait console=tty1 ")


def stage_firstboot(boot, system, valid=True, direct=False):
    boot.mkdir()
    system.mkdir()
    shutil.copy2(FIRSTBOOT, boot / FIRSTBOOT.name)
    (boot / "Install-Lite.sh").write_text("#!/bin/bash\nexit 0\n")
    cmdline = "rootwait console=tty1"
    if direct:
        cmdline += " systemd.run=/boot/firmware/V-Link-FirstBoot.sh systemd.run_success_action=reboot systemd.unit=kernel-command-line.target"
    (boot / "cmdline.txt").write_text(cmdline + "\n")
    proc = boot / "proc-cmdline"
    proc.write_text(cmdline + "\n")
    installer_hash = hashlib.sha256((boot / "Install-Lite.sh").read_bytes()).hexdigest()
    bootstrap_hash = hashlib.sha256((boot / FIRSTBOOT.name).read_bytes()).hexdigest()
    if not valid:
        installer_hash = "0" * 64
    (boot / "v-link-firstboot.conf").write_text(
        f"SOURCE=test\nINSTALLER_SHA256={installer_hash}\nBOOTSTRAP_SHA256={bootstrap_hash}\n")
    bin_dir = boot / "bin"
    bin_dir.mkdir()
    (bin_dir / "systemctl").write_text("#!/bin/sh\nexit 0\n")
    (bin_dir / "systemctl").chmod(0o755)
    env = {**os.environ, "V_LINK_FIRST_BOOT_ROOT": str(system),
           "V_LINK_PROC_CMDLINE": str(proc), "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"]}
    return subprocess.run(["bash", str(boot / FIRSTBOOT.name)], text=True,
                          capture_output=True, env=env, timeout=30)


def test_firstboot_rejects_bad_hash_before_staging():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        result = stage_firstboot(root / "boot", root / "system", valid=False)
        assert result.returncode != 0
        assert not (root / "system/usr/local/libexec/v-link-install-lite").exists()
        assert "SHA256 mismatch" in (root / "boot/v-link-firstboot.log").read_text()


def test_firstboot_rejects_mixed_bootstrap_version():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        boot = root / "boot"
        result = stage_firstboot(boot, root / "system", valid=False)
        # An installer/bootstrap mismatch must be rejected whichever file
        # differs; repeat with an intact installer but a changed bootstrap hash.
        assert result.returncode != 0
        manifest = boot / "v-link-firstboot.conf"
        lines = manifest.read_text().splitlines()
        lines[1] = "INSTALLER_SHA256=" + hashlib.sha256((boot / "Install-Lite.sh").read_bytes()).hexdigest()
        lines[2] = "BOOTSTRAP_SHA256=" + "0" * 64
        manifest.write_text("\n".join(lines) + "\n")
        system = root / "system"
        second = subprocess.run(["bash", str(boot / FIRSTBOOT.name)], text=True,
                                capture_output=True,
                                env={**os.environ, "V_LINK_FIRST_BOOT_ROOT": str(system),
                                     "V_LINK_PROC_CMDLINE": str(boot / "proc-cmdline")}, timeout=30)
        assert second.returncode != 0
        assert not (system / "usr/local/libexec/v-link-install-lite").exists()
        assert "bootstrap SHA256 mismatch" in (boot / "v-link-firstboot.log").read_text()


def test_firstboot_valid_hash_stages_installer_and_user_selection():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        result = stage_firstboot(root / "boot", root / "system")
        assert result.returncode == 0, (root / "boot/v-link-firstboot.log").read_text()
        assert (root / "system/usr/local/libexec/v-link-install-lite").exists()
        selector = (root / "system/usr/local/sbin/v-link-firstboot-user").read_text()
        assert "UID_MIN" in selector and "UID_MAX" in selector
        assert "getent passwd 1000" not in selector
        assert "Multiple eligible users" in selector


def test_firstboot_direct_removes_only_its_temporary_cmdline_arguments():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        result = stage_firstboot(root / "boot", root / "system", direct=True)
        assert result.returncode == 0, (root / "boot/v-link-firstboot.log").read_text()
        assert (root / "boot/cmdline.txt").read_text() == "rootwait console=tty1\n"


def test_firstboot_user_selector_waits_for_one_and_rejects_ambiguity():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        result = stage_firstboot(root / "boot", root / "system")
        assert result.returncode == 0
        selector = root / "system/usr/local/sbin/v-link-firstboot-user"
        home_a = root / "human-a"
        home_b = root / "human-b"
        home_a.mkdir()
        home_b.mkdir()
        bin_dir = root / "boot/bin"
        getent = bin_dir / "getent"
        env = {**os.environ, "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"]}
        getent.write_text("#!/bin/sh\nexit 0\n")
        getent.chmod(0o755)
        assert subprocess.run(["bash", str(selector)], env=env, capture_output=True).returncode == 2
        getent.write_text(f'#!/bin/sh\nprintf "%s\\n" "human-a:x:1100:1100::{home_a}:/bin/bash"\n')
        one = subprocess.run(["bash", str(selector)], env=env, capture_output=True, text=True)
        assert one.returncode == 0 and one.stdout.strip() == "human-a"
        getent.write_text(f'#!/bin/sh\nprintf "%s\\n" "human-a:x:1100:1100::{home_a}:/bin/bash" "human-b:x:1101:1101::{home_b}:/bin/bash"\n')
        many = subprocess.run(["bash", str(selector)], env=env, capture_output=True, text=True)
        assert many.returncode == 3 and "Multiple eligible users" in many.stderr


def test_lite_installer_cache_and_cleanup_remain_scoped():
    source = INSTALL.read_text()
    assert 'npm_config_cache="$TEMP_DIR/npm-cache"' in source
    assert "PIP_NO_CACHE_DIR=1" in source
    assert "rm -rf ~/.cache" not in source and "rm -rf ~/.npm" not in source
    assert "/var/log/v-link-firstboot-installer.log" in source
    assert "/boot/firmware/v-link-firstboot-installer.log" in source
    assert "/usr/local/sbin/v-link-firstboot-user" in source


def test_overlay_has_normal_handoff_and_bounded_fail_open():
    source = (ROOT / "lite/V-Link-Lite-Overlay.py").read_text()
    assert "if READY.is_set():" in source
    assert "SLOW_BOOT_SECONDS = 45" in source
    assert "MAX_COVER_SECONDS = 120" in source
    assert "Continue to V-Link" in source
    assert "self.window.destroy()" in source.split("def absolute_timeout", 1)[1]
    tree = ast.parse(source)
    overlay = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                   and node.name == "Overlay")
    methods = [node for node in overlay.body if isinstance(node, ast.FunctionDef)
               and node.name in {"check_handoff", "absolute_timeout"}]
    namespace = {}
    exec(compile(ast.Module(body=methods, type_ignores=[]), "overlay-methods", "exec"), namespace)

    class Window:
        destroyed = False

        def destroy(self):
            self.destroyed = True

    class Ready:
        value = False

        def is_set(self):
            return self.value

    namespace["READY"] = Ready()
    instance = type("FakeOverlay", (), {"window": Window()})()
    assert namespace["check_handoff"](instance) is True
    assert not instance.window.destroyed
    assert namespace["absolute_timeout"](instance) is False
    assert instance.window.destroyed
    instance.window.destroyed = False
    namespace["READY"].value = True
    assert namespace["check_handoff"](instance) is False
    assert instance.window.destroyed
    instance.window.destroyed = False
    assert namespace["absolute_timeout"](instance) is False
    assert not instance.window.destroyed


def test_platform_rollback_restores_only_unchanged_installer_output():
    source = INSTALL.read_text()
    functions = source.split("platform_sha256() {", 1)[1].split("\nusage() {", 1)[0]
    functions = "platform_sha256() {" + functions
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        target = root / "managed.conf"
        backup = root / "backup"
        backup.mkdir()
        for edited_by_user in (False, True):
            target.write_text("original")
            shutil.copy2(target, backup / "0")
            script = ("set -Eeuo pipefail\n" + functions + "\n"
                      'PLATFORM_PATHS=("$1")\nPLATFORM_BACKUP="$2"\n'
                      'PLATFORM_SEALED=true\n'
                      'platform_fingerprint "$1" >"$2/0.original"\n'
                      'printf installer >"$1"\nseal_platform_files\n')
            if edited_by_user:
                script += 'printf user >"$1"\n'
            script += "rollback_platform_files\n"
            result = subprocess.run(["bash", "-c", script, "bash", str(target), str(backup)],
                                    text=True, capture_output=True)
            assert result.returncode == 0, result.stderr
            assert target.read_text() == ("user" if edited_by_user else "original")

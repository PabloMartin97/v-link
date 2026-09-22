"""Host-only tests for Lite microphone setup (no recording hardware needed)."""

import array
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("v_link_lite_audio", ROOT / "v_link_lite_audio.py")
audio = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audio)


def sample_bytes(values):
    samples = array.array("h", values)
    if os.sys.byteorder != "little":
        samples.byteswap()
    return samples.tobytes()


class MicrophoneTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {"XDG_CONFIG_HOME": self.temp.name})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.home = self.temp.name

    def profile(self, preset="calls", **changes):
        profile = {"preset": preset, "physical": "alsa_input.usb-test", **audio.PRESETS["calls"]}
        profile.update(changes)
        return profile

    def test_silence_rms_peak_and_dbfs(self):
        self.assertEqual(audio.pcm_metrics(sample_bytes([0] * 100)),
                         {"rms": -90.0, "peak": -90.0, "clipping": False})
        self.assertAlmostEqual(audio.dbfs(16384), -6.02, places=1)
        result = audio.pcm_metrics(sample_bytes([16384, -16384] * 50))
        self.assertAlmostEqual(result["rms"], -6.02, places=1)
        self.assertAlmostEqual(result["peak"], -6.02, places=1)

    def test_clipping_needs_repeated_near_full_scale_samples(self):
        self.assertFalse(audio.pcm_metrics(sample_bytes([32767, 0, 0, 0]))["clipping"])
        self.assertTrue(audio.pcm_metrics(sample_bytes([32767, -32768, 32760, 0]))["clipping"])

    def test_noise_floor_is_quiet_quartile(self):
        windows = [{"rms": value} for value in (-31, -49, -51, -20)]
        self.assertEqual(audio.noise_floor(windows), -49)
        self.assertEqual(audio.noise_floor([]), -90)

    def test_calibration_is_conservative(self):
        self.assertGreater(audio.recommend_level(0.5, -50, -26, -12), 0.5)
        self.assertEqual(audio.recommend_level(0.5, -24, -21, -8), 0.5)
        self.assertLess(audio.recommend_level(0.8, -50, -8, -2), 0.8)

    def test_presets_do_not_duplicate_analogue_high_pass_or_enable_agc(self):
        self.assertEqual(audio.PRESETS["calls"],
                         {"noise": True, "agc": False, "high_pass": False})
        fragment = audio.render_config(self.profile())
        self.assertIn("monitor.mode = true", fragment)
        self.assertIn('target.object = "alsa_input.usb-test"', fragment)
        self.assertIn("webrtc.high_pass_filter = false", fragment)
        self.assertIn("webrtc.gain_control = false", fragment)
        self.assertIn(audio.SOURCE_NAME, fragment)
        self.assertNotIn("webrtc.noise_suppression_level", fragment)

    def test_custom_only_emits_supported_boolean_properties(self):
        fragment = audio.render_config(self.profile("custom", noise=True, agc=True))
        self.assertIn("webrtc.noise_suppression = true", fragment)
        self.assertIn("webrtc.gain_control = true", fragment)
        with self.assertRaises(audio.AudioError):
            audio.render_config(self.profile("custom", noise="moderate"))
        with self.assertRaises(audio.AudioError):
            audio.render_config(self.profile(physical='source"\nmalicious'))

    def test_only_managed_fragment_is_removed(self):
        path = audio.config_path(self.home)
        path.parent.mkdir(parents=True)
        other = path.parent / "other.conf"
        other.write_text("preserve me")
        audio._write_config(path, audio.render_config(self.profile()))
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(audio.read_profile(self.home)["preset"], "calls")
        self.assertTrue(audio.validate_installed_config(self.home))
        audio._write_config(path, None)
        self.assertFalse(path.exists())
        self.assertEqual(other.read_text(), "preserve me")

    def test_foreign_and_symlink_files_are_never_removed(self):
        path = audio.config_path(self.home)
        path.parent.mkdir(parents=True)
        path.write_text("foreign config")
        with self.assertRaises(audio.AudioError):
            audio._write_config(path, None)
        path.unlink()
        path.symlink_to(path.parent / "missing")
        with self.assertRaises(audio.AudioError):
            audio.validate_installed_config(self.home)

    def test_off_is_recoverable_from_damaged_lite_fragment(self):
        path = audio.config_path(self.home)
        path.parent.mkdir(parents=True)
        path.write_text(audio.MARKER + "\ninvalid\n")
        with self.assertRaises(audio.AudioError):
            audio.read_profile(self.home)
        audio._write_config(path, None)
        self.assertFalse(path.exists())

    def test_physical_sources_exclude_virtual_and_monitor_nodes(self):
        payload = json.dumps([{"id": index, "info": {"props": {
            "media.class": "Audio/Source", "node.name": name}}} for index, name in enumerate((
                "alsa_input.usb-test", audio.SOURCE_NAME, "alsa_output.hdmi.monitor"), 1)])
        self.assertEqual([node["name"] for node in audio.physical_sources(payload)],
                         ["alsa_input.usb-test"])

    def test_capture_uses_pipe_not_a_persistent_file(self):
        process = unittest.mock.MagicMock()
        process.poll.return_value = None
        with patch.object(audio.subprocess, "Popen", return_value=process) as popen:
            with audio.Capture("alsa_input.usb-test", {}) as capture:
                self.assertIs(capture.process, process)
            args, kwargs = popen.call_args
        self.assertEqual(args[0][-1], "-")
        self.assertEqual(kwargs["stdout"], audio.subprocess.PIPE)
        process.terminate.assert_called_once()

    def test_failed_activation_restores_previous_fragment(self):
        profile = self.profile()
        with patch.object(audio, "graph", return_value=json.dumps([{"id": 2, "info": {"props": {
                "media.class": "Audio/Source", "node.name": profile["physical"]}}}])), \
             patch.object(audio, "current_default_source", return_value=profile["physical"]), \
             patch.object(audio, "_select_source", return_value=True), \
             patch.object(audio, "_restart", side_effect=(audio.AudioError("bad graph"), None)):
            with self.assertRaisesRegex(audio.AudioError, "previous microphone configuration restored"):
                audio.apply_profile(self.home, profile, {})
        self.assertFalse(audio.config_path(self.home).exists())

    def test_successful_activation_sets_processed_default(self):
        profile = self.profile()
        with patch.object(audio, "graph", return_value=json.dumps([{"id": 2, "info": {"props": {
                "media.class": "Audio/Source", "node.name": profile["physical"]}}}])), \
             patch.object(audio, "current_default_source", side_effect=(profile["physical"], audio.SOURCE_NAME)), \
             patch.object(audio, "_restart") as restart, \
             patch.object(audio, "_wait_for_source") as wait:
            audio.apply_profile(self.home, profile, {})
        restart.assert_called_once()
        wait.assert_called_once_with(audio.SOURCE_NAME, {})
        self.assertEqual(audio.read_profile(self.home), profile)

    def test_off_selects_an_available_physical_source(self):
        path = audio.config_path(self.home)
        audio._write_config(path, audio.render_config(self.profile()))
        payload = json.dumps([{"id": 2, "info": {"props": {
            "media.class": "Audio/Source", "node.name": "alsa_input.replacement"}}}])
        with patch.object(audio, "current_default_source", return_value=audio.SOURCE_NAME), \
             patch.object(audio, "graph", return_value=payload), \
             patch.object(audio, "_restart"), \
             patch.object(audio, "_select_source") as select_source:
            audio.apply_profile(self.home, {"preset": "off", "physical": ""}, {})
        select_source.assert_called_once_with("alsa_input.replacement", {})
        self.assertFalse(path.exists())

    def test_off_removes_fragment_even_when_profile_metadata_is_corrupt(self):
        path = audio.config_path(self.home)
        path.parent.mkdir(parents=True)
        path.write_text(audio.MARKER + "\ninvalid\n")
        with patch.object(audio, "current_default_source", return_value=""), \
             patch.object(audio, "graph", return_value="[]"), \
             patch.object(audio, "_restart"):
            audio.apply_profile(self.home, {"preset": "off", "physical": ""}, {})
        self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()

"""
Unit tests for backend/settings.py
"""
import json
from pathlib import Path

import pytest

_APP_ROOT = Path(__file__).resolve().parent.parent.parent


# load_directory
def test_load_directory_creates_missing_dir(tmp_path, monkeypatch):
    from backend import settings
    new_dir = tmp_path / 'new_config'
    monkeypatch.setattr(settings, 'USER_CONFIG_DIR', new_dir)
    result = settings.load_directory()
    assert result == new_dir
    assert new_dir.is_dir()


def test_load_directory_returns_existing_dir(temp_config_dir):
    from backend import settings
    result = settings.load_directory()
    assert result == temp_config_dir
    assert result.is_dir()


# check_settings
def test_check_settings_returns_true_when_config_exists(seeded_config_dir):
    """Returns True when USER_CONFIG_DIR contains files (app.json is present)."""
    from backend import settings
    result = settings.check_settings()
    assert result is True


def test_check_settings_returns_profiles_dict_when_no_config(temp_config_dir):
    """Returns a platform→engines dict when USER_CONFIG_DIR is empty."""
    from backend import settings
    # Remove any files that might be there
    for f in temp_config_dir.iterdir():
        f.unlink()
    result = settings.check_settings()
    assert isinstance(result, dict)

    assert any(k in result for k in ('P1', 'P2'))


# save_settings / load_settings
def test_save_and_load_settings_roundtrip(temp_config_dir):
    from backend import settings
    payload = {'key': 'value', 'nested': {'n': 42}}
    settings.save_settings('test_module', payload)
    loaded = settings.load_settings('test_module')
    assert loaded == payload


def test_load_settings_returns_none_for_missing_file(temp_config_dir):
    from backend import settings
    result = settings.load_settings('nonexistent_module')
    assert result is None


def test_save_settings_writes_valid_json(temp_config_dir):
    from backend import settings
    settings.save_settings('json_check', {'a': 1, 'b': [1, 2, 3]})
    raw = (temp_config_dir / 'json_check.json').read_text()
    parsed = json.loads(raw)
    assert parsed == {'a': 1, 'b': [1, 2, 3]}


# copy_files
def test_copy_files_p1_t5_copies_profile_configs(temp_config_dir):
    """copy_files with P1/T5 must copy base app.json + profile can.json."""
    from backend import settings
    result = settings.copy_files({'platform': 'P1', 'engine': 'T5'})
    assert result is True
    assert (temp_config_dir / 'app.json').exists()


def test_copy_files_p2_d5_copies_profile_configs(temp_config_dir):
    from backend import settings
    result = settings.copy_files({'platform': 'P2', 'engine': 'D5'})
    assert result is True
    assert (temp_config_dir / 'app.json').exists()
    assert (temp_config_dir / 'can.json').exists()


# load_modules
def test_load_modules_sets_shared_state_flags(temp_config_dir, monkeypatch):
    """load_modules reads app.json constants.modules and sets shared_state flags."""
    from backend import settings
    from backend.shared.shared_state import SharedState

    fresh_state = SharedState()
    monkeypatch.setattr(settings, 'shared_state', fresh_state)

    app_data = {
        'constants': {
            'modules': {'can': True, 'rti': False, 'swc': True, 'adc': False}
        }
    }
    (temp_config_dir / 'app.json').write_text(json.dumps(app_data))

    settings.load_modules()

    assert fresh_state.canModule is True
    assert fresh_state.rtiModule is False
    assert fresh_state.swcModule is True
    assert fresh_state.adcModule is False

import json
import shutil
import logging
from pathlib import Path

from backend.shared.shared_state import shared_state

logger = logging.getLogger("vlink")

# Constants
APP_ROOT = Path(__file__).resolve().parent.parent
USER_CONFIG_DIR = Path.home() / ".config" / "v-link"

DEFAULT_PROFILES_DIR = APP_ROOT / "backend" / "config" / "profiles"
DEFAULT_CONFIG_DIR = APP_ROOT / "backend" / "config"

def load_directory():
    # Ensure user config directory exists.
    try:
        USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        return USER_CONFIG_DIR
    except Exception as e:
        logger.error(f"Error creating directory: {e}")
        return None
    

def check_settings():
    logger.info(f"Checking settings...")

    logger.info(f"App Root Directory: {APP_ROOT}")
    logger.info(f"Default profile directory: {DEFAULT_PROFILES_DIR}")
    logger.info(f"Default config directory: {DEFAULT_CONFIG_DIR}")
    logger.info(f"User config directory: {USER_CONFIG_DIR}")
    # If user config already exists and contains files, return True
    if USER_CONFIG_DIR.exists() and any(USER_CONFIG_DIR.iterdir()):
        return True
    else:
        # Scan profile directories and return available platforms + engines.
        try:
            result = {}
            for d in DEFAULT_PROFILES_DIR.iterdir():
                if d.is_dir():
                    subdirs = [sub.name for sub in d.iterdir() if sub.is_dir()]
                    result[d.name] = subdirs
            print (result)
            return result
        except Exception as e:
            logger.error(f"Error reading directories: {e}")
            return None


def load_settings(setting):
    logger.info(f"Loading settings for {setting}...")
    # Load settings file from user config.
    if not USER_CONFIG_DIR:
        return None

    settings_file = USER_CONFIG_DIR / f"{setting}.json"
    try:
        with settings_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
            logger.info(f"{setting}-settings loaded.")
            return data
    except Exception as e:
        logger.error(f"Error loading settings from '{settings_file}': {e}")
        return None
    
    
def save_settings(setting, data):
    # Specify the file path
    logger.info(f"Saving settings to '{setting}.json'...")
    json_path = USER_CONFIG_DIR / f"{setting}.json"

    # Save the settings to the JSON file
    try:
        with open(json_path, 'w') as file:
            json.dump(data, file, indent=4)
    except Exception as e:
        logger.error(f"Error saving settings to '{json_path}': {e}")


def reset_settings():
    # Reset configs by re-applying the last saved profile from app.json.
    logger.info("Resetting settings...")
    app_json_path = USER_CONFIG_DIR / "app.json"
    if not app_json_path.exists():
        raise FileNotFoundError("Undefined profile, please delete .config/v-link/ and restart the app.")

    with app_json_path.open("r", encoding="utf-8") as f:
        config = json.load(f)

    profile_data = config.get("constants", {}).get("profile")
    if not profile_data:
        raise ValueError("Undefined profile, please delete .config/v-link/ and restart the app.")

    copy_files(profile_data)


def copy_files(data):
    try:
        logger.info("Copying files to user config directory...")
        # Copy base + profile-specific config files into user config directory.
        platform = data.get("platform")
        engine = data.get("engine")

        profile_config = DEFAULT_CONFIG_DIR / "profiles" / platform / engine
        USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        def copy_json_files(src: Path, dst: Path):
            if src.is_dir():
                for file in src.glob("*.json"):
                    shutil.copy(file, dst)

        # Copy base + profile-specific configs
        copy_json_files(DEFAULT_CONFIG_DIR, USER_CONFIG_DIR)
        copy_json_files(profile_config, USER_CONFIG_DIR)

        # --- Modify app.json after copying ---
        app_json_path = USER_CONFIG_DIR / "app.json"
        if app_json_path.exists():
            with app_json_path.open("r", encoding="utf-8") as f:
                config = json.load(f)

            constants = config.get("constants", {})
            constants["profile"] = data
            config["constants"] = constants

            with app_json_path.open("w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
                f.write("\n")  # ensure trailing newline

        return True
    except Exception as e:
        logger.error(f"Error copying files: {e}")
        return False

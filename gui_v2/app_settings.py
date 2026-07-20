"""
gui_v2/app_settings.py

Loads and saves the app settings JSON so examiner identity and the AI engine
choice survive restarts.

The Anthropic API key is deliberately NOT persisted — the settings screen
promises "held in memory only, never written to disk", and this module is
where that promise is enforced: the key is stripped before every save.
"""

import json
import os

from .case_store import app_data_dir

_NEVER_PERSIST = ("cloud_api_key",)


def _settings_path() -> str:
    data_root = os.path.dirname(app_data_dir())
    return os.path.join(data_root, "settings.json")


def load() -> dict:
    """Saved settings, or {} on a fresh install / unreadable file."""
    try:
        with open(_settings_path(), "r", encoding="utf-8") as settings_file:
            loaded = json.load(settings_file)
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def save(settings: dict):
    persistable = {key: value for key, value in settings.items()
                   if key not in _NEVER_PERSIST}
    try:
        with open(_settings_path(), "w", encoding="utf-8") as settings_file:
            json.dump(persistable, settings_file, indent=2)
    except OSError:
        pass

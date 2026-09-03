"""
settings.py
Site-wide, admin-editable configuration (the "fully customisable" layer).

Everything here is safe to tweak at runtime from the Settings page without
touching code: brand name, accent colors, shift length, recognition
strictness, the Vault passcode, and default sound preference.
"""

import json
import os

CONFIG_FILE = "config.json"

DEFAULTS = {
    "brand_name": "FaceID",
    "theme_color_start": "#5B63F4",
    "theme_color_end": "#9168FF",
    "shift_hours": 8,
    "recognition_threshold": 100,
    "vault_passcode": "vault",
    "sound_enabled_default": True,
}


def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULTS)
        return dict(DEFAULTS)
    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
        merged = dict(DEFAULTS)
        merged.update(data or {})
        return merged
    except (json.JSONDecodeError, ValueError):
        save_config(DEFAULTS)
        return dict(DEFAULTS)


def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)


def update_config(partial):
    config = load_config()
    config.update(partial)
    save_config(config)
    return config

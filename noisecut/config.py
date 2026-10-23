"""Config, autorun registry and resource paths."""

import json
import os
import sys
import winreg

APP_NAME = "noise-cut"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

DEFAULTS = {
    "input": "",
    "output": "",
    "mix": 100.0,
    "denoiser": "rnnoise",
    "aec": True,
    "auto_start": True,
    "mute_toggle": True,
    "mini_visible": True,
    "mini_x": None,
    "mini_y": None,
}


def resource_path(*parts: str) -> str:
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def config_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, APP_NAME)


def config_path() -> str:
    return os.path.join(config_dir(), "config.json")


def load() -> dict:
    data = dict(DEFAULTS)
    try:
        with open(config_path(), encoding="utf-8") as handle:
            stored = json.load(handle)
        if isinstance(stored, dict):
            for key in DEFAULTS:
                if key in stored:
                    data[key] = stored[key]
    except (OSError, ValueError):
        pass
    return data


def save(data: dict) -> None:
    try:
        os.makedirs(config_dir(), exist_ok=True)
        with open(config_path(), "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
    except OSError:
        pass


def launch_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    script = resource_path("app.py")
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    exe = pythonw if os.path.isfile(pythonw) else sys.executable
    return f'"{exe}" "{script}"'


def autorun_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
        return bool(value)
    except OSError:
        return False


def set_autorun(enabled: bool) -> bool:
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            if enabled:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, launch_command())
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False

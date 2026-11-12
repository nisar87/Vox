"""Settings, stored outside the repo so API keys never reach GitHub."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

DEFAULTS: dict = {
    # AI brain
    "provider": "gemini",  # "gemini" | "openai"
    "gemini_key": "",
    "gemini_model": "gemini-3.5-flash-lite",
    "openai_key": "",
    "openai_model": "",
    "openai_base": "https://api.openai.com/v1",
    # Hearing
    "stt": "auto",  # "auto" (the AI provider if a key is set, else this PC) | "local" | "openai" | "gemini"
    "wake_heard": "",  # how the on-PC model hears this user's "Hi Vox", learned in Settings; "|" separated
    "local_stt_model": "base.en",
    "openai_stt_model": "gpt-transcribe",
    "hotkey": "ctrl+alt+space",
    "listen_mode": "tap",  # "tap" (stops on silence) | "hold"
    "standby": False,  # keep listening for "Hi Vox"
    "pause_on_calls": True,  # stay silent while another app uses the microphone
    "user_name": "",
    # Speaking
    "speak": True,
    "voice_engine": "natural",  # "natural" (AI voice, falls back to Windows) | "windows"
    "natural_voice": "",  # provider voice name; empty = provider default
    "voice": "",
    "speech_rate": 2,  # SAPI scale, -10..10
    # Behaviour
    "browser": "chrome",  # "chrome" | "edge" | "firefox" | "default"
    "confirm_shell": True,
    "learning": True,
    "auto_update": True,
    "port": 8765,
    "settings_version": 2,
}

SECRET_KEYS = ("gemini_key", "openai_key")


def data_dir() -> Path:
    """Folder for large files that should not roam between PCs (speech models)."""
    if os.environ.get("VOX_HOME"):
        base = Path(os.environ["VOX_HOME"])
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Vox"
    else:
        base = Path.home() / ".cache" / "vox"
    base.mkdir(parents=True, exist_ok=True)
    return base


def default_name() -> str:
    """First name from the Windows account, e.g. 'Nisar Ahmad' -> 'Nisar'."""
    try:
        import getpass

        first = getpass.getuser().replace(".", " ").replace("_", " ").split()[0]
        return first.capitalize() if first.isalpha() and first.lower() not in ("user", "admin", "root") else ""
    except Exception:
        return ""


def home() -> Path:
    """Folder for settings, the undo journal and logs."""
    override = os.environ.get("VOX_HOME")
    if override:
        base = Path(override)
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home())) / "Vox"
    else:
        base = Path.home() / ".config" / "vox"
    base.mkdir(parents=True, exist_ok=True)
    return base


class Config:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.path = home() / "config.json"
        self.data = dict(DEFAULTS)
        if self.path.exists():
            try:
                saved = json.loads(self.path.read_text("utf-8"))
                self.data.update({k: v for k, v in saved.items() if k in DEFAULTS})
                self._migrate(saved)
            except (OSError, ValueError):
                pass  # a damaged file falls back to defaults
        if not self.data["user_name"]:
            self.data["user_name"] = default_name()

    def _migrate(self, saved: dict) -> None:
        """Move settings written by older versions to better defaults."""
        if int(saved.get("settings_version", 1)) < 2:
            # 0.3.0 and earlier: on-PC hearing misheard too much, and the default
            # Gemini model spent many seconds thinking about simple commands.
            if saved.get("stt") == "local":
                self.data["stt"] = "auto"
            if saved.get("gemini_model") == "gemini-flash-latest":
                self.data["gemini_model"] = DEFAULTS["gemini_model"]
            self.data["settings_version"] = 2

    def stt_engine(self) -> str:
        """Which speech recognition to use right now."""
        choice = self.data["stt"]
        if choice != "auto":
            return choice
        provider = self.data["provider"]
        return provider if self.data[f"{provider}_key"] else "local"

    def __getitem__(self, key: str):
        return self.data[key]

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def update(self, changes: dict) -> None:
        with self._lock:
            for key, value in changes.items():
                if key not in DEFAULTS:
                    continue
                # An empty secret from the UI means "keep the saved one".
                if key in SECRET_KEYS and not value:
                    continue
                expected = type(DEFAULTS[key])
                if expected is bool:
                    value = bool(value)
                elif expected is int:
                    value = int(value)
                else:
                    value = str(value).strip()
                self.data[key] = value
            self.path.write_text(json.dumps(self.data, indent=2), "utf-8")

    def public(self) -> dict:
        """Settings safe to send to the UI: keys are reduced to a hint."""
        out = dict(self.data)
        for key in SECRET_KEYS:
            secret = out.pop(key)
            out[key + "_set"] = bool(secret)
            out[key + "_hint"] = ("…" + secret[-4:]) if len(secret) > 8 else ""
        return out

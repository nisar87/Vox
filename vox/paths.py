"""Find the user's real folders (Desktop may live inside OneDrive)."""

from __future__ import annotations

import os
import re
from pathlib import Path

_GUIDS = {
    "desktop": "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
    "documents": "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}",
    "downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
    "pictures": "{33E28130-4E1E-4676-835A-98395C3BC3BB}",
    "music": "{4BD8D571-6D19-48D3-BE97-422220080E43}",
    "videos": "{18989B1D-99B5-455B-841C-AB7C74E4DDFC}",
}
KNOWN = tuple(_GUIDS)
_cache: dict[str, Path] = {}


def _windows_folder(guid: str) -> Path | None:
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [
                ("a", wintypes.DWORD),
                ("b", wintypes.WORD),
                ("c", wintypes.WORD),
                ("d", ctypes.c_ubyte * 8),
            ]

        g = GUID()
        ctypes.windll.ole32.CLSIDFromString(ctypes.c_wchar_p(guid), ctypes.byref(g))
        out = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(out)) != 0:
            return None
        path = Path(out.value)
        ctypes.windll.ole32.CoTaskMemFree(out)
        return path
    except Exception:
        return None


def known_folder(name: str) -> Path:
    name = name.lower()
    if name not in _cache:
        path = _windows_folder(_GUIDS[name]) if os.name == "nt" else None
        _cache[name] = path or Path.home() / name.capitalize()
    return _cache[name]


def reset_cache() -> None:
    _cache.clear()


_ALIAS = re.compile(
    r"^(?:my |the )?(desktop|documents|downloads|pictures|music|videos)(?: folder)?(?=$|[\\/])",
    re.I,
)


def resolve(text: str) -> Path:
    """Turn 'desktop', 'Downloads/old', '~/x' or a full path into a Path."""
    text = os.path.expandvars(str(text).strip().strip('"'))
    match = _ALIAS.match(text)
    if match:
        rest = text[match.end():].lstrip("\\/")
        base = known_folder(match.group(1))
        return base / rest if rest else base
    path = Path(text).expanduser()
    return path if path.is_absolute() else Path.home() / path

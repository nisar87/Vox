"""File and folder skills. Everything that moves is journaled for undo."""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from .. import paths
from .base import tool

DAY = 86400
SKIP_NAMES = {"desktop.ini", "thumbs.db"}
CATEGORIES = {
    "Documents": "pdf doc docx txt rtf odt xls xlsx csv ppt pptx md epub",
    "Images": "jpg jpeg png gif bmp webp svg heic tiff ico",
    "Videos": "mp4 mkv avi mov wmv webm flv m4v",
    "Audio": "mp3 wav flac aac ogg m4a wma",
    "Archives": "zip rar 7z tar gz iso",
    "Installers": "exe msi msix appx",
    "Code": "py js ts html css json xml yml yaml sql sh bat ps1 java cs cpp c go rs php ipynb",
}
EXT_TO_CATEGORY = {ext: cat for cat, exts in CATEGORIES.items() for ext in exts.split()}
KEEP_IN_PLACE = {"lnk", "url"}  # shortcuts stay where the user put them
USE_CREATED_TIME = True  # tests switch this off: a file's creation time cannot be back-dated


def _hidden(entry: Path) -> bool:
    if entry.name.startswith(".") or entry.name.lower() in SKIP_NAMES:
        return True
    try:
        return bool(getattr(entry.stat(), "st_file_attributes", 0) & 0x2)
    except OSError:
        return True


def last_used(entry: Path) -> float:
    """Best available 'last used' time.

    Windows often does not update the access time, so this takes the newest of
    accessed, modified and created.
    """
    st = entry.stat()
    # Creation time exists on Windows; elsewhere st_ctime means something else.
    created = getattr(st, "st_birthtime", st.st_ctime if os.name == "nt" else 0) if USE_CREATED_TIME else 0
    return max(st.st_atime, st.st_mtime, created)


def _entries(folder: Path) -> list[Path]:
    return sorted((e for e in folder.iterdir() if not _hidden(e)), key=lambda e: e.name.lower())


def _free_name(dest_dir: Path, name: str) -> Path:
    target = dest_dir / name
    stem, suffix, n = Path(name).stem, Path(name).suffix, 2
    while target.exists():
        target = dest_dir / f"{stem} ({n}){suffix}"
        n += 1
    return target


def _ensure_folder(ctx, folder: Path) -> None:
    if not folder.exists():
        folder.mkdir(parents=True)
        ctx.journal.record("mkdir", path=str(folder))


def _move(ctx, src: Path, dest_dir: Path) -> Path:
    target = _free_name(dest_dir, src.name)
    shutil.move(str(src), str(target))
    ctx.journal.record("move", src=str(src), dst=str(target))
    return target


def _dest(folder: Path, destination: str) -> Path:
    """A bare name like 'Old stuff' means a subfolder of the folder being worked on."""
    bare = not any(sep in destination for sep in "\\/") and not paths._ALIAS.match(destination)
    return folder / destination if bare else paths.resolve(destination)


def _plural(n: int, word: str = "item") -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _select(folder: Path, unused_days=None, extensions=None, name_contains=None,
            include_folders=True, exclude: Path | None = None) -> list[Path]:
    cutoff = time.time() - float(unused_days) * DAY if unused_days else None
    exts = {e.lower().lstrip(".") for e in extensions} if extensions else None
    needle = name_contains.lower() if name_contains else None
    picked = []
    for entry in _entries(folder):
        if exclude and entry == exclude:
            continue
        if entry.is_dir() and (not include_folders or exts):
            continue
        if exts and entry.suffix.lower().lstrip(".") not in exts:
            continue
        if needle and needle not in entry.name.lower():
            continue
        if cutoff and last_used(entry) > cutoff:
            continue
        picked.append(entry)
    return picked


_FILTERS = {
    "unused_days": {"type": "number", "description": "Only items not opened or changed in this many days."},
    "extensions": {"type": "array", "items": {"type": "string"}, "description": "File types, e.g. ['pdf','docx']."},
    "name_contains": {"type": "string", "description": "Only items whose name contains this text."},
}
_FOLDER = {"type": "string", "description": "Folder: 'desktop', 'downloads', 'documents', 'pictures', or a full path."}


@tool("list_folder", "List what is inside a folder.", {"folder": _FOLDER}, ("folder",), kind="info")
def list_folder(ctx, folder):
    path = paths.resolve(folder)
    if not path.is_dir():
        return {"ok": False, "message": f"I can't find the folder {path}."}
    now, rows = time.time(), []
    for entry in _entries(path)[:200]:
        rows.append({
            "name": entry.name,
            "type": "folder" if entry.is_dir() else "file",
            "days_since_used": int((now - last_used(entry)) / DAY),
        })
    return {"message": f"{path} has {_plural(len(rows))}.", "path": str(path), "items": rows}


@tool("find_files", "Search a folder (and its subfolders) for files.",
      {"folder": _FOLDER, **_FILTERS}, ("folder",), kind="info")
def find_files(ctx, folder, unused_days=None, extensions=None, name_contains=None):
    root = paths.resolve(folder)
    if not root.is_dir():
        return {"ok": False, "message": f"I can't find the folder {root}."}
    found = []
    for dirpath, dirnames, _ in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        found += [str(p) for p in _select(Path(dirpath), unused_days, extensions, name_contains, False)]
        if len(found) >= 100:
            break
    return {"message": f"Found {_plural(len(found), 'file')}.", "files": found[:100]}


@tool("create_folder", "Create a folder.",
      {"path": {"type": "string", "description": "e.g. 'desktop/Old stuff' or a full path."}}, ("path",))
def create_folder(ctx, path):
    folder = paths.resolve(path)
    if folder.exists():
        return {"message": f"{folder.name} already exists.", "path": str(folder)}
    _ensure_folder(ctx, folder)
    return {"message": f"Created the folder {folder.name}.", "path": str(folder)}


@tool("move_items", "Move specific files or folders into a destination folder (created if missing).",
      {"sources": {"type": "array", "items": {"type": "string"}, "description": "Paths to move."},
       "destination": {"type": "string", "description": "Destination folder."}},
      ("sources", "destination"))
def move_items(ctx, sources, destination):
    dest = paths.resolve(destination)
    _ensure_folder(ctx, dest)
    moved, missing = 0, []
    for source in sources:
        src = paths.resolve(source)
        if src.exists():
            _move(ctx, src, dest)
            moved += 1
        else:
            missing.append(src.name)
    message = f"Moved {_plural(moved)} to {dest.name}."
    if missing:
        message += f" I couldn't find: {', '.join(missing[:5])}."
    return {"ok": moved > 0 or not missing, "message": message}


@tool("move_matching",
      "Move every item in a folder that matches the filters into a destination folder "
      "(created if missing). Use this for requests like 'move everything on my desktop "
      "not opened in 20 days into a new folder'.",
      {"folder": _FOLDER,
       "destination": {"type": "string", "description": "Folder name (created inside 'folder') or a full path."},
       **_FILTERS,
       "include_folders": {"type": "boolean", "description": "Also move subfolders. Default true."}},
      ("folder", "destination"))
def move_matching(ctx, folder, destination, unused_days=None, extensions=None,
                  name_contains=None, include_folders=True):
    root = paths.resolve(folder)
    if not root.is_dir():
        return {"ok": False, "message": f"I can't find the folder {root}."}
    dest = _dest(root, destination)
    picked = _select(root, unused_days, extensions, name_contains, include_folders, exclude=dest)
    if not picked:
        return {"message": "Nothing matched, so I left everything where it is.", "moved": 0}
    _ensure_folder(ctx, dest)
    for entry in picked:
        _move(ctx, entry, dest)
    note = " I went by the last time each was opened or changed." if unused_days else ""
    return {"message": f"Moved {_plural(len(picked))} into {dest.name}.{note}", "moved": len(picked)}


def _organize_plan(folder: Path) -> dict[str, list[Path]]:
    plan: dict[str, list[Path]] = {}
    for entry in _entries(folder):
        ext = entry.suffix.lower().lstrip(".")
        if entry.is_dir() or ext in KEEP_IN_PLACE:
            continue
        plan.setdefault(EXT_TO_CATEGORY.get(ext, "Other"), []).append(entry)
    return plan


def _organize_preview(args, ctx) -> str:
    folder = paths.resolve(args.get("folder", "desktop"))
    plan = _organize_plan(folder) if folder.is_dir() else {}
    if not plan:
        return f"{folder.name} has no loose files to sort. Continue anyway?"
    total = sum(len(v) for v in plan.values())
    parts = ", ".join(f"{len(v)} to {k}" for k, v in sorted(plan.items(), key=lambda kv: -len(kv[1])))
    return (f"I'll sort {_plural(total, 'file')} in {folder.name} into folders by type: {parts}. "
            "Shortcuts and existing folders stay put. Shall I go ahead?")


@tool("organize_folder",
      "Tidy a folder by sorting its loose files into subfolders by type "
      "(Documents, Images, Videos, Audio, Archives, Installers, Code, Other).",
      {"folder": _FOLDER}, ("folder",), confirm=True, preview=_organize_preview)
def organize_folder(ctx, folder):
    root = paths.resolve(folder)
    if not root.is_dir():
        return {"ok": False, "message": f"I can't find the folder {root}."}
    plan = _organize_plan(root)
    total = 0
    for category, entries in plan.items():
        dest = root / category
        _ensure_folder(ctx, dest)
        for entry in entries:
            _move(ctx, entry, dest)
            total += 1
    if not total:
        return {"message": f"{root.name} was already tidy."}
    return {"message": f"Sorted {_plural(total, 'file')} in {root.name} into {_plural(len(plan), 'folder')}."}


@tool("rename_item", "Rename a file or folder.",
      {"path": {"type": "string"}, "new_name": {"type": "string"}}, ("path", "new_name"))
def rename_item(ctx, path, new_name):
    src = paths.resolve(path)
    if not src.exists():
        return {"ok": False, "message": f"I can't find {src.name}."}
    target = src.with_name(new_name)
    if target.exists():
        return {"ok": False, "message": f"{new_name} already exists there."}
    src.rename(target)
    ctx.journal.record("move", src=str(src), dst=str(target))
    return {"message": f"Renamed {src.name} to {new_name}."}


def _delete_preview(args, ctx) -> str:
    names = [paths.resolve(p).name for p in args.get("items", [])]
    shown = ", ".join(names[:4]) + ("…" if len(names) > 4 else "")
    return f"Send {_plural(len(names))} to the Recycle Bin ({shown})?"


@tool("delete_items", "Send files or folders to the Recycle Bin.",
      {"items": {"type": "array", "items": {"type": "string"}, "description": "Paths to delete."}},
      ("items",), confirm=True, preview=_delete_preview)
def delete_items(ctx, items):
    try:
        from send2trash import send2trash
    except ImportError:
        return {"ok": False, "message": "Deleting needs the send2trash package. Run install.bat again."}
    done = 0
    for item in items:
        path = paths.resolve(item)
        if path.exists():
            send2trash(str(path))
            done += 1
    return {"ok": done > 0, "message": f"Sent {_plural(done)} to the Recycle Bin. You can restore from there."}


@tool("open_path", "Open a file or folder with its default program.",
      {"path": {"type": "string"}}, ("path",))
def open_path(ctx, path):
    target = paths.resolve(path)
    if not target.exists():
        return {"ok": False, "message": f"I can't find {target}."}
    if os.name == "nt":
        os.startfile(str(target))  # noqa: S606 - opening the user's own file
    else:
        import subprocess

        subprocess.Popen(["xdg-open", str(target)])
    return {"message": f"Opened {target.name}."}

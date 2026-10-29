"""File-system operations that do not need the UI: trash, recursive search, bookmarks,
batch renaming."""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from urllib.parse import quote

from .config import data_dir
from .i18n import tr

# ------------------------------------------------------------------ trash


def trash_dir():
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"),
                                                           ".local", "share")
    return os.path.join(base, "Trash")


def _mac_trash(path):
    """macOS: move into ~/.Trash (Finder can "Put Back" only for its own deletions)."""
    tdir = os.path.join(os.path.expanduser("~"), ".Trash")
    os.makedirs(tdir, exist_ok=True)
    name = os.path.basename(path)
    dest, i = os.path.join(tdir, name), 1
    while os.path.lexists(dest):
        i += 1
        root, ext = os.path.splitext(name)
        dest = os.path.join(tdir, "%s %d%s" % (root, i, ext))
    shutil.move(path, dest)


def move_to_trash(path):
    """Move to the freedesktop.org trash in the user's data directory (macOS: ~/.Trash)."""
    path = os.path.abspath(path)
    if sys.platform == "darwin":
        return _mac_trash(path)
    files = os.path.join(trash_dir(), "files")
    infos = os.path.join(trash_dir(), "info")
    os.makedirs(files, mode=0o700, exist_ok=True)
    os.makedirs(infos, mode=0o700, exist_ok=True)
    name = os.path.basename(path)
    dest, i = os.path.join(files, name), 1
    while os.path.lexists(dest) or \
            os.path.lexists(os.path.join(infos, os.path.basename(dest) + ".trashinfo")):
        i += 1
        dest = os.path.join(files, "%s.%d" % (name, i))
    info = os.path.join(infos, os.path.basename(dest) + ".trashinfo")
    with open(info, "w", encoding="utf-8") as f:
        f.write("[Trash Info]\nPath=%s\nDeletionDate=%s\n"
                % (quote(path), time.strftime("%Y-%m-%dT%H:%M:%S")))
    try:
        shutil.move(path, dest)
    except BaseException:
        try:
            os.unlink(info)
        except OSError:
            pass
        raise


def trash(path):
    """Trash a file; files on another disk are handed to `gio trash` when available."""
    try:
        other_disk = os.lstat(path).st_dev != os.stat(os.path.expanduser("~")).st_dev
    except OSError:
        other_disk = False
    if other_disk and sys.platform != "darwin" and shutil.which("gio"):
        r = subprocess.run(["gio", "trash", "--", os.path.abspath(path)],
                           capture_output=True, timeout=120)
        if r.returncode == 0:
            return
    move_to_trash(path)


# ------------------------------------------------------------------ search

SKIP_DIRS = {".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
             ".mypy_cache", ".pytest_cache", ".tox", ".cache"}


def search_files(root, pattern, max_results=2000, budget=8.0, max_size=2 * 1024 * 1024):
    """Recursive regex search. Smart case: an all-lowercase pattern ignores case.
    -> (results, truncated); results = [(path, line_number, line_text, matched_text)].
    Raises re.error for an invalid pattern."""
    rx = re.compile(pattern, re.I if pattern == pattern.lower() else 0)
    results, truncated = [], False
    deadline = time.time() + budget
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".git"))
        for fn in sorted(filenames):
            if time.time() > deadline or len(results) >= max_results:
                return results, True
            path = os.path.join(dirpath, fn)
            try:
                if os.path.islink(path) or os.path.getsize(path) > max_size:
                    continue
                with open(path, "rb") as f:
                    data = f.read()
            except OSError:
                continue
            if b"\0" in data[:8192]:
                continue
            text = data.decode("utf-8", "replace")
            for n, line in enumerate(text.split("\n"), 1):
                m = rx.search(line)
                if m:
                    results.append((path, n, line.rstrip("\r"), m.group(0)))
                    if len(results) >= max_results:
                        truncated = True
                        break
    return results, truncated


# ------------------------------------------------------------------ bookmarks

def _bookmarks_file():
    return os.path.join(data_dir(), "bookmarks.json")


def load_bookmarks():
    try:
        with open(_bookmarks_file(), encoding="utf-8") as f:
            data = json.load(f)
        return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}
    except (OSError, ValueError, AttributeError):
        return {}


def save_bookmarks(marks):
    os.makedirs(data_dir(), exist_ok=True)
    tmp = _bookmarks_file() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(marks, f, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, _bookmarks_file())


# ------------------------------------------------------------------ batch rename

def plan_renames(directory, old_names, new_names):
    """Validate a batch rename. -> (pairs [(old, new)] for the changed names, error or None)."""
    if len(old_names) != len(new_names):
        return [], tr("The number of lines changed: expected {n}").format(n=len(old_names))
    pairs = [(o, n) for o, n in zip(old_names, new_names) if o != n]
    seen = set()
    final = set(new_names)
    moving = {o for o, _ in pairs}
    for _o, n in pairs:
        if not n.strip() or n in (".", "..") or "/" in n or "\0" in n:
            return [], tr("Invalid name: {name}").format(name=n or tr("(empty)"))
        if n in seen:
            return [], tr("Duplicate name: {name}").format(name=n)
        seen.add(n)
    if len(final) != len(new_names):
        dup = next(n for n in new_names if new_names.count(n) > 1)
        return [], tr("Duplicate name: {name}").format(name=dup)
    for _o, n in pairs:
        if os.path.lexists(os.path.join(directory, n)) and n not in moving:
            return [], tr("Already exists: {name}").format(name=n)
    return pairs, None


def apply_renames(directory, pairs):
    """Rename in two phases so that swaps and chains (a->b, b->c) work; rolls back on error."""
    def join(name):
        return os.path.join(directory, name)

    staged, placed = [], []
    try:
        for i, (old, new) in enumerate(pairs):
            tmp = ".nanger-rename-%d-%d" % (os.getpid(), i)
            os.rename(join(old), join(tmp))
            staged.append((tmp, old, new))
        for tmp, old, new in staged:
            os.rename(join(tmp), join(new))
            placed.append((new, old))
    except OSError:
        placed_names = {new for new, _old in placed}
        for new, old in reversed(placed):  # best-effort rollback
            try:
                os.rename(join(new), join(old))
            except OSError:
                pass
        for tmp, old, new in staged:
            if new not in placed_names and os.path.lexists(join(tmp)):
                try:
                    os.rename(join(tmp), join(old))
                except OSError:
                    pass
        raise
    return len(pairs)

"""Crash recovery: unsaved editor buffers are written to a side file and offered back on reopen."""
import hashlib
import json
import os
import time

from .config import data_dir

MAX_AGE = 30 * 86400


def folder():
    return os.path.join(data_dir(), "recovery")


def _file(path):
    key = hashlib.sha1(os.path.realpath(path).encode("utf-8", "surrogateescape")).hexdigest()
    return os.path.join(folder(), key + ".json")


def interval():
    try:
        return max(0.2, float(os.environ.get("NANGER_AUTOSAVE", "5")))
    except ValueError:
        return 5.0


def write(path, lines, enc="utf-8", nl="\n"):
    """Atomically store the buffer; returns True on success."""
    try:
        os.makedirs(folder(), exist_ok=True)
        dest = _file(path)
        tmp = dest + ".tmp"
        with open(tmp, "w", encoding="utf-8", errors="surrogateescape") as f:
            json.dump({"path": os.path.realpath(path), "text": "\n".join(lines), "enc": enc,
                       "nl": nl, "saved_at": time.time()}, f, ensure_ascii=False)
        os.replace(tmp, dest)
        return True
    except (OSError, ValueError, UnicodeError):
        return False


def load(path):
    try:
        with open(_file(path), encoding="utf-8", errors="surrogateescape") as f:
            d = json.load(f)
        if isinstance(d, dict) and isinstance(d.get("text"), str):
            return d
    except (OSError, ValueError):
        pass
    return None


def discard(path):
    try:
        os.unlink(_file(path))
    except OSError:
        pass


def prune():
    """Drop recovery files older than 30 days (and stray temp files)."""
    try:
        now = time.time()
        for n in os.listdir(folder()):
            p = os.path.join(folder(), n)
            if n.endswith(".tmp") or now - os.path.getmtime(p) > MAX_AGE:
                os.unlink(p)
    except OSError:
        pass

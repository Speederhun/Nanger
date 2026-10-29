"""Read-only git integration: status of files in a directory, and the HEAD version of a
file (for the editor's changed-lines gutter). Every function degrades to "nothing" when
git is missing, the directory is not a repository, or git is slow."""
import difflib
import os
import shutil
import subprocess
import time

from .config import settings

_ENV = dict(os.environ, GIT_OPTIONAL_LOCKS="0", LC_ALL="C", GIT_TERMINAL_PROMPT="0")
_root_cache = {}
_status_cache = {}
STATUS_TTL = 2.0


def enabled():
    return settings.git and shutil.which("git") is not None


def _run(args, cwd, timeout=3):
    try:
        r = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, timeout=timeout,
                           env=_ENV)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def repo_root(directory):
    """Top-level directory of the repository containing `directory`, or None."""
    if not enabled():
        return None
    if directory in _root_cache:
        return _root_cache[directory]
    out = _run(["rev-parse", "--show-toplevel"], directory)
    root = os.path.realpath(out.decode("utf-8", "surrogateescape").strip()) if out else None
    _root_cache[directory] = root or None
    return _root_cache[directory]


def invalidate():
    _status_cache.clear()


def status(directory):
    """-> (root, {path relative to root: 'XY'}) or (None, {})."""
    root = repo_root(directory)
    if not root:
        return None, {}
    hit = _status_cache.get(root)
    if hit and time.time() - hit[0] < STATUS_TTL:
        return root, hit[1]
    out = _run(["status", "--porcelain=v1", "-z", "--untracked-files=normal"], root, 5)
    result = {}
    if out:
        parts = out.split(b"\0")
        i = 0
        while i < len(parts):
            entry = parts[i]
            i += 1
            if len(entry) < 4:
                continue
            xy = entry[:2].decode("ascii", "replace")
            path = entry[3:].decode("utf-8", "surrogateescape").rstrip("/")
            if xy[0] in "RC":
                i += 1  # skip the "original path" field of renames/copies
            result[path] = xy
    _status_cache[root] = (time.time(), result)
    return root, result


def entry_status(directory, name):
    """'XY' status of one entry of `directory`; folders get the strongest child status."""
    root, stat = status(directory)
    if not root:
        return ""
    rel = os.path.relpath(os.path.join(os.path.realpath(directory), name), root)
    if rel in stat:
        return stat[rel]
    prefix = rel + os.sep
    best = ""
    for path, xy in stat.items():
        if path.startswith(prefix):
            if "U" in xy or xy in ("AA", "DD"):
                return xy
            best = best or xy
    return best


def head_lines(path):
    """Lines of the HEAD version of `path`, or None (not tracked / no repository)."""
    if not enabled() or not path:
        return None
    d = os.path.dirname(os.path.abspath(path))
    if not repo_root(d):
        return None
    out = _run(["show", "HEAD:./" + os.path.basename(path)], d, 5)
    if out is None or b"\0" in out[:8192]:
        return None
    text = out.decode("utf-8", "replace").replace("\r\n", "\n")
    if text.endswith("\n"):
        text = text[:-1]
    return text.split("\n")


def diff_marks(base, current, limit=8000):
    """{line index in `current`: '+' added | '~' changed | '_' lines deleted above}"""
    if base is None or len(current) > limit or len(base) > limit:
        return {}
    marks = {}
    sm = difflib.SequenceMatcher(None, base, current, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "insert":
            for j in range(j1, j2):
                marks[j] = "+"
        elif tag == "replace":
            for k, j in enumerate(range(j1, j2)):
                marks[j] = "~" if k < i2 - i1 else "+"
        elif tag == "delete":
            marks[min(j1, len(current) - 1)] = "_"
    return marks

"""Pure helpers: text file I/O, clipboard, small string/number utilities."""
import os
import shutil
import subprocess
import sys
import tempfile

from .i18n import tr


def human(n):
    for u in ("B", "K", "M", "G", "T"):
        if n < 1024:
            return "%.0f%s" % (n, u) if u == "B" else "%.1f%s" % (n, u)
        n /= 1024
    return "%.1fP" % n


def unique_path(dst):
    if not os.path.lexists(dst):
        return dst
    base, ext = os.path.splitext(dst)
    i = 1
    while os.path.lexists("%s_%d%s" % (base, i, ext)):
        i += 1
    return "%s_%d%s" % (base, i, ext)


def split_delim(s, d):
    """Split `s` on the delimiter `d`; a backslash before `d` escapes it."""
    parts, cur, i = [], "", 0
    while i < len(s):
        ch = s[i]
        if ch == "\\" and i + 1 < len(s):
            cur += d if s[i + 1] == d else ch + s[i + 1]
            i += 2
            continue
        if ch == d:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
        i += 1
    parts.append(cur)
    return parts


def load_text(path):
    """-> (lines, encoding, newline, trailing_newline). Raises ValueError on binary data."""
    with open(path, "rb") as f:
        data = f.read()
    if b"\0" in data[:8192]:
        raise ValueError(tr("binary file, cannot be edited"))
    try:
        text, enc = data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        text, enc = data.decode("iso-8859-2"), "iso-8859-2"
    nl = "\r\n" if "\r\n" in text else "\n"
    if nl == "\r\n":
        text = text.replace("\r\n", "\n")
    trailing = text.endswith("\n") or text == ""
    if text.endswith("\n"):
        text = text[:-1]
    return text.split("\n"), enc, nl, trailing


def save_text(path, lines, enc, nl, trailing):
    """Atomic save that keeps the file mode and follows symlinks."""
    path = os.path.realpath(path)
    data = (nl.join(lines) + (nl if trailing else "")).encode(enc, errors="replace")
    d = os.path.dirname(path)
    try:
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".nanger-")
    except OSError:
        with open(path, "wb") as f:  # no permission to create files here: write in place
            f.write(data)
        return
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        if os.path.exists(path):
            shutil.copymode(path, tmp)
        else:
            um = os.umask(0)
            os.umask(um)
            os.chmod(tmp, 0o666 & ~um)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def disk_sig(path):
    """(mtime_ns, size) of a file, or None if it does not exist."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def set_system_clipboard(text):
    cmds = []
    if sys.platform == "darwin":
        cmds.append(["pbcopy"])
    if os.environ.get("WAYLAND_DISPLAY"):
        cmds.append(["wl-copy"])
    if os.environ.get("DISPLAY"):
        cmds += [["xclip", "-selection", "clipboard"], ["xsel", "-b", "-i"]]
    for cmd in cmds:
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, input=text.encode(), timeout=1,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:  # noqa: BLE001 - the clipboard is a best-effort extra
                pass
            return

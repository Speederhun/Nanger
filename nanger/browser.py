"""The file manager view: three columns (parent | current | preview), ranger style."""
import curses
import os
import shutil
import stat as statmod
import subprocess
import tempfile
import time

from . import gitinfo
from .config import settings
from .fsops import load_bookmarks, save_bookmarks, trash
from .helptext import browser_help
from .i18n import tr
from .keys import BACKSPACE, C, ENTER, ESC
from .media import OFFICE_EXT, archive_lines, office_text, can_images, cached_render, draw_grid, file_kind, pdf_text
from .term import A, clean, draw_help, put
from .util import human, unique_path

SORT_IDS = ("name", "size", "date", "ext")


def sort_label(mode):
    return {"name": tr("name"), "size": tr("size, largest first"),
            "date": tr("modified, newest first"), "ext": tr("extension")}[mode]


def help_bar1():
    return [("Enter", tr("Open")), ("←", tr("Back")), ("n", tr("New file")),
            ("N", tr("New folder")), ("r", tr("Rename")), ("D", tr("Delete")),
            ("/", tr("Find")), ("q", tr("Quit"))]


def help_bar2():
    return [(tr("Space"), tr("Mark")), ("y", tr("Copy")), ("x", tr("Cut")), ("p", tr("Paste")),
            ("s", tr("Sort")), ("v", tr("View")), ("o", tr("External")), ("f", tr("Grep")),
            ("?", tr("Help"))]


def git_mark(xy):
    """'XY' porcelain status -> (character, attribute)."""
    if not xy:
        return " ", 0
    if xy == "??":
        return "?", A["gnew"]
    if "U" in xy or xy in ("AA", "DD"):
        return "U", A["gbad"]
    if xy[1] != " ":
        return ("D", A["gdel"]) if xy[1] == "D" else ("M", A["gmod"])
    x = xy[0]
    return (x if x in "MDR" else "A"), (A["gdel"] if x == "D" else A["gadd"])


class Browser:
    def __init__(self, app, path):
        self.app = app
        self.cwd = os.path.abspath(os.path.expanduser(path))
        self.prev_cwd = None
        self.hidden = settings.show_hidden
        self.sort = settings.sort
        self.sel = self.top = 0
        self.entries = []
        self.tagged = set()
        self.marked = None  # (paths, "copy" | "cut")
        self.last_search = ""
        self.last_grep = ""
        self._ls_cache = {}
        self._pv_key = None
        self._pv = ("lines", [], "")
        self.refresh()

    def listdir(self, d):
        try:
            mt = os.stat(d).st_mtime_ns
            names = os.listdir(d)
        except OSError:
            return None
        ckey = (mt, self.hidden, self.sort, len(names))
        hit = self._ls_cache.get(d)
        if hit and hit[0] == ckey:
            return hit[1]
        if not self.hidden:
            names = [n for n in names if not n.startswith(".")]

        def key(n):
            p = os.path.join(d, n)
            try:
                st = os.stat(p)
                isdir = os.path.isdir(p)
            except OSError:
                return (False, 0, n.casefold())
            if self.sort == "size":
                return (not isdir, -st.st_size, n.casefold())
            if self.sort == "date":
                return (not isdir, -st.st_mtime, n.casefold())
            if self.sort == "ext":
                return (not isdir, os.path.splitext(n)[1].casefold(), n.casefold())
            return (not isdir, n.casefold())

        names = sorted(names, key=key)
        self._ls_cache[d] = (ckey, names)
        return names

    def refresh(self, select=None):
        self._ls_cache.clear()
        gitinfo.invalidate()
        e = self.listdir(self.cwd)
        if e is None:
            self.app.error(tr("The folder cannot be read"))
            e = []
        self.entries = e
        if select in e:
            self.sel = e.index(select)
        self.sel = max(0, min(self.sel, len(e) - 1))
        self._pv_key = None

    def cd(self, path, select=None):
        path = os.path.abspath(os.path.expanduser(path))
        if not os.path.isdir(path):
            self.app.error(tr("Not a folder: {path}").format(path=path))
            return
        try:
            os.listdir(path)
        except OSError as e:
            self.app.error(tr("Cannot open: {error}").format(error=e.strerror))
            return
        if path != self.cwd:
            self.prev_cwd = self.cwd
        self.cwd = path
        self.sel = self.top = 0
        self.refresh(select)

    def current(self):
        if not self.entries:
            return None
        return os.path.join(self.cwd, self.entries[self.sel])

    def targets(self):
        if self.tagged:
            return sorted(self.tagged)
        cur = self.current()
        return [cur] if cur else []

    # ---- keys
    def handle(self, k):
        app = self.app
        n = len(self.entries)
        cur = self.current()
        page = max(1, app.text_height() - 1)
        if k in (curses.KEY_UP, "k"):
            self.sel = max(0, self.sel - 1)
        elif k in (curses.KEY_DOWN, "j"):
            self.sel = min(max(0, n - 1), self.sel + 1)
        elif k == curses.KEY_PPAGE:
            self.sel = max(0, self.sel - page)
        elif k == curses.KEY_NPAGE:
            self.sel = min(max(0, n - 1), self.sel + page)
        elif k in (curses.KEY_HOME, "g"):
            self.sel = 0
        elif k in (curses.KEY_END, "G"):
            self.sel = max(0, n - 1)
        elif k in (curses.KEY_LEFT, "h") or k in BACKSPACE:
            parent = os.path.dirname(self.cwd)
            if parent != self.cwd:
                self.cd(parent, os.path.basename(self.cwd))
        elif k in (curses.KEY_RIGHT, "l") or k in ENTER:
            if cur and os.path.isdir(cur):
                self.cd(cur)
            elif cur:
                app.open_path(cur)
        elif k == "e":
            if cur and not os.path.isdir(cur):
                app.edit(cur)
        elif k == "v":
            if cur and file_kind(cur) in ("image", "pdf"):
                app.open_path(cur, viewer=True)
            elif cur:
                app.info(tr("The viewer opens images and PDFs only (Enter = open)"))
        elif k == "o":
            if cur and not os.path.isdir(cur):
                app.open_external(cur)
        elif k == "s":
            self.sort = SORT_IDS[(SORT_IDS.index(self.sort) + 1) % len(SORT_IDS)]
            self.refresh(os.path.basename(cur) if cur else None)
            app.info(tr("Sorting: {mode}").format(mode=sort_label(self.sort)))
        elif k == "n":
            name = app.prompt(tr("New file name: "))
            if name:
                app.edit(os.path.join(self.cwd, os.path.expanduser(name)))
        elif k == "N":
            name = app.prompt(tr("New folder name: "))
            if name:
                try:
                    os.makedirs(os.path.join(self.cwd, name))
                    self.refresh(name.split("/")[0])
                except OSError as e:
                    app.error(tr("Failed: {error}").format(error=e.strerror))
        elif k == "r":
            self.rename(cur)
        elif k == "R":
            self.bulk_rename()
        elif k in ("D", curses.KEY_DC):
            self.delete()
        elif k == " ":
            if cur:
                self.tagged ^= {cur}
                self.sel = min(max(0, n - 1), self.sel + 1)
        elif k == ESC:
            self.tagged.clear()
        elif k in ("y", "x"):
            t = self.targets()
            if t:
                self.marked = (t, "copy" if k == "y" else "cut")
                self.tagged.clear()
                msg = tr("{n} items marked for copying — go to the target folder and press p") \
                    if k == "y" else tr("{n} items marked for cutting — go to the target folder and press p")
                app.info(msg.format(n=len(t)))
        elif k == "p":
            self.paste()
        elif k == ".":
            self.hidden = not self.hidden
            self.refresh(os.path.basename(cur) if cur else None)
        elif k == "/":
            t = app.prompt(tr("Search by name: "), self.last_search)
            if t:
                self.last_search = t
                low = t.casefold()
                for i in range(1, n + 1):
                    j = (self.sel + i) % n
                    if low in self.entries[j].casefold():
                        self.sel = j
                        break
                else:
                    app.error(tr("No match: {pattern}").format(pattern=t))
        elif k == "f":
            pat = app.prompt(tr("Search in files (regex, lower case = ignore case): "),
                             self.last_grep)
            if pat:
                self.last_grep = pat
                app.grep(pat, self.cwd)
        elif k == "c":
            p = app.prompt(tr("Go to: "), self.cwd)
            if p:
                self.cd(p if os.path.isabs(os.path.expanduser(p)) else os.path.join(self.cwd, p))
        elif k == "~":
            self.cd(os.path.expanduser("~"))
        elif k == "m":
            key = app.read_key(tr("Set bookmark: press a letter or digit "))
            if isinstance(key, str) and len(key) == 1 and key.isalnum():
                marks = load_bookmarks()
                marks[key] = self.cwd
                try:
                    save_bookmarks(marks)
                    app.info(tr("Bookmark {key} set: {path}").format(key=key, path=self.cwd))
                except OSError as e:
                    app.error(tr("Failed: {error}").format(error=e.strerror))
        elif k == "'":
            key = app.read_key(tr("Jump to bookmark (' = previous folder, ? = list): "))
            if key == "'":
                if self.prev_cwd:
                    self.cd(self.prev_cwd)
            elif key == "?":
                app.list_bookmarks()
            elif isinstance(key, str):
                path = load_bookmarks().get(key)
                if path:
                    self.cd(path)
                else:
                    app.error(tr("No bookmark {key}").format(key=key))
        elif k == "b":
            app.list_buffers()
        elif k in (9, curses.KEY_F4):
            app.return_to_buffer()
        elif k == "S":
            app.shell(None, self.cwd)
            self.refresh(os.path.basename(cur) if cur else None)
        elif k == "!":
            c = app.prompt(tr("Command: "), "", app.cmd_history)
            if c:
                app.shell(c, self.cwd)
                self.refresh(os.path.basename(cur) if cur else None)
        elif k in ("q", C("q")):
            app.request_quit()
        elif k in ("?", curses.KEY_F1):
            app.show_help(browser_help())
        elif k in ("K", curses.KEY_F9):
            app.show_keys("browser")

    def rename(self, cur):
        if not cur:
            return
        old = os.path.basename(cur)
        name = self.app.prompt(tr("Rename: "), old)
        if name and name != old:
            dst = os.path.join(self.cwd, name)
            if os.path.lexists(dst):
                self.app.error(tr("An item with that name already exists"))
            else:
                try:
                    os.rename(cur, dst)
                    self.tagged.discard(cur)
                    self.refresh(name)
                except OSError as e:
                    self.app.error(tr("Failed: {error}").format(error=e.strerror))

    def bulk_rename(self):
        names = [e for e in self.entries
                 if (not self.tagged or os.path.join(self.cwd, e) in self.tagged)
                 and "\n" not in e]
        if not names:
            self.app.error(tr("Nothing to rename"))
            return
        fd, tmp = tempfile.mkstemp(prefix="nanger-rename-", suffix=".txt")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(names) + "\n")
        self.app.edit_bulk(tmp, self.cwd, names)

    def delete(self):
        t = self.targets()
        if not t:
            return
        label = os.path.basename(t[0]) + ("/" if os.path.isdir(t[0]) else "")
        if len(t) > 1:
            label = tr("{n} items").format(n=len(t))
        a = self.app.ask(tr("{label}: t = to the trash, d = delete permanently, n = cancel ")
                         .format(label=label))
        if a in ("t", "i", "y"):
            permanent = False
        elif a == "d":
            if self.app.ask(tr("Delete {label} PERMANENTLY? It cannot be undone! (y = yes) ")
                            .format(label=label)) not in ("y", "i"):
                self.app.info(tr("Deletion cancelled"))
                return
            permanent = True
        else:
            self.app.info(tr("Deletion cancelled"))
            return
        for p in t:
            try:
                if permanent:
                    if os.path.isdir(p) and not os.path.islink(p):
                        shutil.rmtree(p)
                    else:
                        os.remove(p)
                else:
                    trash(p)
            except (OSError, subprocess.SubprocessError) as e:
                self.app.error(tr("Cannot delete: {name} ({error})").format(
                    name=os.path.basename(p), error=getattr(e, "strerror", None) or e))
                break
        else:
            msg = tr("Permanently deleted: {label}") if permanent else tr("Moved to the trash: {label}")
            self.app.info(msg.format(label=label))
        self.tagged.clear()
        self.refresh()

    def paste(self):
        if not self.marked:
            self.app.error(tr("Nothing to paste (y = copy, x = cut)"))
            return
        paths, mode = self.marked
        last = None
        for src in paths:
            if not os.path.lexists(src):
                continue
            if mode == "cut" and os.path.dirname(src) == self.cwd:
                continue
            if os.path.isdir(src) and (self.cwd + os.sep).startswith(src + os.sep):
                self.app.error(tr("A folder cannot be copied into itself"))
                continue
            dst = unique_path(os.path.join(self.cwd, os.path.basename(src)))
            try:
                if mode == "cut":
                    shutil.move(src, dst)
                elif os.path.isdir(src) and not os.path.islink(src):
                    shutil.copytree(src, dst, symlinks=True)
                else:
                    shutil.copy2(src, dst, follow_symlinks=False)
                last = os.path.basename(dst)
            except OSError as e:
                self.app.error(tr("Error: {name} ({error})").format(
                    name=os.path.basename(src), error=e.strerror or e))
                break
        if mode == "cut":
            self.marked = None
        self.refresh(last)
        if last:
            self.app.info(tr("Pasted"))

    # ---- drawing
    def entry_attr(self, p):
        if os.path.islink(p):
            return A["link"]
        if os.path.isdir(p):
            return A["dir"]
        if os.access(p, os.X_OK):
            return A["exe"]
        return 0

    def draw_list(self, scr, x, width, d, ents, sel, top, th, active):
        git_on = active and gitinfo.repo_root(d) is not None
        for r in range(th):
            i = top + r
            if i >= len(ents):
                break
            name = ents[i]
            p = os.path.join(d, name)
            isdir = os.path.isdir(p)
            attr = self.entry_attr(p)
            tagged = p in self.tagged
            if tagged:
                attr = A["tag"]
            label = ("*" if tagged else " ") + (" " if git_on else "") + \
                clean(name) + ("/" if isdir else "")
            size = ""
            if active and not isdir:
                try:
                    size = human(os.lstat(p).st_size) + " "
                except OSError:
                    pass
            room = width - len(size)
            text = (label[:room].ljust(room) + size) if room > 4 else label[:width].ljust(width)
            if i == sel:
                attr |= curses.A_REVERSE
            put(scr, 1 + r, x, text, attr)
            if git_on:
                gch, gattr = git_mark(gitinfo.entry_status(d, name))
                if gch != " ":
                    put(scr, 1 + r, x + 1, gch, gattr | (curses.A_REVERSE if i == sel else 0))

    def preview(self, p, th, w3):
        """('lines', [(text, attr)], caption) or ('image', cells, caption)"""
        try:
            st = os.stat(p)
        except OSError:
            return ("lines", [(tr("[not available]"), A["err"])], "")
        key = (p, st.st_mtime_ns, th, w3, self.hidden, self.sort)
        if key == self._pv_key:
            return self._pv
        kind = file_kind(p)
        caption = human(st.st_size)
        if kind == "dir":
            ents = self.listdir(p)
            if ents is None:
                out = [(tr("[no permission]"), A["err"])]
            elif not ents:
                out = [(tr("(empty folder)"), A["ln"])]
            else:
                out = [(" " + clean(e) + ("/" if os.path.isdir(os.path.join(p, e)) else ""),
                        self.entry_attr(os.path.join(p, e))) for e in ents[:th]]
            caption = ""
        elif kind in ("image", "pdf"):
            return self.preview_media(p, kind, th, w3, key, st)
        elif kind == "archive":
            out, more = archive_lines(p, th - 1)
            out = [(tr("Archive — Enter: open"), A["ln"])] + out
            if more:
                out.append(("…", A["ln"]))
        elif kind == "external" and os.path.splitext(p.lower())[1] in OFFICE_EXT:
            try:
                lines = office_text(p, st.st_mtime_ns)
                out = [(clean(l.expandtabs(settings.tab_width)), 0) for l in lines[:th]]
                if not out:
                    out = [(tr("(empty file)"), A["ln"])]
            except Exception:  # noqa: BLE001 - corrupt/encrypted document
                out = [(tr("[{ext} file, {size}]").format(
                    ext=os.path.splitext(p)[1].lower(), size=human(st.st_size)), A["ln"])]
        elif kind == "external":
            out = [(tr("[{ext} file, {size}]").format(ext=os.path.splitext(p)[1].lower(),
                                                      size=human(st.st_size)), A["ln"]),
                   (tr("Enter: open with an external program"), A["ln"])]
        elif kind == "binary":
            out = [(tr("[binary file, {size}]").format(size=human(st.st_size)), A["ln"])]
        else:
            try:
                with open(p, "rb") as f:
                    data = f.read(64 * 1024)
                text = data.decode("utf-8", errors="replace").replace("\r", "")
                out = [(clean(l.expandtabs(settings.tab_width)), 0) for l in text.split("\n")[:th]]
                if not data:
                    out = [(tr("(empty file)"), A["ln"])]
            except OSError as e:
                out = [(tr("[cannot read: {error}]").format(error=e.strerror), A["err"])]
        self._pv_key, self._pv = key, ("lines", out, caption)
        return self._pv

    def preview_media(self, p, kind, th, w3, key, st):
        app = self.app
        if not can_images():
            # no Pillow / no color UTF-8 terminal: for PDFs at least the text of page 1
            if kind == "pdf" and shutil.which("pdftotext"):
                try:
                    text = pdf_text(p, st.st_mtime_ns, 1)
                    out = [(clean(l.expandtabs(settings.tab_width)), 0)
                           for l in text.split("\n")[:th]]
                except (RuntimeError, OSError, subprocess.SubprocessError) as e:
                    out = [(tr("[PDF: {error}]").format(error=e), A["err"])]
            else:
                out = [(tr("[{kind}, {size}]").format(kind=kind, size=human(st.st_size)), A["ln"]),
                       (tr("For previews install: python3-pil (Debian) / python-pillow (Arch)"),
                        A["ln"])]
            self._pv_key, self._pv = key, ("lines", out, human(st.st_size))
            return self._pv
        try:
            res = cached_render(kind, p, 1, w3, th, lazy=app.input_pending())
        except Exception as e:  # noqa: BLE001 - a preview must never crash the program
            msg = (str(e).strip().splitlines() or [e.__class__.__name__])[-1]
            out = [(tr("[cannot display: {error}]").format(error=msg), A["err"])]
            self._pv_key, self._pv = key, ("lines", out, human(st.st_size))
            return self._pv
        if res is None:  # fast scrolling: do not render now, do not cache the placeholder
            return ("lines", [("…", A["ln"])], "")
        grid, caption = res
        self._pv_key, self._pv = key, ("image", grid, "%s  %s" % (caption, human(st.st_size)))
        return self._pv

    def draw(self, scr, h, w):
        th = h - 4
        n = len(self.entries)
        if self.sel < self.top:
            self.top = self.sel
        elif self.sel >= self.top + th:
            self.top = self.sel - th + 1
        w1 = max(10, w // 6)
        w2 = max(20, (w * 2) // 5)
        w3 = w - w1 - w2 - 2
        home = os.path.expanduser("~")
        shown = "~" + self.cwd[len(home):] if self.cwd.startswith(home) else self.cwd
        put(scr, 0, 0, " " * w, A["title"])
        put(scr, 0, 0, " nanger │ %s" % shown, A["title"])
        parent = os.path.dirname(self.cwd)
        if parent != self.cwd:
            pents = self.listdir(parent) or []
            base = os.path.basename(self.cwd)
            pidx = pents.index(base) if base in pents else 0
            ptop = max(0, min(pidx - th // 2, len(pents) - th))
            self.draw_list(scr, 0, w1, parent, pents, pidx, ptop, th, False)
        for r in range(th):
            put(scr, 1 + r, w1, "│", A["ln"])
            put(scr, 1 + r, w1 + 1 + w2, "│", A["ln"])
        pcap = ""
        if n:
            self.draw_list(scr, w1 + 1, w2, self.cwd, self.entries, self.sel, self.top, th, True)
            if w3 > 3:
                pkind, payload, pcap = self.preview(self.current(), th, w3)
                if pkind == "image":
                    draw_grid(scr, 1, w1 + w2 + 2, payload)
                else:
                    for r, (text, at) in enumerate(payload):
                        put(scr, 1 + r, w1 + w2 + 2, text[:w3], at)
        else:
            put(scr, 1, w1 + 2, tr("(empty folder — n: new file)"), A["ln"])
        if not self.app.msg and n:
            cur = self.current()
            try:
                st = os.lstat(cur)
                info = " %s  %s  %s   %d/%d" % (
                    statmod.filemode(st.st_mode), human(st.st_size),
                    time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime)),
                    self.sel + 1, n)
                if pcap and pcap != human(st.st_size):
                    info += "   " + pcap
                if self.sort != "name":
                    info += "   " + tr("sort: {mode}").format(mode=sort_label(self.sort).split(",")[0])
                if self.tagged:
                    info += "   " + tr("{n} marked").format(n=len(self.tagged))
                if self.marked:
                    info += "   " + tr("clipboard: {n}").format(n=len(self.marked[0]))
                if self.app.buffers:
                    info += "   " + tr("open files: {n} (Tab = back)").format(n=len(self.app.buffers))
                put(scr, h - 3, 0, info, A["ln"])
            except OSError:
                pass
        draw_help(scr, h - 2, help_bar1(), w)
        draw_help(scr, h - 1, help_bar2(), w)
        return None

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
from .fsops import load_bookmarks, save_bookmarks, trash, tree_size
from .helptext import browser_help
from .i18n import tr
from .keys import (BACKSPACE, C, ENTER, ESC, K_ALT_DIGIT, K_ALT_LEFT, K_ALT_RIGHT, K_GO_HOME,
                   K_GO_ROOT, K_GO_TEMP)
from . import archiver
from .media import ARCHIVE_EXT, OFFICE_EXT, archive_preview, office_text, can_images, cached_render, draw_grid, file_kind, pdf_text
from .term import A, clean, draw_help, put
from .util import human, size_column, unique_path

SORT_IDS = ("name", "size", "date", "ext")


def sort_label(mode, reverse=False):
    base = {"name": tr("name, A–Z"), "size": tr("size, largest first"),
            "date": tr("modified, newest first"), "ext": tr("extension")}[mode]
    return base + (" · " + tr("reversed") if reverse else "")


def help_bar1():
    return [("Enter", tr("Open")), ("←", tr("Back")), ("n", tr("New file")),
            ("N", tr("New folder")), ("r", tr("Rename")), ("D", tr("Delete")),
            ("/", tr("Find")), ("q", tr("Quit")), ("F9", tr("Customize"))]


def help_bar2():
    return [(tr("Space"), tr("Mark")), ("y", tr("Copy")), ("x", tr("Cut")), ("p", tr("Paste")),
            ("s", tr("Sort")), ("v", tr("View")), ("o", tr("External")), ("f", tr("Grep")),
            ("F", tr("Filter")), ("?", tr("Help"))]


def split_help():
    return [("Tab", tr("Other panel")), ("C", tr("Copy there")), ("W", tr("Move there")),
            ("w", tr("One panel")), ("F", tr("Filter")), ("Ctrl+T", tr("New tab")),
            ("F4", tr("Open file")), ("?", tr("Help"))]


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
        self._sizes = {}
        self.back, self.fwd = [], []      # folder history (mouse back/forward buttons, Alt+arrows)
        self.hidden = settings.show_hidden
        self.sort = settings.sort
        self.reverse = settings.sort_reverse
        self.sel = self.top = 0
        self.entries = []
        self.tagged = set()
        self.filt = ""            # quick filter text
        self.filtering = False     # typing into the filter
        self.last_search = ""
        self.last_grep = ""
        self._ls_cache = {}
        self._pv_key = None
        self._pv = ("lines", [], "")
        self.refresh()

    @property
    def marked(self):
        """The file clipboard (paths, "copy" | "cut") is shared by every panel and tab."""
        return self.app.fclip

    @marked.setter
    def marked(self, value):
        self.app.fclip = value

    def listdir(self, d):
        try:
            mt = os.stat(d).st_mtime_ns
            names = os.listdir(d)
        except OSError:
            return None
        ckey = (mt, self.hidden, self.sort, self.reverse, len(names))
        hit = self._ls_cache.get(d)
        if hit and hit[0] == ckey:
            return hit[1]
        if not self.hidden:
            names = [n for n in names if not n.startswith(".")]

        def key(n):
            p = os.path.join(d, n)
            try:
                st = os.stat(p)
            except OSError:
                return (0, n.casefold())
            if self.sort == "size":
                return (-st.st_size, n.casefold())
            if self.sort == "date":
                return (-st.st_mtime, n.casefold())
            if self.sort == "ext":
                return (os.path.splitext(n)[1].casefold(), n.casefold())
            return (n.casefold(),)

        dirs = [n for n in names if os.path.isdir(os.path.join(d, n))]
        isdir = set(dirs)
        files = [n for n in names if n not in isdir]
        # folders always stay on top; "reverse" flips the order inside each group
        names = sorted(dirs, key=key, reverse=self.reverse) + \
            sorted(files, key=key, reverse=self.reverse)
        self._ls_cache[d] = (ckey, names)
        return names

    def refresh(self, select=None):
        self._ls_cache.clear()
        self._sizes.clear()
        gitinfo.invalidate()
        e = self.listdir(self.cwd)
        if e is None:
            self.app.error(tr("The folder cannot be read"))
            e = []
        if self.filt:
            f = self.filt.lower()
            e = [n for n in e if f in n.lower()]
        self.entries = e
        if select in e:
            self.sel = e.index(select)
        self.sel = max(0, min(self.sel, len(e) - 1))
        self._pv_key = None

    def cd(self, path, select=None, hist=False):
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
            if not hist:
                self.back.append(self.cwd)
                del self.fwd[:]
                del self.back[:-100]
        self.cwd = path
        self.sel = self.top = 0
        self.filt, self.filtering = "", False
        self.refresh(select)

    # ---- sizes, archives
    def show_size(self):
        app = self.app
        paths = self.targets()
        if not paths:
            return
        app.info(tr("Counting…"))
        app.draw()
        tot = files = dirs = 0
        complete = True
        for p in paths:
            sz, f, d, ok = tree_size(p, 15.0 / len(paths))
            tot, files, dirs, complete = tot + sz, files + f, dirs + d, complete and ok
        more = "" if complete else " (≥)"
        if len(paths) == 1:
            msg = tr("{name}: {size}, {files} files, {dirs} folders").format(
                name=os.path.basename(paths[0]), size=human(tot) + more, files=files, dirs=dirs)
        else:
            msg = tr("{n} items: {size}, {files} files, {dirs} folders").format(
                n=len(paths), size=human(tot) + more, files=files, dirs=dirs)
        app.info(msg)

    def compress(self):
        app = self.app
        paths = self.targets()
        if not paths:
            return
        names = [os.path.relpath(p, self.cwd) for p in paths if os.path.dirname(p) == self.cwd]
        if not names:
            return
        base = names[0] if len(names) == 1 else os.path.basename(self.cwd) or "archive"
        name = app.prompt(tr("Archive name (.7z, .zip, .tar.gz): "), base + ".7z")
        if not name:
            return
        if "/" in name or name in (".", ".."):
            app.error(tr("Invalid name: {name}").format(name=name))
            return
        app.info(tr("Compressing…"))
        app.draw()
        try:
            archiver.compress(self.cwd, names, os.path.join(self.cwd, name))
        except archiver.ArchiveError as e:
            app.error(tr("Archive failed: {error}").format(error=e))
            return
        self.tagged.clear()
        self.refresh(name)
        app.info(tr("Created: {path}").format(path=name))

    def extract(self):
        app = self.app
        paths = [p for p in self.targets() if os.path.isfile(p)]
        if not paths:
            return
        bad = [p for p in paths if not archiver.is_archive(p)]
        if bad and len(paths) == 1:
            app.error(tr("Not an archive: {name}").format(name=os.path.basename(bad[0])))
            return
        paths = [p for p in paths if archiver.is_archive(p)]
        if not paths:
            return
        dests = {}
        if len(paths) == 1:
            default = archiver.stem(os.path.basename(paths[0]))
            d = app.prompt(tr("Extract to: "), default)
            if not d:
                return
            dests[paths[0]] = os.path.join(self.cwd, os.path.expanduser(d))
        else:
            for p in paths:
                dests[p] = os.path.join(self.cwd, archiver.stem(os.path.basename(p)))
        app.info(tr("Extracting…"))
        app.draw()
        first = None
        for p, dest in dests.items():
            try:
                archiver.extract(p, dest)
                first = first or os.path.basename(dest)
            except archiver.ArchiveError as e:
                app.error(tr("Archive failed: {error}").format(error=e))
                self.refresh()
                return
        self.tagged.clear()
        self.refresh(first)
        app.info(tr("Extracted {n} archive(s)").format(n=len(dests)))

    def compare(self):
        """=: compare two marked files, or the marked one with the current one."""
        from .util import load_text
        app = self.app
        files = [p for p in self.targets() if os.path.isfile(p)]
        cur = self.current()
        if len(files) == 1 and cur and os.path.isfile(cur) and cur != files[0]:
            files.append(cur)
        if len(files) != 2:
            app.error(tr("Mark two files (Space) to compare them"))
            return
        try:
            a, b = load_text(files[0])[0], load_text(files[1])[0]
        except (OSError, ValueError) as e:
            app.error(tr("Cannot open: {error}").format(error=getattr(e, "strerror", None) or e))
            return
        app.show_diff(os.path.basename(files[0]), a, os.path.basename(files[1]), b)

    def connect(self):
        """M: mount a remote folder (user@host:/path) with sshfs, or unmount the current one."""
        from . import remote
        app = self.app
        here = remote.mount_of(self.cwd)
        text = app.prompt(tr("Remote (user@host:/path){hint}: ").format(
            hint=tr(", empty = disconnect") if here else ""), "")
        if text is None:
            return
        if not text.strip():
            if here:
                mp, uh = here
                self.cd(os.path.expanduser("~"))
                remote.unmount(mp)
                app.info(tr("Disconnected: {host}").format(host=uh))
            return
        app.info(tr("Connecting..."))
        app.draw()
        try:
            mp = remote.mount(text)
        except remote.RemoteError as e:
            app.error(str(e))
            return
        self.cd(mp)
        app.info(tr("Connected: {host}").format(host=remote.MOUNTS.get(mp, text)))

    def _run_tool(self, cmd):
        r = subprocess.run(cmd, capture_output=True, text=True, errors="replace",
                           stdin=subprocess.DEVNULL, timeout=120)
        return r.returncode, (r.stderr.strip().splitlines() or [""])[-1]

    def permissions(self):
        """chmod on the marked items (or the current one): 644, u+x, a-w, -R 755 ..."""
        import re
        app = self.app
        paths = self.targets()
        if not paths:
            return
        default = ""
        if len(paths) == 1:
            try:
                default = "%o" % (os.lstat(paths[0]).st_mode & 0o7777)
            except OSError:
                pass
        text = app.prompt(tr("Permissions (644, u+x, a-w; -R = recursive): "), default)
        if not text:
            return
        parts = text.split()
        rec = "-R" in parts
        parts = [x for x in parts if x != "-R"]
        mode = parts[0] if len(parts) == 1 else ""
        sym = r"[ugoa]*[+\-=][rwxXst]*(,[ugoa]*[+\-=][rwxXst]*)*"
        if not (re.fullmatch(r"[0-7]{3,4}", mode) or re.fullmatch(sym, mode)):
            app.error(tr("Invalid mode: {mode}").format(mode=text))
            return
        cmd = ["chmod"] + (["-R"] if rec else []) + [mode, "--"] + paths
        try:
            rc, err = self._run_tool(cmd)
        except (OSError, subprocess.SubprocessError) as e:
            app.error(tr("Failed: {error}").format(error=e))
            return
        self.refresh(os.path.basename(paths[0]))
        if rc:
            app.error(tr("Failed: {error}").format(error=err))
        else:
            app.info(tr("Permissions {mode} set on {n} items").format(mode=mode, n=len(paths)))

    def owner(self):
        """chown on the marked items (or the current one); offers sudo when not permitted."""
        import re
        import shlex
        app = self.app
        paths = self.targets()
        if not paths:
            return
        default = ""
        if len(paths) == 1:
            try:
                import grp
                import pwd
                st = os.lstat(paths[0])
                default = "%s:%s" % (pwd.getpwuid(st.st_uid).pw_name,
                                     grp.getgrgid(st.st_gid).gr_name)
            except (OSError, KeyError, ImportError):
                pass
        text = app.prompt(tr("Owner (user, user:group, :group; -R = recursive): "), default)
        if not text:
            return
        parts = text.split()
        rec = "-R" in parts
        parts = [x for x in parts if x != "-R"]
        who = parts[0] if len(parts) == 1 else ""
        if not re.fullmatch(r"[\w.\-]*(:[\w.\-]*)?", who) or not who:
            app.error(tr("Invalid owner: {who}").format(who=text))
            return
        cmd = ["chown"] + (["-R"] if rec else []) + [who, "--"] + paths
        try:
            rc, err = self._run_tool(cmd)
        except (OSError, subprocess.SubprocessError) as e:
            app.error(tr("Failed: {error}").format(error=e))
            return
        if rc and os.geteuid() != 0 and shutil.which("sudo"):
            a = app.ask(tr("Not permitted. Retry with sudo? (y/n) "))
            if a in ("y", "i"):
                app.shell("sudo " + " ".join(shlex.quote(c) for c in cmd), self.cwd)
                rc = 0
        self.refresh(os.path.basename(paths[0]))
        if rc:
            app.error(tr("Failed: {error}").format(error=err))
        else:
            app.info(tr("Owner set to {who} on {n} items").format(who=who, n=len(paths)))

    def right_status(self):
        """Bottom-right text: items in the folder, or the total size of the selection."""
        if self.tagged:
            tot, complete = 0, True
            deadline = time.time() + 0.4          # sizes of selected folders: cached, bounded
            for p in self.tagged:
                hit = self._sizes.get(p)
                if hit is None:
                    left = max(0.02, deadline - time.time())
                    sz, _f, _d, ok = tree_size(p, left)
                    hit = (sz, ok)
                    if ok:
                        self._sizes[p] = hit
                tot += hit[0]
                complete = complete and hit[1]
            return tr("{n} selected, {size}").format(
                n=len(self.tagged), size=human(tot) + ("" if complete else " (≥)"))
        dirs = sum(1 for e in self.entries if os.path.isdir(os.path.join(self.cwd, e)))
        return tr("{files} files, {dirs} folders").format(files=len(self.entries) - dirs,
                                                          dirs=dirs)

    def go_back(self):
        """Previous folder from the history; without history: the parent folder."""
        if self.back:
            came = self.cwd
            self.fwd.append(came)
            self.cd(self.back.pop(), hist=True)
            return
        parent = os.path.dirname(self.cwd)
        if parent != self.cwd:
            self.cd(parent, select=os.path.basename(self.cwd))

    def go_forward(self):
        if self.fwd:
            self.back.append(self.cwd)
            self.cd(self.fwd.pop(), hist=True)

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
        if self.filtering:
            self.filter_key(k)
            return
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
        elif k == K_ALT_LEFT:
            self.go_back()
        elif k == K_ALT_RIGHT:
            self.go_forward()
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
            c = app.read_key(tr("Sort by: n = name, d = date, s = size, e = extension, "
                                "r = reverse "))
            ids = {"n": "name", "d": "date", "s": "size", "e": "ext"}
            if c == "r":
                self.reverse = not self.reverse
            elif c in ids:
                if ids[c] == self.sort:
                    self.reverse = not self.reverse   # same key again: flip the direction
                else:
                    self.sort, self.reverse = ids[c], False
            else:
                c = None
            if c:
                self.refresh(os.path.basename(cur) if cur else None)
                app.info(tr("Sorting: {mode}").format(mode=sort_label(self.sort, self.reverse)))
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
        elif k == "a":
            allp = {os.path.join(self.cwd, e) for e in self.entries}
            self.tagged = set() if allp and self.tagged >= allp else allp
        elif k == "A":
            allp = {os.path.join(self.cwd, e) for e in self.entries}
            self.tagged = allp - self.tagged
        elif k == "i":
            self.show_size()
        elif k == "Z":
            self.compress()
        elif k == "U":
            self.extract()
        elif k == K_GO_TEMP:
            self.cd(tempfile.gettempdir())
        elif k == K_GO_HOME:
            self.cd(os.path.expanduser("~"))
        elif k == K_GO_ROOT:
            self.cd(os.sep)
        elif k == "F":
            self.filtering = True
        elif k == ESC:
            if self.filt:
                self.set_filter("")
            else:
                self.tagged.clear()
        elif k == "w":
            app.toggle_split()
        elif k == 9 and app.tab.split:
            app.switch_pane()
        elif k == "C":
            self.to_other_panel(False)
        elif k == "W":
            self.to_other_panel(True)
        elif k == C("t"):
            app.new_tab()
        elif k == C("w"):
            app.close_tab()
        elif k == "]":
            app.goto_tab((app.cur + 1) % len(app.tabs))
        elif k == "[":
            app.goto_tab((app.cur - 1) % len(app.tabs))
        elif isinstance(k, int) and K_ALT_DIGIT < k <= K_ALT_DIGIT + 9:
            app.goto_tab(k - K_ALT_DIGIT - 1)
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
        elif k == "=":
            self.compare()
        elif k == "M":
            self.connect()
        elif k == "P":
            self.permissions()
        elif k == "O":
            self.owner()
        elif k == "T":
            app.show_themes()
        elif k in ("K", curses.KEY_F9):
            app.show_keys("browser")

    def mouse_split(self, x, y, kind):
        app = self.app
        half, th = app.split_geom
        if kind == "right":
            self.handle(curses.KEY_LEFT)
            return
        if kind == "back":
            self.go_back()
            return
        if kind == "forward":
            self.go_forward()
            return
        if kind == "drag" or not 2 <= y < 2 + th:
            return
        side = 0 if x < half else 1
        if side != app.tab.active:
            app.tab.active = side
            app.focus_browser()
        b = app.browser
        i = b.top + y - 2
        if 0 <= i < len(b.entries):
            b.sel = i
            if kind == "double":
                b.handle(10)

    def mouse(self, x, y, kind):
        app = self.app
        if y == 0 and kind in ("click", "double"):
            for x0, x1, i in app.tab_hits:
                if x0 <= x < x1:
                    app.goto_tab(i)
                    return
            return
        if app.tab.split and app.other_pane() is not None:
            self.mouse_split(x, y, kind)
            return
        if not getattr(self, "geom", None):
            return
        w1, w2, th = self.geom
        if kind == "right":
            self.handle(curses.KEY_LEFT)
            return
        if kind == "back":
            self.go_back()
            return
        if kind == "forward":
            self.go_forward()
            return
        if not 1 <= y <= th or kind == "drag":
            return
        if x < w1:
            pg = getattr(self, "pgeom", None)
            if pg:
                parent, pents, ptop = pg
                i = ptop + y - 1
                if 0 <= i < len(pents) and os.path.isdir(os.path.join(parent, pents[i])):
                    self.cd(os.path.join(parent, pents[i]))
        elif x > w1 + w2:
            if kind == "double":
                self.handle(10)
        elif x > w1:
            i = self.top + y - 1
            if 0 <= i < len(self.entries):
                self.sel = i
                if kind == "double":
                    self.handle(10)

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

    def set_filter(self, text):
        cur = self.current()
        self.filt = text
        self.refresh(os.path.basename(cur) if cur else None)
        if not text:
            self.filtering = False

    def filter_key(self, k):
        """Keys while typing the quick filter."""
        if k == ESC:
            self.set_filter("")
        elif k in ENTER:
            self.filtering = False
            cur = self.current()
            if cur and os.path.isdir(cur):
                self.cd(cur)
            elif cur:
                self.app.open_path(cur)
        elif k in BACKSPACE:
            if self.filt:
                self.set_filter(self.filt[:-1])
            else:
                self.filtering = False
        elif k in (curses.KEY_DOWN, C("n")):
            self.sel = min(max(0, len(self.entries) - 1), self.sel + 1)
        elif k in (curses.KEY_UP, C("p")):
            self.sel = max(0, self.sel - 1)
        elif k == curses.KEY_NPAGE:
            self.sel = min(max(0, len(self.entries) - 1), self.sel + 10)
        elif k == curses.KEY_PPAGE:
            self.sel = max(0, self.sel - 10)
        elif isinstance(k, str) and k.isprintable():
            self.set_filter(self.filt + k)
        self.sel = max(0, min(self.sel, len(self.entries) - 1))

    def to_other_panel(self, move):
        """C / W: copy or move the marked items into the folder of the other panel."""
        app = self.app
        other = app.other_pane()
        if other is None:
            app.error(tr("Open a second panel first (w)"))
            return
        paths = self.targets()
        if not paths:
            return
        last = self.transfer(paths, "cut" if move else "copy", other.cwd)
        self.tagged.clear()
        app.refresh_panels()
        if last:
            other.refresh(last)
            app.info(tr("Moved to the other panel") if move else tr("Copied to the other panel"))

    def paste(self):
        if not self.marked:
            self.app.error(tr("Nothing to paste (y = copy, x = cut)"))
            return
        paths, mode = self.marked
        last = self.transfer(paths, mode, self.cwd)
        if mode == "cut":
            self.marked = None
        self.app.refresh_panels()
        self.refresh(last)
        if last:
            self.app.info(tr("Pasted"))

    def transfer(self, paths, mode, dest):
        """Copy / move `paths` into the folder `dest`; returns the last created name."""
        last = None
        for src in paths:
            if not os.path.lexists(src):
                continue
            if mode == "cut" and os.path.dirname(src) == dest:
                continue
            if os.path.isdir(src) and (dest + os.sep).startswith(src + os.sep):
                self.app.error(tr("A folder cannot be copied into itself"))
                continue
            dst = unique_path(os.path.join(dest, os.path.basename(src)))
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
        return last

    # ---- drawing
    def entry_attr(self, p):
        if os.path.islink(p):
            return A["link"]
        if os.path.isdir(p):
            return A["dir"]
        if p.lower().endswith(ARCHIVE_EXT):
            return A["arc"]
        if os.access(p, os.X_OK):
            return A["exe"]
        return 0

    def draw_list(self, scr, x, width, d, ents, sel, top, th, active, row0=1, hl=curses.A_REVERSE):
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
                clean(name)
            size = ""
            if active and not isdir:
                try:
                    size = size_column(os.lstat(p).st_size) + " "
                except OSError:
                    pass
            room = width - len(size)
            text = (label[:room].ljust(room) + size) if room > 4 else label[:width].ljust(width)
            if i == sel:
                attr |= hl
            put(scr, row0 + r, x, text, attr)
            if active and self.filt and d == self.cwd:
                at = name.lower().find(self.filt.lower())
                off = 1 + (1 if git_on else 0) + at
                if at >= 0 and off < room:
                    put(scr, row0 + r, x + off, clean(name)[at:at + len(self.filt)],
                        attr | A["match"] | curses.A_BOLD)
            if git_on:
                gch, gattr = git_mark(gitinfo.entry_status(d, name))
                if gch != " ":
                    put(scr, row0 + r, x + 1, gch, gattr | (hl if i == sel else 0))

    def preview(self, p, th, w3):
        """('lines', [(text, attr)], caption) or ('image', cells, caption)"""
        try:
            st = os.stat(p)
        except OSError:
            return ("lines", [(tr("[not available]"), A["err"])], "")
        key = (p, st.st_mtime_ns, th, w3, self.hidden, self.sort, self.reverse)
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
                out = [(" " + clean(e),
                        self.entry_attr(os.path.join(p, e))) for e in ents[:th]]
            caption = ""
        elif kind in ("image", "pdf"):
            return self.preview_media(p, kind, th, w3, key, st)
        elif kind == "archive":
            res = archive_preview(p, st.st_mtime_ns, th - 1)
            if res is None:     # still being read in the background: do not cache this
                return ("lines", [(tr("Reading…"), A["ln"])], caption)
            out, more = res
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

    def title(self, scr, w, shown):
        """Row 0: the tab bar (when there are several tabs) followed by the path."""
        app = self.app
        put(scr, 0, 0, " " * w, A["title"])
        app.tab_hits = []
        if len(app.tabs) < 2:
            put(scr, 0, 0, " nanger │ %s" % shown, A["title"])
            return
        x = 0
        for i, t in enumerate(app.tabs):
            b = t.panes[t.active]
            name = os.path.basename(b.cwd) or "/"
            lab = " %d %s " % (i + 1, clean(name)[:16])
            if x + len(lab) >= w - 4:
                break
            put(scr, 0, x, lab, A["title"] | curses.A_BOLD if i == app.cur else A["ln"])
            app.tab_hits.append((x, x + len(lab), i))
            x += len(lab)
        put(scr, 0, x, " │ %s" % shown, A["title"])

    def status(self, scr, h, w, pcap=""):
        n = len(self.entries)
        if self.filtering or self.filt:
            msg = " %s %s▌ %s" % (tr("Filter:"), self.filt, tr("{m} matches / {n} items").format(
                m=n, n=len(self.listdir(self.cwd) or [])))
            msg += "  ·  " + (tr("Enter: open  ·  Esc: clear") if self.filtering
                              else tr("F: edit  ·  Esc: clear"))
            put(scr, h - 3, 0, msg[:w].ljust(w), A["key"])
            return
        if self.app.msg or not n:
            return
        cur = self.current()
        try:
            st = os.lstat(cur)
            info = " %s  %s  %s   %d/%d" % (
                statmod.filemode(st.st_mode), human(st.st_size),
                time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime)),
                self.sel + 1, n)
            if pcap and pcap != human(st.st_size):
                info += "   " + pcap
            if self.sort != "name" or self.reverse:
                info += "   " + tr("sort: {mode}").format(
                    mode=sort_label(self.sort, self.reverse).split(",")[0].split(" · ")[0]
                    + (" ↑" if self.reverse else ""))
            if self.tagged:
                info += "   " + tr("{n} marked").format(n=len(self.tagged))
            if self.marked:
                info += "   " + tr("clipboard: {n}").format(n=len(self.marked[0]))
            if self.app.buffers:
                info += "   " + tr("open files: {n} (F4 = back)").format(n=len(self.app.buffers))
            right = self.right_status()
            room = max(0, w - len(right) - 3)
            put(scr, h - 3, 0, info[:room], A["ln"])
            put(scr, h - 3, max(0, w - len(right) - 1), right, A["ln"] | curses.A_BOLD)
        except OSError:
            pass

    def shown_path(self):
        home = os.path.expanduser("~")
        return "~" + self.cwd[len(home):] if self.cwd.startswith(home) else self.cwd

    def scroll_to_sel(self, th):
        if self.sel < self.top:
            self.top = self.sel
        elif self.sel >= self.top + th:
            self.top = self.sel - th + 1

    def draw_split(self, scr, h, w):
        """Two panels side by side (the active one is this browser)."""
        app = self.app
        t = app.tab
        th = h - 5                                   # row 0 title, row 1 panel paths
        half = w // 2
        self.title(scr, w, "") if len(app.tabs) > 1 else \
            put(scr, 0, 0, (" nanger │ " + tr("two panels") + " ").ljust(w), A["title"])
        app.split_geom = (half, th)
        for side, b in enumerate(t.panes):
            x0 = 0 if side == 0 else half
            width = half - 1 if side == 0 else w - half
            on = side == t.active
            b.scroll_to_sel(th)
            put(scr, 1, x0, (" " + b.shown_path())[:width].ljust(width),
                A["title"] if on else A["ln"])
            b.geom = None
            if b.entries:
                b.draw_list(scr, x0, width, b.cwd, b.entries, b.sel, b.top, th, True, row0=2,
                            hl=curses.A_REVERSE if on else curses.A_UNDERLINE)
            else:
                put(scr, 2, x0 + 1, tr("(empty folder — n: new file)")[:width - 1], A["ln"])
        for r in range(th):
            put(scr, 2 + r, half - 1, "│", A["ln"])
        self.status(scr, h, w)
        draw_help(scr, h - 2, help_bar1(), w)
        draw_help(scr, h - 1, split_help(), w)
        return None

    def draw(self, scr, h, w):
        if self.app.tab.split and self.app.other_pane() is not None:
            return self.draw_split(scr, h, w)
        th = h - 4
        n = len(self.entries)
        self.scroll_to_sel(th)
        w1 = max(10, w // 6)
        w2 = max(20, (w * 2) // 5)
        w3 = w - w1 - w2 - 2
        self.title(scr, w, self.shown_path())
        parent = os.path.dirname(self.cwd)
        if parent != self.cwd:
            pents = self.listdir(parent) or []
            base = os.path.basename(self.cwd)
            pidx = pents.index(base) if base in pents else 0
            ptop = max(0, min(pidx - th // 2, len(pents) - th))
            self.draw_list(scr, 0, w1, parent, pents, pidx, ptop, th, False)
            self.pgeom = (parent, pents, ptop)
        else:
            self.pgeom = None
        self.geom = (w1, w2, th)
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
            put(scr, 1, w1 + 2, (tr("(no matches)") if self.filt else tr("(empty folder — n: new file)")),
                A["ln"])
        self.status(scr, h, w, pcap)
        draw_help(scr, h - 2, help_bar1(), w)
        draw_help(scr, h - 1, help_bar2(), w)
        return None

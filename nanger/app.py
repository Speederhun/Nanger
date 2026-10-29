"""Application: owns the views (file manager, editors, viewer, result lists), the keyboard
loop, prompts and the macro recorder."""
import curses
import os
import re
import select
import subprocess
import sys
import time
from collections import deque

from .browser import Browser
from .config import settings
from .editor import Editor
from .fsops import apply_renames, load_bookmarks, plan_renames, search_files
from .i18n import tr
from .keys import BACKSPACE, C, ENTER, ESC, ESCAPES, K_ALT_LEFT, K_ALT_RIGHT, K_MOUSE, seq_label
from . import actions, media, recovery
from .media import archive_lines, can_view, file_kind, has_gui
from .results import Results
from . import term
from .term import A, put
from .util import load_text, set_system_clipboard
from .viewer import Viewer


class Tab:
    """One file-manager tab: one panel, or two when split."""
    def __init__(self, browser):
        self.panes = [browser]
        self.active = 0
        self.split = False


class App:
    def __init__(self, scr, target, line=None):
        self.scr = scr
        self.msg = ""
        self.msg_err = False
        self.cur = 0                # current tab
        self.fclip = None           # file clipboard shared by all panels: (paths, "copy" | "cut")
        self.tab_hits = []          # clickable tab labels (x0, x1, index)
        self.clip = ("", False)
        self.running = True
        self.queue = deque()
        self.btn_down = False
        self._want_mouse = False
        self.pending = ()
        self.last_click = None
        self.mouse_event = (0, 0, "click")
        self.recording = None
        self.macro = []
        self.cmd_history = []
        self.buffers = []           # open Editor objects (tabs)
        self.last_buffer = None
        self.last_results = None
        self.return_view = None     # where the viewer / result list returns to
        self.quit_when_empty = False
        self._autosaved = time.time()
        self.crashed = False
        self.file_mode_only = False  # started on a file and never opened the file manager
        target = os.path.abspath(os.path.expanduser(target))
        if os.path.isdir(target):
            self.tabs = [Tab(Browser(self, target))]
            self.view = self.browser
        else:
            d = os.path.dirname(target)
            self.tabs = [Tab(Browser(self, d if os.path.isdir(d) else os.getcwd()))]
            self.view = self.browser
            self.quit_when_empty = True
            self.file_mode_only = True
            self.open_path(target, line=line)
            if self.view is self.browser:  # opened externally / failed: stay in the file manager
                self.quit_when_empty = False
        if settings.warnings:
            self.error(settings.warnings[0])

    # ---- messages and small helpers
    def info(self, m):
        self.msg, self.msg_err = m, False

    def error(self, m):
        self.msg, self.msg_err = m, True
        curses.beep()

    # ---- tabs and panels
    @property
    def tab(self):
        return self.tabs[self.cur]

    @property
    def browser(self):
        t = self.tabs[self.cur]
        return t.panes[t.active]

    def other_pane(self):
        t = self.tab
        return t.panes[1 - t.active] if t.split and len(t.panes) == 2 else None

    def focus_browser(self):
        if isinstance(self.view, Browser):
            self.view = self.browser

    def new_tab(self):
        from .browser import Browser as B
        src = self.browser
        b = B(self, src.cwd)
        b.hidden, b.sort, b.reverse = src.hidden, src.sort, src.reverse
        b.refresh()
        self.tabs.append(Tab(b))
        self.cur = len(self.tabs) - 1
        self.focus_browser()
        self.info(tr("Tab {n}").format(n=self.cur + 1))

    def close_tab(self):
        if len(self.tabs) == 1:
            self.info(tr("This is the last tab"))
            return
        del self.tabs[self.cur]
        self.cur = min(self.cur, len(self.tabs) - 1)
        self.focus_browser()

    def goto_tab(self, i):
        if 0 <= i < len(self.tabs):
            self.cur = i
            self.focus_browser()
        else:
            self.error(tr("No tab {n}").format(n=i + 1))

    def toggle_split(self):
        t = self.tab
        if not t.split:
            if len(t.panes) == 1:
                from .browser import Browser as B
                src = t.panes[0]
                b = B(self, src.cwd)
                b.hidden, b.sort, b.reverse = src.hidden, src.sort, src.reverse
                b.refresh()
                t.panes.append(b)
            t.split = True
        else:
            t.split = False
        self.focus_browser()

    def switch_pane(self):
        t = self.tab
        if t.split and len(t.panes) == 2:
            t.active = 1 - t.active
            self.focus_browser()

    def refresh_panels(self):
        for t in self.tabs:
            for b in t.panes:
                b.refresh(os.path.basename(b.current()) if b.current() else None)

    def text_height(self):
        return self.scr.getmaxyx()[0] - 4

    def input_pending(self):
        try:
            return bool(select.select([sys.stdin], [], [], 0)[0])
        except (OSError, ValueError):
            return False

    def set_clip(self, text, linewise):
        self.clip = (text, linewise)
        set_system_clipboard(text)

    def current_editor(self):
        return self.view if isinstance(self.view, Editor) else None

    # ---- opening things
    def open_path(self, path, viewer=False, line=None):
        """Open a file according to its type: text -> editor, image/PDF -> external program
        (with a graphical desktop) or the built-in viewer, documents -> external program."""
        if not os.path.exists(path):
            self.edit(path, line)  # a new file
            return
        kind = file_kind(path)
        if kind == "text":
            self.edit(path, line)
        elif kind in ("image", "pdf") and (viewer or not has_gui()):
            if not can_view(kind):
                self.error(tr("Images need python3-pil (Debian) / python-pillow (Arch); "
                              "PDFs need poppler-utils"))
                return
            try:
                self.return_view = self.view
                self.view = Viewer(self, path, kind)
            except OSError as e:
                self.error(tr("Cannot open: {error}").format(error=e.strerror or e))
        elif kind == "archive" and not has_gui():
            lines, more = archive_lines(path, 5000)
            self.show_help(os.path.basename(path) + "  " + tr("(any key: back)") + "\n\n"
                           + "\n".join(t for t, _a in lines) + ("\n…" if more else ""))
        else:
            self.open_external(path)

    def open_external(self, path):
        if not has_gui():
            self.error(tr("No graphical desktop (or xdg-open) — only text, images and PDFs "
                          "can be opened here"))
            return
        try:
            subprocess.Popen([media.opener(), path], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
            self.info(tr("Opened with an external program: {name}").format(
                name=os.path.basename(path)))
        except OSError as e:
            self.error(tr("Cannot start xdg-open: {error}").format(error=e.strerror or e))

    def edit(self, path, line=None, search=None):
        """Open `path` in a (new or already open) editor buffer and show it."""
        real = os.path.realpath(path)
        ed = next((b for b in self.buffers if b.path and os.path.realpath(b.path) == real), None)
        if ed is None:
            try:
                ed = Editor(self, path, line)
            except (ValueError, OSError) as e:
                self.error(tr("Cannot open: {error}").format(error=getattr(e, "strerror", None) or e))
                return None
            self.buffers.append(ed)
            self.view = ed
            ed.offer_recovery()
        elif line:
            ed.goto(str(line))
        if search:
            ed.search = search
        self.set_view(ed)
        return ed

    def set_view(self, view):
        self.view = view
        if isinstance(view, Editor):
            self.last_buffer = view
            view.check_disk()

    def show_browser(self):
        self.quit_when_empty = False
        self.file_mode_only = False
        ed = self.current_editor()
        self.view = self.browser
        if ed and ed.path and os.path.dirname(os.path.abspath(ed.path)) == self.browser.cwd:
            self.browser.refresh(os.path.basename(ed.path))

    def return_to_buffer(self):
        if not self.buffers:
            self.info(tr("No open files"))
            return
        target = self.last_buffer if self.last_buffer in self.buffers else self.buffers[-1]
        self.set_view(target)

    def switch_buffer(self, delta):
        ed = self.current_editor()
        if ed is None or len(self.buffers) < 2:
            return
        self.set_view(self.buffers[(self.buffers.index(ed) + delta) % len(self.buffers)])

    def goto_buffer(self, n):
        if 1 <= n <= len(self.buffers):
            self.set_view(self.buffers[n - 1])
        else:
            self.error(tr("No open file {n}").format(n=n))

    def close_buffer(self, ed):
        idx = self.buffers.index(ed)
        self.buffers.remove(ed)
        ed.drop_recovery()
        if self.last_buffer is ed:
            self.last_buffer = None
        if self.view is ed:
            if self.buffers:
                self.set_view(self.buffers[min(idx, len(self.buffers) - 1)])
            elif self.quit_when_empty:
                self.running = False
            else:
                self.view = self.browser
        if ed.bulk:
            self.finish_bulk(ed)
        elif ed.path and os.path.dirname(os.path.abspath(ed.path)) == self.browser.cwd:
            self.browser.refresh(os.path.basename(ed.path))
        else:
            self.browser.refresh()

    def close_viewer(self):
        self.view = self.return_view or self.browser
        if self.quit_when_empty and self.view is self.browser and not self.buffers:
            self.running = False
        else:
            cur = self.browser.current()
            self.browser.refresh(os.path.basename(cur) if cur else None)

    def show_themes(self):
        from .config import THEME_NAMES
        items = [("%s %s" % ("●" if n == settings.theme else " ", n), n) for n in THEME_NAMES]
        self.show_list(tr("Colour theme"), items, self.apply_theme)

    def apply_theme(self, name, close=True):
        from .config import save_setting
        settings.theme = name
        term.init_colors()
        self.scr.bkgd(ord(" "), A["base"])
        self.scr.clear()
        if close:
            self.close_results()
        try:
            save_setting("general", "theme", name)
            self.info(tr("Theme: {name}").format(name=name))
        except OSError as e:
            self.error(tr("Failed: {error}").format(error=e.strerror))

    def show_keys(self, mode=None):
        from .keymenu import KeyMenu
        if mode is None:
            mode = "editor" if isinstance(self.view, Editor) else "browser"
        if not isinstance(self.view, (Results, KeyMenu)):
            self.return_view = self.view
        self.view = KeyMenu(self, mode)

    def show_diff(self, ltitle, left, rtitle, right):
        from .diffview import DiffView
        if left == right:
            self.info(tr("The two files are identical"))
            return
        if not isinstance(self.view, (Results, DiffView)):
            self.return_view = self.view
        self.view = DiffView(self, ltitle, left, rtitle, right)

    def close_results(self):
        self.view = self.return_view or self.browser

    def request_quit(self):
        dirty = [b for b in self.buffers if b.modified and not b.bulk]
        if dirty:
            a = self.ask(tr("{n} open files have unsaved changes. Quit anyway? (y/n) ")
                         .format(n=len(dirty)))
            if a not in ("y", "i"):
                return
        self.running = False

    # ---- lists: open files, bookmarks, search results
    def show_list(self, title, items, on_select, note="", remember=False):
        res = Results(self, title, items, on_select, note)
        if remember:
            self.last_results = res
        if not isinstance(self.view, Results):
            self.return_view = self.view
        self.view = res

    def list_buffers(self):
        if not self.buffers:
            self.info(tr("No open files"))
            return
        items = []
        for i, b in enumerate(self.buffers):
            items.append(("%2d %s %s" % (i + 1, "*" if b.modified else " ",
                                         b.path or tr("[new file]")), b))

        def select(ed):
            self.close_results()
            self.set_view(ed)

        self.show_list(tr("Open files"), items, select)

    def list_bookmarks(self):
        marks = load_bookmarks()
        if not marks:
            self.info(tr("No bookmarks yet (m + a letter sets one)"))
            return
        items = [("%s   %s" % (k, marks[k]), marks[k]) for k in sorted(marks)]

        def select(path):
            self.close_results()
            self.browser.cd(path)

        self.show_list(tr("Bookmarks"), items, select)

    def grep(self, pattern, root):
        self.info(tr("Searching…"))
        self.draw()
        try:
            found, truncated = search_files(root, pattern)
        except re.error as e:
            self.error(tr("Invalid regex: {error}").format(error=e))
            return
        if not found:
            self.error(tr("No match: {pattern}").format(pattern=pattern))
            return
        items = []
        for path, n, text, match in found:
            rel = os.path.relpath(path, root)
            items.append(("%s:%d: %s" % (rel, n, text.strip()[:300]), (path, n, match)))

        def select(payload):
            path, n, match = payload
            self.view = self.return_view or self.browser  # leave the list, keep it for :copen
            self.edit(path, line=n, search=match)

        note = tr("(truncated)") if truncated else ""
        self.msg = ""
        self.show_list(tr("Search: {pattern}").format(pattern=pattern), items, select, note,
                       remember=True)

    def show_results(self):
        if self.last_results is None:
            self.info(tr("There are no search results yet (use :grep PATTERN)"))
            return
        if not isinstance(self.view, Results):
            self.return_view = self.view
        self.view = self.last_results

    # ---- bulk rename
    def edit_bulk(self, tmp, cwd, names):
        ed = self.edit(tmp)
        if ed is None:
            return
        ed.bulk = {"cwd": cwd, "old": names}
        self.info(tr("Edit the names, save (Ctrl+S), then close this file (Ctrl+Q) to apply"))

    def finish_bulk(self, ed):
        info = ed.bulk
        try:
            lines = load_text(ed.path)[0]
        except (OSError, ValueError):
            lines = None
        try:
            os.unlink(ed.path)
        except OSError:
            pass
        self.browser.refresh()
        if lines is None:
            return
        old = info["old"]
        new = [l.rstrip("\r") for l in lines]
        while len(new) > len(old) and new and new[-1] == "":
            new.pop()
        if new == old:
            self.info(tr("No names were changed"))
            return
        pairs, err = plan_renames(info["cwd"], old, new)
        if err:
            self.error(err)
            return
        if self.ask(tr("Rename {n} items? (y/n) ").format(n=len(pairs))) not in ("y", "i"):
            self.info(tr("Renaming cancelled"))
            return
        try:
            n = apply_renames(info["cwd"], pairs)
        except OSError as e:
            self.error(tr("Renaming failed: {error}").format(error=e.strerror or e))
        else:
            self.info(tr("Renamed {n} items").format(n=n))
        self.browser.tagged.clear()
        self.browser.refresh()

    # ---- keyboard
    def getkey(self, mouse=False):
        self._want_mouse = mouse
        # wake up for: a finished listing (redraw), or the next crash-recovery snapshot
        self.scr.timeout(150 if media.previews_pending() else
                         int(recovery.interval() * 1000) if self.unsaved() else -1)
        if self.queue:
            return self.queue.popleft()
        try:
            k = self.scr.get_wch()
        except curses.error:
            return None
        except KeyboardInterrupt:
            return C("c")
        if k == curses.KEY_MOUSE:     # terminfo knows "ESC [ <": the report follows
            return self.sgr_mouse(self.read_mouse_rest(), mouse)
        if isinstance(k, str) and len(k) == 1 and (ord(k) < 32 or ord(k) == 127):
            k = ord(k)
        if k == ESC:
            k = self.decode_escape()
            if k is None or k == K_MOUSE:
                return k
        elif isinstance(k, int) and k > 255:
            k = self.named_key(k)
        if self.recording is not None and k not in (curses.KEY_F5, curses.KEY_F6,
                                                    curses.KEY_RESIZE):
            self.recording.append(k)
        return k

    def read_mouse_rest(self):
        """After ncurses consumed the "ESC [ <" start of a mouse report: read "b;x;yM"."""
        self.scr.nodelay(True)
        buf = ""
        try:
            for _i in range(24):
                try:
                    ch = self.scr.get_wch()
                except curses.error:
                    break
                if not isinstance(ch, str):
                    break
                buf += ch
                if ch in "Mm":
                    break
        finally:
            self.scr.nodelay(False)
        return buf

    def sgr_mouse(self, body, wanted):
        """Interpret an SGR (1006) mouse report "b;x;yM" / "b;x;ym".
        Wheel -> three arrow keys (works in every view); clicks etc. -> K_MOUSE."""
        m = re.fullmatch(r"(\d+);(\d+);(\d+)([Mm])", body)
        if not m:
            return None
        b, x, y = int(m.group(1)), int(m.group(2)) - 1, int(m.group(3)) - 1
        press = m.group(4) == "M"
        motion = bool(b & 32)
        if b & 64:                                   # wheel
            if press:
                key = {0: curses.KEY_UP, 1: curses.KEY_DOWN, 2: curses.KEY_LEFT,
                       3: curses.KEY_RIGHT}.get(b & 3)
                if key:
                    self.queue.extend([key] * (3 if key in (curses.KEY_UP, curses.KEY_DOWN)
                                               else 1))
                    return self.queue.popleft()
            return None
        if not press:
            if (b & 3) == 0 and not b & 128:
                self.btn_down = False
            return None
        if not wanted:
            return None
        if b & 128:                                  # extra buttons: 8 = back, 9 = forward
            kind = {0: "back", 1: "forward"}.get(b & 3)
            if kind is None:
                return None
            self.mouse_event = (x, y, kind)
            return K_MOUSE
        button = b & 3
        if button == 0 and motion:
            if self.btn_down:
                self.mouse_event = (x, y, "drag")
                return K_MOUSE
            return None
        if motion:
            return None
        if button == 0:
            now = time.time()
            last = self.last_click
            dbl = bool(last and last[:2] == (x, y) and now - last[2] < 0.4)
            self.last_click = None if dbl else (x, y, now)
            self.btn_down = True
            self.mouse_event = (x, y, "double" if dbl else "click")
            return K_MOUSE
        if button == 2:
            self.mouse_event = (x, y, "right")
            return K_MOUSE
        return None

    def on_mouse(self):
        x, y, kind = self.mouse_event
        if kind in ("click", "double"):
            for row, x0, x1, code in term.HELP_REGIONS:
                if row == y and x0 <= x < x1:
                    self.btn_down = False
                    self.view.handle(code)
                    return
        fn = getattr(self.view, "mouse", None)
        if fn:
            fn(x, y, kind)

    @staticmethod
    def named_key(k):
        """Terminfo extended keys (kLFT3 = Alt+Left, ...) arrive as dynamic codes."""
        try:
            name = curses.keyname(k)
        except (curses.error, ValueError, OverflowError):
            return k
        return {b"kLFT3": K_ALT_LEFT, b"kRIT3": K_ALT_RIGHT}.get(name, k)

    def decode_escape(self):
        """Recognise escape sequences terminfo does not know (Alt keys, tmux variants)."""
        self.scr.nodelay(True)
        seq = ""
        try:
            for _i in range(24):
                try:
                    ch = self.scr.get_wch()
                except curses.error:
                    break
                if not isinstance(ch, str):
                    break
                seq += ch
                if ch.isalpha() or ch == "~":
                    break
        finally:
            self.scr.nodelay(False)
        if not seq:
            return ESC
        if seq.startswith("[<"):
            return self.sgr_mouse(seq[2:], self._want_mouse)
        return ESCAPES.get(seq, ESC)

    def play_macro(self, times=1):
        if self.recording is not None:
            self.error(tr("Cannot play while recording (F5 = stop)"))
        elif not self.macro:
            self.error(tr("No macro recorded (F5 = start recording)"))
        else:
            self.queue.extend(self.macro * max(1, min(times, 10000)))

    def final_dir(self):
        """Folder to leave the shell in (None when nanger was only used to edit a file)."""
        return None if self.file_mode_only else self.browser.cwd

    def unsaved(self):
        return [b for b in self.buffers if b.modified and b.path and not b.bulk]

    def autosave(self, force=False):
        now = time.time()
        if not force and now - self._autosaved < recovery.interval():
            return
        self._autosaved = now
        for b in self.unsaved():
            b.autosave()

    def _on_hangup(self, signum, frame):
        """Terminal closed / killed: keep the work, then leave."""
        self.crashed = True
        self.autosave(force=True)
        raise SystemExit(128 + signum)

    def run(self):
        import signal
        for name in ("SIGHUP", "SIGTERM"):
            try:
                signal.signal(getattr(signal, name), self._on_hangup)
            except (AttributeError, ValueError, OSError):
                pass
        recovery.prune()
        try:
            self.loop()
        finally:
            if not self.crashed:             # a normal exit means the user chose to discard
                for b in self.buffers:
                    b.drop_recovery()
            for b in self.buffers:
                if b.bulk and b.path:
                    try:
                        os.unlink(b.path)
                    except OSError:
                        pass

    def loop(self):
        while self.running:
            self.autosave()
            if not self.queue:
                self.draw()
            k = self.getkey(mouse=True)
            if k is None or k == curses.KEY_RESIZE:
                continue
            self.msg = ""
            if k == K_MOUSE:
                self.on_mouse()
                continue
            if k == curses.KEY_F5:
                if self.recording is None:
                    self.recording = []
                    self.info(tr("Recording macro… (F5 = stop)"))
                else:
                    self.macro, self.recording = self.recording, None
                    self.info(tr("Macro recorded ({n} keys) — F6 = play").format(n=len(self.macro)))
            elif k == curses.KEY_F6:
                self.play_macro()
            else:
                mode = "editor" if isinstance(self.view, Editor) else \
                    "browser" if self.view is self.browser else None
                if getattr(self.view, "filtering", False):
                    mode = None              # typing a filter: keys are text, not commands
                if mode:
                    k = self.resolve_key(mode, k)
                    if k is None:
                        continue
                else:
                    self.pending = ()
                self.view.handle(k)

    def resolve_key(self, mode, k):
        """Apply the user's key map, including two-key sequences (like `zh`).
        Returns the key to handle, or None while a sequence is still incomplete."""
        km = settings.keymaps[mode]
        built = actions.BUILTIN[mode]
        if k == ESC and self.pending:
            self.pending = ()
            self.msg = ""
            return None
        seq = self.pending + (k,)
        for table in (km, built):
            if seq in table:
                self.pending = ()
                self.msg = ""
                return table[seq]
        if any(len(s) > len(seq) and s[:len(seq)] == seq for s in list(km) + list(built)):
            self.pending = seq
            self.info(seq_label(seq) + " …")
            return None
        self.pending = ()
        return km.get((k,), k)

    # ---- screen
    def draw(self, overlay=None):
        scr = self.scr
        scr.erase()
        media.begin_frame()
        media.OVERLAY.clear()
        media.GRAPHICS.clear()
        term.HELP_REGIONS.clear()
        h, w = scr.getmaxyx()
        if h < 8 or w < 30:
            put(scr, 0, 0, tr("Window too small"))
            scr.refresh()
            return
        cursor = self.view.draw(scr, h, w)
        if overlay:
            text, cur = overlay
            start = max(0, cur - (w - 2))
            put(scr, h - 3, 0, " " * (w - 1))
            put(scr, h - 3, 0, text[start:start + w - 1], curses.A_BOLD)
            cursor = (h - 3, cur - start)
        elif self.msg:
            put(scr, h - 3, 0, " " * (w - 1))
            put(scr, h - 3, 0, self.msg[: w - 1], A["err"] if self.msg_err else curses.A_BOLD)
        try:
            if cursor:
                curses.curs_set(1)
                scr.move(max(0, min(cursor[0], h - 1)), max(0, min(cursor[1], w - 1)))
            else:
                curses.curs_set(0)
        except curses.error:
            pass
        scr.refresh()
        media.flush_overlay()

    def prompt(self, label, default="", history=None):
        buf = list(default)
        pos = len(buf)
        hi = len(history) if history is not None else 0
        while True:
            if not self.queue:
                self.draw(overlay=(label + "".join(buf), len(label) + pos))
            k = self.getkey()
            if k is None or k == curses.KEY_RESIZE:
                continue
            if k in ENTER:
                res = "".join(buf)
                if history is not None and res and (not history or history[-1] != res):
                    history.append(res)
                self.msg = ""
                return res
            if k in (ESC, C("c"), C("q")):
                self.msg = ""
                return None
            if k in BACKSPACE:
                if pos:
                    del buf[pos - 1]
                    pos -= 1
            elif k == curses.KEY_DC:
                if pos < len(buf):
                    del buf[pos]
            elif k == curses.KEY_LEFT:
                pos = max(0, pos - 1)
            elif k == curses.KEY_RIGHT:
                pos = min(len(buf), pos + 1)
            elif k in (curses.KEY_HOME, C("a")):
                pos = 0
            elif k in (curses.KEY_END, C("e")):
                pos = len(buf)
            elif k == C("u"):
                buf, pos = [], 0
            elif k in (curses.KEY_UP, curses.KEY_DOWN) and history:
                hi = max(0, hi - 1) if k == curses.KEY_UP else min(len(history), hi + 1)
                buf = list(history[hi]) if hi < len(history) else []
                pos = len(buf)
            elif isinstance(k, str):
                buf[pos:pos] = list(k)
                pos += len(k)

    def ask(self, label):
        """One-key question; returns the lower-case key, or None (Esc / non-character key)."""
        while True:
            if not self.queue:
                self.draw(overlay=(label, len(label)))
            k = self.getkey()
            if k is None or k == curses.KEY_RESIZE:
                continue
            self.msg = ""
            if isinstance(k, str):
                return k.lower()
            return None

    def read_key(self, label):
        """Wait for one key (case sensitive). None on Esc."""
        while True:
            if not self.queue:
                self.draw(overlay=(label, len(label)))
            k = self.getkey()
            if k is None or k == curses.KEY_RESIZE:
                continue
            self.msg = ""
            return None if k == ESC else k

    def show_help(self, text):
        media.hide_graphics()
        lines = text.split("\n")
        top = 0
        while True:
            scr = self.scr
            scr.erase()
            h, w = scr.getmaxyx()
            for r, line in enumerate(lines[top:top + h]):
                put(scr, r, 0, line, curses.A_BOLD if line[:1].isupper() else 0)
            try:
                curses.curs_set(0)
            except curses.error:
                pass
            scr.refresh()
            k = self.getkey()
            if k in (curses.KEY_DOWN, "j", curses.KEY_NPAGE):
                top = min(max(0, len(lines) - h), top + (1 if k != curses.KEY_NPAGE else h))
            elif k in (curses.KEY_UP, "k", curses.KEY_PPAGE):
                top = max(0, top - (1 if k != curses.KEY_PPAGE else h))
            elif k not in (None, curses.KEY_RESIZE):
                return

    def shell(self, cmd, cwd):
        from .cli import mouse_off, mouse_on
        media.hide_graphics()
        mouse_off()
        curses.def_prog_mode()
        curses.endwin()
        try:
            if cmd:
                print("$ %s" % cmd, flush=True)
                subprocess.call(cmd, shell=True, cwd=cwd)
                input("\n" + tr("[Enter = back to nanger] "))
            else:
                sh = os.environ.get("SHELL", "/bin/sh")
                print(tr("nanger: shell in this folder — type exit to return"), flush=True)
                subprocess.call([sh], cwd=cwd)
        except (KeyboardInterrupt, EOFError):
            pass
        curses.reset_prog_mode()
        mouse_on()
        self.scr.clear()
        self.scr.refresh()

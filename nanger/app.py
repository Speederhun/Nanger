"""Application: owns the views (file manager, editors, viewer, result lists), the keyboard
loop, prompts and the macro recorder."""
import curses
import os
import re
import select
import subprocess
import sys
from collections import deque

from .browser import Browser
from .config import settings
from .editor import Editor
from .fsops import apply_renames, load_bookmarks, plan_renames, search_files
from .i18n import tr
from .keys import BACKSPACE, C, ENTER, ESC, ESCAPES, K_ALT_LEFT, K_ALT_RIGHT
from . import media
from .media import archive_lines, can_view, file_kind, has_gui
from .results import Results
from .term import A, put
from .util import load_text, set_system_clipboard
from .viewer import Viewer


class App:
    def __init__(self, scr, target, line=None):
        self.scr = scr
        self.msg = ""
        self.msg_err = False
        self.clip = ("", False)
        self.running = True
        self.queue = deque()
        self.recording = None
        self.macro = []
        self.cmd_history = []
        self.buffers = []           # open Editor objects (tabs)
        self.last_buffer = None
        self.last_results = None
        self.return_view = None     # where the viewer / result list returns to
        self.quit_when_empty = False
        target = os.path.abspath(os.path.expanduser(target))
        if os.path.isdir(target):
            self.browser = Browser(self, target)
            self.view = self.browser
        else:
            d = os.path.dirname(target)
            self.browser = Browser(self, d if os.path.isdir(d) else os.getcwd())
            self.view = self.browser
            self.quit_when_empty = True
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
            subprocess.Popen(["xdg-open", path], stdin=subprocess.DEVNULL,
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
    def getkey(self):
        if self.queue:
            return self.queue.popleft()
        try:
            k = self.scr.get_wch()
        except curses.error:
            return None
        except KeyboardInterrupt:
            return C("c")
        if isinstance(k, str) and len(k) == 1 and (ord(k) < 32 or ord(k) == 127):
            k = ord(k)
        if k == ESC:
            k = self.decode_escape()
        elif isinstance(k, int) and k > 255:
            k = self.named_key(k)
        if self.recording is not None and k not in (curses.KEY_F5, curses.KEY_F6,
                                                    curses.KEY_RESIZE):
            self.recording.append(k)
        return k

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
            for _i in range(8):
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
        return ESCAPES.get(seq, ESC)

    def play_macro(self, times=1):
        if self.recording is not None:
            self.error(tr("Cannot play while recording (F5 = stop)"))
        elif not self.macro:
            self.error(tr("No macro recorded (F5 = start recording)"))
        else:
            self.queue.extend(self.macro * max(1, min(times, 10000)))

    def run(self):
        try:
            self.loop()
        finally:
            for b in self.buffers:
                if b.bulk and b.path:
                    try:
                        os.unlink(b.path)
                    except OSError:
                        pass

    def loop(self):
        while self.running:
            if not self.queue:
                self.draw()
            k = self.getkey()
            if k is None or k == curses.KEY_RESIZE:
                continue
            self.msg = ""
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
                if mode:
                    k = settings.keymaps[mode].get(k, k)
                self.view.handle(k)

    # ---- screen
    def draw(self, overlay=None):
        scr = self.scr
        scr.erase()
        media.OVERLAY.clear()
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
        self.scr.clear()
        self.scr.refresh()

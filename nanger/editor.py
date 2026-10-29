"""The text editor view: nano-simple keys, vim-style command line."""
import curses
import os
import re
import subprocess
import time

from . import gitinfo, recovery
from .config import settings
from .helptext import editor_help
from .i18n import tr
from .keys import (BACKSPACE, C, ENTER, ESC, K_ALT_DIGIT, K_ALT_LEFT, K_ALT_RIGHT, MOVES,
                   SHIFT_MOVES)
from .syntax import COMMENTS, PLAIN, highlight
from .term import A, clean, disp_col, draw_help, idx_from_col, put
from .util import disk_sig, load_text, save_text, split_delim


def help_bar1():
    return [("^S", tr("Save")), ("^Q", tr("Close")), ("^F", tr("Find")), ("^N", tr("Next")),
            ("^R", tr("Replace")), ("^G", tr("Go to line")), ("^P", tr("Command")),
            ("F1", tr("Help")), ("F9", tr("Customize"))]


def help_bar2():
    return [("^Z", tr("Undo")), ("^Y", tr("Redo")), ("^B", tr("Select")), ("^A", tr("All")),
            ("^C", tr("Copy")), ("^K", tr("Cut")), ("^V", tr("Paste")), ("^D", tr("Duplicate")),
            ("F4", tr("Files")), ("F5/F6", tr("Macro"))]


class Editor:
    def __init__(self, app, path, line=None):
        self.app = app
        self.path = path
        self.enc, self.nl, self.trailing = "utf-8", "\n", True
        self.lines = [""]
        self.sig = None
        if path and os.path.exists(path):
            self.lines, self.enc, self.nl, self.trailing = load_text(path)
            self.sig = disk_sig(path)
        self.cy = self.cx = self.top = self.left = self.want = 0
        self.modified = False
        self.undo, self.redo = [], []
        self.typing = False
        self.anchor = None
        self.sticky = False
        self.numbers = settings.line_numbers
        self.search = ""
        self.last_cut = False
        self.bulk = None            # set for the "bulk rename" scratch buffer
        self.warned_sig = None
        self._checked = 0.0
        self._auto = None
        self.git_base = None
        self._marks, self._marks_src = {}, None
        self.use_tabs = any(l.startswith("\t") for l in self.lines[:1000])
        self.set_syntax()
        self.refresh_git()
        if line:
            self.cy = max(0, min(len(self.lines) - 1, line - 1))
            self.center()

    def set_syntax(self):
        ext = os.path.splitext(self.path or "")[1].lower()
        self.ctok = COMMENTS.get(ext, "#")
        self.hl = ext not in PLAIN

    def dir(self):
        return os.path.dirname(self.path) if self.path else self.app.browser.cwd

    def name(self):
        return os.path.basename(self.path) if self.path else tr("[new file]")

    def refresh_git(self):
        self.git_base = gitinfo.head_lines(self.path) if self.path else None
        self._marks_src = None

    def marks(self):
        if self.git_base is None:
            return {}
        if self._marks_src is not None and (self._marks_src == self.lines or
                                            self.app.input_pending()):
            return self._marks
        self._marks = gitinfo.diff_marks(self.git_base, self.lines)
        self._marks_src = self.lines[:]
        return self._marks

    # ---- state
    def push(self):
        self.undo.append((self.lines[:], self.cy, self.cx))
        if len(self.undo) > 400:
            del self.undo[0]
        self.redo.clear()

    def begin(self, group=False):
        if not (group and self.typing):
            self.push()
        self.typing = group
        self.modified = True

    def replace_sel_begin(self, group):
        if self.anchor is not None:
            self.push()
            self.delete_sel()
            self.typing = group
            self.modified = True
        else:
            self.begin(group)

    def clamp(self):
        self.cy = max(0, min(self.cy, len(self.lines) - 1))
        self.cx = max(0, min(self.cx, len(self.lines[self.cy])))

    def set_want(self):
        self.want = disp_col(self.lines[self.cy], self.cx)

    def do_undo(self):
        if not self.undo:
            self.app.info(tr("Nothing to undo"))
            return
        self.redo.append((self.lines[:], self.cy, self.cx))
        self.lines, self.cy, self.cx = self.undo.pop()
        self.anchor = None
        self.modified = True
        self.clamp()

    def do_redo(self):
        if not self.redo:
            self.app.info(tr("Nothing to redo"))
            return
        self.undo.append((self.lines[:], self.cy, self.cx))
        self.lines, self.cy, self.cx = self.redo.pop()
        self.anchor = None
        self.modified = True
        self.clamp()

    # ---- selection
    def mouse(self, x, y, kind):
        g = getattr(self, "geom", None)
        if kind == "back":
            self.handle(curses.KEY_F4)      # back to the file manager
            return
        if not g or kind in ("right", "forward"):
            return
        gutter, th = g
        if y < 1 or y > th:
            return
        ny = min(self.top + y - 1, len(self.lines) - 1)
        nx = idx_from_col(self.lines[ny], max(0, x - gutter) + self.left)
        if kind == "drag":
            if self.anchor is None:
                self.anchor = (self.cy, self.cx)
            self.cy, self.cx = ny, nx
        elif kind == "double":
            line = self.lines[ny]
            a = b = min(nx, len(line))
            while a > 0 and (line[a - 1].isalnum() or line[a - 1] == "_"):
                a -= 1
            while b < len(line) and (line[b].isalnum() or line[b] == "_"):
                b += 1
            self.cy, self.cx = ny, b
            self.anchor = (ny, a) if a != b else None
        else:
            self.cy, self.cx = ny, nx
            self.anchor, self.sticky = None, False
        self.want = disp_col(self.lines[self.cy], self.cx)

    def sel_range(self):
        if self.anchor is None:
            return None
        a, b = self.anchor, (self.cy, self.cx)
        if a == b:
            return None
        return (a, b) if a < b else (b, a)

    def sel_text(self, r):
        (y1, x1), (y2, x2) = r
        L = self.lines
        if y1 == y2:
            return L[y1][x1:x2]
        return "\n".join([L[y1][x1:]] + L[y1 + 1:y2] + [L[y2][:x2]])

    def delete_sel(self):
        r = self.sel_range()
        self.anchor = None
        self.sticky = False
        if not r:
            return
        (y1, x1), (y2, x2) = r
        self.lines[y1:y2 + 1] = [self.lines[y1][:x1] + self.lines[y2][x2:]]
        self.cy, self.cx = y1, x1
        self.set_want()

    def sel_lines(self, default_all):
        r = self.sel_range()
        if r:
            (y1, _x1), (y2, x2) = r
            if x2 == 0 and y2 > y1:
                y2 -= 1
            return y1, y2
        if default_all:
            return 0, len(self.lines) - 1
        return self.cy, self.cy

    def insert_text(self, text):
        parts = text.split("\n")
        line = self.lines[self.cy]
        before, after = line[:self.cx], line[self.cx:]
        if len(parts) == 1:
            self.lines[self.cy] = before + text + after
            self.cx += len(text)
        else:
            new = [before + parts[0]] + parts[1:-1] + [parts[-1] + after]
            self.lines[self.cy:self.cy + 1] = new
            self.cy += len(parts) - 1
            self.cx = len(parts[-1])
        self.set_want()

    # ---- keys
    def handle(self, k):
        app = self.app
        self.check_disk()
        if not (isinstance(k, str) or k in ENTER):
            self.typing = False
        cut_chain = False
        if k in SHIFT_MOVES:
            if self.anchor is None:
                self.anchor = (self.cy, self.cx)
                self.sticky = False
            self.move(SHIFT_MOVES[k])
        elif k in MOVES:
            if self.anchor is not None and not self.sticky:
                self.anchor = None
            self.move(k)
        elif isinstance(k, str):
            self.insert_char(k)
        elif k in ENTER:
            self.newline()
        elif k in BACKSPACE:
            self.backspace()
        elif k == curses.KEY_DC:
            self.delete()
        elif k == 9:
            self.tab()
        elif k == curses.KEY_BTAB:
            self.indent(-1)
        elif k == C("s"):
            self.save()
        elif k == C("o"):
            self.save_as()
        elif k in (C("q"), C("x")):
            self.close()
        elif k == C("f"):
            self.find_prompt()
        elif k in (C("n"), curses.KEY_F3):
            self.find_next()
        elif k == C("r"):
            self.replace_prompt()
        elif k == C("g"):
            self.goto_prompt()
        elif k in (C("p"), curses.KEY_F2):
            c = app.prompt(":", "", app.cmd_history)
            if c:
                self.run_command(c)
        elif k == C("z"):
            self.do_undo()
        elif k == C("y"):
            self.do_redo()
        elif k == C("b"):
            if self.anchor is None:
                self.anchor, self.sticky = (self.cy, self.cx), True
                app.info(tr("Selection mode: move with the arrows, then ^C / ^K"))
            else:
                self.anchor, self.sticky = None, False
        elif k == C("a"):
            self.anchor, self.sticky = (0, 0), True
            self.cy = len(self.lines) - 1
            self.cx = len(self.lines[-1])
        elif k == C("c"):
            self.copy()
        elif k == C("k"):
            self.cut()
            cut_chain = True
        elif k in (C("v"), C("u")):
            self.paste()
        elif k == C("d"):
            self.begin()
            self.lines.insert(self.cy + 1, self.lines[self.cy])
            self.cy += 1
        elif k == C("l"):
            self.numbers = not self.numbers
        elif k == ESC:
            self.anchor, self.sticky = None, False
        elif k == curses.KEY_F1:
            app.show_help(editor_help())
        elif k == curses.KEY_F9:
            app.show_keys("editor")
        elif k in (curses.KEY_F4, C("e")):
            app.show_browser()
        elif k == K_ALT_LEFT:
            app.switch_buffer(-1)
        elif k == K_ALT_RIGHT:
            app.switch_buffer(1)
        elif K_ALT_DIGIT < k <= K_ALT_DIGIT + 9:
            app.goto_buffer(k - K_ALT_DIGIT)
        self.last_cut = cut_chain
        if app.current_editor() is self:
            self.clamp()

    def move(self, k):
        L = self.lines
        page = max(1, self.app.text_height() - 1)
        if k in (curses.KEY_UP, curses.KEY_DOWN, curses.KEY_PPAGE, curses.KEY_NPAGE):
            d = {curses.KEY_UP: -1, curses.KEY_DOWN: 1,
                 curses.KEY_PPAGE: -page, curses.KEY_NPAGE: page}[k]
            self.cy = max(0, min(len(L) - 1, self.cy + d))
            self.cx = idx_from_col(L[self.cy], self.want)
            return
        if k == curses.KEY_LEFT:
            if self.cx > 0:
                self.cx -= 1
            elif self.cy > 0:
                self.cy -= 1
                self.cx = len(L[self.cy])
        elif k == curses.KEY_RIGHT:
            if self.cx < len(L[self.cy]):
                self.cx += 1
            elif self.cy < len(L) - 1:
                self.cy += 1
                self.cx = 0
        elif k == curses.KEY_HOME:
            line = L[self.cy]
            ind = len(line) - len(line.lstrip(" \t"))
            self.cx = 0 if self.cx == ind else ind
        elif k == curses.KEY_END:
            self.cx = len(L[self.cy])
        self.set_want()

    def insert_char(self, ch):
        self.replace_sel_begin(True)
        line = self.lines[self.cy]
        self.lines[self.cy] = line[:self.cx] + ch + line[self.cx:]
        self.cx += len(ch)
        self.set_want()
        if ch in " \t":
            self.typing = False  # undo goes word by word

    def newline(self):
        self.replace_sel_begin(True)
        pasting = self.app.input_pending()
        line = self.lines[self.cy]
        before, after = line[:self.cx], line[self.cx:]
        indent = ""
        if not pasting:
            indent = re.match(r"[ \t]*", before).group(0)
            if before.rstrip().endswith((":", "{", "(", "[")):
                indent += "\t" if self.use_tabs else " " * settings.tab_width
            after = after.lstrip(" \t")
        self.lines[self.cy] = before
        self.lines.insert(self.cy + 1, indent + after)
        self.cy += 1
        self.cx = len(indent)
        self.set_want()

    def backspace(self):
        if self.anchor is not None and self.sel_range():
            self.push()
            self.delete_sel()
            self.modified = True
            return
        self.anchor = None
        if self.cx == 0 and self.cy == 0:
            return
        self.begin()
        L = self.lines
        if self.cx > 0:
            line = L[self.cy]
            n = 1
            tab = settings.tab_width
            if not self.use_tabs and line[:self.cx].strip() == "" and self.cx % tab == 0:
                n = tab
            L[self.cy] = line[:self.cx - n] + line[self.cx:]
            self.cx -= n
        else:
            self.cx = len(L[self.cy - 1])
            L[self.cy - 1] += L[self.cy]
            del L[self.cy]
            self.cy -= 1
        self.set_want()

    def delete(self):
        if self.anchor is not None and self.sel_range():
            self.push()
            self.delete_sel()
            self.modified = True
            return
        self.anchor = None
        L = self.lines
        if self.cx < len(L[self.cy]):
            self.begin()
            L[self.cy] = L[self.cy][:self.cx] + L[self.cy][self.cx + 1:]
        elif self.cy < len(L) - 1:
            self.begin()
            L[self.cy] += L[self.cy + 1]
            del L[self.cy + 1]

    def tab(self):
        r = self.sel_range()
        if r and r[0][0] != r[1][0]:
            self.indent(1)
            return
        tab = settings.tab_width
        unit = "\t" if self.use_tabs else " " * (tab - disp_col(self.lines[self.cy], self.cx) % tab)
        self.replace_sel_begin(True)
        self.insert_text(unit)

    def indent(self, d):
        y1, y2 = self.sel_lines(False)
        tab = settings.tab_width
        unit = "\t" if self.use_tabs else " " * tab
        self.begin()
        for y in range(y1, y2 + 1):
            line = self.lines[y]
            if d > 0:
                if line:
                    self.lines[y] = unit + line
            elif line.startswith("\t"):
                self.lines[y] = line[1:]
            else:
                n = len(line) - len(line.lstrip(" "))
                self.lines[y] = line[min(n, tab):]
        if self.anchor is not None:
            self.anchor = (self.anchor[0], 0)
            self.sticky = True

    def copy(self):
        r = self.sel_range()
        if r:
            self.app.set_clip(self.sel_text(r), False)
            self.anchor, self.sticky = None, False
            self.app.info(tr("Selection copied"))
        else:
            self.anchor = None
            self.app.set_clip(self.lines[self.cy], True)
            self.app.info(tr("Line copied"))

    def cut(self):
        r = self.sel_range()
        if r:
            self.push()
            self.app.set_clip(self.sel_text(r), False)
            self.delete_sel()
            self.modified = True
            return
        self.anchor = None
        self.push()
        self.modified = True
        line = self.lines.pop(self.cy)
        if not self.lines:
            self.lines.append("")
        text, linewise = self.app.clip
        if self.last_cut and linewise:
            self.app.set_clip(text + "\n" + line, True)
        else:
            self.app.set_clip(line, True)

    def paste(self):
        text, linewise = self.app.clip
        if not text and not linewise:
            self.app.info(tr("The clipboard is empty"))
            return
        if linewise and self.anchor is None:
            self.begin()
            new = text.split("\n")
            self.lines[self.cy:self.cy] = new
            self.cy += len(new)
        else:
            self.replace_sel_begin(False)
            self.insert_text(text)

    # ---- file
    def diff(self, other=""):
        """:diff = buffer against the saved file; :diff FILE = buffer against another file."""
        app = self.app
        path = os.path.expanduser(other) if other else self.path
        if not path or not os.path.isfile(path):
            app.error(tr("No file to compare with") if not other
                      else tr("Not a file: {path}").format(path=path))
            return
        try:
            disk = load_text(path)[0]
        except (OSError, ValueError) as e:
            app.error(tr("Cannot open: {error}").format(error=getattr(e, "strerror", None) or e))
            return
        name = os.path.basename(self.path) if self.path else tr("(no name)")
        app.show_diff(os.path.basename(path) + (" " + tr("(on disk)") if not other else ""),
                      disk, name + " " + tr("(edited)"), list(self.lines))

    def autosave(self):
        """Write the unsaved buffer to the recovery folder (only when it changed)."""
        if not self.modified or not self.path or self.bulk:
            return
        text = "\n".join(self.lines)
        state = (len(text), hash(text))
        if state == self._auto:
            return
        if recovery.write(self.path, self.lines, self.enc, self.nl):
            self._auto = state

    def drop_recovery(self):
        self._auto = None
        if self.path:
            recovery.discard(self.path)

    def offer_recovery(self):
        """After opening: offer to restore unsaved changes left by a crash."""
        if not self.path or self.bulk:
            return
        rec = recovery.load(self.path)
        if rec is None:
            return
        if rec["text"] == "\n".join(self.lines):
            recovery.discard(self.path)
            return
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(rec.get("saved_at", 0)))
        a = self.app.ask(tr("Unsaved changes from {when} were found. Restore them? (y/n) ")
                         .format(when=when))
        if a in ("y", "i"):
            self.push()
            self.lines = rec["text"].split("\n") or [""]
            self.modified = True
            self.clamp()
            self.app.info(tr("Unsaved changes restored — Ctrl+S saves them"))
        else:
            recovery.discard(self.path)

    def check_disk(self):
        """Notice when another program changed the file while it is open here."""
        if not self.path or self.sig is None:
            return
        now = time.time()
        if now - self._checked < 0.5:
            return
        self._checked = now
        sig = disk_sig(self.path)
        if sig is None or sig == self.sig:
            return
        if not self.modified:
            self.reload()
            self.app.info(tr("The file changed on disk — reloaded"))
        elif sig != self.warned_sig:
            self.warned_sig = sig
            self.app.error(tr("The file changed on disk! Ctrl+S would overwrite it (:e! reloads)"))

    def reload(self):
        try:
            self.lines, self.enc, self.nl, self.trailing = load_text(self.path)
        except (OSError, ValueError) as e:
            self.app.error(tr("Cannot reload: {error}").format(error=getattr(e, "strerror", None) or e))
            return False
        self.sig = disk_sig(self.path)
        self.warned_sig = None
        self.modified = False
        self.drop_recovery()
        self.undo.clear()
        self.redo.clear()
        self.anchor = None
        self.typing = False
        self.refresh_git()
        self.clamp()
        return True

    def save(self, path=None):
        path = path or self.path
        if not path:
            path = self.app.prompt(tr("Save as (file name): "))
            if not path:
                return False
        path = os.path.expanduser(path)
        if not os.path.isabs(path):
            path = os.path.join(self.app.browser.cwd, path)
        if path == self.path and self.sig is not None and disk_sig(path) not in (None, self.sig):
            if self.app.ask(tr("The file changed on disk. Overwrite it? (y/n) ")) not in ("y", "i"):
                self.app.info(tr("Not saved"))
                return False
        try:
            save_text(path, self.lines, self.enc, self.nl, self.trailing)
        except OSError as e:
            self.app.error(tr("Save failed: {error}").format(error=e.strerror or e))
            return False
        if path != self.path:
            self.path = path
            self.set_syntax()
        self.sig = disk_sig(path)
        self.warned_sig = None
        self.modified = False
        self.typing = False
        self.drop_recovery()
        gitinfo.invalidate()
        self.refresh_git()
        self.app.info(tr("Saved: {name} ({n} lines)").format(name=os.path.basename(path),
                                                              n=len(self.lines)))
        return True

    def save_as(self):
        p = self.app.prompt(tr("Save as: "), self.path or "")
        if p:
            self.save(p)

    def confirm_discard(self):
        if not self.modified:
            return True
        a = self.app.ask(tr("Save the changes? (y = yes, n = no, Esc = cancel) "))
        if a in ("y", "i"):
            return self.save()
        return a == "n"

    def close(self, force=False):
        if force or self.confirm_discard():
            self.app.close_buffer(self)

    # ---- search / replace
    def find_prompt(self):
        t = self.app.prompt(tr("Search: "), self.search)
        if t is None:
            return
        self.search = t
        if t:
            self.find_from(self.cy, self.cx)

    def find_next(self):
        if not self.search:
            self.find_prompt()
        else:
            self.find_from(self.cy, self.cx + 1)

    def find_from(self, y, x):
        t = self.search.lower()
        n = len(self.lines)
        for i in range(n + 1):
            yy = (y + i) % n
            j = self.lines[yy].lower().find(t, x if i == 0 else 0)
            if j != -1:
                if (yy, j) < (y, x):
                    self.app.info(tr("Wrapped around, continuing from the top"))
                self.cy, self.cx = yy, j
                self.anchor = None
                self.set_want()
                self.center()
                return True
        self.app.error(tr("No match: {pattern}").format(pattern=self.search))
        return False

    def center(self):
        th = self.app.text_height()
        if not (self.top <= self.cy < self.top + th):
            self.top = max(0, self.cy - th // 2)

    def replace_prompt(self):
        pat = self.app.prompt(tr("Replace – what (regex): "), self.search)
        if not pat:
            return
        rep = self.app.prompt(tr("Replace – instead of “{pattern}”: ").format(pattern=pat))
        if rep is None:
            return
        y1, y2 = self.sel_lines(True)
        self.substitute(pat, rep, True, 0, y1, y2)

    def substitute(self, pat, rep, glob, flags, y1, y2):
        try:
            rx = re.compile(pat, flags)
        except re.error as e:
            self.app.error(tr("Invalid regex: {error}").format(error=e))
            return
        new = self.lines[y1:y2 + 1]
        total = 0
        try:
            for i, line in enumerate(new):
                s, n = rx.subn(rep, line, count=0 if glob else 1)
                if n:
                    new[i] = s
                    total += n
        except (re.error, IndexError) as e:
            self.app.error(tr("Invalid replacement: {error}").format(error=e))
            return
        if not total:
            self.app.error(tr("No match: {pattern}").format(pattern=pat))
            return
        self.begin()
        self.lines[y1:y2 + 1] = "\n".join(new).split("\n")
        self.anchor = None
        self.clamp()
        self.app.info(tr("{n} replaced").format(n=total))

    def goto_prompt(self):
        s = self.app.prompt(tr("Go to line (line or line:column): "))
        if s:
            self.goto(s)

    def goto(self, s):
        m = re.fullmatch(r"\s*(\d+|\$)\s*(?::\s*(\d+))?\s*", s)
        if not m:
            self.app.error(tr("Enter a line number, e.g. 120 or 120:5"))
            return
        self.cy = len(self.lines) - 1 if m.group(1) == "$" else int(m.group(1)) - 1
        self.clamp()
        self.cx = int(m.group(2)) - 1 if m.group(2) else 0
        self.anchor = None
        self.clamp()
        self.set_want()
        self.center()

    # ---- command line (vim ":")
    def run_command(self, cmd):
        app = self.app
        cmd = cmd.strip().lstrip(":").strip()
        if cmd in ("w", "write"):
            self.save()
        elif cmd.startswith("w ") or cmd.startswith("saveas "):
            self.save(cmd.split(None, 1)[1])
        elif cmd in ("q", "quit", "bd"):
            self.close()
        elif cmd in ("q!", "bd!"):
            self.close(force=True)
        elif cmd in ("wq", "x"):
            if self.save():
                self.close(force=True)
        elif re.fullmatch(r"\d+|\$", cmd):
            self.goto(cmd)
        elif cmd in ("set nu", "set number"):
            self.numbers = True
        elif cmd in ("set nonu", "set nonumber"):
            self.numbers = False
        elif cmd in ("help", "h"):
            app.show_help(editor_help())
        elif cmd.startswith("@"):
            n = cmd[1:].strip()
            app.play_macro(int(n) if n.isdigit() else 1)
        elif cmd == "theme" or cmd.startswith("theme "):
            from .config import THEME_NAMES
            name = cmd[5:].strip()
            if name in THEME_NAMES:
                app.apply_theme(name, close=False)
            else:
                app.show_themes()
        elif cmd == "diff" or cmd.startswith("diff "):
            self.diff(cmd[4:].strip())
        elif cmd in ("keys", "map"):
            app.show_keys("editor")
        elif cmd in ("ls", "buffers", "files"):
            app.list_buffers()
        elif cmd in ("bn", "bnext"):
            app.switch_buffer(1)
        elif cmd in ("bp", "bprev", "bprevious"):
            app.switch_buffer(-1)
        elif re.fullmatch(r"b\s*\d+", cmd):
            app.goto_buffer(int(cmd[1:]))
        elif cmd in ("browse", "Ex", "Explore"):
            app.show_browser()
        elif cmd == "e!":
            if self.path and os.path.exists(self.path):
                if self.reload():
                    app.info(tr("Reloaded from disk"))
            else:
                app.error(tr("There is no file on disk to reload"))
        elif cmd == "e":
            if self.modified:
                app.error(tr("Unsaved changes — use :e! to discard them and reload"))
            elif self.path and self.reload():
                app.info(tr("Reloaded from disk"))
        elif cmd.startswith("e "):
            path = os.path.expanduser(cmd[2:].strip())
            if not os.path.isabs(path):
                path = os.path.join(self.dir(), path)
            app.edit(path)
        elif cmd.startswith("grep ") or cmd.startswith("vimgrep "):
            app.grep(cmd.split(None, 1)[1], self.dir())
        elif cmd in ("copen", "cw"):
            app.show_results()
        elif cmd in ("sort", "sort!", "uniq"):
            y1, y2 = self.sel_lines(True)
            part = self.lines[y1:y2 + 1]
            if cmd == "uniq":
                part = [l for i, l in enumerate(part) if i == 0 or l != part[i - 1]]
            else:
                part = sorted(part, key=str.casefold, reverse=cmd == "sort!")
            self.begin()
            self.lines[y1:y2 + 1] = part
            self.anchor = None
            app.info(tr("{n} lines processed").format(n=y2 - y1 + 1))
        elif cmd in ("upper", "lower"):
            fn = str.upper if cmd == "upper" else str.lower
            r = self.sel_range()
            self.begin()
            if r:
                text = self.sel_text(r)
                self.delete_sel()
                self.insert_text(fn(text))
            else:
                self.lines[self.cy] = fn(self.lines[self.cy])
        elif cmd.startswith("r !") or cmd.startswith("r!"):
            out = self.shell_output(cmd.split("!", 1)[1], None)
            if out is not None:
                self.begin()
                lines = out.split("\n")
                self.lines[self.cy + 1:self.cy + 1] = lines
                app.info(tr("{n} lines inserted").format(n=len(lines)))
        elif cmd.startswith("!"):
            sh = cmd[1:].strip()
            if self.sel_range():
                y1, y2 = self.sel_lines(False)
                out = self.shell_output(sh, "\n".join(self.lines[y1:y2 + 1]) + "\n")
                if out is not None:
                    self.begin()
                    self.lines[y1:y2 + 1] = out.split("\n")
                    self.anchor = None
                    self.cy, self.cx = y1, 0
            else:
                app.shell(sh, self.dir())
        elif self.try_substitute(cmd) or self.try_global(cmd):
            pass
        else:
            app.error(tr("Unknown command: {cmd}   (F1 = help)").format(cmd=cmd))
        if app.current_editor() is self:
            self.clamp()

    def shell_output(self, sh, inp):
        try:
            p = subprocess.run(sh, shell=True, input=inp, capture_output=True,
                               text=True, cwd=self.dir(), timeout=120)
        except subprocess.TimeoutExpired:
            self.app.error(tr("The command took too long"))
            return None
        if p.returncode != 0 and not p.stdout:
            err = (p.stderr.strip().splitlines() or [tr("error")])[-1]
            self.app.error(tr("The command failed: {error}").format(error=err))
            return None
        out = p.stdout
        return out[:-1] if out.endswith("\n") else out

    def try_substitute(self, cmd):
        m = re.fullmatch(r"(%|(\d+|\$),(\d+|\$))?s([^\w\s\\])(.*)", cmd, re.S)
        if not m:
            return False
        parts = split_delim(m.group(5), m.group(4))
        pat = parts[0] or re.escape(self.search)
        rep = parts[1] if len(parts) > 1 else ""
        fl = parts[2] if len(parts) > 2 else ""
        last = len(self.lines)
        if m.group(1) == "%":
            y1, y2 = 0, last - 1
        elif m.group(2):
            def conv(v):
                return last if v == "$" else int(v)

            y1, y2 = conv(m.group(2)) - 1, conv(m.group(3)) - 1
            y1, y2 = max(0, min(y1, y2)), min(last - 1, max(y1, y2))
        else:
            y1, y2 = self.sel_lines(False)
        if not pat:
            self.app.error(tr("Empty search pattern"))
            return True
        self.substitute(pat, rep, "g" in fl, re.I if "i" in fl else 0, y1, y2)
        return True

    def try_global(self, cmd):
        if len(cmd) < 3 or cmd[0] not in "gv" or cmd[1].isalnum() or cmd[1].isspace():
            return False
        parts = split_delim(cmd[2:], cmd[1])
        if len(parts) < 2 or parts[1].strip() != "d":
            self.app.error(tr("Format: g/pattern/d or v/pattern/d"))
            return True
        try:
            rx = re.compile(parts[0])
        except re.error as e:
            self.app.error(tr("Invalid regex: {error}").format(error=e))
            return True
        keep_match = cmd[0] == "v"
        y1, y2 = self.sel_lines(True)
        part = self.lines[y1:y2 + 1]
        kept = [l for l in part if bool(rx.search(l)) == keep_match]
        removed = len(part) - len(kept)
        if removed:
            self.begin()
            self.lines[y1:y2 + 1] = kept
            if not self.lines:
                self.lines = [""]
            self.anchor = None
        self.app.info(tr("{n} lines deleted").format(n=removed))
        return True

    # ---- drawing
    def title(self, scr, w):
        app = self.app
        left_segments = [(" nanger │ ", A["title"])]
        if len(app.buffers) > 1:
            for i, b in enumerate(app.buffers):
                label = "%d:%s%s" % (i + 1, b.name(), "*" if b.modified else "")
                if b is self:
                    left_segments.append(("[" + label + "]", A["title"] | curses.A_BOLD))
                else:
                    left_segments.append((" " + label + " ", A["title"]))
        else:
            name = self.path or tr("[new file]")
            home = os.path.expanduser("~")
            if self.path and self.path.startswith(home):
                name = "~" + self.path[len(home):]
            if self.bulk:
                name = tr("Bulk rename — edit the names, save, then close this file")
            left_segments.append((name + ("  " + tr("[modified]") if self.modified else ""),
                                  A["title"]))
        right = (("● " + tr("REC") + "  " if app.recording is not None else "") +
                 "%d:%d  %d %s  %s " % (self.cy + 1, self.cx + 1, len(self.lines), tr("lines"),
                                         self.enc))
        put(scr, 0, 0, " " * w, A["title"])
        room = max(0, w - len(right) - 1)
        x = 0
        for text, attr in left_segments:
            if x >= room:
                break
            put(scr, 0, x, text[:room - x], attr)
            x += len(text)
        put(scr, 0, max(0, w - len(right)), right, A["title"])

    def draw(self, scr, h, w):
        th = h - 4
        L = self.lines
        marks = self.marks()
        sign = 1 if self.git_base is not None else 0
        gutter = sign + (len(str(len(L))) + 1 if self.numbers else 0)
        tw = max(1, w - gutter)
        self.geom = (gutter, th)
        tab = settings.tab_width
        if self.cy < self.top:
            self.top = self.cy
        elif self.cy >= self.top + th:
            self.top = self.cy - th + 1
        dc = disp_col(L[self.cy], self.cx)
        if dc < self.left:
            self.left = dc
        elif dc >= self.left + tw:
            self.left = dc - tw + 1
        sel = self.sel_range()
        term = self.search.lower()
        sign_attr = {"+": A["gadd"], "~": A["gmod"], "_": A["gdel"]}
        for r in range(th):
            y = self.top + r
            row = 1 + r
            if y >= len(L):
                put(scr, row, 0, "~", A["ln"])
                continue
            if sign and y in marks:
                put(scr, row, 0, marks[y], sign_attr[marks[y]])
            if self.numbers:
                put(scr, row, sign, "%*d " % (gutter - sign - 1, y + 1), A["ln"])
            line = L[y]
            attrs = highlight(line, self.ctok) if self.hl else [0] * len(line)
            if term:
                low = line.lower()
                j = low.find(term)
                while j != -1:
                    for i in range(j, min(j + len(term), len(attrs))):
                        attrs[i] = A["match"]
                    j = low.find(term, j + len(term))
            if sel and sel[0][0] <= y <= sel[1][0]:
                s = sel[0][1] if y == sel[0][0] else 0
                e = sel[1][1] if y == sel[1][0] else len(line)
                for i in range(s, e):
                    attrs[i] = curses.A_REVERSE
            cells = []
            for ch, at in zip(line, attrs):
                if ch == "\t":
                    cells += [(" ", at)] * (tab - len(cells) % tab)
                else:
                    cells.append((clean(ch), at))
                if len(cells) > self.left + tw:
                    break
            cells = cells[self.left:self.left + tw]
            x = gutter
            i = 0
            while i < len(cells):
                at = cells[i][1]
                j = i
                while j < len(cells) and cells[j][1] == at:
                    j += 1
                put(scr, row, x, "".join(c for c, _a in cells[i:j]), at)
                x += j - i
                i = j
            if sel and sel[0][0] <= y < sel[1][0] and len(cells) < tw and \
                    disp_col(line, len(line)) >= self.left:
                put(scr, row, x, " ", curses.A_REVERSE)
        self.title(scr, w)
        draw_help(scr, h - 2, help_bar1(), w)
        draw_help(scr, h - 1, help_bar2(), w)
        return (1 + self.cy - self.top, gutter + dc - self.left)

"""Full-screen menu to change the keyboard shortcuts; saved to the config file."""
import curses

from . import actions, config
from .i18n import tr
from .keys import BACKSPACE, C, ENTER, ESC, key_label, seq_label
from .term import A, draw_help, put


class KeyMenu:
    def __init__(self, app, mode):
        self.app = app
        self.rows = [("browser", i) for i in range(len(actions.BROWSER))] + \
                    [("editor", i) for i in range(len(actions.EDITOR))]
        self.sel = 0 if mode == "browser" else len(actions.BROWSER)
        self.top = 0

    def current(self):
        return self.rows[self.sel]

    def handle(self, k):
        app, n = self.app, len(self.rows)
        page = max(1, app.text_height() - 1)
        if k in ("q", ESC, C("q")) or k in BACKSPACE:
            app.close_results()
        elif k in (curses.KEY_UP, "k"):
            self.sel = (self.sel - 1) % n
        elif k in (curses.KEY_DOWN, "j"):
            self.sel = (self.sel + 1) % n
        elif k == curses.KEY_PPAGE:
            self.sel = max(0, self.sel - page)
        elif k == curses.KEY_NPAGE:
            self.sel = min(n - 1, self.sel + page)
        elif k in (curses.KEY_HOME, "g"):
            self.sel = 0
        elif k in (curses.KEY_END, "G"):
            self.sel = n - 1
        elif k in ENTER or k == curses.KEY_RIGHT:
            self.change()
        elif k in (curses.KEY_DC, "d"):
            mode, i = self.current()
            self.apply(mode, i, None)

    def read_seq(self, name, mode):
        """Ask for one or two keys. None = cancelled."""
        first = self.app.read_key(tr("New key for “{name}” (Esc = cancel): ").format(name=name))
        if first is None:
            return None
        keys = [first]
        second = self.app.read_key(
            tr("New key for “{name}”: {first} + a second key, or Enter to finish: ")
            .format(name=name, first=seq_label((first,))))
        if second is None:
            return None
        if second not in ENTER:
            keys.append(second)
        for k in keys:
            if key_label(k) == "?" or k in ("=", ":", "[", "#", ";"):
                self.app.error(tr("That key cannot be used"))
                return None
            if mode == "editor" and isinstance(k, str):
                self.app.error(tr("In the editor use Ctrl or function keys"))
                return None
        return tuple(keys)

    def change(self):
        mode, i = self.current()
        seq = self.read_seq(actions.label(mode, i), mode)
        if seq is not None:
            self.apply(mode, i, seq)

    def apply(self, mode, i, key):
        km = config.settings.keymaps[mode]
        if key is None:
            new, other = actions.reset(mode, km, i)
        else:
            try:
                new, other = actions.rebind(mode, km, i, key)
            except ValueError as e:
                self.app.error(tr("Conflicts with “{name}”").format(
                    name=actions.label(mode, e.args[0])))
                return
        config.settings.keymaps[mode] = new
        try:
            config.save_keymaps()
        except OSError as e:
            self.app.error(tr("Failed: {error}").format(error=e.strerror))
            return
        msg = tr("Saved to the configuration file")
        if other is not None:
            msg += " — " + tr("swapped with “{name}”").format(name=actions.label(mode, other))
        self.app.info(msg)

    def mouse(self, x, y, kind):
        i = self.top + y - 1
        if kind in ("right", "back"):
            self.app.close_results()
        elif kind in ("click", "double", "drag") and 1 <= y and 0 <= i < len(self.rows):
            self.sel = i
            if kind == "double":
                self.handle(10)

    def draw(self, scr, h, w):
        th = h - 4
        n = len(self.rows)
        if self.sel < self.top:
            self.top = self.sel
        elif self.sel >= self.top + th:
            self.top = self.sel - th + 1
        put(scr, 0, 0, " " * w, A["title"])
        put(scr, 0, 0, (" nanger │ " + tr("Keyboard shortcuts"))[:w], A["title"])
        binds = {m: actions.bindings(m, config.settings.keymaps[m]) for m in actions.TABLES}
        defs = {m: actions.defaults(m) for m in actions.TABLES}
        for r in range(th):
            i = self.top + r
            if i >= n:
                break
            mode, a = self.rows[i]
            head = ""
            if a == 0:
                head = tr("File manager") if mode == "browser" else tr("Editor")
            b, d = binds[mode][a], defs[mode][a]
            text = " %-28s %-14s" % (actions.label(mode, a)[:28], seq_label(b))
            if b != d:
                text += "  (%s: %s)" % (tr("default"), seq_label(d))
            attr = curses.A_REVERSE if i == self.sel else (curses.A_BOLD if b != d else 0)
            tag = ("[%s] " % head) if head else "      "
            put(scr, 1 + r, 0, (tag + text)[:w].ljust(w), attr)
        draw_help(scr, h - 1, [("Enter", tr("Change")), ("Del", tr("Reset")),
                               ("↑↓", tr("Move")), ("q", tr("Back"))], w)
        return None

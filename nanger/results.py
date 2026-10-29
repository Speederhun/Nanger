"""A generic scrollable list view: search results, open files, bookmarks."""
import curses

from .i18n import tr
from .keys import BACKSPACE, C, ENTER, ESC
from .term import A, draw_help, put


class Results:
    """items = [(display text, payload)]; on_select(payload) runs when Enter is pressed."""

    def __init__(self, app, title, items, on_select, note=""):
        self.app = app
        self.title = title
        self.items = items
        self.on_select = on_select
        self.note = note
        self.sel = 0
        self.top = 0

    def handle(self, k):
        n = len(self.items)
        page = max(1, self.app.text_height() - 1)
        if k in ("q", ESC, C("q")) or k in BACKSPACE:
            self.app.close_results()
        elif k in (curses.KEY_UP, "k"):
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
        elif k in ENTER or k in (curses.KEY_RIGHT, "l"):
            if self.items:
                self.on_select(self.items[self.sel][1])

    def draw(self, scr, h, w):
        th = h - 4
        n = len(self.items)
        if self.sel < self.top:
            self.top = self.sel
        elif self.sel >= self.top + th:
            self.top = self.sel - th + 1
        put(scr, 0, 0, " " * w, A["title"])
        put(scr, 0, 0, (" nanger │ %s  (%d)%s" % (self.title, n, "  " + self.note if self.note else ""))[:w],
            A["title"])
        if not self.items:
            put(scr, 1, 1, tr("(nothing found)"), A["ln"])
        for r in range(th):
            i = self.top + r
            if i >= n:
                break
            text = self.items[i][0]
            attr = curses.A_REVERSE if i == self.sel else 0
            put(scr, 1 + r, 0, text[:w].ljust(w), attr)
        draw_help(scr, h - 1, [("Enter", tr("Open")), ("↑↓", tr("Move")), ("q", tr("Back"))], w)
        return None

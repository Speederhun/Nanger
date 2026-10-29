"""Side-by-side file comparison."""
import curses
import difflib

from .i18n import tr
from .keys import BACKSPACE, C, ENTER, ESC
from .term import A, clean, put


def build_rows(left, right):
    """Aligned rows: (left_no, left_text, right_no, right_text, kind); kind is '=', '~', '-' or '+'."""
    rows = []
    sm = difflib.SequenceMatcher(None, left, right, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                rows.append((i1 + k + 1, left[i1 + k], j1 + k + 1, right[j1 + k], "="))
            continue
        n = max(i2 - i1, j2 - j1)
        for k in range(n):
            li = i1 + k if i1 + k < i2 else None
            rj = j1 + k if j1 + k < j2 else None
            kind = "~" if li is not None and rj is not None else ("-" if li is not None else "+")
            rows.append((li + 1 if li is not None else None, left[li] if li is not None else "",
                         rj + 1 if rj is not None else None, right[rj] if rj is not None else "",
                         kind))
    return rows


def change_starts(rows):
    out = []
    for i, r in enumerate(rows):
        if r[4] != "=" and (i == 0 or rows[i - 1][4] == "="):
            out.append(i)
    return out


class DiffView:
    def __init__(self, app, ltitle, left, rtitle, right):
        self.app, self.ltitle, self.rtitle = app, ltitle, rtitle
        self.rows = build_rows(left, right)
        self.starts = change_starts(self.rows)
        self.top = 0
        self.h = 20
        if self.starts:
            self.top = max(0, self.starts[0] - 2)

    def jump(self, d):
        if not self.starts:
            return
        here = self.top + 2
        if d > 0:
            nxt = [s for s in self.starts if s > here]
            self.top = max(0, (nxt[0] if nxt else self.starts[0]) - 2)
        else:
            prv = [s for s in self.starts if s < here]
            self.top = max(0, (prv[-1] if prv else self.starts[-1]) - 2)

    def scroll(self, d):
        self.top = max(0, min(max(0, len(self.rows) - 1), self.top + d))

    def handle(self, k):
        page = max(1, self.h - 1)
        if k in ("q", ESC, C("q")) or k in BACKSPACE or k in ENTER:
            self.app.close_results()
        elif k in ("j", curses.KEY_DOWN):
            self.scroll(1)
        elif k in ("k", curses.KEY_UP):
            self.scroll(-1)
        elif k in (curses.KEY_NPAGE, " ", C("f")):
            self.scroll(page)
        elif k in (curses.KEY_PPAGE, C("b")):
            self.scroll(-page)
        elif k in ("n", "]", curses.KEY_RIGHT, "l"):
            self.jump(1)
        elif k in ("N", "p", "[", curses.KEY_LEFT, "h"):
            self.jump(-1)
        elif k in (curses.KEY_HOME, "g"):
            self.top = 0
        elif k in (curses.KEY_END, "G"):
            self.top = max(0, len(self.rows) - page)

    def mouse(self, x, y, kind):
        if kind in ("right", "back"):
            self.app.close_results()
        elif kind == "wheel_up":
            self.scroll(-3)
        elif kind == "wheel_down":
            self.scroll(3)

    def draw(self, scr, h, w):
        self.h = h - 3
        half = (w - 1) // 2
        num = max(3, len(str(len(self.rows))))
        tw = max(1, half - num - 2)
        total = len(self.starts)
        put(scr, 0, 0, " " * w, A["title"])
        put(scr, 0, 0, (" nanger │ %s │ %s" % (tr("compare"), tr("{n} changes").format(n=total)))[:w],
            A["title"])
        put(scr, 1, 0, (" " + self.ltitle)[:half].ljust(half), A["key"])
        put(scr, 1, half, "│", A["ln"])
        put(scr, 1, half + 1, (" " + self.rtitle)[:w - half - 1].ljust(w - half - 1), A["key"])
        attr = {"~": A["gmod"], "-": A["gdel"], "+": A["gadd"]}
        for r in range(self.h):
            i = self.top + r
            y = 2 + r
            if i >= len(self.rows):
                break
            ln, lt, rn, rt, kind = self.rows[i]
            a = attr.get(kind, 0)
            put(scr, y, 0, ("%*s " % (num, ln or "")), A["ln"])
            put(scr, y, num + 1, ("%s %s" % ("-" if kind in "-~" else " ",
                                              clean(lt.expandtabs(4))))[:tw + 1], a)
            put(scr, y, half, "│", A["ln"])
            put(scr, y, half + 1, ("%*s " % (num, rn or "")), A["ln"])
            put(scr, y, half + num + 2, ("%s %s" % ("+" if kind in "+~" else " ",
                                                    clean(rt.expandtabs(4))))[:max(0, w - half - num - 2)], a)
        from .term import draw_help
        draw_help(scr, h - 1, [("n/N", tr("Next/previous change")), ("j/k", tr("Scroll")),
                               ("q", tr("Back"))], w)
        return None

"""Full-screen image / PDF viewer (works without a graphical desktop, e.g. over SSH)."""
import curses
import os
import shutil

from .i18n import tr
from .keys import BACKSPACE, C, ENTER, ESC
from .media import (IMAGE_EXT, cached_render, can_images, draw_grid, pdf_pages, pdf_text)
from .term import A, clean, draw_help, put


def help_bar():
    return [("←/→", tr("Previous/next")), ("Home/End", tr("First/last")),
            ("t", tr("Text/image")), ("o", tr("External")), ("q", tr("Back"))]


class Viewer:
    def __init__(self, app, path, kind):
        self.app, self.path, self.kind = app, path, kind
        st = os.stat(path)
        self.page = 1
        self.pages = pdf_pages(path, st.st_mtime_ns) if kind == "pdf" else 1
        self.scroll = 0
        self.err = ""
        self.text_mode = kind == "pdf" and bool(shutil.which("pdftotext"))
        self.siblings = []
        if kind == "image":
            d = os.path.dirname(path)
            for n in app.browser.listdir(d) or []:
                f = os.path.join(d, n)
                if os.path.splitext(n.lower())[1] in IMAGE_EXT and os.path.isfile(f):
                    self.siblings.append(f)
            if path not in self.siblings:
                self.siblings.append(path)

    def step(self, d):
        if self.kind == "pdf":
            last = self.pages or 10 ** 6
            self.page = max(1, min(last, self.page + d))
            self.scroll = 0
        else:
            i = self.siblings.index(self.path)
            self.path = self.siblings[max(0, min(len(self.siblings) - 1, i + d))]

    def jump(self, end):
        if self.kind == "pdf":
            self.page = max(1, self.pages) if end else 1
            self.scroll = 0
        else:
            self.path = self.siblings[-1 if end else 0]

    def handle(self, k):
        app = self.app
        if k in ("q", ESC, C("q")) or k in ENTER:
            app.close_viewer()
        elif self.kind == "pdf" and self.text_mode and k in ("j", "k", curses.KEY_DOWN,
                                                              curses.KEY_UP):
            self.scroll = max(0, self.scroll + (1 if k in ("j", curses.KEY_DOWN) else -1))
        elif k in (curses.KEY_RIGHT, "l", " ", curses.KEY_NPAGE, curses.KEY_DOWN, "j"):
            self.step(1)
        elif k in (curses.KEY_LEFT, "h", curses.KEY_PPAGE, curses.KEY_UP, "k") or k in BACKSPACE:
            self.step(-1)
        elif k in (curses.KEY_HOME, "g"):
            self.jump(False)
        elif k in (curses.KEY_END, "G"):
            self.jump(True)
        elif k == "t" and self.kind == "pdf":
            if not shutil.which("pdftotext"):
                app.error(tr("Text mode needs pdftotext (poppler-utils)"))
            elif not can_images():
                app.error(tr("Image mode needs Pillow and a UTF-8 terminal"))
            else:
                self.text_mode = not self.text_mode
                self.scroll = 0
        elif k == "o":
            app.open_external(self.path)

    def mouse(self, x, y, kind):
        w = self.app.scr.getmaxyx()[1]
        if kind == "right":
            self.app.close_viewer()
        elif kind in ("click", "double") and y >= 1:
            self.step(1 if x >= w // 2 else -1)

    def draw(self, scr, h, w):
        th = h - 4
        name = os.path.basename(self.path)
        caption = ""
        put(scr, 0, 0, " " * w, A["title"])
        try:
            st = os.stat(self.path)
            if self.kind == "pdf" and self.text_mode:
                text = pdf_text(self.path, st.st_mtime_ns, self.page)
                lines = [clean(l.expandtabs(4)) for l in text.split("\n")]
                if not text.strip():
                    lines = ["", "  " + tr("(this page has no text — press t for the image)")]
                self.scroll = min(self.scroll, max(0, len(lines) - th))
                for r, line in enumerate(lines[self.scroll:self.scroll + th]):
                    put(scr, 1 + r, 1, line[:w - 2])
                caption = tr("PDF text  page {page}/{pages}").format(page=self.page,
                                                                      pages=self.pages or "?")
            else:
                res = cached_render(self.kind, self.path, self.page, w, th,
                                    lazy=self.app.input_pending())
                if res is None:
                    put(scr, 1 + th // 2, max(0, w // 2 - 1), "…", A["ln"])
                else:
                    grid, caption = res
                    y0 = 1 + max(0, (th - len(grid)) // 2)
                    x0 = max(0, (w - (len(grid[0]) if grid else 0)) // 2)
                    draw_grid(scr, y0, x0, grid)
                    if self.kind == "image" and len(self.siblings) > 1:
                        caption += "  (%d/%d)" % (self.siblings.index(self.path) + 1,
                                                  len(self.siblings))
            self.err = ""
        except Exception as e:  # noqa: BLE001 - the viewer must never crash the program
            self.err = str(e) or e.__class__.__name__
            msg = tr("[cannot display: {error}]").format(error=self.err)
            put(scr, 1 + th // 2, 2, msg[:w - 3], A["err"])
        left = " nanger │ %s │ %s" % (tr("viewer"), name)
        put(scr, 0, 0, left[:max(0, w - len(caption) - 3)], A["title"])
        put(scr, 0, max(0, w - len(caption) - 1), caption, A["title"])
        draw_help(scr, h - 1, help_bar(), w)
        return None

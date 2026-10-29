"""Low-level curses helpers: colors, safe drawing, tab-aware column math."""
import curses

from .config import settings

A = {}  # named text attributes, filled by init_colors()

_CURSES_COLORS = {"black": curses.COLOR_BLACK, "red": curses.COLOR_RED,
                  "green": curses.COLOR_GREEN, "yellow": curses.COLOR_YELLOW,
                  "blue": curses.COLOR_BLUE, "magenta": curses.COLOR_MAGENTA,
                  "cyan": curses.COLOR_CYAN, "white": curses.COLOR_WHITE, "default": -1}

# attribute name -> (config key, default color, extra attribute)
_SPEC = {
    "dir": ("directory", "blue", curses.A_BOLD),
    "exe": ("executable", "green", curses.A_BOLD),
    "link": ("link", "cyan", 0),
    "arc": ("archive", "magenta", curses.A_BOLD),
    "com": ("comment", "green", 0),
    "str": ("string", "yellow", 0),
    "num": ("number", "cyan", 0),
    "kw": ("keyword", "magenta", curses.A_BOLD),
    "err": ("error", "red", curses.A_BOLD),
    "tag": ("marked", "yellow", curses.A_BOLD),
    "gmod": (None, "yellow", 0),
    "gadd": (None, "green", 0),
    "gnew": (None, "magenta", 0),
    "gdel": (None, "red", 0),
    "gbad": (None, "red", curses.A_BOLD),
}
FIRST_FREE_PAIR = 30  # color pairs below this number belong to the UI


def init_colors():
    for name in _SPEC:
        A[name] = curses.A_NORMAL
    A["dir"] = curses.A_BOLD
    A["err"] = curses.A_BOLD
    A["tag"] = curses.A_BOLD
    A["title"] = curses.A_REVERSE
    A["key"] = curses.A_REVERSE
    A["match"] = curses.A_UNDERLINE
    A["ln"] = curses.A_DIM
    if not curses.has_colors():
        return
    try:
        curses.start_color()
    except curses.error:
        return
    bg = -1
    try:
        curses.use_default_colors()
    except curses.error:
        bg = curses.COLOR_BLACK
    pair = 1
    for name, (ckey, default, extra) in _SPEC.items():
        color = settings.colors.get(ckey, default) if ckey else default
        fg = _CURSES_COLORS[color]
        if fg == -1 and bg != -1:
            fg = curses.COLOR_WHITE
        try:
            curses.init_pair(pair, fg, bg)
            A[name] = curses.color_pair(pair) | extra
        except curses.error:
            pass
        pair += 1
    try:
        curses.init_pair(pair, curses.COLOR_BLACK, curses.COLOR_YELLOW)
        A["match"] = curses.color_pair(pair)
    except curses.error:
        pass


def put(scr, y, x, text, attr=0):
    h, w = scr.getmaxyx()
    if y < 0 or y >= h or x < 0 or x >= w:
        return
    text = text[: w - x]
    try:
        scr.addstr(y, x, text, attr)
    except curses.error:
        pass  # writing the bottom-right cell raises, but the text is drawn


def clean(s):
    return "".join(ch if ch >= " " or ch == "\t" else "·" for ch in s)


def disp_col(line, idx):
    tab = settings.tab_width
    col = 0
    for ch in line[:idx]:
        col += tab - col % tab if ch == "\t" else 1
    return col


def idx_from_col(line, target):
    tab = settings.tab_width
    col = 0
    for i, ch in enumerate(line):
        col += tab - col % tab if ch == "\t" else 1
        if col > target:
            return i
    return len(line)


HELP_REGIONS = []   # (row, x0, x1, key code) of the clickable help-bar entries


def draw_help(scr, row, items, w):
    from .keys import label_key
    x = 0
    for key, label in items:
        if x >= w - 1:
            break
        code = label_key(key)
        if code is not None:
            HELP_REGIONS.append((row, x, min(w, x + len(key) + len(label) + 3), code))
        put(scr, row, x, key, A["key"])
        x += len(key)
        put(scr, row, x, " " + label + "  ")
        x += len(label) + 3

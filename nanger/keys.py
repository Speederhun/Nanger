"""Key codes, escape-sequence decoding table and key-name parsing (for the config)."""
import curses
import re

ESC = 27


def C(ch):
    """Ctrl+<ch> key code."""
    return ord(ch) & 0x1F


ENTER = (10, 13, curses.KEY_ENTER)
BACKSPACE = (curses.KEY_BACKSPACE, 127, 8)
MOVES = (curses.KEY_UP, curses.KEY_DOWN, curses.KEY_LEFT, curses.KEY_RIGHT,
         curses.KEY_HOME, curses.KEY_END, curses.KEY_PPAGE, curses.KEY_NPAGE)
SHIFT_MOVES = {
    curses.KEY_SLEFT: curses.KEY_LEFT, curses.KEY_SRIGHT: curses.KEY_RIGHT,
    curses.KEY_SR: curses.KEY_UP, curses.KEY_SF: curses.KEY_DOWN,
    curses.KEY_SHOME: curses.KEY_HOME, curses.KEY_SEND: curses.KEY_END,
}

# Alt-key codes (terminals send them as ESC sequences, curses does not name them)
K_ALT_LEFT = 20001
K_ALT_RIGHT = 20002
K_ALT_DIGIT = 20010  # + 1..9

ESCAPES = {}
for _p in ("[", "O"):
    ESCAPES.update({_p + "A": curses.KEY_UP, _p + "B": curses.KEY_DOWN,
                    _p + "C": curses.KEY_RIGHT, _p + "D": curses.KEY_LEFT,
                    _p + "H": curses.KEY_HOME, _p + "F": curses.KEY_END})
ESCAPES.update({
    "[1;2A": curses.KEY_SR, "[1;2B": curses.KEY_SF, "[1;2C": curses.KEY_SRIGHT,
    "[1;2D": curses.KEY_SLEFT, "[1;2H": curses.KEY_SHOME, "[1;2F": curses.KEY_SEND,
    "[1;3C": K_ALT_RIGHT, "[1;3D": K_ALT_LEFT, "[Z": curses.KEY_BTAB,
    "[1~": curses.KEY_HOME, "[7~": curses.KEY_HOME, "[4~": curses.KEY_END,
    "[8~": curses.KEY_END, "[3~": curses.KEY_DC, "[5~": curses.KEY_PPAGE,
    "[6~": curses.KEY_NPAGE,
    "OP": curses.KEY_F1, "OQ": curses.KEY_F2, "OR": curses.KEY_F3, "OS": curses.KEY_F4,
    "[11~": curses.KEY_F1, "[12~": curses.KEY_F2, "[13~": curses.KEY_F3,
    "[14~": curses.KEY_F4, "[15~": curses.KEY_F5, "[17~": curses.KEY_F6,
    "[[A": curses.KEY_F1, "[[B": curses.KEY_F2, "[[C": curses.KEY_F3,
    "[[D": curses.KEY_F4, "[[E": curses.KEY_F5,
})
ESCAPES.update({"b": K_ALT_LEFT, "f": K_ALT_RIGHT})   # macOS Terminal/iTerm: Option+arrows
for _d in range(1, 10):
    ESCAPES[str(_d)] = K_ALT_DIGIT + _d  # Alt+1 .. Alt+9

_NAMES = {
    "enter": 10, "return": 10, "esc": ESC, "escape": ESC, "tab": 9, "space": " ",
    "backspace": 127, "delete": curses.KEY_DC, "del": curses.KEY_DC,
    "up": curses.KEY_UP, "down": curses.KEY_DOWN, "left": curses.KEY_LEFT,
    "right": curses.KEY_RIGHT, "home": curses.KEY_HOME, "end": curses.KEY_END,
    "pageup": curses.KEY_PPAGE, "pagedown": curses.KEY_NPAGE,
    "shift-tab": curses.KEY_BTAB, "alt-left": K_ALT_LEFT, "alt-right": K_ALT_RIGHT,
}


def parse_key(name):
    """'ctrl-s' -> 19, 'f5' -> KEY_F5, 'x' -> 'x', ... None if the name is unknown."""
    raw = name.strip()
    n = raw.lower()
    if not n:
        return None
    if n in _NAMES:
        return _NAMES[n]
    m = re.fullmatch(r"ctrl-([a-z])", n)
    if m:
        return C(m.group(1))
    m = re.fullmatch(r"f(\d{1,2})", n)
    if m and 1 <= int(m.group(1)) <= 12:
        return curses.KEY_F0 + int(m.group(1))
    m = re.fullmatch(r"alt-([1-9])", n)
    if m:
        return K_ALT_DIGIT + int(m.group(1))
    if len(raw) == 1:
        return raw
    return None


NOOP = -2   # "this key does nothing" (used when an action is moved to another key)


def key_name(k):
    """Inverse of parse_key, for the config file. None if the key cannot be named."""
    if k == NOOP:
        return "none"
    if isinstance(k, str):
        return k if len(k) == 1 and k != " " else ("space" if k == " " else None)
    for n in ("enter", "tab", "backspace", "delete", "up", "down", "left", "right", "home",
              "end", "pageup", "pagedown", "shift-tab", "alt-left", "alt-right"):
        if _NAMES[n] == k:
            return n
    if isinstance(k, int):
        if curses.KEY_F0 + 1 <= k <= curses.KEY_F0 + 12:
            return "f%d" % (k - curses.KEY_F0)
        if K_ALT_DIGIT + 1 <= k <= K_ALT_DIGIT + 9:
            return "alt-%d" % (k - K_ALT_DIGIT)
        if 1 <= k <= 26:
            return "ctrl-" + chr(96 + k)
    return None


def key_label(k):
    """Human readable: 'Ctrl+S', 'F4', 'Enter', 'x'."""
    if k is None:
        return "—"
    n = key_name(k)
    if n is None:
        return "?"
    if n.startswith("ctrl-"):
        return "Ctrl+" + n[5:].upper()
    if n.startswith("alt-"):
        return "Alt+" + n[4:].capitalize()
    return n.capitalize() if len(n) > 1 else n


_old_parse = parse_key


def parse_key(name):  # noqa: F811 - extends the table above with "none"
    if name.strip().lower() == "none":
        return NOOP
    return _old_parse(name)


K_MOUSE = 20100


def label_key(label):
    """Key code for a help-bar label ('^S', 'F4', 'Enter', 'n', ...) so it can be clicked."""
    if len(label) == 2 and label[0] == "^" and label[1].isalpha():
        return C(label[1].lower())
    m = re.fullmatch(r"F(\d{1,2})(/.*)?", label)
    if m and 1 <= int(m.group(1)) <= 12:
        return curses.KEY_F0 + int(m.group(1))
    special = {"Enter": 10, "←": curses.KEY_LEFT, "Del": curses.KEY_DC, "Tab": 9,
               "Space": " ", "Szóköz": " "}
    if label in special:
        return special[label]
    if len(label) == 1:
        return label
    return None

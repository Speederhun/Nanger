"""The remappable actions (what the key menu shows) and the key-binding logic."""
from .i18n import tr
from .keys import NOOP, key_name, parse_key

# (message id, default key name)
BROWSER = [
    ("Open", "enter"), ("Back", "left"), ("New file", "n"), ("New folder", "N"),
    ("Rename", "r"), ("Bulk rename", "R"), ("Delete", "D"), ("Mark", "space"),
    ("Copy", "y"), ("Cut", "x"), ("Paste", "p"), ("Find", "/"), ("Grep", "f"),
    ("Go to: ", "c"), ("Set bookmark", "m"), ("Jump to bookmark", "'"),
    ("Sort", "s"), ("Hidden files", "."), ("View", "v"), ("External", "o"),
    ("Open files", "b"), ("Shell", "S"), ("Command", "!"), ("Quit", "q"), ("Help", "?"),
]
EDITOR = [
    ("Save", "ctrl-s"), ("Save as: ", "ctrl-o"), ("Close", "ctrl-q"), ("Find", "ctrl-f"),
    ("Next", "ctrl-n"), ("Replace", "ctrl-r"), ("Go to line", "ctrl-g"), ("Undo", "ctrl-z"),
    ("Redo", "ctrl-y"), ("All", "ctrl-a"), ("Copy", "ctrl-c"), ("Cut", "ctrl-k"),
    ("Paste", "ctrl-v"), ("Duplicate", "ctrl-d"), ("Command", "ctrl-p"),
    ("Line numbers", "ctrl-l"), ("Files", "f4"), ("Help", "f1"),
]
TABLES = {"browser": BROWSER, "editor": EDITOR}


def label(mode, i):
    return tr(TABLES[mode][i][0]).strip().rstrip(":").strip()


def defaults(mode):
    return [parse_key(d) for _, d in TABLES[mode]]


def bindings(mode, keymap):
    """Current key of each action (None = unbound), derived from the key map."""
    out = []
    for d in defaults(mode):
        keys = [k for k, v in keymap.items() if v == d and k != NOOP]
        if keys:
            out.append(keys[0])
        elif keymap.get(d) is None:
            out.append(d)
        else:
            out.append(None)
    return out


def keymap_from(mode, binds):
    """Key map (pressed -> default key) that realises the given bindings."""
    km = {}
    ds = defaults(mode)
    for b, d in zip(binds, ds):
        if b is not None and b != d:
            km[b] = d
    for b, d in zip(binds, ds):
        if b != d and d not in km:
            km[d] = NOOP
    return km


def rebind(mode, keymap, index, key):
    """Give action `index` the key `key`; if another action has it they swap.
    Returns (new keymap, swapped action index or None)."""
    binds = bindings(mode, keymap)
    other = next((i for i, b in enumerate(binds) if b == key and i != index), None)
    old = binds[index]
    binds[index] = key
    if other is not None:
        binds[other] = old
    return keymap_from(mode, binds), other


def reset(mode, keymap, index):
    return rebind(mode, keymap, index, defaults(mode)[index])


def names(keymap):
    """{pressed: target} -> [(pressed name, target name)] for the config file."""
    out = []
    for k, v in keymap.items():
        a, b = key_name(k), key_name(v)
        if a and b:
            out.append((a, b))
    return sorted(out)

"""The remappable actions (what the key menu shows) and the key-binding logic.

A binding is a tuple of one or two keys (a "sequence", e.g. ("z", "h")); the key map is
{pressed sequence: default key of the action}."""
from .i18n import tr
from .keys import NOOP, parse_key, seq_name

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
# built-in extra shortcuts (not remappable, shadowed by the user's own bindings)
BUILTIN = {"browser": {("z", "h"): "."}, "editor": {}}


def label(mode, i):
    return tr(TABLES[mode][i][0]).strip().rstrip(":").strip()


def defaults(mode):
    return [(parse_key(d),) for _, d in TABLES[mode]]


def bindings(mode, keymap):
    """Current key sequence of each action (None = unbound), derived from the key map."""
    out = []
    for d in defaults(mode):
        seqs = [s for s, v in keymap.items() if v == d[0] and s != d and v != NOOP]
        if seqs:
            out.append(sorted(seqs, key=len)[0])
        elif keymap.get(d) is None:
            out.append(d)
        else:
            out.append(None)
    return out


def keymap_from(mode, binds):
    """Key map (pressed sequence -> default key) that realises the given bindings."""
    km = {}
    ds = defaults(mode)
    for b, d in zip(binds, ds):
        if b is not None and b != d:
            km[b] = d[0]
    for b, d in zip(binds, ds):
        if b != d and d not in km:
            km[d] = NOOP
    return km


def conflicts(mode, binds, index, seq):
    """Index of another action whose binding is a strict prefix of `seq` or starts with it
    (that would make one of them unreachable), else None."""
    for i, b in enumerate(binds):
        if i != index and b and b != seq and (b[:len(seq)] == seq or seq[:len(b)] == b):
            return i
    return None


def rebind(mode, keymap, index, seq):
    """Give action `index` the key sequence `seq`; if another action has exactly that
    sequence they swap. Returns (new keymap, swapped index or None).
    Raises ValueError(<index of the conflicting action>) on a prefix conflict."""
    binds = bindings(mode, keymap)
    other = next((i for i, b in enumerate(binds) if b == seq and i != index), None)
    if other is None:
        c = conflicts(mode, binds, index, seq)
        if c is not None:
            raise ValueError(c)
    old = binds[index]
    binds[index] = seq
    if other is not None:
        binds[other] = old
    return keymap_from(mode, binds), other


def reset(mode, keymap, index):
    return rebind(mode, keymap, index, defaults(mode)[index])


def names(keymap):
    """{pressed sequence: target} -> [(pressed name, target name)] for the config file."""
    from .keys import key_name
    out = []
    for seq, v in keymap.items():
        a, b = seq_name(seq), key_name(v)
        if a and b:
            out.append((a, b))
    return sorted(out)

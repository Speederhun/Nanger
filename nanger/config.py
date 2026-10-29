"""User settings: ~/.config/nanger/config.ini (see `nanger --init-config`)."""
import configparser
import os

from .keys import parse_key

COLOR_NAMES = ("default", "black", "red", "green", "yellow", "blue", "magenta", "cyan", "white")
COLOR_KEYS = ("directory", "executable", "link", "comment", "string", "number", "keyword",
              "error", "marked")
SORT_MODES = ("name", "size", "date", "ext")

DEFAULT_TEXT = """\
# nanger configuration. Lines starting with # or ; are comments.
# Delete this file to go back to the defaults.

[general]
# user interface language: auto (from the locale), en or hu
language = auto
# width of a tab character
tab_width = 4
# show line numbers in the editor
line_numbers = yes
# show hidden files (names starting with a dot) in the file manager
show_hidden = no
# default sorting: name, size, date or ext
sort = name
# reverse the sort order (folders always stay on top)
sort_reverse = no
# mouse support (click, double-click, wheel); hold Shift to select text with the terminal
mouse = yes
# image previews: auto, kitty, iterm, sixel (real pixels) or blocks (coloured text cells)
graphics = auto
# show git status in the file manager and changed lines in the editor
git = yes

[colors]
# default black red green yellow blue magenta cyan white
directory = blue
executable = green
link = cyan
comment = green
string = yellow
number = cyan
keyword = magenta
error = red
marked = yellow

# Key remapping: "pressed key = key whose action it should trigger".
# Key names: a single character, ctrl-x, f1..f12, enter, esc, tab, backspace, delete,
# up, down, left, right, home, end, pageup, pagedown, space, alt-left, alt-right, alt-1..alt-9
[keys.browser]
# x = D

[keys.editor]
# ctrl-w = ctrl-q
"""


class Settings:
    def __init__(self):
        self.language = "auto"
        self.tab_width = 4
        self.line_numbers = True
        self.show_hidden = False
        self.sort = "name"
        self.sort_reverse = False
        self.git = True
        self.graphics = "auto"
        self.mouse = True
        self.colors = {}
        self.keymaps = {"browser": {}, "editor": {}}
        self.warnings = []


settings = Settings()


def config_dir():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "nanger")


def config_path():
    return os.path.join(config_dir(), "config.ini")


def data_dir():
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"),
                                                           ".local", "share")
    return os.path.join(base, "nanger")


def _bool(value):
    v = value.strip().lower()
    if v in ("1", "yes", "true", "on"):
        return True
    if v in ("0", "no", "false", "off"):
        return False
    raise ValueError(value)


def load(path=None):
    """Read the config file into `settings`; problems become warnings, never exceptions."""
    global settings
    s = Settings()
    settings.__dict__.update(s.__dict__)
    path = path or config_path()
    if not os.path.exists(path):
        return settings
    cp = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=None)
    cp.optionxform = str  # key names are case sensitive ("x" vs "X")
    try:
        with open(path, encoding="utf-8") as f:
            cp.read_file(f)
    except (OSError, UnicodeDecodeError, configparser.Error) as e:
        settings.warnings.append("config: %s" % e)
        return settings

    def warn(section, key, value):
        settings.warnings.append("config: [%s] %s = %s" % (section, key, value))

    for key, raw in cp.items("general") if cp.has_section("general") else []:
        try:
            if key == "language":
                if raw.strip().lower() not in ("auto", "en", "hu"):
                    raise ValueError(raw)
                settings.language = raw.strip().lower()
            elif key == "tab_width":
                n = int(raw)
                if not 1 <= n <= 16:
                    raise ValueError(raw)
                settings.tab_width = n
            elif key == "line_numbers":
                settings.line_numbers = _bool(raw)
            elif key == "show_hidden":
                settings.show_hidden = _bool(raw)
            elif key == "mouse":
                settings.mouse = _bool(raw)
            elif key == "graphics":
                if raw.strip().lower() not in ("auto", "kitty", "iterm", "sixel", "blocks"):
                    raise ValueError(raw)
                settings.graphics = raw.strip().lower()
            elif key == "git":
                settings.git = _bool(raw)
            elif key == "sort_reverse":
                settings.sort_reverse = _bool(raw)
            elif key == "sort":
                if raw.strip().lower() not in SORT_MODES:
                    raise ValueError(raw)
                settings.sort = raw.strip().lower()
            else:
                raise ValueError(raw)
        except ValueError:
            warn("general", key, raw)
    if cp.has_section("colors"):
        for key, raw in cp.items("colors"):
            if key in COLOR_KEYS and raw.strip().lower() in COLOR_NAMES:
                settings.colors[key] = raw.strip().lower()
            else:
                warn("colors", key, raw)
    for mode in ("browser", "editor"):
        section = "keys." + mode
        if not cp.has_section(section):
            continue
        for src, dst in cp.items(section):
            a, b = parse_key(src), parse_key(dst)
            if a is None or b is None:
                warn(section, src, dst)
            else:
                settings.keymaps[mode][a] = b
    return settings


def write_default(path=None):
    """Create the default config file if missing. Returns (path, created)."""
    path = path or config_path()
    if os.path.exists(path):
        return path, False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(DEFAULT_TEXT)
    return path, True


def save_keymaps(path=None):
    """Rewrite the [keys.browser] / [keys.editor] sections of the config file."""
    import re
    from .actions import names
    path = path or config_path()
    write_default(path)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    text = re.sub(r"(?ms)^\[keys\.(browser|editor)\][^\[]*", "", text).rstrip() + "\n"
    for mode in ("browser", "editor"):
        text += "\n[keys.%s]\n" % mode
        for a, b in names(settings.keymaps[mode]):
            text += "%s = %s\n" % (a, b)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)

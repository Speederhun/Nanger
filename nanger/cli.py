"""Command line entry point."""
import curses
import locale
import os
import sys

from . import __version__, config, i18n
from .i18n import tr
from .term import init_colors


def usage():
    return "\n".join([
        tr("nanger {version} — file manager and text editor (ranger + nano + vim)")
        .format(version=__version__),
        "",
        tr("Usage:"),
        "  nanger                  " + tr("file manager in the current folder"),
        "  nanger FOLDER           " + tr("file manager in the given folder"),
        "  nanger FILE             " + tr("open the file by its type (text: editor)"),
        "  nanger +N FILE          " + tr("open the text file at line N"),
        "",
        "  -h, --help              " + tr("this help"),
        "  -v, --version           " + tr("version"),
        "  --init-config           " + tr("create the default configuration file"),
        "  --config-path           " + tr("print the path of the configuration file"),
        "  --doctor                " + tr("check why previews or colours do not work"),
        "",
        tr("Inside the program F1 (editor) or ? (file manager) shows the keys."),
        tr("Language: NANGER_LANG=en|hu or 'language' in the configuration file."),
        ""])


def _utf8():
    return "utf" in (locale.getpreferredencoding(False) or "").lower()


def setup_locale():
    """Use the user's locale; if it is missing or not UTF-8 (a bare `LANG` on macOS or over
    SSH), fall back to a UTF-8 one so box drawing characters and previews work."""
    try:
        locale.setlocale(locale.LC_ALL, "")
    except locale.Error:  # e.g. LANG=hu_HU.UTF-8 but that locale is not generated
        pass
    if _utf8():
        return
    for name in ("en_US.UTF-8", "C.UTF-8", "UTF-8", "en_GB.UTF-8"):
        try:
            locale.setlocale(locale.LC_CTYPE, name)
        except locale.Error:
            continue
        if _utf8():
            return


def doctor():
    """`nanger --doctor`: everything that decides whether previews work."""
    import platform
    import shutil
    setup_locale()
    out = []
    out.append("nanger %s  python %s (%s)" % (__version__, platform.python_version(),
                                              sys.executable))
    out.append("platform: %s %s" % (sys.platform, platform.machine()))
    for k in ("TERM", "TERM_PROGRAM", "COLORTERM", "LANG", "LC_ALL", "TMUX", "SSH_CONNECTION",
              "NANGER_GRAPHICS", "NANGER_TRUECOLOR"):
        if os.environ.get(k):
            out.append("%s=%s" % (k, os.environ[k]))
    out.append("encoding: %s %s" % (locale.getpreferredencoding(False),
                                    "(ok)" if _utf8() else "(NOT UTF-8: previews are off)"))
    try:
        curses.setupterm()
        out.append("terminal colors: %s" % curses.tigetnum("colors"))
    except curses.error as e:
        out.append("terminal colors: unknown (%s)" % e)
    try:
        import PIL
        out.append("Pillow: %s (%s)" % (PIL.__version__, os.path.dirname(PIL.__file__)))
    except Exception as e:  # noqa: BLE001
        out.append("Pillow: MISSING (%s) -> no image/PDF previews. Install it for THIS python: "
                   "%s -m pip install pillow   (Homebrew: brew install pillow)"
                   % (e, sys.executable))
    for tool in ("pdftoppm", "pdftotext", "git", "7zz", "7z", "bsdtar", "open", "xdg-open"):
        out.append("%-9s %s" % (tool + ":", shutil.which(tool) or "-"))
    from . import media
    out.append("graphics protocol: %s" % (media.graphics_mode() or "none (coloured blocks)"))
    if sys.stdout.isatty():
        out.append("cell size in pixels: %dx%d" % media.cell_pixels())
    print("\n".join(out))
    return 0


MOUSE_ON = "\x1b[?1000h\x1b[?1002h\x1b[?1006h"
MOUSE_OFF = "\x1b[?1006l\x1b[?1002l\x1b[?1000l"


def mouse_enabled():
    return config.settings.mouse and os.environ.get("NANGER_MOUSE") != "0"


def mouse_on():
    if mouse_enabled():
        try:
            os.write(1, MOUSE_ON.encode())
        except OSError:
            pass


def mouse_off():
    try:
        os.write(1, MOUSE_OFF.encode())
    except OSError:
        pass


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    config.load()
    i18n.set_language(i18n.detect(config.settings.language))
    target, line = ".", None
    paths = []
    for a in args:
        if a in ("-h", "--help"):
            print(usage())
            return 0
        if a in ("-v", "--version"):
            print("nanger %s" % __version__)
            return 0
        if a == "--doctor":
            return doctor()
        if a == "--config-path":
            print(config.config_path())
            return 0
        if a == "--init-config":
            path, created = config.write_default()
            print((tr("Created: {path}") if created else tr("Already exists: {path}"))
                  .format(path=path))
            return 0
        if a.startswith("+") and a[1:].isdigit():
            line = int(a[1:])
        else:
            paths.append(a)
    if len(paths) > 1:
        print(tr("Give one folder or file at a time.") + "\n\n" + usage(), file=sys.stderr)
        return 2
    if paths:
        target = paths[0]
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print(tr("nanger: it must be run in a terminal"), file=sys.stderr)
        return 1
    setup_locale()
    os.environ.setdefault("ESCDELAY", "25")

    def run(scr):
        from .app import App
        curses.raw()
        curses.noecho()
        scr.keypad(True)
        init_colors()
        mouse_on()
        App(scr, target, line).run()

    try:
        curses.wrapper(run)
    finally:
        mouse_off()
    return 0

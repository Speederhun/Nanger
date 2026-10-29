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
        "",
        tr("Inside the program F1 (editor) or ? (file manager) shows the keys."),
        tr("Language: NANGER_LANG=en|hu or 'language' in the configuration file."),
        ""])


def setup_locale():
    try:
        locale.setlocale(locale.LC_ALL, "")
    except locale.Error:  # e.g. LANG=hu_HU.UTF-8 but that locale is not generated
        for name in ("C.UTF-8", "en_US.UTF-8"):
            try:
                locale.setlocale(locale.LC_ALL, name)
                return
            except locale.Error:
                continue


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
        App(scr, target, line).run()

    curses.wrapper(run)
    return 0

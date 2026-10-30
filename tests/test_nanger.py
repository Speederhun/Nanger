"""Automata tesztek: a nanger-t egy valódi pszeudo-terminálban indítjuk, billentyűket
küldünk neki, és a (pyte-tal emulált) képernyőt meg a lemezen lévő fájlokat nézzük.

Futtatás:  pip install -r requirements-dev.txt && pytest -q
"""
import importlib.machinery
import importlib.util
import os
import shutil
import signal
import stat
import tarfile
import time
import zipfile
from pathlib import Path

import pytest

pexpect = pytest.importorskip("pexpect")
pyte = pytest.importorskip("pyte")

ROOT = Path(__file__).resolve().parent.parent
NANGER = os.environ.get("NANGER_BIN") or str(ROOT / "bin" / "nanger")

CTRL = lambda c: chr(ord(c) & 0x1F)  # noqa: E731
UP, DOWN, RIGHT, LEFT = "\x1b[A", "\x1b[B", "\x1b[C", "\x1b[D"
END, F1, F5, F6 = "\x1b[F", "\x1bOP", "\x1b[15~", "\x1b[17~"
SHIFT_DOWN = "\x1b[1;2B"
ROWS, COLS = 30, 100


def load_module():
    import sys
    sys.path.insert(0, str(ROOT))
    from nanger import media, fsops

    class M:
        pass
    m = M()
    for mod in (media, fsops):
        for k in dir(mod):
            setattr(m, k, getattr(mod, k))
    return m


class Term:
    def __init__(self, arg, cwd, env):
        self.scr = pyte.Screen(COLS, ROWS)
        self.stream = pyte.ByteStream(self.scr)
        self.p = pexpect.spawn(NANGER, [str(arg)], cwd=str(cwd), dimensions=(ROWS, COLS),
                               env=env)
        self.pump(1.0)

    def pump(self, t=0.4):
        end = time.time() + t
        while time.time() < end:
            try:
                self.stream.feed(self.p.read_nonblocking(65536, timeout=0.1))
            except pexpect.TIMEOUT:
                pass
            except pexpect.EOF:
                break

    def send(self, s, t=0.3):
        for part in [s] if s.startswith("\x1b") else s:
            self.p.send(part)
            time.sleep(0.01)
        self.pump(t)

    def text(self):
        return "\n".join(self.scr.display)

    def row(self, y):
        return self.scr.display[y]

    def alive(self):
        return self.p.isalive()

    def wait_exit(self, t=2.0):
        end = time.time() + t
        while time.time() < end and self.p.isalive():
            self.pump(0.1)
        return not self.p.isalive()


@pytest.fixture
def work(tmp_path):
    w = tmp_path / "work"
    w.mkdir()
    return w


@pytest.fixture
def env(tmp_path):
    e = {k: v for k, v in os.environ.items() if k not in ("DISPLAY", "WAYLAND_DISPLAY")}
    home = tmp_path / "home"
    home.mkdir()
    e.update(TERM="xterm-256color", LANG="C.UTF-8", LC_ALL="C.UTF-8", HOME=str(home),
             XDG_DATA_HOME=str(tmp_path / "xdg"), XDG_CONFIG_HOME=str(tmp_path / "cfg"),
             NANGER_LANG="hu")
    return e


@pytest.fixture
def spawn(work, env):
    terms = []

    def make(arg=".", extra_env=None):
        e = dict(env)
        e.update(extra_env or {})
        t = Term(arg, work, e)
        terms.append(t)
        return t

    yield make
    for t in terms:
        if t.p.isalive():
            t.p.terminate(force=True)


# ------------------------------------------------------------------ egységtesztek

def test_color_quantizer():
    m = load_module()
    assert m.rgb_to_256(0, 0, 0) == 16
    assert m.rgb_to_256(255, 0, 0) == 196
    assert m.rgb_to_256(255, 255, 255) == 231
    assert m.rgb_to_256(128, 128, 128) == 244  # a szürkeskála közelebb van, mint a kocka


def test_file_kind(work):
    m = load_module()
    (work / "a.txt").write_text("szia\n")
    (work / "b.bin").write_bytes(b"\x00\x01\x02")
    (work / "c.PDF").write_bytes(b"%PDF-1.4")
    (work / "d.png").write_bytes(b"x")
    (work / "e.tar.gz").write_bytes(b"x")
    (work / "f.docx").write_bytes(b"x")
    (work / "g").mkdir()
    (work / "script").write_text("#!/bin/sh\necho hi\n")
    kinds = {p.name: m.file_kind(str(p)) for p in work.iterdir()}
    assert kinds == {"a.txt": "text", "b.bin": "binary", "c.PDF": "pdf", "d.png": "image",
                     "e.tar.gz": "archive", "f.docx": "external", "g": "dir", "script": "text"}


@pytest.mark.skipif(__import__('sys').platform == 'darwin', reason="freedesktop trash is not used on macOS")
def test_move_to_trash_follows_freedesktop_spec(work, tmp_path, monkeypatch):
    m = load_module()
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    for _ in range(2):  # kétszer ugyanaz a név: nem írhatja felül az elsőt
        f = work / "régi fájl.txt"
        f.write_text("tartalom")
        m.move_to_trash(str(f))
        assert not f.exists()
    trash = tmp_path / "xdg" / "Trash"
    assert len(list((trash / "files").iterdir())) == 2
    info = sorted((trash / "info").iterdir())
    assert len(info) == 2
    body = info[0].read_text()
    assert body.startswith("[Trash Info]\nPath=") and "%C3%A9" in body and "DeletionDate=" in body


def test_archive_lines(work):
    m = load_module()
    z = work / "x.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("egy.txt", "a" * 2048)
        zf.writestr("mappa/ketto.txt", "b")
    lines, more = m.archive_lines(str(z), 10)
    assert not more and "egy.txt" in lines[0][0] and "2.0K" in lines[0][0]
    lines, more = m.archive_lines(str(z), 1)
    assert more and len(lines) == 1


# ------------------------------------------------------------------ szerkesztő

def test_type_save_and_quit(spawn, work):
    t = spawn("uj.txt")
    t.send("Szia világ, ékezet: őű")
    t.send(CTRL("s"))
    t.send(CTRL("q"))
    assert (work / "uj.txt").read_text() == "Szia világ, ékezet: őű\n"
    assert t.wait_exit()


def test_regex_replace_global_delete_and_undo(spawn, work):
    (work / "b.txt").write_text("alma\nkörte\nalma\nbanán\n")
    t = spawn("b.txt")
    t.send(CTRL("p"))
    t.send("%s/alma/eper/g\r")
    t.send(CTRL("p"))
    t.send("g/banán/d\r")
    t.send(CTRL("s"))
    assert (work / "b.txt").read_text() == "eper\nkörte\neper\n"
    assert "^S Mentés" in t.text()
    t.send(CTRL("z"))
    t.send(CTRL("s"))
    assert (work / "b.txt").read_text() == "eper\nkörte\neper\nbanán\n"


def test_macro_record_and_replay(spawn, work):
    (work / "m.txt").write_text("a\nb\nc\n")
    t = spawn("m.txt")
    for key in (F5, END, ";", DOWN, F5, F6, F6):
        t.send(key)
    t.send(CTRL("s"))
    assert (work / "m.txt").read_text() == "a;\nb;\nc;\n"


def test_cut_paste_lines_and_autoindent(spawn, work):
    (work / "c.py").write_text("x\ny\n")
    t = spawn("c.py")
    t.send(CTRL("k"))
    t.send(DOWN)
    t.send(CTRL("v"))
    t.send(END)
    t.send("\rif 1:\rpass")
    t.send(CTRL("s"))
    assert (work / "c.py").read_text() == "x\ny\nif 1:\n    pass\n"


def test_discard_prompt(spawn, work):
    (work / "c.txt").write_text("x\n")
    t = spawn("c.txt")
    t.send("z")
    t.send(CTRL("q"))
    t.send("n")
    assert t.wait_exit()
    assert (work / "c.txt").read_text() == "x\n"


def test_shell_filter_and_replace_dialog_and_help(spawn, work):
    (work / "s.txt").write_text("3\n1\n2\nvége\n")
    t = spawn("s.txt")
    for _ in range(3):
        t.send(SHIFT_DOWN)
    t.send(CTRL("p"))
    t.send("!sort -n\r")
    t.send(CTRL("r"))
    t.send("vége\r")
    t.send("VÉGE\r")
    t.send(CTRL("s"))
    assert (work / "s.txt").read_text() == "1\n2\n3\nVÉGE\n"
    t.send(F1)
    assert "MAKRÓK" in t.text()


def test_latin2_and_crlf_roundtrip(spawn, work):
    (work / "l2.txt").write_bytes("árvíztűrő\r\n".encode("iso-8859-2"))
    t = spawn("l2.txt")
    assert "árvíztűrő" in t.text()
    t.send(END)
    t.send("!")
    t.send(CTRL("s"))
    assert (work / "l2.txt").read_bytes() == "árvíztűrő!\r\n".encode("iso-8859-2")


# ------------------------------------------------------------------ fájlkezelő

def test_browser_lists_and_previews_text(spawn, work):
    (work / "a.py").write_text("def f():\n    return 1\n")
    (work / "sub").mkdir()
    t = spawn(".")
    s = t.text()
    assert "sub" in s and "a.py" in s
    t.send("j")
    assert "def f():" in t.text()


def test_mkdir_newfile_rename_copy(spawn, work):
    t = spawn(".")
    t.send("N")
    t.send("mappa\r")
    assert (work / "mappa").is_dir()
    t.send("n")
    t.send("jegyzet.md\r")
    t.send("hello")
    t.send(CTRL("s"))
    t.send(CTRL("q"))
    assert (work / "jegyzet.md").read_text() == "hello\n"
    t.send("r")
    t.send(CTRL("u"))
    t.send("j2.md\r")
    assert (work / "j2.md").exists() and not (work / "jegyzet.md").exists()
    t.send("y")       # másolás
    t.send("g")
    t.send("\r")      # be a "mappa" nevű mappába (az első elem)
    t.send("p")
    assert (work / "mappa" / "j2.md").exists() and (work / "j2.md").exists()


@pytest.mark.skipif(__import__('sys').platform == 'darwin', reason="freedesktop trash is not used on macOS")
def test_delete_goes_to_trash(spawn, work, tmp_path):
    (work / "torlendo.txt").write_text("fontos")
    t = spawn(".")
    t.send("D")
    assert "kukába" in t.text()
    t.send("t")
    assert not (work / "torlendo.txt").exists()
    trashed = list((tmp_path / "xdg" / "Trash" / "files").iterdir())
    assert [p.name for p in trashed] == ["torlendo.txt"]
    assert trashed[0].read_text() == "fontos"


@pytest.mark.skipif(__import__('sys').platform == 'darwin', reason="freedesktop trash is not used on macOS")
def test_permanent_delete_needs_two_confirmations(spawn, work, tmp_path):
    (work / "a.txt").write_text("x")
    t = spawn(".")
    t.send("D")
    t.send("d")
    t.send("n")  # a második megerősítésnél nemet mondunk
    assert (work / "a.txt").exists()
    t.send("D")
    t.send("d")
    t.send("i")
    assert not (work / "a.txt").exists()
    assert not (tmp_path / "xdg" / "Trash").exists()


def test_sort_cycle(spawn, work):
    (work / "a_small.txt").write_text("x" * 10)
    (work / "b_big.txt").write_text("x" * 5000)
    (work / "c_mid.txt").write_text("x" * 500)
    t = spawn(".")

    def order():
        rows = {}
        for y in range(1, 20):
            cell = t.row(y)[17:57]
            for n in ("a_small", "b_big", "c_mid"):
                if n in cell:
                    rows[n] = y
        return sorted(rows, key=rows.get)

    assert order() == ["a_small", "b_big", "c_mid"]
    t.send("s")
    t.send("s")                                  # méret szerint: a legnagyobb elöl
    assert "méret" in t.text()
    assert order() == ["b_big", "c_mid", "a_small"]
    t.send("s")
    t.send("s")                                  # ugyanaz újra: fordított
    assert order() == ["a_small", "c_mid", "b_big"]
    t.send("s")
    t.send("n")                                  # vissza név szerint
    assert order() == ["a_small", "b_big", "c_mid"]


def test_sort_by_date_reverse_and_folders_on_top(spawn, work):
    import os
    for i, n in enumerate(("a.txt", "b.txt", "c.txt")):
        (work / n).write_text("x")
        os.utime(work / n, (1_000_000 + i * 100, 1_000_000 + i * 100))
    (work / "zmappa").mkdir()
    t = spawn(".")
    t.send("s")
    t.send("d")                                  # dátum: legújabb elöl
    rows = {n: y for y in range(1, 10) for n in ("a.txt", "b.txt", "c.txt", "zmappa")
            if n in t.row(y)[17:57]}
    assert rows["zmappa"] < rows["c.txt"] < rows["b.txt"] < rows["a.txt"]
    t.send("s")
    t.send("r")                                  # fordítva: a legrégebbi elöl, a mappa így is fent
    rows = {n: y for y in range(1, 10) for n in ("a.txt", "b.txt", "c.txt", "zmappa")
            if n in t.row(y)[17:57]}
    assert rows["zmappa"] < rows["a.txt"] < rows["b.txt"] < rows["c.txt"]


def test_macos_helpers(work, tmp_path, monkeypatch):
    import sys
    sys.path.insert(0, str(ROOT))
    from nanger import fsops, media
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("HOME", str(tmp_path / "mac"))
    assert media.opener() == "open"
    for _ in range(2):
        f = work / "régi.txt"
        f.write_text("x")
        fsops.trash(str(f))
        assert not f.exists()
    names = sorted(p.name for p in (tmp_path / "mac" / ".Trash").iterdir())
    assert names == ["régi 2.txt", "régi.txt"]


# ------------------------------------------------------------------ előnézetek

def cell_rgb(cell):
    fg = cell.fg
    assert len(fg) == 6, f"256 színű (hexa) szín kellene, ez: {fg!r}"
    return tuple(int(fg[i:i + 2], 16) for i in (0, 2, 4))


def preview_cells(t, y0=1, y1=26, x0=58):
    return [t.scr.buffer[y][x] for y in range(y0, y1) for x in range(x0, COLS)
            if t.scr.buffer[y][x].data == "▀"]


@pytest.fixture
def pil():
    return pytest.importorskip("PIL.Image")


def make_png(path, left=(220, 30, 30), right=(30, 30, 220), size=(200, 100)):
    from PIL import Image
    im = Image.new("RGB", size, right)
    im.paste(Image.new("RGB", (size[0] // 2, size[1]), left), (0, 0))
    im.save(path)


def test_image_preview_shows_real_colors(spawn, work, pil):
    make_png(work / "kep.png")
    t = spawn(".")
    cells = preview_cells(t)
    assert len(cells) > 100
    xs = [x for x in range(58, COLS) if t.scr.buffer[5][x].data == "▀"]
    r, g, b = cell_rgb(t.scr.buffer[5][xs[0]])    # bal oldal: piros
    assert r > 150 and b < 100
    r, g, b = cell_rgb(t.scr.buffer[5][xs[-1]])   # jobb oldal: kék
    assert b > 150 and r < 100
    assert "PNG" in t.text() and "200×100" in t.text()


def test_broken_image_does_not_crash(spawn, work, pil):
    (work / "rossz.png").write_bytes(b"ez nem kep")
    t = spawn(".")
    assert "nem jeleníthető meg" in t.text()
    assert t.alive()
    t.send("q")
    assert t.wait_exit()


def test_image_viewer_without_gui_walks_siblings(spawn, work, pil):
    make_png(work / "a.png")
    make_png(work / "b.png", left=(0, 200, 0))
    t = spawn(".")
    t.send("\r")  # Enter, nincs DISPLAY → beépített nézegető
    assert "nézegető │ a.png" in t.row(0) and "(1/2)" in t.row(0)
    t.send(RIGHT)
    assert "b.png" in t.row(0) and "(2/2)" in t.row(0)
    t.send("q")
    assert "Enter Megnyit" in t.text()  # vissza a fájlkezelőben
    assert t.row(0).startswith(" nanger │ ") and "nézegető" not in t.row(0)


def make_text_pdf(path, pages):
    n = len(pages)
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(n))
    objs = ["<< /Type /Catalog /Pages 2 0 R >>",
            f"<< /Type /Pages /Kids [{kids}] /Count {n} >>",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    for i, text in enumerate(pages):
        content = f"BT /F1 24 Tf 72 700 Td ({text}) Tj ET"
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                    f"/Contents {5 + 2 * i} 0 R /Resources << /Font << /F1 3 0 R >> >> >>")
        objs.append(f"<< /Length {len(content)} >>\nstream\n{content}\nendstream")
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{off:010d} 00000 n \n".encode() for off in offsets)
    out += (f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
            .encode())
    Path(path).write_bytes(out)


needs_poppler = pytest.mark.skipif(not (shutil.which("pdftoppm") and shutil.which("pdftotext")),
                                   reason="poppler-utils nincs telepítve")


@needs_poppler
def test_pdf_preview_is_rendered(spawn, work, pil):
    make_text_pdf(work / "doc.pdf", ["Elso oldal"])
    t = spawn(".")
    assert len(preview_cells(t)) > 100
    assert "PDF" in t.text() and "1/1 oldal" in t.text()


@needs_poppler
def test_pdf_viewer_text_and_image_modes_and_pages(spawn, work, pil):
    make_text_pdf(work / "doc.pdf", ["Elso oldal szovege", "Masodik oldal szovege"])
    t = spawn(".")
    t.send("\r", 1.0)
    assert "Elso oldal szovege" in t.text() and "1/2 oldal" in t.row(0)
    t.send(RIGHT, 1.0)
    assert "Masodik oldal szovege" in t.text() and "2/2 oldal" in t.row(0)
    t.send("t", 1.0)  # képes mód
    assert len([1 for y in range(1, 26) for x in range(COLS)
                if t.scr.buffer[y][x].data == "▀"]) > 100
    t.send("t", 0.5)
    assert "Masodik oldal szovege" in t.text()
    t.send("q")
    assert "doc.pdf" in t.text() and "Enter Megnyit" in t.text()


@needs_poppler
def test_pdf_opened_directly_from_command_line(spawn, work, pil):
    make_text_pdf(work / "doc.pdf", ["Parancssorbol"])
    t = spawn("doc.pdf")
    t.pump(1.0)
    assert "Parancssorbol" in t.text()
    t.send("q")
    assert t.wait_exit()


def fake_xdg_open(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    out = tmp_path / "xdg-open.log"
    script = bin_dir / "xdg-open"
    script.write_text(f'#!/bin/sh\necho "$@" >> "{out}"\n')
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return bin_dir, out


def test_gui_session_opens_images_and_documents_externally(spawn, work, tmp_path, pil):
    bin_dir, log = fake_xdg_open(tmp_path)
    make_png(work / "a.png")
    (work / "b.docx").write_bytes(b"PK")
    t = spawn(".", {"DISPLAY": ":99", "PATH": f"{bin_dir}:{os.environ['PATH']}"})
    t.send("\r")
    t.send("j")
    t.send("\r")
    time.sleep(0.3)
    lines = log.read_text().split()
    assert [Path(x).name for x in lines] == ["a.png", "b.docx"]
    assert "nézegető" not in t.row(0)


def test_gui_session_v_key_forces_builtin_viewer(spawn, work, tmp_path, pil):
    bin_dir, log = fake_xdg_open(tmp_path)
    make_png(work / "a.png")
    t = spawn(".", {"DISPLAY": ":99", "PATH": f"{bin_dir}:{os.environ['PATH']}"})
    t.send("v")
    assert "nézegető │ a.png" in t.row(0)
    assert not log.exists()


def test_no_gui_document_gives_clear_error(spawn, work):
    (work / "b.docx").write_bytes(b"PK")
    t = spawn(".")
    t.send("\r")
    assert "Nincs grafikus felület" in t.text()
    assert t.alive()


def test_archive_preview_and_listing_without_gui(spawn, work):
    with zipfile.ZipFile(work / "x.zip", "w") as z:
        z.writestr("egy.txt", "a")
        z.writestr("mappa/ketto.txt", "b")
    t = spawn(".")
    t.pump(1.0)                                   # a lista a háttérben készül
    assert "egy.txt" in t.text() and "mappa/ketto.txt" in t.text()
    t.send("\r")  # grafikus felület nélkül: tartalomjegyzék lapozóban
    assert "x.zip" in t.text() and "mappa/ketto.txt" in t.text()
    t.send("x")
    assert "Enter Megnyit" in t.text()


def test_tar_gz_preview(spawn, work):
    (work / "in").mkdir()
    (work / "in" / "f.txt").write_text("x")
    with tarfile.open(work / "y.tar.gz", "w:gz") as t_:
        t_.add(work / "in" / "f.txt", arcname="in/f.txt")
    (work / "in" / "f.txt").unlink()
    (work / "in").rmdir()
    t = spawn(".")
    assert "in/f.txt" in t.text()


def test_binary_file_preview_and_edit_refusal(spawn, work):
    (work / "prog.bin").write_bytes(b"\x7fELF\x00\x00\x01")
    t = spawn(".")
    assert "bináris fájl" in t.text()
    t.send("e")
    assert "bináris" in t.row(ROWS - 3)


# ------------------------------------------------------------------ 1.2 újdonságok

def test_every_message_has_hungarian_translation():
    import ast
    import sys
    sys.path.insert(0, str(ROOT))
    from nanger.catalog_hu import HU
    ids = set()
    for f in (ROOT / "nanger").glob("*.py"):
        for n in ast.walk(ast.parse(f.read_text())):
            if (isinstance(n, ast.Call) and getattr(n.func, "id", "") == "tr" and n.args
                    and isinstance(n.args[0], ast.Constant)):
                ids.add(n.args[0].value)
    src = ast.parse((ROOT / "nanger" / "actions.py").read_text())
    for n in ast.walk(src):  # the key-menu labels live in tables, not in tr() calls
        if isinstance(n, ast.Tuple) and n.elts and isinstance(n.elts[0], ast.Constant) \
                and isinstance(n.elts[0].value, str) and len(n.elts[0].value) > 1 and len(n.elts) == 2:
            ids.add(n.elts[0].value)
    assert ids - set(HU) == set()
    for k, v in HU.items():  # a {mezők} egyezzenek
        import re
        assert sorted(re.findall(r"\{\w+\}", k)) == sorted(re.findall(r"\{\w+\}", v)), k


def test_english_ui(spawn, work):
    (work / "a.txt").write_text("x\n")
    t = spawn(".", {"NANGER_LANG": "en"})
    assert "Enter Open" in t.text()
    t.send("\r")
    assert "^S Save" in t.text()


def test_cli_flags(work, env):
    import subprocess
    out = subprocess.run([NANGER, "--version"], capture_output=True, text=True, env=env)
    assert out.stdout.startswith("nanger 1.")
    out = subprocess.run([NANGER, "--init-config"], capture_output=True, text=True, env=env)
    cfg = Path(env["XDG_CONFIG_HOME"]) / "nanger" / "config.ini"
    assert cfg.exists() and "[colors]" in cfg.read_text()
    out = subprocess.run([NANGER, "--config-path"], capture_output=True, text=True, env=env)
    assert out.stdout.strip() == str(cfg)


def test_plus_line_opens_at_line(spawn, work):
    (work / "l.txt").write_text("".join(f"sor{i}\n" for i in range(1, 80)))
    t = Term.__new__(Term)
    t.scr = pyte.Screen(COLS, ROWS)
    t.stream = pyte.ByteStream(t.scr)
    e = dict(os.environ, TERM="xterm-256color", LANG="C.UTF-8", NANGER_LANG="hu")
    t.p = pexpect.spawn(NANGER, ["+60", "l.txt"], cwd=str(work), dimensions=(ROWS, COLS), env=e)
    t.pump()
    assert "sor60" in t.text()
    t.p.terminate(force=True)


def test_config_tab_width_and_key_remap(spawn, work, env):
    cfg = Path(env["XDG_CONFIG_HOME"]) / "nanger"
    cfg.mkdir(parents=True)
    (cfg / "config.ini").write_text("[general]\ntab_width = 2\n[keys.browser]\nx = D\n")
    (work / "a.txt").write_text("x")
    t = spawn(".")
    t.send("x")   # x -> D (törlés)
    assert "kukába" in t.text()
    t.send("n")


def test_git_status_in_browser_and_gutter(spawn, work):
    import subprocess
    if not shutil.which("git"):
        pytest.skip("nincs git")
    run = lambda *a: subprocess.run(a, cwd=work, check=True, capture_output=True)  # noqa: E731
    run("git", "init", "-q")
    run("git", "config", "user.email", "t@t")
    run("git", "config", "user.name", "t")
    (work / "a.txt").write_text("egy\nketto\nharom\n")
    run("git", "add", ".")
    run("git", "commit", "-qm", "x")
    (work / "a.txt").write_text("egy\nMODOSITVA\nharom\nnegy\n")
    (work / "uj.txt").write_text("uj\n")
    t = spawn(".")
    s = t.text()
    assert "M" in t.row(1) + t.row(2) and "?" in t.row(1) + t.row(2)
    t.send("\r")  # a.txt a lista elején van
    gut = "".join(t.row(y)[:6] for y in range(1, 8))
    assert "~" in gut and "+" in gut


def test_tabs_switch_and_disk_change(spawn, work):
    (work / "a.txt").write_text("alfa\n")
    (work / "b.txt").write_text("beta\n")
    t = spawn("a.txt")
    t.send(CTRL("e"))            # fájlkezelő
    t.send("j")
    t.send("\r")                 # b.txt megnyitása
    assert "beta" in t.text()
    assert "a.txt" in t.row(0) and "b.txt" in t.row(0)
    t.send("\x1b[1;3D")          # Alt+balra
    assert "alfa" in t.text()
    (work / "a.txt").write_text("kívülről\n")
    time.sleep(1.2)
    t.send(RIGHT)
    assert "kívülről" in t.text()


def test_grep_in_files_and_open_at_line(spawn, work):
    (work / "a.txt").write_text("x\ny\nkeresett szo\n")
    (work / "b.txt").write_text("semmi\n")
    t = spawn(".")
    t.send("f")
    t.send("keresett\r", 1.0)
    assert "a.txt" in t.text() and "keresett szo" in t.text()
    t.send("\r")
    assert "keresett szo" in t.text() and "^S" in t.text()


def test_bookmarks_persist(spawn, work, tmp_path):
    (work / "mappa").mkdir()
    t = spawn(".")
    t.send("\r")          # be a mappába
    t.send("m")
    t.send("a")
    t.send("~")
    t.send("'")
    t.send("a")
    assert "mappa" in t.row(0)
    marks = (tmp_path / "xdg" / "nanger" / "bookmarks.json").read_text()
    assert str(work / "mappa") in marks


def test_bulk_rename(spawn, work):
    for n in ("a1.txt", "a2.txt", "a3.txt"):
        (work / n).write_text("x")
    t = spawn(".")
    t.send("R", 0.8)
    t.send(CTRL("p"))
    t.send("%s/a/b/g\r")
    t.send(CTRL("s"))
    t.send(CTRL("q"))
    t.send("i")
    t.pump(0.8)
    assert sorted(p.name for p in work.iterdir()) == ["b1.txt", "b2.txt", "b3.txt"]


def test_truecolor_image_preview(spawn, work, pil):
    make_png(work / "kep.png", left=(201, 33, 47), right=(12, 99, 222))
    t = spawn(".", {"COLORTERM": "truecolor"})
    xs = [x for x in range(58, COLS) if t.scr.buffer[5][x].data == "▀"]
    assert t.scr.buffer[5][xs[0]].fg == "c9212f"      # (201, 33, 47) pontosan
    assert t.scr.buffer[5][xs[-1]].fg == "0c63de"


def test_photo_preview_is_dithered_not_streaky(spawn, work, pil):
    from PIL import Image
    im = Image.new("RGB", (400, 300))
    for y in range(300):                                  # lágy átmenet: égbolt
        for x in range(400):
            im.putpixel((x, y), (190 + x // 20, 215 + y // 30, 245))
    im.save(work / "ég.jpg")
    t = spawn(".")
    assert len(preview_cells(t)) > 100 and t.alive()


def test_docx_and_odt_text_preview(spawn, work):
    with zipfile.ZipFile(work / "level.docx", "w") as z:
        z.writestr("word/document.xml",
                   '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                   '<w:body><w:p><w:r><w:t>Tisztelt Uram!</w:t></w:r></w:p>'
                   '<w:p><w:r><w:t>Masodik bekezdes</w:t></w:r></w:p></w:body></w:document>')
    t = spawn(".")
    assert "Tisztelt Uram!" in t.text() and "Masodik bekezdes" in t.text()
    (work / "level.docx").rename(work / "x.docx")
    (work / "sub").mkdir()
    with zipfile.ZipFile(work / "sub" / "o.odt", "w") as z:
        z.writestr("content.xml",
                   '<o:d xmlns:o="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
                   'xmlns:t="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
                   '<t:p>ODT szoveg</t:p></o:d>')
    t2 = spawn("sub")
    assert "ODT szoveg" in t2.text()


def test_kitty_graphics_protocol_is_emitted(work, env, pil):
    make_png(work / "kep.png")
    e = dict(env, NANGER_GRAPHICS="kitty")
    log = work.parent / "raw.bin"
    with open(log, "wb") as f:
        p = pexpect.spawn(NANGER, ["."], cwd=str(work), dimensions=(ROWS, COLS), env=e)
        p.logfile_read = f
        time.sleep(1.5)
        try:
            p.read_nonblocking(65536, timeout=0.3)
        except Exception:  # noqa: BLE001
            pass
        p.send("q")
        time.sleep(0.4)
        p.terminate(force=True)
    raw = log.read_bytes()
    assert b"\x1b_Ga=T,f=100" in raw and b"iVBOR" in raw      # PNG, base64


def test_sixel_encoder_roundtrip_header(pil):
    import sys
    sys.path.insert(0, str(ROOT))
    from nanger.media import encode_sixel
    from PIL import Image
    s = encode_sixel(Image.new("RGB", (20, 13), (200, 10, 10)))
    assert s.startswith("\x1bP0;1;0q") and s.endswith("\x1b\\") and "#" in s


def test_key_menu_rebind_and_persist(spawn, work, env):
    (work / "a.txt").write_text("x")
    t = spawn(".")
    t.send("K")
    assert "Gyorsbillentyűk" in t.row(0)
    # "Törlés"-t keressük: lejjebb lépünk a 7. sorra (Open, Back, New file, New folder, Rename, Bulk, Delete)
    for _ in range(6):
        t.send("j")
    t.send("\r")
    t.send("X")                      # D helyett X törli a fájlt
    t.send("\r")                     # második billentyű nincs: Enter = kész
    assert "Elmentve" in t.text()
    cfg = (Path(env["XDG_CONFIG_HOME"]) / "nanger" / "config.ini").read_text()
    assert "X = D" in cfg and "D = none" in cfg
    t.send("q")
    t.send("X")
    assert "kukába" in t.text()
    t.send("n")
    t.send("D")                      # az eredeti billentyű már nem csinál semmit
    assert "kukába" not in t.row(ROWS - 3)


def test_keys_module_swap_and_reset():
    import curses
    import sys
    sys.path.insert(0, str(ROOT))
    from nanger import actions
    from nanger.keys import NOOP
    km, other = actions.rebind("browser", {}, 6, ("X",))        # Delete -> X
    assert km == {("X",): "D", ("D",): NOOP} and other is None
    km, other = actions.rebind("browser", km, 2, ("X",))        # New file -> X: swap
    assert other == 6 and actions.bindings("browser", km)[6] == ("n",)
    km, _ = actions.reset("browser", km, 2)
    km, _ = actions.reset("browser", km, 6)
    assert km == {}


def click(x, y, press="M"):
    return f"\x1b[<0;{x};{y}{press}"


def mouse_click(t, x, y):
    t.send(click(x, y, "M"), 0.2)
    t.send(click(x, y, "m"), 0.3)


def test_mouse_select_open_wheel_and_help_bar(spawn, work):
    for n in ("a.txt", "b.txt", "c.txt"):
        (work / n).write_text(n + " tartalom\n")
    t = spawn(".")
    mouse_click(t, 30, 3)                         # a 2. sor (b.txt) — 1. sor a címsor
    assert "2/3" in t.text()
    t.send("\x1b[<65;30;3M", 0.3)                 # görgő le
    assert "3/3" in t.text() or "2/3" not in t.text()
    for part in (click(30, 2, "M"), click(30, 2, "m"), click(30, 2, "M"), click(30, 2, "m")):
        t.send(part, 0.06)                        # dupla kattintás: gyors egymásutánban
    t.pump(0.6)
    assert "a.txt tartalom" in t.text() and "^S" in t.text()
    mouse_click(t, 8, 1 + 1)                      # szerkesztőben: kurzor a szövegre
    assert "1:" in t.row(0)
    # a súgósorban a "^Q Bezár" gombra kattintva bezár
    y = ROWS - 2
    x = t.row(y).index("^Q") + 1
    mouse_click(t, x, y + 1)
    assert "Enter Megnyit" in t.text()


def test_mouse_can_be_disabled(work, env):
    (work / "a.txt").write_text("x")
    log = work.parent / "raw2.bin"
    for flag, expect in (("0", False), ("1", True)):
        with open(log, "wb") as f:
            p = pexpect.spawn(NANGER, ["."], cwd=str(work), dimensions=(ROWS, COLS),
                              env=dict(env, NANGER_MOUSE=flag))
            p.logfile_read = f
            time.sleep(1.0)
            try:
                p.read_nonblocking(1 << 20, timeout=0.5)
            except Exception:  # noqa: BLE001
                pass
            p.terminate(force=True)
        assert (b"1000h" in log.read_bytes()) == expect


def test_zh_toggles_hidden_files(spawn, work):
    (work / ".titkos").write_text("x")
    (work / "latszik.txt").write_text("x")
    t = spawn(".")
    assert ".titkos" not in t.text()
    t.send("z")
    t.send("h")
    assert ".titkos" in t.text()
    t.send("z")
    t.send("h")
    assert ".titkos" not in t.text()


def test_two_key_binding_from_menu(spawn, work, env):
    (work / ".titkos").write_text("x")
    t = spawn(".")
    t.send("K")
    for _ in range(17):                 # "Hidden files" a 18. sor
        t.send("j")
    t.send("\r")
    t.send("g")
    t.send("i")                         # g + i
    assert "Elmentve" in t.text()
    cfg = (Path(env["XDG_CONFIG_HOME"]) / "nanger" / "config.ini").read_text()
    assert "g i = ." in cfg
    t.send("q")
    t.send("g")
    t.send("i")
    assert ".titkos" in t.text()


def test_archives_are_purple(spawn, work):
    with zipfile.ZipFile(work / "a.zip", "w") as z:
        z.writestr("x", "1")
    (work / "b.txt").write_text("x")
    t = spawn(".")
    row = next(y for y in range(1, 6) if "a.zip" in t.row(y))
    cell = t.scr.buffer[row][19]
    assert cell.fg in ("magenta", "ff00ff", "af00af", "800080") or cell.fg.startswith(("8", "a", "f")) \
        and cell.fg != "default", cell.fg
    row_b = next(y for y in range(1, 6) if "b.txt" in t.row(y))
    assert t.scr.buffer[row_b][19].fg != cell.fg


def test_wheel_down_scrolls_and_back_button_goes_back(spawn, work):
    for n in "abcde":
        (work / (n + ".txt")).write_text(n)
    (work / "sub").mkdir()
    (work / "sub" / "in.txt").write_text("x")
    t = spawn(".")
    t.send("\x1b[<65;30;3M", 0.3)
    assert "4/6" in t.text()            # 3 sor lefelé (a mappa az 1.)
    t.send("\x1b[<64;30;3M", 0.3)
    assert "1/6" in t.text()
    t.send("g")
    t.send("\r")                        # be a sub mappába
    assert "in.txt" in t.row(1)
    t.send("\x1b[<128;30;3M", 0.3)      # vissza gomb
    t.send("\x1b[<128;30;3m", 0.3)
    assert "sub" in t.text() and "a.txt" in t.text()
    assert t.row(0).rstrip().endswith("work")


def test_mouse_drag_selects_text_in_editor(spawn, work):
    (work / "t.txt").write_text("abcdefghij\n")
    t = spawn("t.txt")
    t.send("\x1b[<0;5;2M", 0.15)       # lenyom a 3. karakternél (gutter = 2)
    t.send("\x1b[<32;7;2M", 0.15)
    t.send("\x1b[<32;9;2M", 0.15)
    t.send("\x1b[<0;9;2m", 0.2)
    t.send("\x7f", 0.3)                 # Backspace törli a kijelölést
    t.send(CTRL("s"))
    assert (work / "t.txt").read_text() == "abghij\n"


def test_select_all_status_and_folder_size(spawn, work):
    (work / "a.txt").write_text("x" * 1000)
    (work / "dir").mkdir()
    (work / "dir" / "b.bin").write_bytes(b"y" * 3000)
    (work / "c.txt").write_text("z" * 500)
    t = spawn(".")
    assert "2 fájl, 1 mappa" in t.row(ROWS - 3)             # jobb alsó sor
    t.send("a")                                              # összes kijelölése
    assert "3 kijelölve, 4.4K" in t.row(ROWS - 3)            # 1000 + 3000 + 500 (mappa is)
    t.send("a")
    assert "kijelölve" not in t.row(ROWS - 3)
    t.send("i")                                              # mappaméret: az aktuális (dir)
    assert "dir: 2.9K, 1 fájl, 0 mappa" in t.text()


HAS7Z = bool(shutil.which("7z") or shutil.which("7zz") or shutil.which("7za"))


def test_compress_and_extract_zip_and_targz(spawn, work):
    (work / "a.txt").write_text("alma\n")
    (work / "b.txt").write_text("korte\n")
    t = spawn(".")
    t.send(" ")
    t.send(" ")                                              # a és b kijelölve
    t.send("Z")
    t.send(CTRL("u"))
    t.send("csomag.zip\r", 0.8)
    if HAS7Z:
        t.send("\r", 0.8)                                    # üres jelszó
    assert (work / "csomag.zip").exists()
    with zipfile.ZipFile(work / "csomag.zip") as z:
        assert sorted(z.namelist()) == ["a.txt", "b.txt"]
    t.send("Z")                                              # a kurzor a(z új) fájlon áll
    t.send(CTRL("u"))
    t.send("x.tar.gz\r", 0.8)
    assert (work / "x.tar.gz").exists()
    # kicsomagolás: csomag.zip kiválasztása és U
    names = [n for n in sorted(p.name for p in work.iterdir())]
    t2 = spawn(".")
    idx = names.index("csomag.zip")
    for _ in range(idx):
        t2.send("j")
    t2.send("U")
    t2.send("\r", 0.8)
    assert (work / "csomag" / "a.txt").read_text() == "alma\n"


@pytest.mark.skipif(not shutil.which("7z") and not shutil.which("7zz") and not shutil.which("7za"),
                    reason="nincs 7z")
def test_compress_7z(spawn, work):
    (work / "a.txt").write_text("alma\n")
    t = spawn(".")
    t.send("Z")
    t.send("\r")                                            # név
    t.send("\r", 1.5)                                       # üres jelszó
    assert (work / "a.txt.7z").exists()


def test_extract_refuses_path_traversal(work):
    import sys
    sys.path.insert(0, str(ROOT))
    from nanger import archiver
    z = work / "evil.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("../kint.txt", "x")
    with pytest.raises(archiver.ArchiveError):
        archiver.extract(str(z), str(work / "out"))
    assert not (work / "kint.txt").exists()


def test_double_key_remap_yy(spawn, work, env):
    (work / "a.txt").write_text("x")
    (work / "mappa").mkdir()
    t = spawn(".")
    t.send("K")
    for _ in range(8):                  # "Copy" a 9. sor (Open, Back, New file, New folder, Rename, Bulk, Delete, Mark, Copy)
        t.send("j")
    t.send("\r")
    t.send("y")
    t.send("y")                         # yy
    assert "Elmentve" in t.text()
    t.send("q")
    t.send("y")
    assert "y …" in t.text() or "y…" in t.text().replace(" ", "")   # egy y: csak a sorozat eleje
    t.send("y")
    assert "kijelölve" in t.text() or "másolásra" in t.text()       # a yy lefutott: másolás


def test_doctor_reports_environment(env):
    import subprocess
    out = subprocess.run([NANGER, "--doctor"], capture_output=True, text=True, env=env).stdout
    assert "nanger 1." in out and "Pillow:" in out and "graphics protocol:" in out


def test_shell_wrapper_leaves_shell_in_last_folder(work, env, tmp_path):
    (work / "sub").mkdir()
    (work / "sub" / "x.txt").write_text("x")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "nanger").symlink_to(NANGER)
    e = dict(env, PATH=f"{bindir}:{os.environ['PATH']}", PS1="$ ")
    p = pexpect.spawn("bash", ["--norc", "-i"], cwd=str(work), env=e, dimensions=(ROWS, COLS),
                      encoding="utf-8")
    p.sendline('eval "$(command nanger --shell-init bash)"')
    time.sleep(0.5)
    p.sendline("nanger")
    time.sleep(1.2)
    p.send("\r")        # be a "sub" mappába (az első elem)
    time.sleep(0.5)
    p.send("q")
    time.sleep(0.8)
    p.sendline("echo CWD=$(pwd)")
    p.expect(r"CWD=(\S+)", timeout=5)
    p.expect(r"CWD=(\S+)", timeout=5)
    assert p.match.group(1).endswith("/work/sub")
    p.terminate(force=True)


def test_install_shell_is_idempotent(env, tmp_path):
    import subprocess
    e = dict(env, SHELL="/bin/bash", HOME=str(tmp_path / "h2"))
    (tmp_path / "h2").mkdir()
    for _ in range(2):
        subprocess.run([NANGER, "--install-shell"], env=e, capture_output=True, text=True)
    rc = (tmp_path / "h2" / ".bashrc").read_text()
    assert rc.count("nanger --shell-init") == 1


@pytest.mark.skipif(not shutil.which("7z") and not shutil.which("7zz") and not shutil.which("7za"),
                    reason="nincs 7z")
def test_7z_preview_is_async_and_readable(spawn, work):
    import subprocess
    (work / "in").mkdir()
    (work / "in" / "szoveg a.txt").write_text("x" * 2048)
    exe = shutil.which("7z") or shutil.which("7zz") or shutil.which("7za")
    subprocess.run([exe, "a", "-bd", str(work / "k.7z"), "in"], cwd=work, capture_output=True,
                   check=True)
    subprocess.run(["rm", "-rf", str(work / "in")], check=True)
    t = spawn(".")
    t.pump(1.0)
    assert "szoveg a.txt" in t.text() and "2.0K" in t.text()
    assert "....A" not in t.text()


def test_theme_menu_applies_and_persists(spawn, work, env):
    (work / "a.txt").write_text("x")
    t = spawn(".")
    t.send("T")
    assert "Színtéma" in t.row(0)
    for _ in range(3):                       # default, dark, light, solarized-dark
        t.send("j")
    t.send("\r")
    assert "Téma: solarized-dark" in t.text()
    cfg = (Path(env["XDG_CONFIG_HOME"]) / "nanger" / "config.ini").read_text()
    assert "theme = solarized-dark" in cfg
    # a téma háttere: 234-es szín = 1c1c1c
    assert t.scr.buffer[20][5].bg == "1c1c1c"
    t2 = spawn(".")                          # újraindítás: megmarad
    assert t2.scr.buffer[20][5].bg == "1c1c1c"


def test_theme_names_match_between_config_and_term():
    import sys
    sys.path.insert(0, str(ROOT))
    from nanger import config, term
    assert tuple(term.THEMES) == config.THEME_NAMES


def test_chmod_on_selection(spawn, work):
    a, b = work / "a.sh", work / "b.sh"
    for f in (a, b):
        f.write_text("x")
        f.chmod(0o644)
    t = spawn(".")
    t.send(" ")
    t.send(" ")                                  # a és b kijelölve
    t.send("P")
    assert "Jogosultságok" in t.text()
    t.send("\x15")                               # Ctrl+U
    t.send("755\r")
    assert "755 jogosultság beállítva 2 elemen" in t.text()
    assert (a.stat().st_mode & 0o777) == 0o755
    assert (b.stat().st_mode & 0o777) == 0o755
    t.send("P")
    t.send("\x15")
    t.send("u+x;rm\r")                           # érvénytelen -> hiba, semmi sem fut
    assert "Érvénytelen jogosultság" in t.text()


def test_chown_to_self_and_invalid(spawn, work):
    import grp
    import pwd
    f = work / "a.txt"
    f.write_text("x")
    t = spawn(".")
    me = pwd.getpwuid(os.getuid()).pw_name
    t.send("O")
    assert "Tulajdonos" in t.text()
    t.send("\x15")
    t.send(me + "\r")
    assert "Tulajdonos (%s) beállítva 1 elemen" % me in t.text()
    t.send("O")
    t.send("\x15")
    t.send("a b;c\r")
    assert "Érvénytelen tulajdonos" in t.text()


def test_remote_spec_parsing():
    import sys
    sys.path.insert(0, str(ROOT))
    from nanger import remote
    assert remote.parse("me@box:/srv/x") == ("me@box", None, "/srv/x")
    assert remote.parse("box:") == ("box", None, "")
    assert remote.parse("sftp://me@box:2222/srv") == ("me@box", "2222", "/srv")
    assert remote.parse("/tmp/a:b") is None
    assert remote.parse("./a:b") is None
    assert remote.parse("C:") is None
    cmd = remote.command("me@box", "2222", "/srv", "/mnt/x")
    assert cmd[:3] == ["sshfs", "me@box:/srv", "/mnt/x"] and "BatchMode=yes" in cmd[4]
    assert cmd[-2:] == ["-p", "2222"]


def test_remote_connect_with_fake_sshfs(spawn, work, env, tmp_path):
    """A fake sshfs puts a file in the mountpoint; the real flow (M, cd, unmount) is exercised."""
    bin_ = tmp_path / "fakebin"
    bin_.mkdir()
    (bin_ / "sshfs").write_text('#!/bin/sh\necho "remote content" > "$2/remote.txt"\n')
    (bin_ / "fusermount3").write_text('#!/bin/sh\nrm -f "$3/remote.txt"\n')
    for f in bin_.iterdir():
        f.chmod(0o755)
    t = spawn(".", extra_env={"PATH": "%s:%s" % (bin_, os.environ["PATH"])})
    t.send("M")
    assert "Távoli" in t.text()
    t.send("me@box:/srv\r")
    assert "Csatlakozva: me@box" in t.text()
    assert "remote.txt" in t.text()
    t.send("M")
    t.send("\r")
    assert "Lecsatlakozva: me@box" in t.text()
    assert "remote.txt" not in t.text()


def test_remote_without_sshfs_reports_error(spawn, work, tmp_path):
    bare = tmp_path / "barebin"
    bare.mkdir()
    for n in ("python3", "env"):
        (bare / n).symlink_to(shutil.which(n))
    t = spawn(".", extra_env={"PATH": str(bare)})
    t.send("M")
    t.send("me@box:/srv\r")
    assert "sshfs" in t.text()


def test_diff_two_marked_files(spawn, work):
    (work / "a.txt").write_text("one\ntwo\nthree\nfour\n")
    (work / "b.txt").write_text("one\n2\nthree\nfour\nfive\n")
    t = spawn(".")
    t.send(" ")
    t.send(" ")
    t.send("=")
    assert "összehasonlítás" in t.row(0)
    assert "2 eltérés" in t.row(0)
    txt = t.text()
    assert "- two" in txt and "+ 2" in txt and "+ five" in txt
    t.send("n")                                   # következő eltérés: nem hibázik
    t.send("q")
    assert "a.txt" in t.text()


def test_diff_identical_and_editor_vs_disk(spawn, work):
    (work / "a.txt").write_text("x\ny\n")
    (work / "b.txt").write_text("x\ny\n")
    t = spawn(".")
    t.send(" ")
    t.send(" ")
    t.send("=")
    assert "egyforma" in t.text()
    t2 = spawn("a.txt")
    t2.send("hello ")                             # a puffer eltér a lemeztől
    t2.send("\x10")                               # Ctrl+P: parancssor
    t2.send("diff\r")
    txt = t2.text()
    assert "(lemezen)" in txt and "(szerkesztett)" in txt
    assert "- x" in txt and "+ hello x" in txt


def _recovery_files(env):
    d = Path(env["XDG_DATA_HOME"]) / "nanger" / "recovery"
    return list(d.glob("*.json")) if d.is_dir() else []


def test_autosave_and_restore_after_kill(spawn, work, env):
    f = work / "a.txt"
    f.write_text("alap\n")
    t = spawn("a.txt", extra_env={"NANGER_AUTOSAVE": "0.5"})
    t.send("elveszett ")
    deadline = time.time() + 6
    while time.time() < deadline and not _recovery_files(env):
        time.sleep(0.2)
    assert _recovery_files(env), "nincs helyreállítási fájl"
    t.p.kill(signal.SIGKILL)                      # összeomlás: semmi sem menti el
    assert f.read_text() == "alap\n"
    t2 = spawn("a.txt")
    assert "Mentetlen módosítások találhatók" in t2.text()
    t2.send("i")
    assert "visszaállítva" in t2.text()
    assert "elveszett alap" in t2.text()
    t2.send("\x13")                               # Ctrl+S
    assert f.read_text() == "elveszett alap\n"
    assert not _recovery_files(env)


def test_hangup_saves_recovery_and_decline_discards(spawn, work, env):
    f = work / "b.txt"
    f.write_text("x\n")
    t = spawn("b.txt")                            # alap 5 mp: csak a SIGHUP menthet
    t.send("fontos ")
    t.p.kill(signal.SIGHUP)
    t.p.wait()
    assert _recovery_files(env)
    t2 = spawn("b.txt")
    assert "Mentetlen módosítások találhatók" in t2.text()
    t2.send("n")
    assert not _recovery_files(env)
    assert "fontos" not in t2.text()


def test_normal_quit_without_saving_leaves_no_recovery(spawn, work, env):
    (work / "c.txt").write_text("x\n")
    t = spawn("c.txt", extra_env={"NANGER_AUTOSAVE": "0.5"})
    t.send("valami ")
    time.sleep(1.5)
    assert _recovery_files(env)
    t.send("\x11")                                # Ctrl+Q
    t.send("y")                                   # mentés nélkül kilép
    time.sleep(0.8)
    assert not _recovery_files(env)


def test_quick_filter(spawn, work):
    for n in ("browser.py", "breadcrumb.py", "app.py", "zebra.txt"):
        (work / n).write_text("x")
    t = spawn(".")
    t.send("F")
    t.send("br")
    txt = t.text()
    assert "Szűrő: br" in txt and "3 találat / 4 elem" in txt    # browser, breadcrumb, zebra
    assert "app.py" not in txt
    t.send("o")
    assert "1 találat / 4 elem" in t.text()
    t.send("\x7f")                                  # Backspace: vissza "br"
    assert "3 találat / 4 elem" in t.text()
    t.send("\x1b")
    assert "Szűrő:" not in t.text() and "app.py" in t.text()
    t.send("F")
    t.send("zeb")
    t.send("\r")                                    # megnyitja az egyetlen találatot
    assert "Szűrő:" not in t.text()


def test_tabs_new_switch_close(spawn, work):
    (work / "sub").mkdir()
    (work / "sub" / "inner.txt").write_text("x")
    t = spawn(".")
    t.send("\x14")                                  # Ctrl+T
    assert "2. fül" in t.text()
    assert " 1 " in t.row(0) and " 2 " in t.row(0)
    t.send("\r")                                    # 2. fül: belép a sub-ba
    assert "inner.txt" in t.text()
    t.send("[")                                     # vissza az 1. fülre: még a work-ben
    assert "sub" in t.text() and "inner.txt" not in t.text().split("│")[1]
    t.send("]")
    assert "inner.txt" in t.text()
    t.send("\x17")                                  # Ctrl+W bezár
    assert " 2 " not in t.row(0)
    t.send("\x17")
    assert "utolsó fül" in t.text()


def test_split_panels_copy_and_move(spawn, work):
    (work / "dst").mkdir()
    (work / "a.txt").write_text("alpha")
    (work / "b.txt").write_text("beta")
    t = spawn(".")
    t.send("w")
    assert "két panel" in t.row(0)
    t.send("\t")                                    # jobb panel aktív (a dst mappán áll)
    t.send("\r")                                    # belép a dst-be (jobb panel)
    t.send("\t")                                    # vissza a bal panelre
    t.send("j")                                     # a.txt
    t.send("C")
    assert "Átmásolva" in t.text()
    assert (work / "dst" / "a.txt").read_text() == "alpha"
    assert (work / "a.txt").exists()
    t.send("j")                                     # b.txt
    t.send("W")
    assert "Áthelyezve" in t.text()
    assert (work / "dst" / "b.txt").exists() and not (work / "b.txt").exists()
    t.send("w")                                     # egy panel
    assert "két panel" not in t.row(0)


def test_split_help_and_copy_without_second_panel(spawn, work):
    (work / "a.txt").write_text("x")
    t = spawn(".")
    t.send("C")
    assert "második panelt" in t.text()


def test_goto_actions_unbound_until_set(spawn, work, env):
    cfg = Path(env["XDG_CONFIG_HOME"]) / "nanger"
    cfg.mkdir(parents=True)
    t = spawn(".")
    t.send("gx")                                    # nincs kötés: nem történik semmi
    assert str(work.name) in t.row(0)
    (cfg / "config.ini").write_text(
        "[keys.browser]\nf2 = go-root\nf3 = go-home\nf4 = go-temp\n")
    t2 = spawn(".")
    t2.send("\x1bOQ")                               # F2 -> gyökér
    assert " / " in t2.row(0) or t2.row(0).rstrip().endswith("/")
    t2.send("\x1bOR")                               # F3 -> home
    assert "~" in t2.row(0) or str(Path(env["HOME"]).name) in t2.row(0)


def test_unbound_actions_in_key_map():
    import sys
    sys.path.insert(0, str(ROOT))
    from nanger import actions
    from nanger.keys import K_GO_ROOT, key_name, parse_key
    i = next(n for n, (m, d) in enumerate(actions.BROWSER) if d == "go-root")
    assert actions.bindings("browser", {})[i] is None          # nincs alapértelmezett kötés
    assert key_name(K_GO_ROOT) == "go-root" and parse_key("go-root") == K_GO_ROOT
    km, _ = actions.rebind("browser", {}, i, ("Q",))
    assert actions.bindings("browser", km)[i] == ("Q",)
    km2, _ = actions.reset("browser", km, i)
    assert actions.bindings("browser", km2)[i] is None


def test_hacker_theme_and_f4_without_files(spawn, work, env):
    cfg = Path(env["XDG_CONFIG_HOME"]) / "nanger"
    cfg.mkdir(parents=True)
    (cfg / "config.ini").write_text("[general]\ntheme = hacker\n")
    (work / "a.txt").write_text("x")
    t = spawn(".")
    assert t.scr.buffer[20][5].bg == "000000"
    t.send("\x1bOS")                                # F4: még nincs megnyitott fájl
    assert "Még nincs megnyitott fájl" in t.text()


def test_remote_password_login_with_fake_sshfs(spawn, work, tmp_path):
    """Keys fail ("Permission denied") -> nanger asks for a password and retries via stdin."""
    bin_ = tmp_path / "pwbin"
    bin_.mkdir()
    (bin_ / "sshfs").write_text(
        '#!/bin/sh\n'
        'case "$*" in *password_stdin*) read pw; [ "$pw" = "titok" ] || { echo "Permission denied" >&2; exit 1; }\n'
        '  echo hi > "$2/remote.txt";;\n'
        '*) echo "me@box: Permission denied (publickey,password)." >&2; exit 1;; esac\n')
    (bin_ / "fusermount3").write_text('#!/bin/sh\nrm -f "$3/remote.txt"\n')
    for f in bin_.iterdir():
        f.chmod(0o755)
    t = spawn(".", extra_env={"PATH": "%s:%s" % (bin_, os.environ["PATH"])})
    t.send("M")
    t.send("me@box:/srv\r")
    assert "Jelszó" in t.text()
    t.send("titok")
    assert "titok" not in t.text()                  # a jelszó nem látszik
    assert "*****" in t.text()
    t.send("\r")
    assert "Csatlakozva: me@box" in t.text()
    assert "remote.txt" in t.text()
    t.send("M")
    t.send("\r")
    t3 = spawn(".", extra_env={"PATH": "%s:%s" % (bin_, os.environ["PATH"])})
    t3.send("M")
    t3.send("me@box:/srv\r")
    t3.send("rossz\r")
    assert "Permission denied" in t3.text()


@pytest.mark.skipif(not HAS7Z, reason="nincs 7z")
@pytest.mark.parametrize("ext", ["7z", "zip"])
def test_password_archive_roundtrip(spawn, work, ext):
    (work / "titkos.txt").write_text("nagyon titkos\n")
    t = spawn(".")
    t.send("Z")
    t.send(CTRL("u"))
    t.send("vedett.%s\r" % ext)
    assert "Jelszó (üres = nincs)" in t.text()
    t.send("jelszo1")
    assert "jelszo1" not in t.text()
    t.send("\r", 1.5)
    arc = work / ("vedett." + ext)
    assert arc.exists()
    assert b"nagyon titkos" not in arc.read_bytes()          # tényleg titkosított
    (work / "titkos.txt").unlink()
    t2 = spawn(".")
    t2.send("U")                                              # az archívumon áll a kurzor
    t2.send("\r", 0.5)                                       # célmappa
    assert "Jelszó (vedett.%s)" % ext in t2.text()
    t2.send("rossz\r", 1.0)
    assert "Hibás jelszó" in t2.text()
    t2.send("jelszo1\r", 1.5)
    assert (work / "vedett" / "titkos.txt").read_text() == "nagyon titkos\n"


@pytest.mark.skipif(not HAS7Z, reason="nincs 7z")
def test_encrypted_archive_preview_and_api(work):
    import sys
    sys.path.insert(0, str(ROOT))
    from nanger import archiver
    (work / "a.txt").write_text("x")
    arc = str(work / "e.7z")
    archiver.compress(str(work), ["a.txt"], arc, "pw")
    with pytest.raises(archiver.ArchiveError) as e:
        archiver.extract(arc, str(work / "o1"))
    assert e.value.needs_password and not (work / "o1").exists()
    with pytest.raises(archiver.ArchiveError) as e:
        archiver.extract(arc, str(work / "o2"), "wrong")
    assert e.value.needs_password
    archiver.extract(arc, str(work / "o3"), "pw")
    assert (work / "o3" / "a.txt").read_text() == "x"
    from nanger import term
    term.A.setdefault("ln", 0)
    m = load_module()
    lines, _ = m.archive_lines(arc, 50)
    assert "titkosított" in lines[0][0] or "encrypted" in lines[0][0]
    with pytest.raises(archiver.ArchiveError):
        archiver.compress(str(work), ["a.txt"], str(work / "t.tar.gz"), "pw")

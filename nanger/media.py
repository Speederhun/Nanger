"""File type detection and previews: images, PDF, archives (half-block rendering in any
256-color UTF-8 terminal; needs Pillow and, for PDF, poppler-utils)."""
import curses
import functools
import io
import locale
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from collections import OrderedDict

from .i18n import tr
from .term import A, FIRST_FREE_PAIR, clean
from .util import human

try:  # optional: image and PDF previews
    from PIL import Image
except Exception:  # noqa: BLE001 - any import problem simply disables previews
    Image = None

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".jfif", ".gif", ".bmp", ".webp", ".tif", ".tiff",
             ".ico", ".ppm", ".pgm", ".pbm"}
ARCHIVE_EXT = (".zip", ".jar", ".whl", ".apk", ".tar", ".tar.gz", ".tgz", ".tar.bz2",
               ".tbz2", ".tar.xz", ".txz", ".tar.zst", ".7z", ".rar", ".gz", ".bz2", ".xz",
               ".zst", ".lz4", ".lzma", ".iso", ".cab", ".deb", ".rpm", ".cpio", ".arj", ".z")
EXTERNAL_EXT = {".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp", ".doc", ".xls", ".ppt",
                ".rtf", ".epub", ".mp3", ".mp4", ".mkv", ".avi", ".mov", ".webm", ".flac",
                ".ogg", ".wav", ".m4a", ".opus"}
_CUBE = (0, 95, 135, 175, 215, 255)
_RENDER_CACHE = OrderedDict()
_PAIRS = {}


def pillow_available():
    return Image is not None


def file_kind(p):
    """dir | pdf | image | archive | external | text | binary"""
    if os.path.isdir(p):
        return "dir"
    low = p.lower()
    ext = os.path.splitext(low)[1]
    if ext == ".pdf":
        return "pdf"
    if ext in IMAGE_EXT:
        return "image"
    if ext in EXTERNAL_EXT:
        return "external"
    if low.endswith(ARCHIVE_EXT):
        return "archive"
    try:
        with open(p, "rb") as f:
            head = f.read(8192)
    except OSError:
        return "binary"
    return "binary" if b"\0" in head else "text"


def opener():
    """The desktop "open" command: `open` on macOS, `xdg-open` elsewhere."""
    return "open" if sys.platform == "darwin" else "xdg-open"


def has_gui():
    if sys.platform == "darwin":   # no DISPLAY on a Mac; not usable over SSH
        return shutil.which("open") is not None and not os.environ.get("SSH_CONNECTION")
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")) \
        and shutil.which("xdg-open") is not None


def is_utf8():
    return "utf" in (locale.getpreferredencoding(False) or "").lower()


def can_images():
    return Image is not None and curses.has_colors() and is_utf8()


def can_view(kind):
    if kind == "pdf":
        return bool(shutil.which("pdftotext")) or \
            (can_images() and bool(shutil.which("pdftoppm")))
    return can_images()


# ------------------------------------------------------------------ rendering

@functools.lru_cache(maxsize=1 << 16)
def rgb_to_256(r, g, b):
    def lv(c):
        return 0 if c < 48 else 1 if c < 115 else (c - 35) // 40

    ri, gi, bi = lv(r), lv(g), lv(b)
    avg = (r + g + b) // 3
    gl = 23 if avg > 238 else max(0, (avg - 3) // 10)
    gv = 8 + 10 * gl
    d_cube = (_CUBE[ri] - r) ** 2 + (_CUBE[gi] - g) ** 2 + (_CUBE[bi] - b) ** 2
    d_gray = (gv - r) ** 2 + (gv - g) ** 2 + (gv - b) ** 2
    return 232 + gl if d_gray < d_cube else 16 + 36 * ri + 6 * gi + bi


def quant(px):
    r, g, b = px[:3]
    if curses.COLORS >= 256:
        return rgb_to_256(r, g, b)
    return int(r > 127) | int(g > 127) << 1 | int(b > 127) << 2


_LEVELS = (0, 95, 135, 175, 215, 255)
GRAPHICS = []    # (y, x, Grid) real-image placements for this frame
_SHOWN = {}
OVERLAY = []     # (y, x, row) true-colour rows to paint after curses has flushed
_PAL = None


def truecolor():
    return (os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit")
            and curses.COLORS >= 256 and os.environ.get("NANGER_TRUECOLOR", "1") != "0")


def _dither_to_256(img):
    """Floyd-Steinberg dither to the xterm 6x6x6 cube + gray ramp (much better on photos)."""
    global _PAL
    if _PAL is None:
        cols = [(r, g, b) for r in _LEVELS for g in _LEVELS for b in _LEVELS]
        cols += [(8 + 10 * i,) * 3 for i in range(24)]
        flat = [c for rgb in cols for c in rgb]
        flat += flat[:3] * (256 - len(cols))
        pal = Image.new("P", (1, 1))
        pal.putpalette(flat)
        _PAL = pal
    return img.quantize(palette=_PAL, dither=Image.FLOYDSTEINBERG).convert("RGB")


class Grid(list):
    """Half-block cells (a list of rows) plus, when the terminal can show real images,
    a high-resolution picture for the same cell box."""
    px = None          # PIL image for graphics protocols
    ncols = nrows = 0
    _png = None
    _sixel = None

    def png(self):
        if self._png is None:
            buf = io.BytesIO()
            self.px.save(buf, "PNG")
            self._png = buf.getvalue()
        return self._png

    def sixel(self):
        if self._sixel is None:
            self._sixel = encode_sixel(self.px)
        return self._sixel


def graphics_mode():
    """kitty | iterm | sixel | None  (config 'graphics' or NANGER_GRAPHICS overrides)."""
    from .config import settings
    want = (os.environ.get("NANGER_GRAPHICS") or getattr(settings, "graphics", "auto")).lower()
    if want in ("blocks", "off", "none", "no"):
        return None
    if want in ("kitty", "iterm", "sixel"):
        return want
    env = os.environ
    if env.get("TMUX") or env.get("STY"):
        return None                       # multiplexers swallow the escape sequences
    prog = env.get("TERM_PROGRAM", "")
    term = env.get("TERM", "")
    if env.get("KITTY_WINDOW_ID") or "kitty" in term or prog in ("ghostty", "WezTerm"):
        return "kitty"
    if prog == "iTerm.app":
        return "iterm"
    if term.startswith(("foot", "mlterm", "contour")) or env.get("WT_SESSION"):
        return "sixel"
    return None


def cell_pixels():
    try:
        import fcntl
        import struct
        import termios
        rows, cols, xp, yp = struct.unpack("HHHH", fcntl.ioctl(1, termios.TIOCGWINSZ,
                                                               b"\0" * 8))
        if xp and yp and cols and rows:
            return max(4, xp // cols), max(8, yp // rows)
    except Exception:  # noqa: BLE001
        pass
    return 9, 18


def encode_sixel(img, colors=64):
    img = img.convert("RGB")
    q = img.quantize(colors=colors, dither=Image.FLOYDSTEINBERG)
    pal = q.getpalette()[:colors * 3]
    w, h = q.size
    data = q.tobytes()
    out = ['\x1bP0;1;0q"1;1;%d;%d' % (w, h)]
    used = sorted(set(data))
    for i in used:
        out.append("#%d;2;%d;%d;%d" % (i, pal[i * 3] * 100 // 255, pal[i * 3 + 1] * 100 // 255,
                                        pal[i * 3 + 2] * 100 // 255))
    for y0 in range(0, h, 6):
        band = [data[(y0 + k) * w:(y0 + k + 1) * w] for k in range(min(6, h - y0))]
        present = set()
        for row in band:
            present.update(row)
        first = True
        for c in used:
            if c not in present:
                continue
            chars = []
            for x in range(w):
                bits = 0
                for k, row in enumerate(band):
                    if row[x] == c:
                        bits |= 1 << k
                chars.append(chr(63 + bits))
            line = "".join(chars)
            out.append(("" if first else "$") + "#%d" % c + _rle(line))
            first = False
        out.append("-")
    out.append("\x1b\\")
    return "".join(out)


def _rle(s):
    out, i, n = [], 0, len(s)
    while i < n:
        j = i
        while j < n and s[j] == s[i]:
            j += 1
        run = j - i
        out.append("!%d%s" % (run, s[i]) if run > 3 else s[i] * run)
        i = j
    return "".join(out)


def render_grid(img, cols, rows):
    """PIL image -> Grid of half-block cells: per row a list of (top RGB, bottom RGB)."""
    rs = getattr(Image, "Resampling", Image)
    img = img.convert("RGBA")
    if img.getchannel("A").getextrema()[0] < 255:
        img = Image.alpha_composite(Image.new("RGBA", img.size, (0, 0, 0, 255)), img)
    img = img.convert("RGB")
    w, h = img.size
    gm = graphics_mode()
    if gm:
        cw, ch = cell_pixels()
        scale = min(cols * cw / w, rows * ch / h)
        pw, ph = max(1, int(w * scale)), max(1, int(h * scale))
        nw, nrows = max(1, -(-pw // cw)), max(1, -(-ph // ch))
        nh = nrows * 2
        big = img.resize((pw, ph), rs.LANCZOS if scale < 1 else rs.BICUBIC)
        small = big.resize((nw, nh), rs.BOX)
    else:
        scale = min(cols / w, rows * 2 / h)
        nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
        nh += nh % 2
        method = rs.LANCZOS if scale < 1 else (rs.NEAREST if scale >= 2 else rs.BILINEAR)
        small = img.resize((nw, nh), method)
        if not truecolor() and curses.COLORS >= 256 and scale < 1:
            small = _dither_to_256(small)
        big = None
    px = small.load()
    grid = Grid([[(px[x, y], px[x, y + 1]) for x in range(nw)] for y in range(0, nh, 2)])
    if big is not None:
        grid.px, grid.ncols, grid.nrows = big, nw, nh // 2
    return grid


def color_attr(fg, bg):
    key = (fg, bg)
    a = _PAIRS.get(key)
    if a is None:
        n = FIRST_FREE_PAIR + len(_PAIRS)
        if n >= curses.COLOR_PAIRS:
            return 0
        curses.init_pair(n, fg, bg)
        a = _PAIRS[key] = curses.color_pair(n)
    return a


def draw_grid(scr, y0, x0, grid):
    h, w = scr.getmaxyx()
    tc = truecolor()
    if getattr(grid, "px", None) is not None and grid and y0 + grid.nrows <= h \
            and x0 + grid.ncols <= w:
        GRAPHICS.append((y0, x0, grid))
    for r, row in enumerate(grid):
        y = y0 + r
        if y >= h:
            break
        row = row[:max(0, w - x0)]
        if tc and row:
            OVERLAY.append((y, x0, row))
        for c, (top, bot) in enumerate(row):
            try:
                scr.addstr(y, x0 + c, "▀", color_attr(quant(top), quant(bot)))
            except curses.error:
                pass


def _flush_graphics():
    import base64
    mode = graphics_mode()
    out = []
    if not GRAPHICS:
        if _SHOWN.pop("kitty", None):
            out.append("\x1b_Ga=d,d=I,i=77,q=2\x1b\\")
        return "".join(out)
    y, x, g = GRAPHICS[-1]
    pos = "\x1b[%d;%dH" % (y + 1, x + 1)
    if mode == "kitty":
        key = (id(g), y, x)
        if _SHOWN.get("kitty") == key:
            return ""
        data = base64.standard_b64encode(g.png()).decode()
        chunks = [data[i:i + 4096] for i in range(0, len(data), 4096)] or [""]
        out.append("\x1b_Ga=d,d=I,i=77,q=2\x1b\\" + pos)
        for n, ch in enumerate(chunks):
            more = 1 if n < len(chunks) - 1 else 0
            head = ("a=T,f=100,i=77,p=1,c=%d,r=%d,C=1,q=2,m=%d" % (g.ncols, g.nrows, more)
                    if n == 0 else "m=%d,q=2" % more)
            out.append("\x1b_G%s;%s\x1b\\" % (head, ch))
        _SHOWN["kitty"] = key
    elif mode == "iterm":
        data = base64.standard_b64encode(g.png()).decode()
        out.append(pos + "\x1b]1337;File=inline=1;width=%d;height=%d;"
                   "preserveAspectRatio=0:%s\x07" % (g.ncols, g.nrows, data))
    elif mode == "sixel":
        out.append(pos + g.sixel())
    return "".join(out)


def flush_overlay():
    """Paint real images / true-colour rows over the placeholders (call after refresh)."""
    try:
        gfx = _flush_graphics()
    except Exception:  # noqa: BLE001 - a graphics problem must never break the UI
        gfx = ""
    if gfx and not OVERLAY:
        _write("\x1b7" + gfx + "\x1b8")
        return
    if not OVERLAY:
        if gfx:
            _write(gfx)
        return
    out = ["\x1b7"]
    for y, x, row in OVERLAY:
        out.append("\x1b[%d;%dH" % (y + 1, x + 1))
        last = None
        for top, bot in row:
            if (top, bot) != last:
                out.append("\x1b[38;2;%d;%d;%d;48;2;%d;%d;%dm" % (top + bot))
                last = (top, bot)
            out.append("▀")
    out.append("\x1b[0m")
    out.append(gfx)
    out.append("\x1b8")
    _write("".join(out))


def hide_graphics():
    if _SHOWN.pop("kitty", None):
        _write("\x1b_Ga=d,d=I,i=77,q=2\x1b\\")


def _write(text):
    data = text.encode("utf-8")
    try:
        while data:
            n = os.write(1, data)
            data = data[n:]
    except OSError:
        pass


# ------------------------------------------------------------------ PDF

@functools.lru_cache(maxsize=64)
def pdf_pages(path, mtime):
    try:
        out = subprocess.run(["pdfinfo", path], capture_output=True, text=True,
                             timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return 0
    m = re.search(r"^Pages:\s+(\d+)", out, re.M)
    return int(m.group(1)) if m else 0


@functools.lru_cache(maxsize=32)
def pdf_text(path, mtime, page):
    exe = shutil.which("pdftotext")
    if not exe:
        raise RuntimeError(tr("pdftotext is missing (poppler-utils)"))
    r = subprocess.run([exe, "-f", str(page), "-l", str(page), "-layout", path, "-"],
                       capture_output=True, timeout=20)
    if r.returncode != 0:
        msg = r.stderr.decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError(msg[-1] if msg else tr("cannot read the text of this PDF"))
    return r.stdout.decode("utf-8", "replace").replace("\f", "")


def pdf_page_image(path, page, px):
    exe = shutil.which("pdftoppm")
    if not exe:
        raise RuntimeError(tr("pdftoppm is missing (poppler-utils)"))
    # render to a temporary file: writing to stdout does not work in every poppler version
    with tempfile.TemporaryDirectory(prefix="nanger-") as tmp:
        root = os.path.join(tmp, "page")
        r = subprocess.run([exe, "-png", "-singlefile", "-f", str(page), "-l", str(page),
                            "-scale-to-x", str(px), "-scale-to-y", "-1", path, root],
                           capture_output=True, timeout=20)
        if r.returncode != 0 or not os.path.exists(root + ".png"):
            msg = r.stderr.decode("utf-8", "replace").strip().splitlines()
            raise RuntimeError(msg[-1] if msg else tr("cannot render this PDF"))
        with open(root + ".png", "rb") as f:
            img = Image.open(io.BytesIO(f.read()))
            img.load()
    return img


def cached_render(kind, path, page, cols, rows, lazy=False):
    """(cells, caption). With lazy=True returns None when it is not cached yet."""
    st = os.stat(path)
    key = (kind, path, st.st_mtime_ns, st.st_size, page, cols, rows)
    hit = _RENDER_CACHE.get(key)
    if hit is not None:
        _RENDER_CACHE.move_to_end(key)
        return hit
    if lazy:
        return None
    if Image is None:
        raise RuntimeError(tr("images need Pillow (python3-pil / python-pillow)"))
    if kind == "pdf":
        img = pdf_page_image(path, page, min(2400, max(300, cols * 4)))
        pages = pdf_pages(path, st.st_mtime_ns)
        caption = tr("PDF  page {page}/{pages}").format(page=page, pages=pages) if pages else "PDF"
    else:
        img = Image.open(path)
        caption = "%s  %d×%d" % (img.format or tr("image"), img.width, img.height)
        img.draft("RGB", (cols * 4, rows * 8))
    res = (render_grid(img, cols, rows), caption)
    _RENDER_CACHE[key] = res
    while len(_RENDER_CACHE) > 12:
        _RENDER_CACHE.popitem(last=False)
    return res


# ------------------------------------------------------------------ archives

def _external_archive_lines(p, limit):
    """7z, rar, iso, deb, ... : list with whichever extractor tool is installed."""
    for cmd in (["bsdtar", "-tf", p], ["7z", "l", "-ba", p], ["7zz", "l", "-ba", p],
                ["7za", "l", "-ba", p], ["unrar", "lb", p]):
        if not shutil.which(cmd[0]):
            continue
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10,
                               errors="replace")
        except (OSError, subprocess.SubprocessError):
            continue
        if r.returncode == 0 and r.stdout.strip():
            rows = [clean(l.rstrip()) for l in r.stdout.splitlines() if l.strip()]
            return [(l, 0) for l in rows[:limit]], len(rows) > limit
    ext = os.path.splitext(p)[1].lower()
    return [(tr("[{ext} file, {size}]").format(ext=ext, size=human(os.path.getsize(p))),
             A["ln"]),
            (tr("Install p7zip / bsdtar to see the contents"), A["ln"])], False


def archive_lines(p, limit):
    """-> ([(text, attr)], has_more)"""
    out, more = [], False
    try:
        if p.lower().endswith((".zip", ".jar", ".whl", ".apk")):
            with zipfile.ZipFile(p) as z:
                infos = z.infolist()
                more = len(infos) > limit
                for zi in infos[:limit]:
                    size = "" if zi.is_dir() else human(zi.file_size)
                    out.append(("%7s  %s" % (size, clean(zi.filename)), 0))
        elif not p.lower().endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz",
                                     ".txz")):
            return _external_archive_lines(p, limit)
        else:
            with tarfile.open(p) as t:
                for m in t:
                    if len(out) >= limit:
                        more = True
                        break
                    size = "" if m.isdir() else human(m.size)
                    out.append(("%7s  %s%s" % (size, clean(m.name), "/" if m.isdir() else ""), 0))
    except (OSError, EOFError, zipfile.BadZipFile, tarfile.TarError) as e:
        return [(tr("[cannot read the archive: {error}]").format(error=e), A["err"])], False
    if not out:
        out = [(tr("(empty archive)"), A["ln"])]
    return out, more


# ------------------------------------------------------------------ office documents

OFFICE_EXT = {".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp"}


def _xml_text(xml, para_tags, text_tags):
    """Very small XML text extractor: paragraphs separated, tabs/breaks kept."""
    import xml.etree.ElementTree as ET
    out, cur = [], []
    try:
        for ev, el in ET.iterparse(io.BytesIO(xml), events=("start", "end")):
            tag = el.tag.rsplit("}", 1)[-1]
            if ev == "end" and tag in text_tags and el.text:
                cur.append(el.text)
            elif ev == "end" and tag in ("tab",):
                cur.append("  ")
            elif ev == "end" and tag in ("br", "line-break"):
                out.append("".join(cur))
                cur = []
            elif ev == "end" and tag in para_tags:
                out.append("".join(cur))
                cur = []
            if ev == "end":
                el.clear()
    except ET.ParseError:
        pass
    if cur:
        out.append("".join(cur))
    return out


@functools.lru_cache(maxsize=16)
def office_text(path, mtime, limit=200):
    """Plain-text lines of a docx / odt / xlsx / pptx / ods / odp, or raise."""
    ext = os.path.splitext(path.lower())[1]
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        lines = []
        if ext == ".docx":
            lines = _xml_text(z.read("word/document.xml"), {"p"}, {"t"})
        elif ext in (".odt", ".ods", ".odp"):
            lines = _odf_lines(z.read("content.xml"))
        elif ext == ".pptx":
            slides = sorted((n for n in names if re.match(r"ppt/slides/slide\d+\.xml$", n)),
                            key=lambda n: int(re.findall(r"\d+", n)[-1]))
            for i, n in enumerate(slides, 1):
                lines.append("── %d ──" % i)
                lines += [t for t in _xml_text(z.read(n), {"p"}, {"t"}) if t.strip()]
        elif ext == ".xlsx":
            shared = []
            if "xl/sharedStrings.xml" in names:
                shared = _xml_text(z.read("xl/sharedStrings.xml"), {"si"}, {"t"})
            sheets = sorted(n for n in names if re.match(r"xl/worksheets/sheet\d+\.xml$", n))
            if sheets:
                lines = _xlsx_rows(z.read(sheets[0]), shared)
        return [l for l in (x.rstrip() for x in lines)][:limit]


def _odf_lines(xml):
    import xml.etree.ElementTree as ET
    out = []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return out
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag in ("p", "h"):
            out.append("".join(el.itertext()))
    return out


def _xlsx_rows(xml, shared):
    import xml.etree.ElementTree as ET
    out = []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return out
    for row in root.iter():
        if row.tag.rsplit("}", 1)[-1] != "row":
            continue
        cells = []
        for c in row:
            v = next((e for e in c if e.tag.rsplit("}", 1)[-1] == "v"), None)
            val = v.text if v is not None and v.text else ""
            if c.get("t") == "s" and val.isdigit() and int(val) < len(shared):
                val = shared[int(val)]
            elif c.get("t") == "inlineStr":
                val = "".join(c.itertext())
            cells.append(val)
        out.append(" │ ".join(cells))
    return out

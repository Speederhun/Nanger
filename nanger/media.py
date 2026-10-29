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
               ".tbz2", ".tar.xz", ".txz")
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


def has_gui():
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


def render_grid(img, cols, rows):
    """PIL image -> half-block cells: per row a list of (top color, bottom color) pairs."""
    rs = getattr(Image, "Resampling", Image)
    img = img.convert("RGBA")
    if img.getchannel("A").getextrema()[0] < 255:
        img = Image.alpha_composite(Image.new("RGBA", img.size, (0, 0, 0, 255)), img)
    img = img.convert("RGB")
    w, h = img.size
    scale = min(cols / w, rows * 2 / h)
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    nh += nh % 2
    method = rs.LANCZOS if scale < 1 else (rs.NEAREST if scale >= 2 else rs.BILINEAR)
    px = img.resize((nw, nh), method).load()
    return [[(quant(px[x, y]), quant(px[x, y + 1])) for x in range(nw)]
            for y in range(0, nh, 2)]


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
    for r, row in enumerate(grid):
        y = y0 + r
        if y >= h:
            break
        for c, (fg, bg) in enumerate(row):
            if x0 + c >= w:
                break
            try:
                scr.addstr(y, x0 + c, "▀", color_attr(fg, bg))
            except curses.error:
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

"""Create and extract archives: .7z (needs 7z/7zz/7za), .zip, .tar.gz/.bz2/.xz (pure Python)."""
import os
import shutil
import subprocess
import tarfile
import zipfile

from .i18n import tr

TAR_EXT = (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")
ZIP_EXT = (".zip", ".jar", ".whl", ".apk")
EXTRACTABLE = TAR_EXT + ZIP_EXT + (".7z", ".rar", ".iso", ".cab", ".deb", ".rpm", ".cpio",
                                   ".arj", ".lzma", ".gz", ".bz2", ".xz", ".zst")


class ArchiveError(Exception):
    pass


def seven_zip():
    for n in ("7zz", "7z", "7za", "7zr"):
        p = shutil.which(n)
        if p:
            return p
    return None


def is_archive(name):
    return name.lower().endswith(EXTRACTABLE)


def stem(name):
    low = name.lower()
    for ext in sorted(EXTRACTABLE, key=len, reverse=True):
        if low.endswith(ext) and len(name) > len(ext):
            return name[:-len(ext)]
    return name


def _run(cmd, cwd=None):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, errors="replace")
    except OSError as e:
        raise ArchiveError(e.strerror or str(e))
    if r.returncode != 0:
        msg = (r.stderr.strip() or r.stdout.strip()).splitlines()
        raise ArchiveError(msg[-1] if msg else "exit %d" % r.returncode)


def compress(cwd, names, archive):
    """Pack `names` (relative to `cwd`) into `archive` (a path). Format by extension."""
    if os.path.lexists(archive):
        raise ArchiveError(tr("Already exists: {name}").format(name=os.path.basename(archive)))
    low = archive.lower()
    try:
        if low.endswith(ZIP_EXT):
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
                for n in names:
                    full = os.path.join(cwd, n)
                    if os.path.isdir(full) and not os.path.islink(full):
                        z.write(full, n)
                        for root, dirs, files in os.walk(full):
                            for f in dirs + files:
                                p = os.path.join(root, f)
                                z.write(p, os.path.relpath(p, cwd))
                    else:
                        z.write(full, n)
        elif low.endswith(TAR_EXT):
            mode = "w:" + {"gz": "gz", "tgz": "gz", "bz2": "bz2", "tbz2": "bz2", "xz": "xz",
                           "txz": "xz"}.get(low.rsplit(".", 1)[-1], "")
            with tarfile.open(archive, mode.rstrip(":")) as t:
                for n in names:
                    t.add(os.path.join(cwd, n), arcname=n)
        else:
            exe = seven_zip()
            if not exe:
                raise ArchiveError(tr("Install p7zip (7zip) to create .7z archives"))
            _run([exe, "a", "-bd", "-y", "--", archive] + list(names), cwd=cwd)
    except (OSError, tarfile.TarError, zipfile.BadZipFile) as e:
        _cleanup(archive)
        raise ArchiveError(getattr(e, "strerror", None) or str(e))
    except ArchiveError:
        _cleanup(archive)
        raise


def _cleanup(path):
    try:
        os.unlink(path)
    except OSError:
        pass


def _inside(dest, name):
    target = os.path.realpath(os.path.join(dest, name))
    root = os.path.realpath(dest)
    return target == root or target.startswith(root + os.sep)


def extract(archive, dest):
    """Extract `archive` into the folder `dest` (created). Refuses paths escaping `dest`."""
    low = archive.lower()
    os.makedirs(dest, exist_ok=True)
    try:
        if low.endswith(ZIP_EXT):
            with zipfile.ZipFile(archive) as z:
                for n in z.namelist():
                    if not _inside(dest, n):
                        raise ArchiveError(tr("Unsafe path in the archive: {name}").format(name=n))
                z.extractall(dest)
            return
        if low.endswith(TAR_EXT):
            with tarfile.open(archive) as t:
                for m in t.getmembers():
                    bad = not _inside(dest, m.name) or m.isdev()
                    if m.issym():
                        link = m.linkname if os.path.isabs(m.linkname) else \
                            os.path.join(os.path.dirname(m.name), m.linkname)
                        bad = bad or not _inside(dest, link)
                    elif m.islnk():
                        bad = bad or not _inside(dest, m.linkname)
                    if bad:
                        raise ArchiveError(tr("Unsafe path in the archive: {name}")
                                           .format(name=m.name))
                t.extractall(dest)
            return
    except (OSError, tarfile.TarError, zipfile.BadZipFile) as e:
        raise ArchiveError(getattr(e, "strerror", None) or str(e))
    exe = seven_zip()
    if exe:
        _run([exe, "x", "-y", "-bd", "-o" + dest, "--", archive])
    elif shutil.which("bsdtar"):
        _run(["bsdtar", "-xf", archive, "-C", dest])
    elif low.endswith(".rar") and shutil.which("unrar"):
        _run(["unrar", "x", "-y", archive, dest + os.sep])
    else:
        raise ArchiveError(tr("Install p7zip or bsdtar to extract this archive"))

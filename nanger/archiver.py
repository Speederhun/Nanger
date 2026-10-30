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
    def __init__(self, msg, needs_password=False):
        super().__init__(msg)
        self.needs_password = needs_password   # True: ask the user for a password and retry


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


def _run(cmd, cwd=None, password=None, twice=False):
    """Run an archiver. The password goes through stdin (7z asks for it there), never argv."""
    data = None
    if password is not None:
        data = (password + "\n") * (2 if twice else 1)
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, errors="replace",
                           input=data, stdin=subprocess.DEVNULL if data is None else None)
    except OSError as e:
        raise ArchiveError(e.strerror or str(e))
    if r.returncode != 0:
        text = r.stderr.strip() + "\n" + r.stdout.strip()
        if "password" in text.lower():
            raise ArchiveError(tr("Password needed or wrong"), needs_password=True)
        msg = (r.stderr.strip() or r.stdout.strip()).splitlines()
        raise ArchiveError(msg[-1] if msg else "exit %d" % r.returncode)


def can_encrypt(archive):
    return archive.lower().endswith((".7z", ".zip")) and seven_zip() is not None


def compress(cwd, names, archive, password=None):
    """Pack `names` (relative to `cwd`) into `archive` (a path). Format by extension.
    A password (.7z / .zip, needs 7z) encrypts the contents with AES-256 (7z: names too)."""
    if os.path.lexists(archive):
        raise ArchiveError(tr("Already exists: {name}").format(name=os.path.basename(archive)))
    low = archive.lower()
    try:
        if password:
            exe = seven_zip()
            if not exe or not low.endswith((".7z", ".zip")):
                raise ArchiveError(tr("A password needs p7zip (7z) and a .7z or .zip archive"))
            opts = ["-mem=AES256", "-tzip"] if low.endswith(".zip") else ["-mhe=on"]
            _run([exe, "a", "-bd", "-y", "-p"] + opts + ["--", archive] + list(names), cwd=cwd,
                 password=password, twice=True)
        elif low.endswith(ZIP_EXT):
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


def extract(archive, dest, password=None):
    """Extract `archive` into the folder `dest` (created). Refuses paths escaping `dest`.
    Raises ArchiveError(needs_password=True) for an encrypted archive without / with a wrong
    password."""
    created = not os.path.exists(dest)
    os.makedirs(dest, exist_ok=True)
    try:
        _extract(archive, dest, password)
    except (ArchiveError, OSError, tarfile.TarError, zipfile.BadZipFile) as e:
        if created:                       # do not leave a half-filled new folder behind
            shutil.rmtree(dest, ignore_errors=True)
        if isinstance(e, ArchiveError):
            raise
        raise ArchiveError(getattr(e, "strerror", None) or str(e))


def _zip_encrypted(archive):
    try:
        with zipfile.ZipFile(archive) as z:
            return any(i.flag_bits & 0x1 for i in z.infolist())
    except (OSError, zipfile.BadZipFile):
        return False


def _extract(archive, dest, password):
    low = archive.lower()
    exe = seven_zip()
    try:
        if low.endswith(ZIP_EXT):
            if _zip_encrypted(archive):
                if password is None:
                    raise ArchiveError(tr("The archive is password protected"), needs_password=True)
                if exe:                   # handles AES as well as the old ZipCrypto
                    _run([exe, "x", "-y", "-bd", "-o" + dest, "--", archive], password=password)
                    return
                with zipfile.ZipFile(archive) as z:
                    try:
                        z.extractall(dest, pwd=password.encode("utf-8"))
                    except RuntimeError:
                        raise ArchiveError(tr("Password needed or wrong"), needs_password=True)
                    except NotImplementedError:
                        raise ArchiveError(tr("Install p7zip to open this encrypted zip"))
                return
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
    if exe:
        _run([exe, "x", "-y", "-bd", "-o" + dest, "--", archive], password=password)
    elif shutil.which("bsdtar"):
        _run(["bsdtar", "-xf", archive, "-C", dest])
    elif low.endswith(".rar") and shutil.which("unrar"):
        _run(["unrar", "x", "-y", archive, dest + os.sep])
    else:
        raise ArchiveError(tr("Install p7zip or bsdtar to extract this archive"))

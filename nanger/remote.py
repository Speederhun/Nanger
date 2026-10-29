"""Remote folders over SSH: mounted with sshfs, so every nanger feature just works on them."""
import atexit
import os
import re
import shutil
import subprocess
import tempfile

from .i18n import tr

MOUNTS = {}        # mountpoint -> "user@host"


class RemoteError(Exception):
    def __init__(self, msg, auth=False):
        super().__init__(msg)
        self.auth = auth          # True: the server refused the login (a password may help)


_SCP = re.compile(r"^(?:(?P<user>[^@/\s:]+)@)?(?P<host>[A-Za-z0-9._\-]+|\[[0-9A-Fa-f:]+\]):(?P<path>.*)$")
_URL = re.compile(r"^(?:sftp|ssh)://(?:(?P<user>[^@/\s]+)@)?(?P<host>[A-Za-z0-9._\-]+|\[[0-9A-Fa-f:]+\])"
                  r"(?::(?P<port>\d+))?(?P<path>/.*)?$")


def parse(spec):
    """'user@host:/path', 'sftp://user@host:2222/path' -> (user@host, port or None, path); else None."""
    spec = spec.strip()
    m = _URL.match(spec)
    if m:
        user, host, port, path = m.group("user"), m.group("host"), m.group("port"), m.group("path") or ""
    else:
        if spec.startswith(("/", ".", "~")) or "://" in spec:
            return None
        m = _SCP.match(spec)
        if not m:
            return None
        user, host, port, path = m.group("user"), m.group("host"), None, m.group("path")
        if len(host) == 1 and not user:      # looks like a Windows drive letter
            return None
    return ("%s@%s" % (user, host) if user else host), port, path


def looks_remote(spec):
    """True for a remote spec that is not an existing local path."""
    return parse(spec) is not None and not os.path.exists(os.path.expanduser(spec))


def command(userhost, port, path, mountpoint, password=False):
    """sshfs command line. Without a password only keys / the agent are tried (BatchMode);
    with one, sshfs reads it from stdin (never from the command line)."""
    opts = "reconnect,ConnectTimeout=10,ServerAliveInterval=15,ServerAliveCountMax=3," \
           "StrictHostKeyChecking=accept-new"
    opts += ",password_stdin,PreferredAuthentications=password:keyboard-interactive" \
        if password else ",BatchMode=yes"
    cmd = ["sshfs", "%s:%s" % (userhost, path), mountpoint, "-o", opts]
    if port:
        cmd += ["-p", str(port)]
    return cmd


def mount(spec, password=None):
    """Mount the remote folder; returns the local mountpoint. Raises RemoteError
    (with .auth set when the login was refused)."""
    p = parse(spec)
    if not p:
        raise RemoteError(tr("Not a remote address: {spec}").format(spec=spec))
    if not shutil.which("sshfs"):
        raise RemoteError(tr("sshfs is not installed (apt install sshfs / pacman -S sshfs / brew install macfuse sshfs)"))
    userhost, port, path = p
    base = os.environ.get("XDG_RUNTIME_DIR")
    mp = tempfile.mkdtemp(prefix="nanger-ssh-", dir=base if base and os.path.isdir(base) else None)
    try:
        r = subprocess.run(command(userhost, port, path, mp, password is not None),
                           capture_output=True, text=True, errors="replace",
                           input=None if password is None else password + "\n",
                           stdin=subprocess.DEVNULL if password is None else None, timeout=40)
    except (OSError, subprocess.SubprocessError) as e:
        _rmdir(mp)
        raise RemoteError(str(e))
    if r.returncode:
        _rmdir(mp)
        msg = (r.stderr.strip().splitlines() or ["sshfs failed"])[-1]
        raise RemoteError(msg, auth="Permission denied" in r.stderr or "denied" in msg.lower())
    MOUNTS[mp] = userhost
    return mp


def _rmdir(path):
    try:
        os.rmdir(path)
    except OSError:
        pass


def unmount(mp):
    for cmd in (["fusermount3", "-u", "-z", mp], ["fusermount", "-u", "-z", mp], ["umount", mp]):
        if shutil.which(cmd[0]):
            try:
                if subprocess.run(cmd, capture_output=True, stdin=subprocess.DEVNULL,
                                  timeout=20).returncode == 0:
                    break
            except (OSError, subprocess.SubprocessError):
                pass
    _rmdir(mp)
    MOUNTS.pop(mp, None)


def unmount_all():
    for mp in list(MOUNTS):
        unmount(mp)


def mount_of(path):
    """(mountpoint, userhost) when `path` lies inside one of our mounts, else None."""
    for mp, uh in MOUNTS.items():
        if path == mp or path.startswith(mp + os.sep):
            return mp, uh
    return None


atexit.register(unmount_all)

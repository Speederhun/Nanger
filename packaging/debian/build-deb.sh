#!/bin/sh
# Build the .deb:  packaging/debian/build-deb.sh [version] [arch]
# arch: all (default, any CPU), amd64, arm64 or armhf (pure Python: identical contents)
# Result: dist/nanger_<version>_<arch>.deb
set -eu
cd "$(dirname "$0")/../.."
VERSION="${1:-$(sed -n 's/^__version__ = "\(.*\)"/\1/p' nanger/__init__.py)}"
ARCH="${2:-all}"
case "$ARCH" in all|amd64|arm64|armhf|i386|riscv64) ;; *) echo "unknown arch $ARCH" >&2; exit 1;; esac
ROOT="$(mktemp -d)"
trap 'rm -rf "$ROOT"' EXIT

make -s install DESTDIR="$ROOT" PREFIX=/usr
rm -rf "$ROOT/usr/share/licenses"
gzip -9n "$ROOT/usr/share/man/man1/nanger.1" "$ROOT/usr/share/man/hu/man1/nanger.1"
install -Dm644 LICENSE "$ROOT/usr/share/doc/nanger/copyright"
mkdir -p "$ROOT/DEBIAN"
cat > "$ROOT/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = configure ] && command -v py3compile >/dev/null 2>&1; then
    py3compile -p nanger /usr/share/nanger || true
fi
exit 0
EOF
cat > "$ROOT/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e
if command -v py3clean >/dev/null 2>&1; then
    py3clean -p nanger || true
fi
exit 0
EOF
chmod 755 "$ROOT/DEBIAN/postinst" "$ROOT/DEBIAN/prerm"
cat > "$ROOT/DEBIAN/control" <<EOF
Package: nanger
Version: $VERSION
Section: editors
Priority: optional
Architecture: $ARCH
Depends: python3 (>= 3.8)
Recommends: python3-pil, poppler-utils, xdg-utils, git
Suggests: xclip | wl-clipboard, sshfs
Installed-Size: $(du -ks "$ROOT/usr" | cut -f1)
Maintainer: Speederhun <https://github.com/Speederhun/Nanger>
Homepage: https://github.com/Speederhun/Nanger
Description: file manager and text editor in one (ranger + nano + vim)
 Terminal file manager with a ranger-style three-column view and a built-in
 editor that is as easy as nano (Ctrl keys, always visible help bar) but has
 vim power: regex substitution, :g/pattern/d, sort, shell filters, macros,
 undo/redo. Previews images and PDFs, shows git status, supports several open
 files, bookmarks, bulk rename and grep. English and Hungarian interface.
EOF
mkdir -p dist
dpkg-deb --root-owner-group --build "$ROOT" "dist/nanger_${VERSION}_${ARCH}.deb"

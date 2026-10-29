#!/bin/sh
# .deb csomag építése:  packaging/debian/build-deb.sh [verzió]
# Eredmény: dist/nanger_<verzió>_all.deb
set -eu
cd "$(dirname "$0")/../.."
VERSION="${1:-$(sed -n 's/^VERSION = "\(.*\)"/\1/p' nanger)}"
ROOT="$(mktemp -d)"
trap 'rm -rf "$ROOT"' EXIT

make -s install DESTDIR="$ROOT" PREFIX=/usr
rm -rf "$ROOT/usr/share/licenses"
gzip -9n "$ROOT/usr/share/man/man1/nanger.1"
install -Dm644 LICENSE "$ROOT/usr/share/doc/nanger/copyright"
mkdir -p "$ROOT/DEBIAN"
cat > "$ROOT/DEBIAN/control" <<EOF
Package: nanger
Version: $VERSION
Section: editors
Priority: optional
Architecture: all
Depends: python3 (>= 3.8)
Suggests: xclip | wl-clipboard
Installed-Size: $(du -ks "$ROOT/usr" | cut -f1)
Maintainer: Speederhun <https://github.com/Speederhun/Nanger>
Homepage: https://github.com/Speederhun/Nanger
Description: file manager and text editor in one (ranger + nano + vim)
 Terminal file manager with a ranger-style three-column view and a built-in
 editor that is as easy as nano (Ctrl keys, always visible help bar) but has
 vim power: regex substitution, :g/pattern/d, sort, shell filters, macros,
 undo/redo. Hungarian user interface.
EOF
mkdir -p dist
dpkg-deb --root-owner-group --build "$ROOT" "dist/nanger_${VERSION}_all.deb"

#!/bin/sh
# Build a signed apt repository from .deb files.
#   packaging/apt/build-repo.sh <deb-dir> <out-dir> [gpg-key-id]
# <out-dir> can be published as-is (GitHub Pages). Layout: pool/ + dists/stable/...
set -eu
GPG_OPTS="${GPG_OPTS:-}"   # e.g. "--pinentry-mode loopback --passphrase-file FILE"
DEBS="$1"; OUT="$2"; KEY="${3:-}"
command -v apt-ftparchive >/dev/null || { echo "apt-utils is required" >&2; exit 1; }
mkdir -p "$OUT/pool/main" "$OUT/dists/stable/main/binary-all" "$OUT/dists/stable/main/binary-amd64" "$OUT/dists/stable/main/binary-arm64" "$OUT/dists/stable/main/binary-armhf"
cp "$DEBS"/*.deb "$OUT/pool/main/"
cd "$OUT"
apt-ftparchive packages pool/main > dists/stable/main/binary-all/Packages
for a in amd64 arm64 armhf; do cp dists/stable/main/binary-all/Packages dists/stable/main/binary-$a/Packages; done
for d in dists/stable/main/binary-*; do gzip -9nkf "$d/Packages"; done
apt-ftparchive \
  -o APT::FTPArchive::Release::Origin=nanger \
  -o APT::FTPArchive::Release::Label=nanger \
  -o APT::FTPArchive::Release::Suite=stable \
  -o APT::FTPArchive::Release::Codename=stable \
  -o APT::FTPArchive::Release::Architectures="all amd64 arm64 armhf" \
  -o APT::FTPArchive::Release::Components=main \
  release dists/stable > dists/stable/Release
if [ -n "$KEY" ]; then
  gpg --batch --yes $GPG_OPTS --default-key "$KEY" --armor --detach-sign -o dists/stable/Release.gpg dists/stable/Release
  gpg --batch --yes $GPG_OPTS --default-key "$KEY" --clearsign -o dists/stable/InRelease dists/stable/Release
  gpg --batch --yes $GPG_OPTS --export "$KEY" > key.gpg
  gpg --batch --yes $GPG_OPTS --armor --export "$KEY" > key.asc
fi
touch .nojekyll

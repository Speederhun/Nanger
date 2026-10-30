#!/bin/sh
# One-time setup so that every nanger release is pushed to the AUR automatically
# (then `yay -Syu` updates it). Run it on your own computer (Arch), from a clone of the repo:
#   sh packaging/aur/setup-aur.sh
# Needs: ssh, git; optional: gh (GitHub CLI, logged in) to store the secret for you.
set -eu

REPO="${NANGER_REPO:-Speederhun/Nanger}"
KEY="$HOME/.ssh/aur_nanger"
HERE="$(cd "$(dirname "$0")" && pwd)"

say() { printf '\n== %s\n' "$*"; }

say "1/4  SSH key for the AUR"
if [ ! -f "$KEY" ]; then
    mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
    ssh-keygen -t ed25519 -N "" -C "nanger-aur" -f "$KEY"
fi
echo "Public key (copy ALL of it):"
echo
cat "$KEY.pub"
cat <<'T'

Now, in a browser:
  1. Register / log in at https://aur.archlinux.org/register  (confirm the e-mail address)
  2. Open "My Account" -> "SSH Public Key" and paste the key above, then save.
T
printf 'Press Enter when done... '; read -r _

say "2/4  Testing the connection"
export GIT_SSH_COMMAND="ssh -i $KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
if ! ssh -i "$KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new aur@aur.archlinux.org help >/dev/null 2>&1; then
    echo "The AUR did not accept the key. Check the key on your AUR account page and run this again."
    exit 1
fi
echo "OK"

say "3/4  Creating / updating the 'nanger' package on the AUR"
TMP="$(mktemp -d)"
git clone ssh://aur@aur.archlinux.org/nanger.git "$TMP/aur" 2>/dev/null || { git init -q "$TMP/aur"; git -C "$TMP/aur" remote add origin ssh://aur@aur.archlinux.org/nanger.git; }
cp "$HERE/PKGBUILD" "$HERE/.SRCINFO" "$TMP/aur/"
if command -v makepkg >/dev/null 2>&1; then
    (cd "$TMP/aur" && makepkg --printsrcinfo > .SRCINFO)
fi
cd "$TMP/aur"
git checkout -q -B master
git add -A
git -c user.name="${GIT_AUTHOR_NAME:-Speederhun}" -c user.email="${GIT_AUTHOR_EMAIL:-noreply@github.com}" \
    commit -qm "Initial import of nanger" || true
git push origin master
echo "Package page: https://aur.archlinux.org/packages/nanger"

say "4/4  GitHub secret for automatic updates"
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    gh secret set AUR_SSH_PRIVATE_KEY --repo "$REPO" < "$KEY"
    echo "Secret AUR_SSH_PRIVATE_KEY saved in $REPO."
else
    cat <<T
gh is not installed / not logged in. Add the secret by hand:
  https://github.com/$REPO/settings/secrets/actions/new
  Name:  AUR_SSH_PRIVATE_KEY
  Value: the whole content of  $KEY   (cat $KEY)
T
fi

cat <<'T'

Done. From the next release on, the workflow pushes the new version to the AUR and
`yay -Syu` finds it. Install it now with:  yay -S nanger
T

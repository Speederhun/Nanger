# nanger

**ranger + nano + vim in one terminal program.** A three-column file manager with a
built-in editor that is as easy as nano (Ctrl keys, always visible help bar) and has vim
power (regex replace, `:g/pat/d`, sort, shell filters, macros, undo/redo).

English and Hungarian interface · Hungarian docs: [README.hu.md](README.hu.md)

## Features

- Three-column file manager with previews: text, folders, archives, **images and PDFs**
  (real pixels in kitty / WezTerm / Ghostty / iTerm2 / sixel terminals, coloured half-blocks elsewhere, works over SSH), text preview of docx/odt/xlsx/pptx
- **Git status** in the list and a changed-lines gutter in the editor
- **Several open files**, file-changed-on-disk detection
- **Bookmarks**, **bulk rename**, **search in files** (`f`, `:grep`)
- **Mouse support** (click, double-click, wheel, clickable help bar, drag to select)
- Safe delete to the freedesktop **trash**
- Opens documents/media with the desktop's default program (`xdg-open`)
- **Colour themes** (`T`): dark, light, Solarized, Gruvbox, Nord
- **Permissions / owner** of the marked files (`P`, `O`), **side-by-side compare** (`=`, `:diff`)
- **Password-protected archives** (`Z` / `U`, .7z and .zip with AES-256, needs p7zip)
- **Remote folders over SSH** (`M` or `nanger user@host:/path`, via `sshfs`)
- **Crash recovery**: unsaved edits are snapshotted every 5 s and offered back after a crash or closed terminal
- Config file with colours, plus a **menu to change any keyboard shortcut** (`K` / `F9`)

## Install

### Debian / Ubuntu (apt repository, updates with `apt upgrade`)

```sh
curl -fsSL https://speederhun.github.io/Nanger/key.gpg | sudo tee /usr/share/keyrings/nanger.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/nanger.gpg] https://speederhun.github.io/Nanger stable main" \
  | sudo tee /etc/apt/sources.list.d/nanger.list
sudo apt update && sudo apt install nanger
```

Or download the `.deb` from the [Releases](https://github.com/Speederhun/Nanger/releases)
page and run `sudo apt install ./nanger_*.deb`. Pick the file for your device:

| Device | File |
|---|---|
| PC (Intel/AMD 64-bit) | `nanger_<version>_amd64.deb` |
| ARM 64-bit (Raspberry Pi 3/4/5, ARM servers) | `nanger_<version>_arm64.deb` |
| ARM 32-bit (older Raspberry Pi OS) | `nanger_<version>_armhf.deb` |
| any CPU | `nanger_<version>_all.deb` |

(nanger is pure Python, so all of them contain the same program. Arch Linux ARM can use the
same `PKGBUILD`; it is architecture-independent.)

### Arch Linux

Add the project's own pacman repository once (no AUR account needed), then it updates with
the system (`sudo pacman -Syu`):

```sh
sudo tee -a /etc/pacman.conf <<'EOF'

[nanger]
SigLevel = Optional TrustAll
Server = https://github.com/Speederhun/Nanger/releases/download/arch-repo
EOF
sudo pacman -Sy nanger
```

(The packages are not GPG-signed, hence `SigLevel = Optional TrustAll`; the download is HTTPS
from this repository.) Or build it yourself: `cd packaging/arch && makepkg -f && sudo pacman -U nanger-*.pkg.tar.zst`.

### macOS (Homebrew)

```sh
brew tap Speederhun/nanger https://github.com/Speederhun/Nanger
brew install nanger
```

(For a private repository Homebrew needs git access: `gh auth login` or a
`HOMEBREW_GITHUB_API_TOKEN`.) Without Homebrew: `sudo make install PREFIX=/usr/local`.
In Terminal.app use *Settings → Profiles → Keyboard → Use Option as Meta key* for Alt shortcuts.

### From source

```sh
sudo make install        # PREFIX=/usr/local to change
```

## Update

| Installed with | Update |
|---|---|
| apt repository | `sudo apt update && sudo apt upgrade` |
| downloaded `.deb` | `sudo apt install ./nanger_<new>_all.deb` |
| pacman repository / AUR | `sudo pacman -Syu` / `yay -Syu` |
| Homebrew (macOS) | `brew update && brew upgrade nanger` |
| `makepkg` / `make install` | pull, then run it again |

## Stay in the folder after quitting

A program cannot change the folder of the shell that started it, so install the tiny shell
function once:

```sh
nanger --install-shell     # bash, zsh or fish; then open a new terminal
```

After that, quitting `nanger` leaves your terminal in the folder you were browsing.

## Optional dependencies

`python3-pil` (image/PDF preview), `poppler-utils` (PDF), `git` (status), `xdg-utils`
(external open), `xclip` / `wl-clipboard` (system clipboard).

## Keys

`?` in the file manager and `F1` in the editor show all keys. Main ones:

| File manager | |
|---|---|
| Enter / → / ← | open / parent folder |
| `n` `N` `r` `R` `D` | new file, new folder, rename, bulk rename, delete |
| `y` `x` `p` `Space` | copy, cut, paste, mark |
| `/` `f` | find by name / grep in files |
| `m` `'` | set / jump to bookmark |
| `s` | sort menu: `n` name, `d` date, `s` size, `e` extension, `r` reverse |
| `.` `v` `o` | hidden files, built-in viewer, external open |
| `P` `O` | permissions (`chmod`) / owner (`chown`) of the marked files (sudo offered if needed) |
| `=` | compare two marked files side by side (editor: `:diff` = buffer vs. disk) |
| `M` | connect to `user@host:/path` over SSH (needs `sshfs`; also `nanger user@host:/path`) |
| `F` | quick filter: type to narrow the list |
| `w` `Tab` `C` `W` | two panels; switch panel; copy / move to the other panel |
| `Ctrl+T` `Ctrl+W` `[` `]` | new tab, close tab, previous / next tab (`Alt+1`…`9` jumps) |
| `T` | colour themes: dark, light, solarized-dark/light, gruvbox, nord, hacker (green on black) (saved) |

| Editor | |
|---|---|
| Ctrl+S / Ctrl+Q | save / close |
| Ctrl+F, Ctrl+N, Ctrl+R, Ctrl+G | find, next, replace, go to line |
| Ctrl+P | command line: `%s/a/b/g`, `g/pat/d`, `sort`, `!cmd`, `:grep`, `:e file` |
| Alt+←/→, F4 | switch files / file manager |

## Configuration

`nanger --init-config` creates `~/.config/nanger/config.ini`. Language: `NANGER_LANG=en|hu`.

## Development

```sh
pip install -r requirements-dev.txt && pytest -q tests
sh packaging/debian/build-deb.sh
```

## Maintainer notes: publishing updates

Releases are automatic: bump `__version__` in `nanger/__init__.py`, add a `CHANGELOG.md`
section and push to `main`. The *release* workflow creates the GitHub release with the
`.deb`, and (if the secrets exist) publishes the apt repository to the `gh-pages` branch and
updates the AUR package.

One-time setup for the apt repository:

1. `gpg --quick-gen-key "nanger repo" rsa3072 sign never`, then
   `gpg --armor --export-secret-keys <ID>` → repository secret `APT_GPG_PRIVATE_KEY`
   (passphrase, if any → `APT_GPG_PASSPHRASE`).
2. Run the workflow once, then *Settings → Pages → Deploy from branch → `gh-pages`*.
   GitHub Pages needs a public repository (or a paid plan for private ones).
3. For the AUR: create the `nanger` package there once and put an SSH key in `AUR_SSH_PRIVATE_KEY`.

## License

MIT

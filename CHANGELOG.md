# Changelog

## 1.10.1

- On exit, if the shell is not set up to follow you (no `nanger --install-shell` yet), a hint with the detected shell is printed.

## 1.10.0

- **Colour themes**: `T` (or `:theme NAME`) switches between dark, light, solarized-dark,
  solarized-light, gruvbox and nord; the choice is saved (`theme =` in the config). Needs a
  256-colour terminal; your own `[colors]` still win.
- **Permissions and owner** on the marked files: `P` (chmod: `644`, `u+x`, `-R 755`) and `O`
  (chown: `user`, `user:group`, `:group`); offers `sudo` when the change is not permitted.
- **Side-by-side compare**: `=` on two marked files (or one marked + the current one), and
  `:diff` / `:diff FILE` in the editor (buffer against the file on disk). `n`/`N` jump between changes.
- **Remote folders over SSH**: `M`, or `nanger user@host:/path` / `sftp://user@host/path`, mount
  the folder with `sshfs` (SSH keys only); it is unmounted on exit or with `M` + empty line.
- **Autosave and crash recovery**: modified files are snapshotted every 5 s
  (`~/.local/share/nanger/recovery`, `NANGER_AUTOSAVE=seconds`); closing the terminal or `kill`
  saves at once; reopening the file offers to restore. A normal quit/discard removes the snapshot.

## 1.9.1

- Archive previews are read in the background (no lag while moving over big archives or
  `.7z`/`.tar.gz` files); `.7z`/`.rar`/`.iso` listings now look like zip listings (size + name).

## 1.9.0

- **The shell stays in the folder where you quit.** A program cannot change its parent shell's
  folder, so run `nanger --install-shell` once (adds a small function to `~/.bashrc`,
  `~/.zshrc` or fish's `config.fish`); after a new terminal is opened, `nanger` leaves the shell
  in the folder you were in. Manual setup: `eval "$(command nanger --shell-init bash)"`.
  `--choosedir=FILE` writes the final folder to a file (for other wrappers).

## 1.8.2

- Folders are listed without a trailing `/` (they keep their colour).
- File sizes are aligned in a column: numbers right-aligned, units one under another.

## 1.8.1

- `nanger --doctor` shows why previews/colours do not work (Python, Pillow, locale, terminal,
  graphics protocol, helper tools).
- Falls back to a UTF-8 locale when `LANG` is missing (macOS/SSH), which previously disabled
  image previews.
- Homebrew formula uses the default `python`, so it always matches Homebrew's `pillow`.

## 1.8.0

- **Pack / extract:** mark files with Space, `Z` packs them (`.7z` needs p7zip; `.zip`, `.tar.gz`,
  `.tar.bz2`, `.tar.xz` work without extra tools), `U` extracts into a folder of the same
  name (paths escaping the folder are refused). Both keys can be changed in the shortcut menu.
- **Select all** (`a`, again = clear) and **invert selection** (`A`).
- **Folder size:** `i` shows the size, file and folder count of the marked items / current item.
- **Bottom-right status line:** number of files and folders in the current folder; with marks
  it shows how many are selected and their total size (folders counted recursively).
- Fixed: a two-key shortcut that starts with the old key (e.g. `y` -> `yy`) did not work.

## 1.7.0

- `zh` shows/hides hidden files (like ranger; `.` still works).
- **Two-key shortcuts:** the shortcut menu accepts one or two keys (e.g. `g` `i`); saved as
  `g i = .` in the config.
- **Archives in purple** (zip, 7z, rar, tar, gz, iso, deb, ...), colour `archive` in the config;
  7z/rar/iso contents are listed when `bsdtar` or `7z` is installed.
- **Mouse rewritten:** wheel down works everywhere, drag selects text in the editor,
  the side **back button** goes to the previous folder (forward button: next), Alt+Left/Right
  does the same in the file manager.

## 1.6.0

- **macOS support:** Homebrew formula (`brew tap Speederhun/nanger https://github.com/Speederhun/Nanger`,
  `brew install nanger`), `open` instead of `xdg-open`, `pbcopy` clipboard, trash into `~/.Trash`,
  Option+arrows, portable `make install`.
- **Sort menu:** `s` asks `n` name, `d` date, `s` size, `e` extension, `r` reverse (pressing the
  current key again also reverses). Folders always stay on top. `sort_reverse` in the config.

## 1.5.0

- **Mouse support:** click to select, double-click to open, wheel to scroll, right-click for
  back, click the help-bar entries (`^S Save`, `F9 Customize`, ...), click/drag/double-click
  in the editor to place the cursor, select text or select a word. Click a folder in the
  left column to jump there. Turn off with `mouse = no` in the config (or `NANGER_MOUSE=0`);
  hold Shift to select text with the terminal itself.
- `F9 Customize` is shown in the help bar (file manager and editor).
- **ARM packages:** every release now has separate `amd64`, `arm64` (Raspberry Pi 3/4/5, ARM
  servers), `armhf` (32-bit Raspberry Pi OS) and universal `all` `.deb` files plus `SHA256SUMS`.
  The apt repository serves the universal package, which works on every architecture.

## 1.4.0

- **Keyboard shortcut menu:** `K` (file manager), `F9` or `:keys` (editor) lists the actions
  with their keys. Enter changes a key (if it is taken, the two actions swap), Del resets it.
  Saved to `~/.config/nanger/config.ini` (`[keys.browser]` / `[keys.editor]`).

## 1.3.0

- **Sharp image and PDF previews with real pixels** in terminals that support it:
  kitty graphics protocol (kitty, WezTerm, Ghostty), iTerm2 inline images and sixel (foot,
  mlterm, ...). Detected automatically; override with `graphics = kitty|iterm|sixel|blocks`
  in the config or `NANGER_GRAPHICS`. Other terminals keep the coloured-block preview.
- **Text preview for Office documents** (docx, odt, xlsx, ods, pptx, odp) in the file manager.

## 1.2.1

- Sharper image and PDF previews: **24-bit true colour** when the terminal supports it
  (`COLORTERM=truecolor`; set `NANGER_TRUECOLOR=0` to disable) and Floyd-Steinberg
  dithering in 256-colour terminals (no more streaky skies).

## 1.2.0

- **Git integration:** status letters in the file list (M/A/?/D/!) and a changed-lines
  gutter in the editor (`+` added, `~` changed, `_` deleted above).
- **Several open files** (tabs): Alt+Left/Right, Alt+1..9, `F4`/Ctrl+E to the file manager,
  `:ls`, `:b N`, `:bn`, `:bp`. Warning/reload when a file changes on disk.
- **Bookmarks:** `m` + key sets, `'` + key jumps (`''` previous folder, `'?` list).
- **Bulk rename:** `R` opens the names in the editor; save and close to apply (with rollback).
- **Search in files:** `f` in the file manager or `:grep PATTERN` in the editor; Enter opens
  the file at the matching line. `nanger +N FILE` opens at a line.
- **Configuration file** (`nanger --init-config`): colours, tab width, line numbers, sorting,
  git on/off, key remapping, language.
- **English and Hungarian interface** (`NANGER_LANG=en|hu`, default from the locale).
- Code split into a Python package (`/usr/share/nanger`), Hungarian and English man pages.
- **Updates through apt:** signed apt repository on GitHub Pages and an AUR package,
  both published automatically by the release workflow.

## 1.1.0

- Image and PDF previews (coloured half-blocks), open by file type (`xdg-open`),
  built-in image/PDF viewer, archive listings, freedesktop trash, sorting, tests and CI.

## 1.0.0

- First release: ranger-like file manager, nano-easy editor, vim-like command line,
  macros, `.deb` and Arch packaging.

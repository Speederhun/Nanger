# Changelog

## 1.0.0

First stable release.

**File manager**
- Three-column view with previews: text, folders, archives (read in the background), images and
  PDFs (real pixels in kitty / WezTerm / Ghostty / iTerm2 / sixel terminals, coloured half-blocks
  elsewhere), text preview of docx / odt / xlsx / pptx
- Git status in the list, folder sizes, selection (Space, select all, invert), sort menu
  (name, date, size, extension, reverse), hidden files (`.` / `zh`), bookmarks, bulk rename,
  search by name and in file contents, safe delete to the trash
- Compress / extract `.7z`, `.zip`, `.tar.*` (password-protected `.7z` / `.zip` with AES-256)
- Permissions and owner of the selection (`P`, `O`), side-by-side compare (`=`)
- Quick filter (`F`), tabs (`Ctrl+T`, `Ctrl+W`, `[` `]`), two panels (`w`, `Tab`, `C` / `W`)
- Remote folders over SSH with `sshfs` (keys or password): `M` or `nanger user@host:/path`
- Mouse: click, double-click, wheel, back / forward buttons, clickable help bar
- The shell can follow you to the folder you quit in (`nanger --install-shell`)

**Editor**
- As easy as nano (Ctrl keys, always visible help bar) with vim power: regex replace,
  `:g/pat/d`, sort, shell filters, macros, undo / redo, several open files, git gutter,
  file-changed-on-disk detection, mouse selection
- Side-by-side diff against the file on disk (`:diff`)
- Autosave and crash recovery (snapshots every 5 s, restore offered on reopening)

**Customisation**
- Colour themes (`T`): default, dark, light, solarized-dark/light, gruvbox, nord, hacker
- Menu to change any keyboard shortcut, including two-key sequences (`K` / `F9`)
- Config file, English and Hungarian interface (`NANGER_LANG=en|hu`)

**Packaging**
- Debian / Ubuntu `.deb` (all, amd64, arm64, armhf), signed apt repository (optional),
  Arch Linux pacman repository, `PKGBUILD`, Homebrew formula (macOS)
- `nanger --doctor` checks why previews or colours do not work

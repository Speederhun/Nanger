# Changelog

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

# nanger

**ranger + nano + vim egyben, terminálban.** Háromoszlopos fájlkezelő beépített
szerkesztővel, amely olyan egyszerű, mint a nano (Ctrl-billentyűk, mindig látható súgósor),
de tud vim-es dolgokat is (regex-csere, `:g/minta/d`, rendezés, szűrés shell-parancson,
makrók, visszavonás).

## Funkciók

- Háromoszlopos fájlkezelő előnézettel: szöveg, mappák, archívumok, **képek és PDF-ek**,
  docx/odt/xlsx/pptx szövegesen; git-állapot a listában és a szerkesztő szélén
- **Gyors szűrő** (`F`), **fülek** (`Ctrl+T`), **osztott panel** (`w`), könyvjelzők, tömeges átnevezés,
  keresés névre és fájltartalomra, kukába törlés
- **Csomagolás / kicsomagolás** (`.7z`, `.zip`, `.tar.*`), jelszóval védett archívumok (AES-256)
- **Jogosultság és tulajdonos** (`P`, `O`), **összehasonlítás** egymás mellett (`=`, `:diff`)
- **Távoli mappák SSH-n** (`M`, vagy `nanger user@host:/mappa`; kulcs vagy jelszó, `sshfs` kell)
- **Automatikus mentés és helyreállítás** a szerkesztőben
- **Színtémák** (`T`: sötét, világos, Solarized, Gruvbox, Nord, hacker), minden billentyű átállítható (`K` / `F9`)
- Egér, magyar és angol felület, a shell követi a mappát kilépéskor (`nanger --install-shell`)

## Telepítés

### Debian / Ubuntu (apt-tároló – `apt upgrade` frissíti)

```sh
curl -fsSL https://speederhun.github.io/Nanger/key.gpg | sudo tee /usr/share/keyrings/nanger.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/nanger.gpg] https://speederhun.github.io/Nanger stable main" \
  | sudo tee /etc/apt/sources.list.d/nanger.list
sudo apt update && sudo apt install nanger
```

Vagy a [Releases](https://github.com/Speederhun/Nanger/releases) oldalról a `.deb`:
`sudo apt install ./nanger_*_all.deb`

### Arch Linux

A projekt saját pacman-tárolóját add hozzá egyszer (AUR-fiók nem kell), utána a rendszerrel együtt
frissül (`sudo pacman -Syu`):

```sh
sudo tee -a /etc/pacman.conf <<'EOF'

[nanger]
SigLevel = Optional TrustAll
Server = https://github.com/Speederhun/Nanger/releases/download/arch-repo
EOF
sudo pacman -Sy nanger
```

(A csomagok nincsenek GPG-vel aláírva, ezért kell a `SigLevel = Optional TrustAll`; a letöltés HTTPS-en
megy a repóból.) Vagy építsd magad: `cd packaging/arch && makepkg -f && sudo pacman -U nanger-*.pkg.tar.zst`.

### macOS (Homebrew)

```sh
brew tap Speederhun/nanger https://github.com/Speederhun/Nanger
brew trust speederhun/nanger     # Homebrew 6+: harmadik fél tapját előbb meg kell bízni
brew install nanger
```

(A `brew trust` lépés nélkül az újabb Homebrew nem telepít harmadik fél tapjából.) Frissítés:
`brew update && brew upgrade nanger`. Homebrew nélkül: `sudo make install PREFIX=/usr/local`.
A Terminal.appban az Alt-gyorsbillentyűkhöz: *Beállítások → Profilok → Billentyűzet → Option használata Meta billentyűként*.

### Forrásból

```sh
sudo make install
```

## Frissítés

| Telepítés módja | Frissítés |
|---|---|
| apt-tároló | `sudo apt update && sudo apt upgrade` |
| letöltött `.deb` | `sudo apt install ./nanger_<új>_all.deb` (felülírja a régit) |
| pacman-tároló / AUR | `sudo pacman -Syu` / `yay -Syu` |
| `makepkg` / `make install` | `git pull`, majd újra |

## Használat

Az összes billentyűt a `?` (fájlkezelő) és az `F1` (szerkesztő) mutatja. A felület nyelve:
`NANGER_LANG=hu` (alapból a rendszer nyelve). Beállítófájl: `nanger --init-config`.

Opcionális csomagok: `python3-pil`, `poppler-utils`, `git`, `xdg-utils`, `xclip`/`wl-clipboard`.

## Kiadás (karbantartóknak)

Verziót emelni az `nanger/__init__.py`-ban kell, a `CHANGELOG.md`-be új szakasz, és
`git push` a `main` ágra: a *release* workflow elkészíti a kiadást és a `.deb`-et, és –
ha be vannak állítva a titkok – kiteszi az apt-tárolót (`gh-pages` ág) és frissíti az AUR-t.
Az apt-tároló egyszeri beállítása az angol README végén van (GPG-kulcs mint `APT_GPG_PRIVATE_KEY`
titok, majd Settings → Pages → `gh-pages`; privát tárolónál a Pages fizetős csomagot kér).

## Licenc

MIT

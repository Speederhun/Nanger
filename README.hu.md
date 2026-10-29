# nanger

**ranger + nano + vim egyben, terminálban.** Háromoszlopos fájlkezelő beépített
szerkesztővel, amely olyan egyszerű, mint a nano (Ctrl-billentyűk, mindig látható súgósor),
de tud vim-es dolgokat is (regex-csere, `:g/minta/d`, rendezés, szűrés shell-parancson,
makrók, visszavonás).

## Újdonságok az 1.11-ben

gyors szűrő (`F`), fülek (`Ctrl+T`, `Ctrl+W`, `[` `]`, `Alt+1…9`), osztott panel (`w`, `Tab` vált,
`C`/`W` másol/mozgat a másik panelre), valamint kikötetlen ugrás-akciók a temp / home / gyökér
mappába (a `K` / `F9` menüben rendelhetsz hozzájuk billentyűt).

## Újdonságok az 1.10-ben

színtémák (`T`: sötét, világos, Solarized, Gruvbox, Nord), jogosultság és tulajdonos a kijelölteken
(`P`, `O`), fájl-összehasonlítás egymás mellett (`=`, szerkesztőben `:diff`), távoli mappák SSH-n
(`M` vagy `nanger user@host:/mappa`, `sshfs` kell), automatikus mentés és helyreállítás
(5 mp-enként pillanatkép; összeomlás vagy bezárt terminál után visszakérdez).

## Újdonságok az 1.2-ben

git-állapot a listában és a szerkesztő szélén, több megnyitott fájl (fülek), könyvjelzők
(`m`, `'`), tömeges átnevezés (`R`), keresés a fájlokban (`f`, `:grep`), beállítófájl,
angol és magyar felület, frissítés `apt upgrade`-del.

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

```sh
yay -S nanger                       # AUR
cd packaging/arch && makepkg -si    # vagy innen
```

### Forrásból

```sh
sudo make install
```

## Frissítés

| Telepítés módja | Frissítés |
|---|---|
| apt-tároló | `sudo apt update && sudo apt upgrade` |
| letöltött `.deb` | `sudo apt install ./nanger_<új>_all.deb` (felülírja a régit) |
| AUR | `yay -Syu` |
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

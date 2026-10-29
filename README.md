# nanger

**Fájlkezelő és szövegszerkesztő egyben: ranger + nano + vim.**

- **Olyan, mint a ranger:** háromoszlopos fájlkezelő (szülő mappa │ aktuális │ előnézet).
- **Olyan egyszerű, mint a nano:** Ctrl-billentyűk, és alul mindig látszik, mi mit csinál.
- **Annyit tud, mint a vim:** regex-csere, sorok törlése minta alapján, rendezés,
  szűrés shell-parancson át, makrók, visszavonás/újra.

- **Mindent megnyit:** szöveget a szerkesztőben, képet és PDF-et előnézettel (a harmadik
  oszlopban), dokumentumot, hangot és videót a rendszer alapértelmezett programjával.
  Grafikus felület nélkül (SSH) a beépített kép- és PDF-nézegető működik.
- **Biztonságos:** törlés a kukába megy (visszaállítható).

Szerkesztéshez és fájlkezeléshez csak Python 3 kell, külső csomag nem. Az előnézetekhez
opcionális csomagok vannak (lásd lent), a `.deb` ezeket magától telepíti.

```
 nanger │ ~/projekt
 docs/          │ src/                          │ main.py
 projekt/       │ tests/                        │ util.py
                │ README.md                4.1K │
                │ setup.py                 1.2K │
 -rw-r--r--  4.1K  2026-10-29 09:09   3/4
Enter Megnyit  ← Vissza  n Új fájl  N Új mappa  r Átnevez  D Töröl  / Keres  q Kilép
Szóköz Jelöl  y Másol  x Kivág  p Beilleszt  . Rejtett  c Ugrás  S Shell  ? Súgó
```

## Telepítés

### Debian, Ubuntu, Linux Mint (apt)

Töltsd le a `nanger_<verzió>_all.deb` fájlt a [Releases](https://github.com/Speederhun/Nanger/releases)
oldalról, majd:

```sh
sudo apt install ./nanger_1.0.0_all.deb
```

Eltávolítás: `sudo apt remove nanger`

Az `apt` a javasolt csomagokat (`python3-pil`, `poppler-utils`, `xdg-utils`) is felteszi,
ezekkel működik a kép- és PDF-előnézet.

### Arch, Manjaro (pacman)

```sh
git clone https://github.com/Speederhun/Nanger.git
cd Nanger/packaging/arch
makepkg -si
```

Eltávolítás: `sudo pacman -R nanger`

Az előnézetekhez: `sudo pacman -S python-pillow poppler xdg-utils`

### Bármely más Linux

```sh
git clone https://github.com/Speederhun/Nanger.git
cd Nanger
sudo make install          # eltávolítás: sudo make uninstall
```

## Használat

```sh
nanger                # fájlkezelő az aktuális mappában
nanger ~/projekt      # fájlkezelő a megadott mappában
nanger jegyzet.txt    # a fájl azonnali szerkesztése
man nanger            # kézikönyv
```

A programon belül a **?** (fájlkezelő) vagy az **F1** (szerkesztő) mutatja az összes billentyűt.

### Fájlkezelő

| Billentyű | Művelet |
|---|---|
| ↑ ↓ / `k` `j` | mozgás |
| ← / `h` / Backspace | szülő mappa |
| → / `l` / Enter | mappába lépés / fájl megnyitása típus szerint (lásd lent) |
| `v` | megnyitás a beépített nézegetőben (kép, PDF) |
| `o` | megnyitás külső programmal (`xdg-open`) |
| `s` | rendezés váltása: név → méret → dátum → kiterjesztés |
| `n` / `N` | új fájl / új mappa |
| `r` | átnevezés |
| `D` / Delete | törlés: `t` = kukába, `d` = végleges (kétszer kell megerősíteni) |
| Szóköz | megjelölés (több fájl egyszerre) |
| `y` / `x` / `p` | másolás / kivágás / beillesztés |
| `/` | keresés név alapján |
| `.` | rejtett fájlok |
| `c` | ugrás egy elérési útra |
| `S` / `!` | shell ebben a mappában / egy parancs futtatása |
| `q` | kilépés |

### Előnézet és megnyitás

| Fájltípus | Előnézet (harmadik oszlop) | Enter |
|---|---|---|
| szöveg, forráskód | az első sorok | szerkesztő |
| kép (png, jpg, gif, webp, …) | színes rajz a képről | külső program; grafikus felület nélkül a beépített nézegető |
| PDF | az első oldal rajza | külső program; grafikus felület nélkül a beépített nézegető |
| zip, tar, tar.gz, … | tartalomjegyzék | külső program; grafikus felület nélkül lapozható lista |
| docx, odt, xlsx, mp3, mp4, … | méret és tipp | külső program (`xdg-open`) |
| mappa | a tartalma | belépés |

Az előnézet félblokkos karakterekkel készül, ezért szabványos 256 színű UTF-8
terminálban (SSH-n és tmux-ban is) működik, külön grafikus protokoll nélkül. Kép előnézetéhez a **Pillow**, PDF-hez emellett a
**poppler-utils** kell; ha nincs meg, a PDF-nél legalább az első oldal szövege látszik.

A beépített nézegetőben (`v`, vagy Enter grafikus felület nélkül): ←/→ a mappa képei
vagy a PDF oldalai között lapoz, `t` PDF-nél szöveg és kép között vált, `o` külső
programmal nyit, `q` visszalép.

### Szerkesztő

| Billentyű | Művelet |
|---|---|
| Ctrl+S / Ctrl+O | mentés / mentés másként |
| Ctrl+Q | bezárás (vissza a fájlkezelőbe) |
| Ctrl+F / Ctrl+N | keresés / következő találat |
| Ctrl+R | csere (regex) |
| Ctrl+G | ugrás sorra (`120` vagy `120:5`) |
| Ctrl+Z / Ctrl+Y | visszavonás / újra |
| Shift+nyilak, Ctrl+B, Ctrl+A | kijelölés |
| Ctrl+C / Ctrl+K / Ctrl+V | másolás / kivágás / beillesztés |
| Ctrl+D | sor duplikálása |
| Tab / Shift+Tab | kijelölt sorok be- / kihúzása |
| F5 / F6 | makró felvétele / lejátszása |
| Ctrl+P | parancssor (lásd lent) |

### Parancssor (Ctrl+P) — a vim `:` parancsai

| Parancs | Művelet |
|---|---|
| `w`, `q`, `q!`, `wq` | mentés, kilépés, kilépés mentés nélkül, mindkettő |
| `120`, `$` | ugrás a 120. / utolsó sorra |
| `s/régi/új/g` | csere az aktuális vagy a kijelölt sorokban |
| `%s/régi/új/gi` | csere az egész fájlban (`i` = kis/nagybetű mindegy) |
| `10,20s/a/b/g` | csere a 10–20. sorban |
| `g/minta/d`, `v/minta/d` | illeszkedő / nem illeszkedő sorok törlése |
| `sort`, `sort!`, `uniq` | rendezés, fordított rendezés, ismétlődők törlése |
| `upper`, `lower` | nagy- / kisbetűsítés |
| `!parancs` | a kijelölt sorok átszűrése (pl. `!sort -n`) |
| `r !parancs` | a parancs kimenetének beszúrása |
| `@ 20` | a makró lejátszása 20-szer |
| `e fájl` | másik fájl megnyitása |

## Fejlesztés

```sh
pip install -r requirements-dev.txt     # pytest, pexpect, pyte, pillow
sudo apt install poppler-utils          # a PDF-tesztekhez
make test                               # a tesztek valódi pszeudo-terminálban futnak
make deb                                # .deb építése a dist/ mappába
```

A tesztek (`tests/`) a programot egy valódi terminálban indítják, billentyűket küldenek
neki, és a képernyőt meg a lemezen történt változásokat ellenőrzik. A GitHub Actions
minden push-nál lefuttatja őket Python 3.8–3.13 alatt, és kipróbálja a `.deb`
telepítését és eltávolítását is.

## Új verzió kiadása

1. Írd át a verziót a `nanger` fájlban (`VERSION = "..."`), a `packaging/arch/PKGBUILD`-ben
   (`pkgver`), a `nanger.1`-ben, és vezesd be a `CHANGELOG.md`-be.
2. Címkézd meg és töltsd fel:
   ```sh
   git tag v1.0.1 && git push origin v1.0.1
   ```
3. A GitHub Actions automatikusan megépíti a `.deb`-et és közzéteszi a Releases oldalon.

## Licenc

MIT

# nanger

**Fájlkezelő és szövegszerkesztő egyben: ranger + nano + vim.**

- **Olyan, mint a ranger:** háromoszlopos fájlkezelő (szülő mappa │ aktuális │ előnézet).
- **Olyan egyszerű, mint a nano:** Ctrl-billentyűk, és alul mindig látszik, mi mit csinál.
- **Annyit tud, mint a vim:** regex-csere, sorok törlése minta alapján, rendezés,
  szűrés shell-parancson át, makrók, visszavonás/újra.

Csak Python 3 kell hozzá, külső csomag nem.

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

### Arch, Manjaro (pacman)

```sh
git clone https://github.com/Speederhun/Nanger.git
cd Nanger/packaging/arch
makepkg -si
```

Eltávolítás: `sudo pacman -R nanger`

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
| → / `l` / Enter | mappába lépés / fájl szerkesztése |
| `n` / `N` | új fájl / új mappa |
| `r` | átnevezés |
| `D` / Delete | törlés (megerősítéssel) |
| Szóköz | megjelölés (több fájl egyszerre) |
| `y` / `x` / `p` | másolás / kivágás / beillesztés |
| `/` | keresés név alapján |
| `.` | rejtett fájlok |
| `c` | ugrás egy elérési útra |
| `S` / `!` | shell ebben a mappában / egy parancs futtatása |
| `q` | kilépés |

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

## Új verzió kiadása

1. Írd át a verziót a `nanger` fájlban (`VERSION = "..."`) és a `packaging/arch/PKGBUILD`-ben (`pkgver`).
2. Címkézd meg és töltsd fel:
   ```sh
   git tag v1.0.1 && git push origin v1.0.1
   ```
3. A GitHub Actions automatikusan megépíti a `.deb`-et és közzéteszi a Releases oldalon.

## Licenc

MIT

# Változások

## 1.1.0

- **Kép- és PDF-előnézet** a harmadik oszlopban (színes félblokkos rajz, bármely
  256 színű UTF-8 terminálban működik).
- **Típus szerinti megnyitás:** Enter szövegnél a szerkesztőt, képnél/PDF-nél/dokumentumnál
  a rendszer alapértelmezett programját nyitja (`xdg-open`); grafikus felület nélkül
  (SSH, konzol) a beépített nézegetőt.
- **Beépített nézegető** képekhez és PDF-ekhez: lapozás a mappa képei / a PDF oldalai
  között, PDF-nél szöveges és képes mód (`t`).
- **Archívum-előnézet:** zip és tar (gz/bz2/xz) tartalomjegyzéke.
- **Törlés a kukába** (szabványos freedesktop.org kuka); végleges törlés kétszeri
  megerősítéssel.
- **Rendezés** váltása (`s`): név, méret, dátum, kiterjesztés.
- Automata tesztek (pytest, pszeudo-terminállal) és CI.

## 1.0.0

- Első kiadás: ranger-szerű fájlkezelő, nano-egyszerű szerkesztő, vim-szerű
  parancssor (`Ctrl+P`), makrók, `.deb` és Arch csomagolás.

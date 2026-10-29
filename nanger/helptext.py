"""Full-screen help pages (English and Hungarian)."""
from .i18n import language

EDITOR_EN = """\
nanger — EDITOR                                    (any key: back)

BASICS (like nano)
  Ctrl+S   save                Ctrl+O   save as
  Ctrl+Q   close this file (Ctrl+X works too)
  Ctrl+F   search              Ctrl+N / F3  next match
  Ctrl+R   replace (regex)     Ctrl+G   go to line (e.g. 120 or 120:5)
  Ctrl+Z   undo                Ctrl+Y   redo
  Ctrl+L   line numbers on/off Esc      clear the selection
  F9 or :keys   change the keyboard shortcuts (menu)

SELECTION AND CLIPBOARD
  Shift+arrows   select         Ctrl+B   selection mode on/off (grows with the arrows)
  Ctrl+A   select all          Ctrl+C   copy (without selection: the line)
  Ctrl+K   cut (repeated Ctrl+K collects several lines)
  Ctrl+V   paste (Ctrl+U too)  Ctrl+D   duplicate the line
  Tab / Shift+Tab   indent / unindent the selected lines

SEVERAL FILES
  Alt+Left / Alt+Right, Alt+1..9   switch between the open files
  F4 or Ctrl+E   back to the file manager (the files stay open)
  :ls   list the open files    :b N   go to file N    :bn / :bp   next / previous

MACROS (vim power)
  F5   start / stop recording             F6   play
  :@ 20   play the macro 20 times

COMMAND LINE — Ctrl+P (or F2), like vim's ":"
  w [file]   save            q / q!   close / close without saving     wq   save + close
  120        go to line 120               $   last line
  s/old/new/g       replace on the current line (or in the selected lines)
  %s/old/new/gi     replace in the whole file (g = all, i = ignore case)
  10,20s/a/b/g      replace in lines 10-20        (\\1, \\g<0> back-references)
  g/pattern/d   delete the matching lines     v/pattern/d  delete the non-matching ones
  sort  sort!  uniq      sort / reverse sort / remove repeated lines
  upper  lower           change case (selection or line)
  !command   filter the selection through a shell command (e.g. !sort -n); without a
             selection: run the command and show its output
  r !command   insert the output of the command below the line
  e file     open another file     e! reload from disk     set nu / set nonu   line numbers
  grep PATTERN   search the files under the current folder (lower case = ignore case)
  copen          show the last search results again
  browse         back to the file manager

GIT
  Changed lines are marked in the left margin: + added  ~ changed  _ lines deleted above.
"""

EDITOR_HU = """\
nanger — SZERKESZTŐ                                (bármely billentyű: vissza)

ALAPOK (mint a nano)
  Ctrl+S   mentés              Ctrl+O   mentés másként
  Ctrl+Q   a fájl bezárása (Ctrl+X is jó)
  Ctrl+F   keresés             Ctrl+N / F3  következő találat
  Ctrl+R   csere (regex)       Ctrl+G   ugrás sorra (pl. 120 vagy 120:5)
  Ctrl+Z   visszavonás         Ctrl+Y   újra
  Ctrl+L   sorszámok be/ki     Esc      kijelölés megszüntetése
  F9 vagy :keys   gyorsbillentyűk módosítása

KIJELÖLÉS ÉS VÁGÓLAP
  Shift+nyilak   kijelölés      Ctrl+B   kijelölés-mód be/ki (nyilakkal bővül)
  Ctrl+A   mindent kijelöl     Ctrl+C   másol (kijelölés nélkül: a sort)
  Ctrl+K   kivág (egymás után több sort is gyűjt)
  Ctrl+V   beilleszt (Ctrl+U is)  Ctrl+D   sor duplikálása
  Tab / Shift+Tab   kijelölt sorok be- / kihúzása

TÖBB FÁJL
  Alt+Bal / Alt+Jobb, Alt+1..9   váltás a megnyitott fájlok között
  F4 vagy Ctrl+E   vissza a fájlkezelőbe (a fájlok nyitva maradnak)
  :ls   a megnyitott fájlok listája    :b N   ugrás az N. fájlra    :bn / :bp   következő / előző

MAKRÓK (vim-erő)
  F5   felvétel indítása / leállítása     F6   lejátszás
  :@ 20   a makró lejátszása 20-szor

PARANCSSOR — Ctrl+P (vagy F2), mint a vim ":" parancsa
  w [fájl]   mentés          q / q!   bezárás / mentés nélkül      wq   mentés+bezárás
  120        ugrás a 120. sorra           $   utolsó sor
  s/régi/új/g       csere az aktuális soron (vagy a kijelölt sorokon)
  %s/régi/új/gi     csere az egész fájlban (g = mind, i = kis/nagybetű mindegy)
  10,20s/a/b/g      csere a 10–20. sorban       (\\1, \\g<0> visszahivatkozás)
  g/minta/d   a mintára illő sorok törlése   v/minta/d  a nem illők törlése
  sort  sort!  uniq      rendezés / fordítva / ismétlődő sorok törlése
  upper  lower           kis/nagybetűsítés (kijelölés vagy sor)
  !parancs   kijelölés átszűrése shell-parancson (pl. !sort -n), kijelölés
             nélkül: a parancs futtatása és a kimenet megmutatása
  r !parancs   a parancs kimenetének beszúrása a sor alá
  e fájl     másik fájl megnyitása   e!  újratöltés lemezről   set nu / set nonu   sorszámok
  grep MINTA   keresés az aktuális mappa fájljaiban (csupa kisbetű: kis/nagybetű mindegy)
  copen        az utolsó keresés találatai újra
  browse       vissza a fájlkezelőbe

GIT
  A megváltozott sorokat a bal margó jelzi: + új  ~ módosított  _ fölötte törölt sorok.
"""

BROWSER_EN = """\
nanger — FILE MANAGER                              (any key: back)

MOVING (arrows or vim keys)
  Up Down  or  k j       up / down          PgUp PgDn   page
  Left  or  h  or Backspace   parent folder
  Right or  l  or Enter       enter a folder / open a file by its type
  g / G   top / bottom of the list          ~   home folder
  c       jump to a typed path              /   search by name
  Space   mark    a   mark / unmark all    A   invert the marks
  Z   pack the marked files (or the current one) into .7z / .zip / .tar.gz
  U   extract the archive(s) into a folder of the same name
  i   size of the marked items / current folder
  P   permissions (chmod) of the marked items: 644, u+x, a-w; add -R for folders
  O   owner (chown): user, user:group, :group  (offers sudo when not permitted)
  =   compare two marked files (or the marked one with the current one), side by side
  M   connect to a remote folder over SSH (user@host:/path, needs sshfs); empty = disconnect
  T   colour theme menu (dark, light, solarized, gruvbox, nord)
  . or zh   show / hide hidden files
  mouse   click select, double-click open, wheel scroll, right-click or the side "back"
          button = previous folder (forward button = next), drag in the editor to select
  s       sort menu: n name, d date, s size, e extension, r reverse (same key again = reverse)
  m + key   set a bookmark here     ' + key   jump to a bookmark   ' + ?   list bookmarks
  K / F9    change the keyboard shortcuts (menu, saved to the config file)
  ' + '     back to the previous folder

OPENING AND PREVIEW (third column)
  text      Enter: editor            image, PDF   preview; Enter: external program
  (on a graphical desktop) or the built-in viewer (over SSH, on a console)
  v   built-in viewer: Left/Right = images / PDF pages, t = PDF text/image
  o   open with the external program (xdg-open)
  archive   preview: contents; Enter: open / list
  git       M modified, A added, ? untracked, D deleted, U conflict (left of the names)

FILE OPERATIONS
  e       edit the file                  n   new file      N   new folder
  r       rename                         D   (or Delete) trash / delete permanently
  R       bulk rename: edit the names of the marked files (or all) in the editor,
          save, close, confirm
  Space   mark a file (several at once)
  y       copy the marked files (or the current one)
  x       cut                            p   paste into this folder
  Esc     clear the marks

SEARCH AND FILES
  f       search in the files under this folder (regex, lower case = ignore case)
  Tab     back to the open file (F4 too)   b   list of the open files

OTHER
  S       open a shell in this folder (exit = back)
  !       run a command in this folder
  F5 / F6 record / play macro            q   quit
"""

BROWSER_HU = """\
nanger — FÁJLKEZELŐ                                (bármely billentyű: vissza)

MOZGÁS (nyilak vagy vim-billentyűk)
  ↑ ↓  vagy  k j        fel / le          PgUp PgDn   lapozás
  ←    vagy  h  vagy Backspace   szülő mappa
  →    vagy  l  vagy Enter       mappába lépés / fájl megnyitása típus szerint
  g / G   lista eleje / vége              ~   saját mappa (home)
  c       ugrás egy beírt elérési útra    /   keresés név alapján
  Szóköz  jelöl    a   mind kijelöl / törli    A   kijelölés megfordítása
  Z   a kijelöltek (vagy az aktuális) becsomagolása .7z / .zip / .tar.gz-be
  U   archívum kicsomagolása a nevével azonos mappába
  i   a kijelöltek / az aktuális mappa mérete
  P   a kijelöltek jogosultsága (chmod): 644, u+x, a-w; mappákhoz -R
  O   tulajdonos (chown): user, user:csoport, :csoport  (ha nem engedélyezett, sudo-t kínál)
  =   két kijelölt fájl (vagy a kijelölt és az aktuális) összehasonlítása egymás mellett
  M   távoli mappa SSH-n (user@host:/mappa, sshfs kell); üresen = lecsatlakozás
  T   színtéma menü (sötét, világos, solarized, gruvbox, nord)
  . vagy zh   rejtett fájlok mutatása / elrejtése
  egér    kattintás kijelöl, dupla kattintás megnyit, görgő lapoz, jobb gomb vagy az oldalsó
          „vissza” gomb = előző mappa (előre gomb = következő), szerkesztőben húzás = kijelölés
  s       rendezés menü: n név, d dátum, s méret, e kiterjesztés, r fordított (ugyanaz újra = fordítva)
  m + billentyű   könyvjelző ide   ' + billentyű   ugrás a könyvjelzőre   ' + ?   lista
  K / F9     gyorsbillentyűk módosítása (menü, a beállítófájlba mentődik)
  ' + '   vissza az előző mappába

MEGNYITÁS ÉS ELŐNÉZET (a harmadik oszlopban)
  szöveg   Enter: szerkesztő          kép, PDF   előnézet; Enter: külső program
  (grafikus felületen) vagy beépített nézegető (SSH-n, konzolon)
  v   beépített nézegető: ←/→ képek / PDF-oldalak, t = PDF szöveg/kép
  o   megnyitás külső programmal (xdg-open)
  archívum   előnézet: tartalomjegyzék; Enter: megnyitás / listázás
  git        M módosított, A új, ? követetlen, D törölt, U ütközés (a nevek előtt)

FÁJLMŰVELETEK
  e       fájl szerkesztése              n   új fájl      N   új mappa
  r       átnevezés                      D   (vagy Delete) kukába / végleges törlés
  R       tömeges átnevezés: a megjelölt (vagy az összes) fájl nevét a szerkesztőben
          írod át, mentés, bezárás, megerősítés
  Szóköz  fájl megjelölése (több fájl egyszerre)
  y       megjelöltek (vagy az aktuális) másolása
  x       kivágás                        p   beillesztés az aktuális mappába
  Esc     jelölések törlése

KERESÉS ÉS FÁJLOK
  f       keresés a mappa fájljainak tartalmában (regex, csupa kisbetű: kis/nagybetű mindegy)
  Tab     vissza a megnyitott fájlhoz (F4 is)   b   a megnyitott fájlok listája

EGYÉB
  S       shell nyitása ebben a mappában (exit = vissza)
  !       egy parancs futtatása ebben a mappában
  F5 / F6 makró felvétele / lejátszása   q   kilépés
"""


def editor_help():
    return EDITOR_HU if language() == "hu" else EDITOR_EN


def browser_help():
    return BROWSER_HU if language() == "hu" else BROWSER_EN

PREFIX ?= /usr
DESTDIR ?=
LIBDIR = $(PREFIX)/share/nanger

install:
	install -d $(DESTDIR)$(LIBDIR)/nanger
	install -m644 nanger/*.py $(DESTDIR)$(LIBDIR)/nanger/
	install -d $(DESTDIR)$(PREFIX)/bin
	sed 's|@LIBDIR@|$(LIBDIR)|' bin/nanger.in > $(DESTDIR)$(PREFIX)/bin/nanger
	chmod 755 $(DESTDIR)$(PREFIX)/bin/nanger
	install -d $(DESTDIR)$(PREFIX)/share/man/man1 $(DESTDIR)$(PREFIX)/share/man/hu/man1 $(DESTDIR)$(PREFIX)/share/licenses/nanger
	install -m644 nanger.1 $(DESTDIR)$(PREFIX)/share/man/man1/nanger.1
	install -m644 nanger.hu.1 $(DESTDIR)$(PREFIX)/share/man/hu/man1/nanger.1
	install -m644 LICENSE $(DESTDIR)$(PREFIX)/share/licenses/nanger/LICENSE

uninstall:
	rm -f $(DESTDIR)$(PREFIX)/bin/nanger
	rm -rf $(DESTDIR)$(LIBDIR)
	rm -f $(DESTDIR)$(PREFIX)/share/man/man1/nanger.1 $(DESTDIR)$(PREFIX)/share/man/hu/man1/nanger.1
	rm -rf $(DESTDIR)$(PREFIX)/share/licenses/nanger

test:
	python3 -m pytest -q tests

deb:
	sh packaging/debian/build-deb.sh

.PHONY: install uninstall test deb

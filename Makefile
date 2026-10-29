PREFIX ?= /usr
DESTDIR ?=

install:
	install -Dm755 nanger $(DESTDIR)$(PREFIX)/bin/nanger
	install -Dm644 nanger.1 $(DESTDIR)$(PREFIX)/share/man/man1/nanger.1
	install -Dm644 LICENSE $(DESTDIR)$(PREFIX)/share/licenses/nanger/LICENSE

uninstall:
	rm -f $(DESTDIR)$(PREFIX)/bin/nanger
	rm -f $(DESTDIR)$(PREFIX)/share/man/man1/nanger.1
	rm -rf $(DESTDIR)$(PREFIX)/share/licenses/nanger

test:
	python3 -m pytest -q tests

deb:
	sh packaging/debian/build-deb.sh

.PHONY: install uninstall test deb

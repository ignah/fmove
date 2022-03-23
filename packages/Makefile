
all: fmove.deb

fmove.deb:
	(cd fmove && mkdir -p usr/bin usr/share/fmove/icons usr/share/fmove/lib usr/share/applications)
	cp -f ../fmove.py fmove/usr/share/fmove/lib
	cp -f ../res/icons/* fmove/usr/share/fmove/icons
	cp -f ../res/fmove.desktop fmove/usr/share/fmove
	cp -f fmove/usr/share/fmove/fmove.desktop fmove/usr/share/applications/
	ln -fs /usr/share/fmove/lib/fmove.py fmove/usr/bin/fmove
	dpkg-deb --build fmove

install: fmove.deb
	sudo apt install ./fmove.deb

uninstall:
	sudo apt remove fmove || true

clean:
	rm -rf fmove.deb fmove/usr

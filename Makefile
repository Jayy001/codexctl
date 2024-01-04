.DEFAULT_GOAL := all
FW_VERSION := 2.15.1.1189
FW_DATA := wVbHkgKisg-

OBJ := $(shell find codexctl -type f)
OBJ += $(shell find data -type f)
OBJ += README.md

.venv/bin/activate: requirements.remote.txt requirements.txt
	@echo "Setting up development virtual env in .venv"
	python -m venv .venv
	. .venv/bin/activate; \
	python -m pip install \
	    --extra-index-url=https://wheels.eeems.codes/ \
	    -r requirements.remote.txt

.venv/${FW_VERSION}_reMarkable2-${FW_DATA}.signed: .venv/bin/activate $(OBJ)
	. .venv/bin/activate; \
	python -m codexctl download --out .venv ${FW_VERSION}

test: .venv/bin/activate .venv/${FW_VERSION}_reMarkable2-${FW_DATA}.signed
	if [ -d .venv/mnt ] && mountpoint -q .venv/mnt; then \
		umount -ql .venv/mnt; \
	fi
	mkdir -p .venv/mnt
	. .venv/bin/activate; \
	python -m codexctl mount --out .venv/mnt ".venv/${FW_VERSION}_reMarkable2-${FW_DATA}.signed"
	[[ "$(shell \ls .venv/mnt)" == "bin boot dev etc home lib lost+found media mnt postinst proc run sbin sys tmp uboot-postinst uboot-version usr var" ]]
	umount -ql .venv/mnt

clean:
	if [ -d .venv/mnt ] && mountpoint -q .venv/mnt; then \
		umount -ql .venv/mnt; \
	fi
	git clean --force -dX

executable: .venv/bin/activate
	. .venv/bin/activate; \
	python -m pip install --extra-index-url=https://wheels.eeems.codes/ wheel nuitka; \
	NUITKA_CACHE_DIR="$(realpath .)/.nuitka" \
	python -m nuitka \
	    --enable-plugin=pylint-warnings \
	    --onefile \
	    --lto=yes \
	    --assume-yes-for-downloads \
	    --remove-output \
	    --output-dir=dist \
	    --python-arg=-m \
	    codexctl
	dist/codexctl.* --help

all: executable

.PHONY: \
	all \
	executable \
	clean \
	test

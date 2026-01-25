.DEFAULT_GOAL := all
FW_VERSION := 2.15.1.1189
FW_DATA := wVbHkgKisg-
IMG_SHA := fc7d145e18f14a1a3f435f2fd5ca5924fe8dfe59bf45605dc540deed59551ae4
LS_DATA := ". .. lost+found bin boot dev etc home lib media mnt postinst proc run sbin sys tmp uboot-postinst uboot-version usr var"
CAT_DATA := 20221026104022
FW_VERSION_SWU := 3.20.0.92
FW_FILE_SWU := remarkable-production-memfault-image-$(FW_VERSION_SWU)-rm2-public
IMG_SHA_SWU := 7de74325d82d249ccd644e6a6be2ada954a225cfe434d3bf16c4fa6e1c145eb9
LS_DATA_SWU := ". .. lost+found bin boot dev etc home lib media mnt postinst postinst-waveform proc run sbin srv sys tmp uboot-version usr var"
CAT_DATA_SWU := 20250613122401
SHELL := /bin/bash

ifeq ($(OS),Windows_NT)
	ifeq ($(VENV_BIN_ACTIVATE),)
		VENV_BIN_ACTIVATE := .venv/Scripts/activate
	endif
	CODEXCTL_BIN := codexctl.exe
	export MSYS_NO_PATHCONV = 1
else
	ifeq ($(VENV_BIN_ACTIVATE),)
		VENV_BIN_ACTIVATE := .venv/bin/activate
	endif
	CODEXCTL_BIN := codexctl
endif
CODEXCTL_FLAGS :=
ifeq ($(DEBUG_BUILD),1)
	CODEXCTL_FLAGS := --debug
endif

UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
    SHA256SUM := gsha256sum
else
    SHA256SUM := sha256sum
endif

OBJ := $(wildcard codexctl/**)
OBJ += $(wildcard data/*)
OBJ += README.md

$(VENV_BIN_ACTIVATE): requirements.remote.txt requirements.txt
	@echo "[info] Setting up development virtual env in .venv"
	python -m venv --system-site-packages .venv
	@set -e; \
	. $(VENV_BIN_ACTIVATE); \
	python -m pip install wheel
	@echo "[info] Installing dependencies"
	@set -e; \
	. $(VENV_BIN_ACTIVATE); \
	python -m pip install \
		--extra-index-url=https://wheels.eeems.codes/  \
	    -r requirements.remote.txt

.venv/${FW_VERSION}_reMarkable2-${FW_DATA}.signed: $(VENV_BIN_ACTIVATE) $(OBJ)
	@echo "[info] Downloading remarkable update file"
	@set -e; \
	. $(VENV_BIN_ACTIVATE); \
	python -m codexctl download --hardware rm2 --out .venv ${FW_VERSION}

.venv/$(FW_FILE_SWU): $(VENV_BIN_ACTIVATE) $(OBJ)
	@echo "[info] Downloading remarkable .swu update file"
	@set -e; \
	. $(VENV_BIN_ACTIVATE); \
	python -m codexctl download --hardware rm2 --out .venv $(FW_VERSION_SWU)

test: $(VENV_BIN_ACTIVATE) .venv/${FW_VERSION}_reMarkable2-${FW_DATA}.signed .venv/$(FW_FILE_SWU)
	@echo "[info] Running test"
	@set -e; \
	. $(VENV_BIN_ACTIVATE); \
	python tests/test.py; \
	if [[ "linux" == "$$(python -c 'import sys;print(sys.platform)')" ]]; then \
	  if [ -d .venv/mnt ] && mountpoint -q .venv/mnt; then \
	    umount -ql .venv/mnt; \
	  fi; \
	  mkdir -p .venv/mnt; \
	  python -m codexctl mount --out .venv/mnt ".venv/${FW_VERSION}_reMarkable2-${FW_DATA}.signed"; \
	  mountpoint .venv/mnt; \
	  umount -ql .venv/mnt; \
	fi; \
	python -m codexctl extract --out ".venv/${FW_VERSION}_reMarkable2-${FW_DATA}.img" ".venv/${FW_VERSION}_reMarkable2-${FW_DATA}.signed"; \
	echo "${IMG_SHA}  .venv/${FW_VERSION}_reMarkable2-${FW_DATA}.img" | $(SHA256SUM) -c; \
	rm -f ".venv/${FW_VERSION}_reMarkable2-${FW_DATA}.img"; \
	set -o pipefail; \
	if ! diff --color <(python -m codexctl ls ".venv/${FW_VERSION}_reMarkable2-${FW_DATA}.signed" / | tr -d "\n\r") <(echo -n ${LS_DATA}) | cat -te; then \
	  echo "codexctl ls failed test"; \
	  exit 1; \
	fi; \
	if ! diff --color <(python -m codexctl cat ".venv/${FW_VERSION}_reMarkable2-${FW_DATA}.signed" /etc/version | tr -d "\n\r") <(echo -n ${CAT_DATA}) | cat -te; then \
	  echo "codexctl cat failed test"; \
	  exit 1; \
	fi; \
	echo "[info] Running .swu tests"; \
	python -m codexctl extract --out ".venv/$(FW_FILE_SWU).img" ".venv/$(FW_FILE_SWU)"; \
	echo "$(IMG_SHA_SWU)  .venv/$(FW_FILE_SWU).img" | $(SHA256SUM) -c; \
	rm -f ".venv/$(FW_FILE_SWU).img"; \
	if ! diff --color <(python -m codexctl ls ".venv/$(FW_FILE_SWU)" / | tr -d "\n\r") <(echo -n $(LS_DATA_SWU)) | cat -te; then \
	  echo "codexctl ls .swu failed test"; \
	  exit 1; \
	fi; \
	if ! diff --color <(python -m codexctl cat ".venv/$(FW_FILE_SWU)" /etc/version | tr -d "\n\r") <(echo -n $(CAT_DATA_SWU)) | cat -te; then \
	  echo "codexctl cat .swu failed test"; \
	  exit 1; \
	fi

test-executable: .venv/${FW_VERSION}_reMarkable2-${FW_DATA}.signed .venv/$(FW_FILE_SWU)
	@set -e; \
	. $(VENV_BIN_ACTIVATE); \
	dist/${CODEXCTL_BIN} extract --out ".venv/${FW_VERSION}_reMarkable2-${FW_DATA}.img" ".venv/${FW_VERSION}_reMarkable2-${FW_DATA}.signed"; \
	echo "${IMG_SHA}  .venv/${FW_VERSION}_reMarkable2-${FW_DATA}.img" | $(SHA256SUM) -c; \
	rm -f ".venv/${FW_VERSION}_reMarkable2-${FW_DATA}.img"; \
	set -o pipefail; \
	if ! diff --color <(dist/${CODEXCTL_BIN} ls ".venv/${FW_VERSION}_reMarkable2-${FW_DATA}.signed" / | tr -d "\n\r") <(echo -n ${LS_DATA}) | cat -te; then \
	  echo "codexctl ls failed test"; \
	  exit 1; \
	fi; \
	if ! diff --color <(dist/${CODEXCTL_BIN} cat ".venv/${FW_VERSION}_reMarkable2-${FW_DATA}.signed" /etc/version | tr -d "\n\r") <(echo -n ${CAT_DATA}) | cat -te; then \
	  echo "codexctl cat failed test"; \
	  exit 1; \
	fi; \
	echo "[info] Running .swu tests"; \
	dist/${CODEXCTL_BIN} extract --out ".venv/$(FW_FILE_SWU).img" ".venv/$(FW_FILE_SWU)"; \
	echo "$(IMG_SHA_SWU)  .venv/$(FW_FILE_SWU).img" | $(SHA256SUM) -c; \
	rm -f ".venv/$(FW_FILE_SWU).img"; \
	if ! diff --color <(dist/${CODEXCTL_BIN} ls ".venv/$(FW_FILE_SWU)" / | tr -d "\n\r") <(echo -n $(LS_DATA_SWU)) | cat -te; then \
	  echo "codexctl ls .swu failed test"; \
	  exit 1; \
	fi; \
	if ! diff --color <(dist/${CODEXCTL_BIN} cat ".venv/$(FW_FILE_SWU)" /etc/version | tr -d "\n\r") <(echo -n $(CAT_DATA_SWU)) | cat -te; then \
	  echo "codexctl cat .swu failed test"; \
	  exit 1; \
	fi

clean:
	@echo "[info] Cleaning"
	if [ -d .venv/mnt ] && mountpoint -q .venv/mnt; then \
		umount -ql .venv/mnt; \
	fi
	git clean --force -dX

executable: $(VENV_BIN_ACTIVATE)
	@echo "[info] Installing Nuitka"
	@set -e; \
	. $(VENV_BIN_ACTIVATE); \
	python -m pip install \
		--extra-index-url=https://wheels.eeems.codes/ \
	    nuitka==2.8.10 \
	    setuptools
	@echo "[info] Building codexctl"
	@set -e; \
	. $(VENV_BIN_ACTIVATE); \
	NUITKA_CACHE_DIR="$(realpath .)/.nuitka" \
	python -m nuitka \
	    --assume-yes-for-downloads \
	    --remove-output \
	    --output-dir=dist \
	    --report=compilation-report.xml \
	    --output-filename=codexctl \
	    $(CODEXCTL_FLAGS) \
	    main.py

	if [ -d dist/codexctl.build ]; then \
	    rm -r dist/codexctl.build; \
	fi
	@echo "[info] Sanity check"
	dist/${CODEXCTL_BIN} --help

all: executable

.PHONY: \
	all \
	executable \
	clean \
	test \
	test-executable

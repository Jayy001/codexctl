#!/bin/sh

set -eu

opkg update

echo "Installing basic build tools"
opkg install gcc binutils busybox gawk ldd make sed tar patchelf

echo "Installing recommended build tools"
opkg install coreutils-install diffutils ldconfig patch pkg-config --force-overwrite

echo "Installing automake, cmake, meson, and ninja"
opkg install automake libintl-full libtool-bin cmake icu libopenssl bash git git-http python3-pip python3-setuptools coreutils-od python3-psutil python3-bcrypt python3-cryptography
python3 -m pip install -U wheel
cd /opt/tmp
git clone https://github.com/ninja-build/ninja.git
cd ./ninja
git checkout release
CONFIG_SHELL=/opt/bin/bash python3 ./configure.py --bootstrap
install -Dm0755 -t /opt/bin ./ninja
cd /opt/tmp && rm -Rf /opt/tmp/ninja
python3 -m pip install -U meson

echo "Installing header files"
opkg install --force-overwrite --force-reinstall libncurses-dev libxml2-dev python3-dev ruby-dev zlib-dev
/opt/bin/busybox wget -qO- "$(/opt/bin/busybox sed -Ene \
  's|^src/gz[[:space:]]entware[[:space:]]https?([[:graph:]]+)|http\1/include/include.tar.gz|p' \
  /opt/etc/opkg.conf)" | /opt/bin/busybox tar x -vzC /opt/include

source /opt/bin/gcc_env.sh

echo "Installing rust"
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source "$HOME/.cargo/env"

echo "Installing python dependencies"
ln -s /opt/lib/libffi.so.8 /opt/lib/libffi.so
python3 -m pip install -U pip setuptools
git clone https://github.com/Jayy001/codexctl.git
cd codexctl
python3 -m pip install --extra-index-url extra-index-url=https://www.piwheels.org/simple -r requirements.txt nuitka

echo "Building codexctl"
python3 -m nuitka \
    --enable-plugin=pylint-warnings \
    --onefile \
    --lto=yes \
    --assume-yes-for-downloads \
    --remove-output \
    --output-dir=dist \
    modules/codexctl.py

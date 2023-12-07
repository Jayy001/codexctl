#!/bin/sh
set -eu

cd /opt/tmp/src

echo "Installing dependencies"
python3 -m pip install -r requirements.txt

echo "Building codexctl"
pyinstaller \
  --noconfirm \
  --runtime-tmpdir /tmp \
  --onefile \
  --strip \
  codexctl.py

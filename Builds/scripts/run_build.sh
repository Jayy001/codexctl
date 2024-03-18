#!/bin/bash
set -e

run_vm.sh \
  -serial null \
  -daemonize

wait_ssh.sh

rsync -avr \
  --exclude ".git" \
  --exclude "rm-docker" \
  --filter=':- .gitignore' \
  /src \
  root@localhost:/opt/tmp

ssh root@localhost 'bash -l -c /opt/bin/build.sh'

rsync -avr root@localhost:/opt/tmp/src/dist /src

save_vm.sh

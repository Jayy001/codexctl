#!/bin/bash
set -e

run_vm.sh -serial null -daemonize
wait_ssh.sh
rsync -avr --exclude ".git" /src root@localhost:/opt/tmp
ssh root@localhost 'bash -l -c /opt/bin/build.sh'
save_vm.sh

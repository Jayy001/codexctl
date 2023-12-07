#!/bin/bash
set -e

run_vm.sh -serial null -daemonize
wait_ssh.sh
scp -r /src root@localhost:/opt/tmp
ssh root@localhost '/opt/bin/build.sh'
save_vm.sh

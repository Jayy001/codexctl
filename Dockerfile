#syntax=docker/dockerfile:1.4
FROM rm-docker as qemu-toltec-codexctl

ADD scripts/build.sh /opt/build.sh
ADD scripts/install_build_tools.sh /opt/install_build_tools.sh
ADD scripts/run_build.sh /opt/bin/run_build.sh

RUN run_vm.sh -serial null -daemonize && \
    wait_ssh.sh && \
    scp /opt/build.sh root@localhost:/opt/bin && \
    scp /opt/install_build_tools.sh root@localhost:/opt/bin && \
    ssh root@localhost 'bash -l -c install_build_tools.sh' && \
    save_vm.sh

CMD run_build.sh

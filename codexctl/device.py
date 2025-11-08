import enum
import socket
import subprocess
import logging
import threading
import re
import os
import time

from .server import startUpdate

try:
    import paramiko
    import psutil
except ImportError:
    pass


class HardwareType(enum.Enum):
    RM1 = enum.auto()
    RM2 = enum.auto()
    RMPP = enum.auto()

    @classmethod
    def parse(cls, device_type: str) -> "HardwareType":
        if device_type.lower() in ("pp", "pro", "rmpp", "ferrari", "remarkable ferrari"):
            return cls.RMPP
        elif device_type.lower() in ("2", "rm2", "remarkable 2", "remarkable 2.0"):
            return cls.RM2
        elif device_type.lower() in ("1", "rm1", "remarkable 1", "remarkable 1.0", "remarkable prototype 1"):
            return cls.RM1

        raise ValueError(f"Unknown hardware version: {device_type} (rm1, rm2, rmpp)")

    @property
    def old_download_hw(self):
        match self:
            case HardwareType.RM1:
                return "reMarkable"
            case HardwareType.RM2:
                return "reMarkable2"
            case HardwareType.RMPP:
                raise ValueError("ReMarkable Paper Pro does not support the old update engine")

    @property
    def new_download_hw(self):
        match self:
            case HardwareType.RM1:
                return "rm1"
            case HardwareType.RM2:
                return "rm2"
            case HardwareType.RMPP:
                return "rmpp"

    @property
    def swupdate_hw(self):
        match self:
            case HardwareType.RM1:
                return "reMarkable1"
            case HardwareType.RM2:
                return "reMarkable2"
            case HardwareType.RMPP:
                return "ferrari"

    @property
    def toltec_type(self):
        match self:
            case HardwareType.RM1:
                return "rm1"
            case HardwareType.RM2:
                return "rm2"
            case HardwareType.RMPP:
                raise ValueError("ReMarkable Paper Pro does not support toltec")

class DeviceManager:
    def __init__(
        self, logger=None, remote=False, address=None, authentication=None, port=22
    ) -> None:
        """Initializes the DeviceManager for codexctl

        Args:
            remote (bool, optional): Whether the device is remote. Defaults to False.
            address (bool, optional): Known IP of remote device, if applicable. Defaults to None.
            port (int, optional): Known port of remote device SSH service. Defaults to 22.
            logger (logger, optional): Logger object for logging. Defaults to None.
            Authentication (str, optional): Authentication method. Defaults to None.
        """
        self.logger = logger
        self.address = address
        self.port = port
        self.authentication = authentication
        self.client = None

        if self.logger is None:
            self.logger = logging

        if remote:
            self.client = self.connect_to_device(
                authentication=authentication, remote_address=address, port=port
            )

            ftp = self.client.open_sftp()
            with ftp.file("/sys/devices/soc0/machine") as file:
                machine_contents = file.read().decode("utf-8").strip("\n")
        else:
            with open("/sys/devices/soc0/machine") as file:
                machine_contents = file.read().strip("\n")

        self.hardware = HardwareType.parse(machine_contents)

    def get_host_address(self) -> list[str] | list | None:  # Interaction required
        """Gets the IP address of the host machine

        Returns:
            str | None: IP address of the host machine, or None if not found
        """

        possible_ips = []
        try:
            for interface, snics in psutil.net_if_addrs().items():
                self.logger.debug(f"New interface found: {interface}")
                for snic in snics:
                    if snic.family == socket.AF_INET:
                        if snic.address.startswith("10.11.99"):
                            return snic.address
                        self.logger.debug(f"Adding new address: {snic.address}")
                        possible_ips.append(snic.address)

        except Exception as error:
            self.logger.error(f"Error automatically getting interfaces: {error}")

        if possible_ips:
            host_interfaces = "\n".join(possible_ips)
        else:
            host_interfaces = "Could not find any available interfaces."

        print(f"\n{host_interfaces}")
        while True:
            host_address = input(
                "\nPlease enter your host IP for the network the device is connected to: "
            )

            if possible_ips and host_address not in host_interfaces.split("\n"):
                print("Error: Invalid IP given")
                continue

            if "n" in input("Are you sure? (Y/n): ").lower():
                continue

            break

        return host_address

    def get_remarkable_address(self) -> str:
        """Gets the IP address of the remarkable device

        Returns:
            str: IP address of the remarkable device
        """

        if self.check_if_address_reachable("10.11.99.1", self.port):
            return "10.11.99.1"

        while True:
            remote_ip = input("Please enter the IP of the remarkable device: ")

            if self.check_if_address_reachable(remote_ip, self.port):
                return remote_ip

            print(f"Error: Device {remote_ip} is not reachable. Please try again.")

    def check_if_address_reachable(self, remote_ip="10.11.99.1", remote_port=22) -> bool:
        """Checks if the given IP address is reachable over SSH

        Args:
            remote_ip (str, optional): IP to check. Defaults to '10.11.99.1'.
            remote_port (int, optional): Port to check. Defaults to `22`.
        Returns:
            bool: True if reachable, False otherwise
        """
        self.logger.debug(f"Checking if {remote_ip} is reachable")

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)

            sock.connect((remote_ip, remote_port))
            sock.shutdown(2)

            return True
        except FileNotFoundError:
            self.logger.debug(f"Device {remote_ip} is not reachable")
            return False

    def connect_to_device(
        self, remote_address=None, authentication=None, port=22
    ) -> paramiko.client.SSHClient:
        """Connects to the device using the given IP address

        Args:
            remote_address (str, optional): IP address of the device.
            authentication (str, optional): Authentication credentials. Defaults to None.

        Returns:
            paramiko.client.SSHClient: SSH client object for the device.
        """

        if remote_address is None:
            remote_address = self.get_remarkable_address()
            self.address = remote_address  # For future reference
        else:
            if self.check_if_address_reachable(remote_address, port) is False:
                raise SystemError(f"Error: Device {remote_address} is not reachable!")

        client = paramiko.client.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        if authentication != None:
            self.logger.debug(f"Using authentication: {authentication}")
            try:
                if os.path.isfile(authentication):
                    self.logger.debug(
                        f"Attempting to connect to {remote_address} with key file {authentication}"
                    )
                    client.connect(
                        remote_address, username="root", key_filename=authentication
                    )
                else:
                    self.logger.debug(
                        f"Attempting to connect to {remote_address} with password {authentication}"
                    )

                    if authentication == " ":
                        transport = paramiko.transport.Transport((remote_address, port))
                        transport.start_client()
                        transport.auth_none("root")
                        client._transport = transport
                    else:
                        client.connect(
                            remote_address, username="root", password=authentication, port=port
                        )

            except paramiko.ssh_exception.AuthenticationException:
                print("Incorrect password or ssh path given in arguments!")

        elif (
            "n" in input("Would you like to use a password to connect? (Y/n): ").lower()
        ):
            while True:
                key_path = input("Enter path to SSH key: ")

                try:
                    self.logger.debug(
                        f"Attempting to connect to {remote_address} with key file {key_path}"
                    )
                    client.connect(
                        remote_address, username="root", key_filename=key_path
                    )
                except Exception:
                    print("Error while connecting to device: {error}")

                    continue
                break
        else:
            while True:
                password = input("Enter RM SSH password: ")

                try:
                    self.logger.debug(
                        f"Attempting to connect to {remote_address} with password {password}"
                    )
                    client.connect(remote_address, username="root", password=password)
                except paramiko.ssh_exception.AuthenticationException:
                    print("Incorrect password given")

                    continue
                break

        print("Success: Connected to device")

        return client

    def get_device_status(self) -> tuple[str | None, str, str]:
        """Gets the status of the device

        Returns:
            tuple: Beta status, previous version, and current version (in that order)
        """
        old_update_engine = True

        if self.client:
            self.logger.debug("Connecting to FTP")
            ftp = self.client.open_sftp()
            self.logger.debug("Connected")

            try:
                with ftp.file("/usr/share/remarkable/update.conf") as file:
                    xochitl_version = re.search(
                        "(?<=REMARKABLE_RELEASE_VERSION=).*",
                        file.read().decode("utf-8").strip("\n"),
                    ).group()
            except Exception:
                with ftp.file("/etc/os-release") as file:
                    xochitl_version = (
                        re.search("(?<=IMG_VERSION=).*", file.read().decode("utf-8"))
                        .group()
                        .strip('"')
                    )
                    old_update_engine = False

            with ftp.file("/etc/version") as file:
                version_id = file.read().decode("utf-8").strip("\n")

            with ftp.file("/home/root/.config/remarkable/xochitl.conf") as file:
                beta_contents = file.read().decode("utf-8")

        else:
            if os.path.exists("/usr/share/remarkable/update.conf"):
                with open("/usr/share/remarkable/update.conf") as file:
                    xochitl_version = re.search(
                        "(?<=REMARKABLE_RELEASE_VERSION=).*",
                        file.read().decode("utf-8").strip("\n"),
                    ).group()
            else:
                with open("/etc/os-release") as file:
                    xochitl_version = (
                        re.search("(?<=IMG_VERSION=).*", file.read().decode("utf-8"))
                        .group()
                        .strip('"')
                    )

                    old_update_engine = False
            if os.path.exists("/etc/version"):
                with open("/etc/version") as file:
                    version_id = file.read().rstrip()
            else:
                version_id = ""

            if os.path.exists("/home/root/.config/remarkable/xochitl.conf"):
                with open("/home/root/.config/remarkable/xochitl.conf") as file:
                    beta_contents = file.read().rstrip()
            else:
                beta_contents = ""

        beta_possible = re.search("(?<=GROUP=).*", beta_contents)
        beta = "Release"

        if beta_possible is not None:
            beta = re.search("(?<=GROUP=).*", beta_contents).group()

        return beta, old_update_engine, xochitl_version, version_id

    def set_server_config(self, contents: str, server_host_name: str) -> str:
        """Converts the contents given to point to the given server IP and port

        Args:
            contents (str): Contents of the update.conf file
            server_host_name (str): Hostname of the server

        Returns:
            str: Converted contents
        """
        data_attributes = contents.split("\n")
        line = 0

        self.logger.debug(f"Contents are:\n{contents}")

        for i in range(0, len(data_attributes)):
            if data_attributes[i].startswith("[General]"):
                self.logger.debug("Found [General] line")
                line = i + 1
            if not data_attributes[i].startswith("SERVER="):
                continue

            data_attributes[i] = f"#{data_attributes[i]}"
            self.logger.debug(f"Using {data_attributes[i]}")

        data_attributes.insert(line, f"SERVER={server_host_name}")
        converted = "\n".join(data_attributes)

        self.logger.debug(f"Converted contents are:\n{converted}")

        return converted

    def edit_update_conf(self, server_ip: str, server_port: str) -> bool:
        """Edits the update.conf file to point to the given server IP and port

        Args:
            server_ip (str): IP of update server
            server_port (str): Port of update service

        Returns:
            bool: True if successful, False otherwise
        """
        server_host_name = f"http://{server_ip}:{server_port}"
        self.logger.debug(f"Hostname is: {server_host_name}")
        try:
            if not self.client:
                self.logger.debug("Detected running on local device")
                with open(
                    "/usr/share/remarkable/update.conf", encoding="utf-8"
                ) as file:
                    modified_conf_version = self.set_server_config(
                        file.read(), server_host_name
                    )

                with open("/usr/share/remarkable/update.conf", "w") as file:
                    file.write(modified_conf_version)

                return True

            self.logger.debug("Connecting to FTP")
            ftp = self.client.open_sftp()  # or ssh
            self.logger.debug("Connected")

            with ftp.file("/usr/share/remarkable/update.conf") as update_conf_file:
                modified_conf_version = self.set_server_config(
                    update_conf_file.read().decode("utf-8"), server_host_name
                )

            with ftp.file("/usr/share/remarkable/update.conf", "w") as update_conf_file:
                update_conf_file.write(modified_conf_version)

            return True
        except Exception as error:
            self.logger.error(f"Error while editing update.conf: {error}")
            return False

    def restore_previous_version(self) -> None:
        """Restores the previous version of the device"""

        RESTORE_CODE = """/sbin/fw_setenv "upgrade_available" "1"
/sbin/fw_setenv "bootcount" "0"

OLDPART=$(/sbin/fw_printenv -n active_partition)
if [ $OLDPART  ==  "2" ]; then
    NEWPART="3"
else
    NEWPART="2"
fi
echo "new: ${NEWPART}"
echo "fallback: ${OLDPART}"

/sbin/fw_setenv "fallback_partition" "${OLDPART}"
/sbin/fw_setenv "active_partition" "${NEWPART}\""""

        if self.hardware == HardwareType.RMPP:
            RESTORE_CODE = """#!/bin/bash
OLDPART=$(< /sys/devices/platform/lpgpr/root_part)
if [[ $OLDPART  ==  "a" ]]; then
    NEWPART="b"
else
    NEWPART="a"
fi
echo "new: ${NEWPART}"
echo "fallback: ${OLDPART}"
echo $NEWPART > /sys/devices/platform/lpgpr/root_part
"""

        if self.client:
            self.logger.debug("Connecting to FTP")
            ftp = self.client.open_sftp()
            self.logger.debug("Connected")

            with ftp.file("/tmp/restore.sh", "w") as file:
                file.write(RESTORE_CODE)

            self.logger.debug("Setting permissions and running restore.sh")

            self.client.exec_command("chmod +x /tmp/restore.sh")
            self.client.exec_command("bash /tmp/restore.sh")
        else:
            with open("/tmp/restore.sh", "w") as file:
                file.write(RESTORE_CODE)

            self.logger.debug("Setting permissions and running restore.sh")

            os.system("chmod +x /tmp/restore.sh")
            os.system("/tmp/restore.sh")

        self.logger.debug("Restore script ran")

    def transfer_file_to_remote(self, file_location: str, destination: str):
        """
        Tranfers file at file_location to destination on devicec
        """
        ftp_client = self.client.open_sftp()

        print(f"Uploading {file_location} to {destination}")

        ftp_client.put(
            file_location, destination, callback=self.output_put_progress
        )

    def install_manual_update(self, version_file: str) -> None:
        if self.client:
            print(f"Uploading {version_file} image")

            out_image_file = f"/tmp/{out_image_file}"

            self.transfer_file_to_remote(version_file, destination=out_image_file)

            _stdin, stdout, _stderr = self.client.exec_command("/sbin/fw_printenv -n active_partition")
            # TODO Before merge: Make this utilise the mount command instead

            fallback_partition = f"mmcblk2p{stdout}"

            print("Now running dd to overwrite the fallback partition")

            _stdin, stdout, _stderr = self.client.exec_command(f"dd if={version_file} of=/dev/{fallback_partition}")
            
            self.logger.debug(
                f'Stdout of dd is {_stderr.readlines()}'
            )

            #### Now disable automatic updates

            self.client.exec_command("sleep 1 && reboot")  # Should be enough
            self.client.close()

            time.sleep(
                2
            )  # Somehow the code runs faster than the time it takes for the device to reboot

            print("Trying to connect to device")

            while not self.check_if_address_reachable(self.address, self.port):
                time.sleep(1)

            self.client = self.connect_to_device(
                remote_address=self.address, authentication=self.authentication, port=self.port
            )
            self.client.exec_command("systemctl stop swupdate memfaultd")

            print(
                "Update complete and update service disabled, restart device to enable it"
            )

        else:
            stdout = subprocess.run(['/sbin/fw_printenv', '-n', 'active_partition'], stdout=subprocess.PIPE).stdout.decode().strip()
            # TODO Before merge: Make this utilise the mount command instead

            fallback_partition = f"mmcblk2p{stdout}" 

            print("Now running dd to overwrite the fallback partition")

            with subprocess.Popen(
                f"dd if={version_file} of=/dev/{fallback_partition}",
                text=True,
                shell=True, 
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={"PATH": "/bin:/usr/bin:/sbin"},
            ) as process:
                self.logger.debug(
                    f'Stdout of update checking service is {"".join(process.stderr.readlines())}'
                )

            print("Update complete and device rebooting")
            os.system("reboot")
            
    def reboot_device(self) -> None:
        REBOOT_CODE = """
if systemctl is-active --quiet tarnish.service; then
    rot system call reboot
else
    systemctl reboot
fi
"""
        if self.client:
            self.logger.debug("Connecting to FTP")
            ftp = self.client.open_sftp()
            self.logger.debug("Connected")
            with ftp.file("/tmp/reboot.sh", "w") as file:
                file.write(REBOOT_CODE)

            self.logger.debug("Running reboot.sh")
            self.client.exec_command("sh /tmp/reboot.sh")

        else:
            with open("/tmp/reboot.sh", "w") as file:
                file.write(REBOOT_CODE)

            self.logger.debug("Running reboot.sh")
            os.system("sh /tmp/reboot.sh")

        self.logger.debug("Device rebooted")

    def install_sw_update(self, version_file: str) -> None:
        """
        Installs new version from version file path, utilising swupdate

        Args:
            version_file (str): Path to img file

        Raises:
            SystemExit: If there was an error installing the update

        """
        command = f'/usr/bin/swupdate -v -i VERSION_FILE -k /usr/share/swupdate/swupdate-payload-key-pub.pem -H "{self.hardware.swupdate_hw}:1.0" -e "stable,copy1"'

        if self.client:
            print(f"Uploading {version_file} image")

            out_location = f"/tmp/{os.path.basename(version_file)}.swu"
            ftp_client.put(
                version_file, out_location, callback=self.output_put_progress
            )

            print("\nDone! Running swupdate (PLEASE BE PATIENT, ~5 MINUTES)")

            command = command.replace("VERSION_FILE", out_location)

            for num in (1, 2):
                command = command.replace(
                    "stable,copy1", f"stable,copy{num}"
                )  # terrible hack but it works
                self.logger.debug(command)
                _stdin, stdout, _stderr = self.client.exec_command(command)

                self.logger.debug(f"Stdout of swupdate checking: {stdout.readlines()}")

                exit_status = stdout.channel.recv_exit_status()

                if exit_status != 0:
                    if "over our current root" in "".join(_stderr.readlines()):
                        continue
                    else:
                        print("".join(_stderr.readlines()))
                        raise SystemError("Update failed!")

            print("Done! Now rebooting the device and disabling update service")

            #### Now disable automatic updates

            self.client.exec_command("sleep 1 && reboot")  # Should be enough
            self.client.close()

            time.sleep(
                2
            )  # Somehow the code runs faster than the time it takes for the device to reboot

            print("Trying to connect to device")

            while not self.check_if_address_reachable(self.address, self.port):
                time.sleep(1)

            self.client = self.connect_to_device(
                remote_address=self.address, authentication=self.authentication, port=self.port
            )
            self.client.exec_command("systemctl stop swupdate memfaultd")

            print(
                "Update complete and update service disabled, restart device to enable it"
            )

        else:
            print("Running swupdate")
            command = command.replace("VERSION_FILE", version_file)

            for num in (1, 2):
                command = command.replace(
                    "stable,copy1", f"stable,copy{num}"
                )  # terrible hack but it works
                self.logger.debug(command)

                with subprocess.Popen(
                    command,
                    text=True,
                    shell=True,  # Being lazy...
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env={"PATH": "/bin:/usr/bin:/sbin"},
                ) as process:
                    if process.wait() != 0:
                        if "installing over our current root" in "".join(
                            process.stderr.readlines()
                        ):
                            continue
                        else:
                            print("".join(process.stderr.readlines()))
                            raise SystemError("Update failed")

                    self.logger.debug(
                        f"Stdout of update checking service is {''.join(process.stdout.readlines())}"
                    )

            print("Update complete and device rebooting")
            os.system("reboot")

    def install_ohma_update(self, version_available: dict) -> None:
        """Installs version from update folder on the device

        Args:
            version_available (dict): Version available for installation from `get_available_version`

        Raises:
            SystemExit: If there was an error installing the update
        """

        server_host = self.get_host_address()

        self.logger.debug("Editing config file")

        if (
            self.edit_update_conf(server_ip=server_host, server_port=8085) is False
        ):  # We want a port that probably isn't being used
            self.logger.error("Error while editing update.conf")

            return

        thread = threading.Thread(
            target=startUpdate, args=(version_available, server_host, 8085), daemon=True
        )
        thread.start()

        self.logger.debug("Thread started")

        if self.client:
            print("Checking if device can connect to this machine")

            _stdin, stdout, _stderr = self.client.exec_command(
                f"sleep 2 && echo | nc {server_host} 8085"
            )
            check = stdout.channel.recv_exit_status()
            self.logger.debug(f"Stdout of nc checking: {stdout.readlines()}")

            if check != 0:
                raise SystemError(
                    "Device cannot connect to this machine! Is the firewall blocking connections?"
                )

            print("Starting update service on device")

            self.client.exec_command("systemctl start update-engine")

            _stdin, stdout, _stderr = self.client.exec_command(
                "/usr/bin/update_engine_client -update"
            )
            exit_status = stdout.channel.recv_exit_status()

            if exit_status != 0:
                print("".join(_stderr.readlines()))
                raise SystemError("There was an error updating :(")

            self.logger.debug(
                f"Stdout of update checking service is {''.join(_stderr.readlines())}"
            )

            #### Now disable automatic updates

            print("Done! Now rebooting the device and disabling update service")

            self.client.exec_command("sleep 1 && reboot")  # Should be enough
            self.client.close()

            time.sleep(
                2
            )  # Somehow the code runs faster than the time it takes for the device to reboot

            print("Trying to connect to device")

            while not self.check_if_address_reachable(self.address, self.port):
                time.sleep(1)

            self.client = self.connect_to_device(
                remote_address=self.address, authentication=self.authentication, port=self.port
            )
            self.client.exec_command("systemctl stop update-engine")

            print(
                "Update complete and update service disabled. Restart device to enable it"
            )

        else:
            print("Enabling update service")

            subprocess.run(
                ["/bin/systemctl", "start", "update-engine"],
                text=True,
                check=True,
                env={"PATH": "/bin:/usr/bin:/sbin"},
            )

            with subprocess.Popen(
                ["/usr/bin/update_engine_client", "-update"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={"PATH": "/bin:/usr/bin:/sbin"},
            ) as process:
                if process.wait() != 0:
                    print("".join(process.stderr.readlines()))

                    raise SystemError("There was an error updating :(")

                self.logger.debug(
                    f"Stdout of update checking service is {''.join(process.stderr.readlines())}"
                )

            print("Update complete and device rebooting")
            os.system("reboot")

    @staticmethod
    def output_put_progress(transferred: int, toBeTransferred: int) -> None:
        """Used for displaying progress for paramiko ftp.put function"""

        print(
            f"Transferring progress {int((transferred/toBeTransferred)*100)}%",
            end="\r",
        )




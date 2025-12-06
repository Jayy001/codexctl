import enum
import logging
import os
import re
import socket
import subprocess
import tempfile
import threading
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
    RMPPM = enum.auto()

    @classmethod
    def parse(cls, device_type: str) -> "HardwareType":
        match device_type.lower():
            case "ppm" | "rmppm" | "chiappa" | "remarkable chiappa":
                return cls.RMPPM

            case "pp" | "pro" | "rmpp" | "ferrari" | "remarkable ferrari":
                return cls.RMPP

            case "2" | "rm2" | "remarkable 2" | "remarkable 2.0":
                return cls.RM2

            case "1" | "rm1" | "remarkable 1" | "remarkable 1.0" | "remarkable prototype 1":
                return cls.RM1

            case _:
                raise ValueError(f"Unknown hardware version: {device_type} (rm1, rm2, rmpp, rmppm)")

    @property
    def old_download_hw(self):
        match self:
            case HardwareType.RM1:
                return "reMarkable"
            case HardwareType.RM2:
                return "reMarkable2"
            case HardwareType.RMPP:
                raise ValueError("reMarkable Paper Pro does not support the old update engine")
            case HardwareType.RMPPM:
                raise ValueError("reMarkable Paper Pro Move does not support the old update engine")

    @property
    def new_download_hw(self):
        match self:
            case HardwareType.RM1:
                return "rm1"
            case HardwareType.RM2:
                return "rm2"
            case HardwareType.RMPP:
                return "rmpp"
            case HardwareType.RMPPM:
                return "rmppm"

    @property
    def swupdate_hw(self):
        match self:
            case HardwareType.RM1:
                return "reMarkable1"
            case HardwareType.RM2:
                return "reMarkable2"
            case HardwareType.RMPP:
                return "ferrari"
            case HardwareType.RMPPM:
                return "chiappa"

    @property
    def toltec_type(self):
        match self:
            case HardwareType.RM1:
                return "rm1"
            case HardwareType.RM2:
                return "rm2"
            case HardwareType.RMPP:
                raise ValueError("reMarkable Paper Pro does not support toltec")
            case HardwareType.RMPPM:
                raise ValueError("reMarkable Paper Pro Move does not support toltec")

class DeviceManager:
    def __init__(
        self, logger=None, remote=False, address=None, authentication=None
    ) -> None:
        """Initializes the DeviceManager for codexctl

        Args:
            remote (bool, optional): Whether the device is remote. Defaults to False.
            address (bool, optional): Known IP of remote device, if applicable. Defaults to None.
            logger (logger, optional): Logger object for logging. Defaults to None.
            Authentication (str, optional): Authentication method. Defaults to None.
        """
        self.logger = logger
        self.address = address
        self.authentication = authentication
        self.client = None

        if self.logger is None:
            self.logger = logging

        if remote:
            self.client = self.connect_to_device(
                authentication=authentication, remote_address=address
            )

            self.client.authentication = authentication
            self.client.address = address

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

        if self.check_is_address_reachable("10.11.99.1"):
            return "10.11.99.1"

        while True:
            remote_ip = input("Please enter the IP of the remarkable device: ")

            if self.check_is_address_reachable(remote_ip):
                return remote_ip

            print(f"Error: Device {remote_ip} is not reachable. Please try again.")

    def check_is_address_reachable(self, remote_ip="10.11.99.1") -> bool:
        """Checks if the given IP address is reachable over SSH

        Args:
            remote_ip (str, optional): IP to check. Defaults to '10.11.99.1'.

        Returns:
            bool: True if reachable, False otherwise
        """
        self.logger.debug(f"Checking if {remote_ip} is reachable")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)

            sock.connect((remote_ip, 22))
            sock.shutdown(2)

            return True

        except Exception:
            self.logger.debug(f"Device {remote_ip} is not reachable")
            return False

    def connect_to_device(
        self, remote_address=None, authentication=None
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
            if self.check_is_address_reachable(remote_address) is False:
                raise SystemError(f"Error: Device {remote_address} is not reachable!")

        client = paramiko.client.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        if authentication:
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
                    client.connect(
                        remote_address, username="root", password=authentication
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

    def _read_version_from_path(self, ftp, base_path: str = "") -> tuple[str, bool]:
        """Reads version from a given path (current partition or mounted backup)

        Args:
            ftp: SFTP client connection
            base_path: Base path prefix (empty for current partition, /tmp/mount_pX for backup)

        Returns:
            tuple: (version_string, old_update_engine_boolean)
        """
        update_conf_path = f"{base_path}/usr/share/remarkable/update.conf" if base_path else "/usr/share/remarkable/update.conf"
        os_release_path = f"{base_path}/etc/os-release" if base_path else "/etc/os-release"

        def file_exists(path: str) -> bool:
            try:
                ftp.stat(path)
                return True
            except FileNotFoundError:
                return False

        if file_exists(update_conf_path):
            with ftp.file(update_conf_path) as file:
                contents = file.read().decode("utf-8").strip("\n")
                match = re.search("(?<=REMARKABLE_RELEASE_VERSION=).*", contents)
                if match:
                    return match.group(), True
                raise SystemError(f"REMARKABLE_RELEASE_VERSION not found in {update_conf_path}")

        if file_exists(os_release_path):
            with ftp.file(os_release_path) as file:
                contents = file.read().decode("utf-8")
                match = re.search("(?<=IMG_VERSION=).*", contents)
                if match:
                    return match.group().strip('"'), False
                raise SystemError(f"IMG_VERSION not found in {os_release_path}")

        raise SystemError(f"Cannot read version from {base_path or 'current partition'}: no version file found")

    def _get_backup_partition_version(self) -> str:
        """Gets the version installed on the backup (inactive) partition

        Returns:
            str: Version string

        Raises:
            SystemError: If backup partition version cannot be determined
        """
        if not self.client:
            raise SystemError("Cannot get backup partition version: no SSH client connection")

        ftp = self.client.open_sftp()

        if self.hardware in (HardwareType.RMPP, HardwareType.RMPPM):
            _stdin, stdout, _stderr = self.client.exec_command("swupdate -g")
            active_device = stdout.read().decode("utf-8").strip()
            active_part = int(active_device.split('p')[-1])
            inactive_part = 3 if active_part == 2 else 2
            device_base = re.sub(r'p\d+$', '', active_device)
        else:
            _stdin, stdout, _stderr = self.client.exec_command("rootdev")
            active_device = stdout.read().decode("utf-8").strip()
            active_part = int(active_device.split('p')[-1])
            inactive_part = 3 if active_part == 2 else 2
            device_base = re.sub(r'p\d+$', '', active_device)

        mount_point = f"/tmp/mount_p{inactive_part}"

        self.client.exec_command(f"mkdir -p {mount_point}")
        _stdin, stdout, _stderr = self.client.exec_command(
            f"mount -o ro {device_base}p{inactive_part} {mount_point}"
        )
        exit_status = stdout.channel.recv_exit_status()

        if exit_status != 0:
            error_msg = _stderr.read().decode('utf-8')
            raise SystemError(f"Failed to mount backup partition: {error_msg}")

        try:
            version, _ = self._read_version_from_path(ftp, mount_point)
            return version
        finally:
            self.client.exec_command(f"umount {mount_point}")
            self.client.exec_command(f"rm -rf {mount_point}")

    def _get_paper_pro_partition_info(self, current_version: str) -> tuple[int, int, int]:
        """Gets partition information for Paper Pro devices

        Args:
            current_version: Current OS version string for version-aware detection

        Returns:
            tuple: (current_partition, inactive_partition, next_boot_partition)
        """
        if not self.client:
            raise SystemError("SSH client required for partition detection")

        _stdin, stdout, _stderr = self.client.exec_command("swupdate -g")
        active_device = stdout.read().decode("utf-8").strip()
        current_part = int(active_device.split('p')[-1])
        inactive_part = 3 if current_part == 2 else 2

        parts = current_version.split('.')
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            is_new_version = [int(parts[0]), int(parts[1])] >= [3, 22]
        else:
            raise SystemError(f"Cannot detect partition scheme: unexpected version format '{current_version}'")

        next_boot_part = current_part

        if is_new_version:
            try:
                ftp = self.client.open_sftp()
                with ftp.file("/sys/bus/mmc/devices/mmc0:0001/boot_part") as file:
                    boot_part_value = file.read().decode("utf-8").strip()
                    next_boot_part = 2 if boot_part_value == "1" else 3
            except (IOError, OSError):
                is_new_version = False

        if not is_new_version:
            try:
                ftp = self.client.open_sftp()
                with ftp.file("/sys/devices/platform/lpgpr/root_part") as file:
                    root_part_value = file.read().decode("utf-8").strip()
                    next_boot_part = 2 if root_part_value == "a" else 3
            except (IOError, OSError) as e:
                self.logger.debug(f"Failed to read next boot partition: {e}")

        return current_part, inactive_part, next_boot_part

    def get_device_status(self) -> tuple[str | None, str, str, str, str]:
        """Gets the status of the device

        Returns:
            tuple: Beta status, old_update_engine, current version, version_id, backup version (in that order)
        """
        old_update_engine = True

        if self.client:
            self.logger.debug("Connecting to FTP")
            ftp = self.client.open_sftp()
            self.logger.debug("Connected")

            xochitl_version, old_update_engine = self._read_version_from_path(ftp)

            with ftp.file("/etc/version") as file:
                version_id = file.read().decode("utf-8").strip("\n")

            with ftp.file("/home/root/.config/remarkable/xochitl.conf") as file:
                beta_contents = file.read().decode("utf-8")

        else:
            if os.path.exists("/usr/share/remarkable/update.conf"):
                with open("/usr/share/remarkable/update.conf", encoding="utf-8") as file:
                    xochitl_version = re.search(
                        "(?<=REMARKABLE_RELEASE_VERSION=).*",
                        file.read().strip("\n"),
                    ).group()
            else:
                with open("/etc/os-release", encoding="utf-8") as file:
                    xochitl_version = (
                        re.search("(?<=IMG_VERSION=).*", file.read())
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

        backup_version = self._get_backup_partition_version()

        return beta, old_update_engine, xochitl_version, version_id, backup_version

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

        if self.hardware in (HardwareType.RMPP, HardwareType.RMPPM):
            _, _, current_version, _, backup_version = self.get_device_status()
            current_part, inactive_part, _ = self._get_paper_pro_partition_info(current_version)

            new_part_label = "a" if inactive_part == 2 else "b"

            parts = current_version.split('.')
            if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
                raise SystemError(f"Cannot restore: unexpected current version format '{current_version}'")

            current_is_new = [int(parts[0]), int(parts[1])] >= [3, 22]

            parts = backup_version.split('.')
            if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
                raise SystemError(f"Cannot restore: unexpected backup version format '{backup_version}'")

            target_is_new = [int(parts[0]), int(parts[1])] >= [3, 22]

            code = [
                "#!/bin/bash",
                f"echo 'Switching from partition {current_part} to partition {inactive_part}'",
                f"echo 'Current version: {current_version}'",
                f"echo 'Target version: {backup_version}'",
            ]

            if not current_is_new:
                code.extend([
                    f"echo '{new_part_label}' > /sys/devices/platform/lpgpr/root_part",
                    "echo 'Set next boot via sysfs (legacy method)'",
                ])

            if target_is_new or current_is_new:
                code.extend([
                    f"mmc bootpart enable {inactive_part - 1} 0 /dev/mmcblk0boot{inactive_part - 2}",
                    "echo 'Set next boot via mmc bootpart (new method)'",
                ])

            code.extend([
                f"echo '0' > /sys/devices/platform/lpgpr/root{new_part_label}_errcnt 2>/dev/null || true",
                "echo 'Partition switch complete'",
            ])

            RESTORE_CODE = "\n".join(code)

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

    def install_sw_update(self, version_file: str, bootloader_files: dict[str, bytes] | None = None) -> None:
        """
        Installs new version from version file path, utilising swupdate

        Args:
            version_file (str): Path to img file
            bootloader_files (dict[str, bytes] | None): Bootloader files for Paper Pro downgrade

        Raises:
            SystemExit: If there was an error installing the update

        """
        if self.client:
            ftp_client = self.client.open_sftp()

            print(f"Uploading {version_file} image")

            out_location = f"/tmp/{os.path.basename(version_file)}.swu"
            ftp_client.put(
                version_file, out_location, callback=self.output_put_progress
            )

            print("\nDone! Running swupdate (PLEASE BE PATIENT, ~5 MINUTES)")

            command = f"/usr/sbin/swupdate-from-image-file {out_location}"
            self.logger.debug(command)
            _stdin, stdout, _stderr = self.client.exec_command(command)

            exit_status = stdout.channel.recv_exit_status()

            if exit_status != 0:
                print("".join(_stderr.readlines()))
                raise SystemError("Update failed!")

            if bootloader_files:
                print("\nApplying bootloader update...")
                self._update_paper_pro_bootloader(
                    bootloader_files['update-bootloader.sh'],
                    bootloader_files['imx-boot']
                )
                print("✓ Bootloader update completed")

            print("Done! Now rebooting the device and disabling update service")

            #### Now disable automatic updates

            self.client.exec_command("sleep 1 && reboot")  # Should be enough
            self.client.close()

            time.sleep(
                2
            )  # Somehow the code runs faster than the time it takes for the device to reboot

            print("Trying to connect to device")

            while not self.check_is_address_reachable(self.address):
                time.sleep(1)

            self.client = self.connect_to_device(
                remote_address=self.address, authentication=self.authentication
            )

            self.client.exec_command("systemctl stop swupdate memfaultd")

            print(
                "Update complete and update service disabled, restart device to enable it"
            )

        else:
            print("Running swupdate")
            command = ["/usr/sbin/swupdate-from-image-file", version_file]
            self.logger.debug(command)

            try:
                output = subprocess.check_output(
                    command,
                    stderr=subprocess.STDOUT,
                    text=True,
                    env={"PATH": "/bin:/usr/bin:/sbin:/usr/sbin"},
                )
                self.logger.debug(f"Stdout of swupdate: {output}")
            except subprocess.CalledProcessError as e:
                print(e.output)
                raise SystemError("Update failed")

            print("Update complete and device rebooting")
            os.system("reboot")

    def _update_paper_pro_bootloader(self, bootloader_script: bytes, imx_boot: bytes) -> None:
        """
        Update bootloader on Paper Pro device for 3.22+ -> <3.22 downgrades.

        This method uploads the bootloader script and image to the device,
        then runs the update script twice (preinst and postinst) to update
        both boot partitions.

        Args:
            bootloader_script: Contents of update-bootloader.sh
            imx_boot: Contents of imx-boot image file

        Raises:
            SystemError: If bootloader update fails
        """
        self.logger.info("Starting bootloader update for Paper Pro")

        if not self.client:
            raise SystemError("No SSH connection to device")

        ftp_client = None
        try:
            ftp_client = self.client.open_sftp()
        except Exception:
            raise SystemError("Failed to open SFTP connection for bootloader update")

        script_path = "/tmp/update-bootloader.sh"
        boot_image_path = "/tmp/imx-boot"

        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.sh') as tmp_script:
            tmp_script.write(bootloader_script)
            tmp_script_path = tmp_script.name

        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.img') as tmp_boot:
            tmp_boot.write(imx_boot)
            tmp_boot_path = tmp_boot.name

        try:
            self.logger.debug("Uploading bootloader script to device")
            ftp_client.put(tmp_script_path, script_path)

            self.logger.debug("Uploading imx-boot image to device")
            ftp_client.put(tmp_boot_path, boot_image_path)

            self.logger.debug("Making bootloader script executable")
            _stdin, stdout, _stderr = self.client.exec_command(f"chmod +x {script_path}")
            stdout.channel.recv_exit_status()

            self.logger.info("Running bootloader update script (preinst)")
            _stdin, stdout, stderr = self.client.exec_command(
                f"{script_path} preinst {boot_image_path}"
            )
            exit_status = stdout.channel.recv_exit_status()
            if exit_status != 0:
                error_msg = "".join(stderr.readlines())
                raise SystemError(f"Bootloader preinst failed: {error_msg}")

            self.logger.info("Running bootloader update script (postinst)")
            _stdin, stdout, stderr = self.client.exec_command(
                f"{script_path} postinst {boot_image_path}"
            )
            exit_status = stdout.channel.recv_exit_status()
            if exit_status != 0:
                error_msg = "".join(stderr.readlines())
                raise SystemError(f"Bootloader postinst failed: {error_msg}")

            self.logger.info("Bootloader update completed successfully")

        finally:
            self.logger.debug("Cleaning up temporary bootloader files on device")
            self.client.exec_command(f"rm -f {script_path} {boot_image_path}")

            self.logger.debug("Cleaning up local temporary files")
            os.unlink(tmp_script_path)
            os.unlink(tmp_boot_path)
            if ftp_client:
                ftp_client.close()

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

            while not self.check_is_address_reachable(self.address):
                time.sleep(1)

            self.client = self.connect_to_device(
                remote_address=self.address, authentication=self.authentication
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
            f"Transferring progress{int((transferred / toBeTransferred) * 100)}%",
            end="\r",
        )

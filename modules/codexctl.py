import argparse
import subprocess
import re
import threading
import os.path
import socket
import psutil

from modules.updates import UpdateManager
from modules.server import startUpdate, scanUpdates

REMOTE_DEPS_MET = True

try:
    import paramiko
except ImportError:
    REMOTE_DEPS_MET = False

RESTORE_CODE = """
# switches the active root partition

fw_setenv "upgrade_available" "1"
fw_setenv "bootcount" "0"

OLDPART=$(fw_printenv -n active_partition)
if [ $OLDPART  ==  "2" ]; then
    NEWPART="3"
else
    NEWPART="2"
fi
echo "new: ${NEWPART}"
echo "fallback: ${OLDPART}"

fw_setenv "fallback_partition" "${OLDPART}"
fw_setenv "active_partition" "${NEWPART}"
"""

updateman = UpdateManager()


def get_host_ip():
    possible_ips = []
    try:
        for interface, snics in psutil.net_if_addrs().items():
            for snic in snics:
                if snic.family == socket.AF_INET:
                    if snic.address.startswith("10.11.99"):
                        return [snic.address]
                    possible_ips.append(snic.address)
    except Exception as error:
        pass

    return possible_ips


def version_lookup(version, device):
    if version == "latest":
        return updateman.get_latest_version(device=device)
    if version == "toltec":
        return updateman.latest_toltec_version

    if device == 2:
        version_dict = updateman.id_lookups_rm2
    elif device == 1:
        version_dict = updateman.id_lookups_rm1
    else:
        raise SystemError("Error: Invalid device given!")

    if version in version_dict:
        return version

    raise SystemExit(
        "Error: Invalid version! Examples: latest, toltec, 3.2.3.1595, 2.15.0.1067"
    )


def connect_to_rm(args, ip="10.11.99.1"):
    client = paramiko.client.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    if args.auth:
        try:
            if os.path.isfile(args.auth):
                client.connect("10.11.99.1", username="root", key_filename=args.auth)
            else:
                client.connect("10.11.99.1", username="root", password=args.auth)

            print("Connected to device")
            return client

        except paramiko.ssh_exception.AuthenticationException:
            print("Incorrect password or ssh path given in arguments!: {error}")

    if "n" in input("Would you like to use a password to connect? (Y/n) ").lower():
        while True:
            key_path = input("Enter path to SSH key: ")

            if not os.path.isfile(key_path):
                print("Invalid path given")

                continue
            try:
                client.connect("10.11.99.1", username="root", key_filename=key_path)
            except Exception as error:
                print("Error while connecting to device: {error}")

                continue
            break
    else:
        while True:
            password = input("Enter RM SSH password: ")

            try:
                client.connect(ip, username="root", password=password)
            except paramiko.ssh_exception.AuthenticationException:
                print("Incorrect password given")

                continue
            break

    print("Connected to device")
    return client


def set_server_config(contents, server_host_name):
    data_attributes = contents.split("\n")
    data_attributes[2] = f"SERVER={server_host_name}"
    return "\n".join(data_attributes)


def edit_config(server_ip, port=8080, remarkable_remote=None):
    if not remarkable_remote:
        with open("/usr/share/remarkable/update.conf", encoding="utf-8") as file:
            modified_conf_version = set_server_config(
                file.read(), f"http://{server_ip}:{port}"
            )

        with open("/usr/share/remarkable/update.conf", "w") as file:
            file.write(modified_conf_version)

        return

    server_host_name = f"http://{server_ip}:{port}"
    ftp = remarkable_remote.open_sftp()  # or ssh
    with ftp.file("/usr/share/remarkable/update.conf") as update_conf_file:
        modified_conf_version = set_server_config(
            update_conf_file.read().decode("utf-8"), server_host_name
        )

    with ftp.file(
        "/usr/share/remarkable/update.conf", "w+"
    ) as update_conf_file:  # w/w+ mode
        update_conf_file.write(modified_conf_version)


def get_remarkable_ip():
    while True:
        remote_ip = input("Please enter the IP of the remarkable device: ")
        if input("Are you sure? (Y/n) ").lower() != "n":
            break

    return remote_ip


def do_download(args, device_type):
    version = version_lookup(version=args.version, device=device_type)
    print(f"Downloading {version}")
    filename = updateman.get_version(version=version, device=device_type)

    if filename is None:
        raise SystemExit("Error: Was not able to download firmware file!")

    if filename == "Not in version list":
        raise SystemExit("Error: This version is not currently supported!")

    print(f"Done! ({filename})")


def do_status(args):
    try:
        with open("/etc/remarkable.conf") as file:
            config_contents = file.read()
        with open("/etc/version") as file:
            version_id = file.read().rstrip()
        with open("/usr/share/remarkable/update.conf") as file:
            version_contents = file.read().rstrip()
    except FileNotFoundError: 
        if not REMOTE_DEPS_MET:
            raise SystemExit(
            "Error: Detected as running on the remote device, but could not resolve dependencies. "
            'Please install them with "pip install -r requirements.txt'
        )
        if len(get_host_ip()) == 1:
            ip = "10.11.99.1"
        else:
            ip = get_remarkable_ip()

        remarkable_remote = connect_to_rm(args, ip=ip)
        ftp = remarkable_remote.open_sftp()  # or ssh

        with ftp.file("/etc/remarkable.conf") as file:
            config_contents = file.read().decode("utf-8")

        with ftp.file("/etc/version") as file:
            version_id = file.read().decode("utf-8").strip("\n")

        with ftp.file("/usr/share/remarkable/update.conf") as file:
            version_contents = file.read().decode("utf-8")

    beta = re.search("(?<=BetaProgram=).*", config_contents)
    prev = re.search("(?<=[Pp]reviousVersion=).*", config_contents).group()
    current = re.search("(?<=REMARKABLE_RELEASE_VERSION=).*", version_contents).group()

    print(
        f'You are running {current} [{version_id}]{"[BETA]" if beta is not None and beta.group() else ""}, previous version was {prev}'
    )

def get_available_version(version):
    available_versions = scanUpdates()
    
    for device, ids in available_versions.items():
        if version in ids:
            available_version = {device: ids}
            
            return available_version

def do_install(args, device_type):
    available_versions = scanUpdates()

    version = version_lookup(version=args.version, device=device_type)
    available_versions = get_available_version(version)

    if available_versions is None:
        print(
            f"The version firmware file you specified could not be found, attempting to download ({version})"
        )
        result = updateman.get_version(version=version, device=device_type)
        
        if result is None:
            raise SystemExit("Error: Was not able to download firmware file!")

        if result == "Not in version list":
            raise SystemExit("Error: This version is not supported!")
        
        available_versions = get_available_version(version)
        if available_versions is None:
            raise SystemExit("Error: Something went wrong trying to download update file!")

    server_host = "0.0.0.0"
    remarkable_remote = None

    if not os.path.isfile("/usr/share/remarkable/update.conf") and not REMOTE_DEPS_MET:
        raise SystemExit(
            "Error: Detected as running on the remote device, but could not resolve dependencies. "
            'Please install them with "pip install -r requirements.txt'
        )

    server_host = get_host_ip()

    if server_host is None:
        raise SystemExit(
            "Error: This device does not seem to have a network connection."
        )

    if len(server_host) == 1:  # This means its found the USB interface
        server_host = server_host[0]
        remarkable_remote = connect_to_rm(args)
    else:
        host_interfaces = "\n".join(server_host)

        print(
            f"\n{host_interfaces}\nCould not find USB interface, assuming connected over WiFi (interfaces list above)"
        )
        while True:
            server_host = input(
                "\nPlease enter your IP for the network the device is connected to: "
            )

            if server_host not in host_interfaces.split("\n"):  # Really...? This co
                print("Error: Invalid IP given")
                continue
            if "n" in input("Are you sure? (Y/n) ").lower():
                continue

            break

        remote_ip = get_remarkable_ip()

        remarkable_remote = connect_to_rm(args, remote_ip)

    edit_config(remarkable_remote=remarkable_remote, server_ip=server_host, port=8080)

    print(
        f"Available versions to update to are: {available_versions}\nThe device will update to the latest one."
    )
    thread = threading.Thread(
        target=startUpdate, args=(available_versions, server_host), daemon=True
    )
    thread.start()
    
    # Is it worth mapping the messages to a variable?
    if remarkable_remote is None:
        print("Enabling update service")
        subprocess.run("systemctl start update-engine", shell=True, text=True)

        process = subprocess.Popen(
            "update_engine_client -update",
            text=True,
            stdout=subprocess.PIPE,
            shell=True,
        )

        if process.wait() != 0:
            # TODO: More verbose error handling!
            raise SystemExit("There was an error updating :(")

        if "y" in input("Done! Would you like to shutdown?: ").lower():
            subprocess.run(["shutdown", "now"])
    else:
        print("Checking if device can reach server")
        _stdin, stdout, _stderr = remarkable_remote.exec_command(
            f"sleep 2 && echo | nc {server_host} 8080"
        )
        stdout.channel.recv_exit_status()

        if stdout.channel.recv_exit_status() != 0:
            raise SystemExit(
                "Device cannot reach server! Is the firewall blocking connections?"
            )

        print("Starting update service on device")
        remarkable_remote.exec_command("systemctl start update-engine")

        _stdin, stdout, _stderr = remarkable_remote.exec_command(
            "update_engine_client -update"
        )
        exit_status = stdout.channel.recv_exit_status()

        if exit_status != 0:
            raise SystemExit("There was an error updating :(")

        print("Success! Please restart the reMarkable device!")


def do_restore(args):
    if "y" not in input("Are you sure you want to restore? (y/N) ").lower():
        raise SystemExit("Aborted!!!")

    if os.path.isfile("/usr/share/remarkable/update.conf"):
        # TODO: This is repeated code...organise it!
        subprocess.run(RESTORE_CODE, shell=True, text=True)

        if "y" in input("Done! Would you like to shutdown?: ").lower():
            subprocess.run(["shutdown", "now"])

    elif not REMOTE_DEPS_MET:
        raise SystemExit(
            "Error: Detected as running on the remote device, but could not resolve dependencies. "
            'Please install them with "pip install -r requirements.txt"'
        )

    else:
        if len(get_host_ip()) == 1:
            print("Detected as USB connection")
            remote_ip = "10.11.99.1"
        else:
            print("Detected as WiFi connection")
            remote_ip = get_remarkable_ip()

        remarkable_remote = connect_to_rm(args, remote_ip)

        _stdin, stdout, _stderr = remarkable_remote.exec_command(RESTORE_CODE)
        stdout.channel.recv_exit_status()

        print("Done, Please reboot the device!")


def do_list():
    print("\nRM2:")
    [print(codexID) for codexID in updateman.id_lookups_rm2]
    print("\nRM1:")
    [print(codexID) for codexID in updateman.id_lookups_rm1]


def main():
    parser = argparse.ArgumentParser("Codexctl app")
    parser.add_argument("--debug", action="store_true", help="Print debug info")
    parser.add_argument("--rm1", action="store_true", default=False, help="Use rm1")
    parser.add_argument("--auth", required=False, help="Specify password or SSH key for SSH")

    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True  # This fixes a bug with older versions of python

    install = subparsers.add_parser(
        "install",
        help="Install the specified version (will download if not available on the device)",
    )
    download = subparsers.add_parser(
        "download", help="Download the specified version firmware file"
    )
    subparsers.add_parser(
        "status", help="Get the current version of the device and other information"
    )
    subparsers.add_parser(
        "restore", help="Restores to previous version installed on device"
    )
    subparsers.add_parser("list", help="List all versions available for use")

    install.add_argument("version", help="Version to install")
    download.add_argument("version", help="Version to download")

    args = parser.parse_args()
    choice = args.command

    device_type = 2

    if args.rm1:
        device_type = 1

    ### Decision making ###
    if choice == "install":
        do_install(args, device_type)

    elif choice == "download":
        do_download(args, device_type)

    elif choice == "status":
        do_status(args)

    elif choice == "restore":
        do_restore(args)

    elif choice == "list":
        do_list()


if __name__ == "__main__":
    main()

#!/opt/bin/python
from modules.updates import UpdateManager
from modules.server import startUpdate, scanUpdates
from time import sleep

import argparse
import subprocess
import re
import threading
import os.path

remoteDepsMet = True

try:
    import paramiko
    import netifaces as ni
except ImportError:
    remoteDepsMet = False

parser = argparse.ArgumentParser("Codexctl app")
parser.add_argument("--debug", action="store_true", help="Print debug info")

subparsers = parser.add_subparsers(dest="command")
subparsers.required = True  # This fixes a bug with older versions of python

install = subparsers.add_parser(
    "install",
    help="Install the specified version (will download if not available on the device)",
)
download = subparsers.add_parser(
    "download", help="Download the specified version firmware file"
)
status = subparsers.add_parser(
    "status", help="Get the current version of the device and other information"
)
restore = subparsers.add_parser(
    "restore", help="Restores to previous version installed on device"
)
list_ = subparsers.add_parser("list", help="List all versions available for use")

install.add_argument("version", help="Version to install")
download.add_argument("version", help="Version to download")

download.add_argument(
    "--rm1", help="Add this to select rm1", action="store_true", required=False
)
install.add_argument(
    "--rm1", help="Add this to select rm1", action="store_true", required=False
)

args = parser.parse_args()
updateman = UpdateManager()
choice = args.command

deviceType = 2

if hasattr(args, "rm1"):
    if args.rm1:
        deviceType = 1  # Weird checking but okay/alright

restoreCode = """
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


def get_host_ip():
    possible_ips = []
    try:
        for interface in ni.interfaces():
            for num in ni.ifaddresses(interface).values():
                for ip in num:
                    if ip["addr"].startswith("10.11.99"):
                        return [ip["addr"]]
                    possible_ips.append(ip["addr"])
    except Exception as error:
        pass

    return possible_ips


def version_lookup(version, device):
    if version == "latest":
        return updateman.get_latest_version(device=deviceType)
    if version == "toltec":
        return updateman.latest_toltec_version

    if device == 2:
        versionDict = updateman.id_lookups_rm2
    elif device == 1:
        versionDict = updateman.id_lookups_rm1
    else:
        raise SystemError("Error: Invalid device given!")

    if version in versionDict:
        return version

    raise SystemExit(
        "Error: Invalid version! Examples: latest, toltec, 3.2.3.1595, 2.15.0.1067"
    )


def connect_to_rm(ip="10.11.99.1"):
    client = paramiko.client.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

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


def edit_config(serverIP, port=8080, remarkableRemote=None):
    if remarkableRemote:
        server_host_name = f"http://{serverIP}:{port}"
        ftp = remarkableRemote.open_sftp()  # or ssh

        with ftp.file("/usr/share/remarkable/update.conf") as update_conf_file:
            contents = update_conf_file.read().decode("utf-8")
            data_attributes = contents.split("\n")

            data_attributes[2] = f"SERVER={server_host_name}"

            modified_conf_version = "\n".join(data_attributes)  # add final ?

        with ftp.file(
            "/usr/share/remarkable/update.conf", "w+"
        ) as update_conf_file:  # w/w+ mode
            update_conf_file.write(modified_conf_version)

    else:
        with open("/usr/share/remarkable/update.conf", encoding="utf-8") as file:
            contents = file.read()
            data_attributes = contents.split("\n")
            data_attributes[2] = f"SERVER=http://{serverIP}:{port}"
            modified_conf_version = "\n".join(data_attributes)
        with open("/usr/share/remarkable/update.conf", "w") as file:
            file.write(modified_conf_version)


def get_remarkable_ip():
    while True:
        remoteIP = input("Please enter the IP of the remarkable device: ")
        if input("Are you sure? (Y/n) ").lower() != "n":
            break

    return remoteIP


### Decision making ###
if choice == "install":
    prerequisitesMet = False

    while prerequisitesMet == False:
        availableVersions = scanUpdates()

        version = version_lookup(version=args.version, device=deviceType)

        for device, ids in availableVersions.items():
            if version in ids:
                availableVersions = {device: ids}
                prerequisitesMet = True
                break
        else:
            print(
                f"The version firmware file you specified could not be found, attempting to download ({version})"
            )
            result = updateman.get_version(version=version, device=deviceType)

            if result is None:
                raise SystemExit("Error: Was not able to download firmware file!")
            elif result == "Not in version list":
                raise SystemExit("Error: This version is not supported!")

    if availableVersions == {}:
        raise SystemExit("No updates available!")

    serverHost = "0.0.0.0"
    remarkableRemote = None

    if os.path.isfile("/usr/share/remarkable/update.conf"):
        pass
    elif remoteDepsMet == False:
        raise SystemExit(
            'Error: Detected as running on the remote device, but could not resolve dependencies. Please install them with "pip install paramiko netifaces"'
        )
    else:
        serverHost = get_host_ip()

        if serverHost == None:
            raise SystemExit(
                "Error: This device does not seem to have a network connection."
            )

        elif len(serverHost) == 1:  # This means its found the USB interface
            serverHost = serverHost[0]
            remarkableRemote = connect_to_rm("10.11.99.1")
        else:
            hostInterfaces = "\n".join(serverHost)

            print(
                f"\n{hostInterfaces}\nCould not find USB interface, assuming connected over WiFi (interfaces list above)"
            )
            while True:
                serverHost = input(
                    f"\nPlease enter your IP for the network the device is connected to: "
                )

                if serverHost not in hostInterfaces.split("\n"):  # Really...? This co
                    print("Error: Invalid IP given")
                    continue
                if "n" in input("Are you sure? (Y/n) ").lower():
                    continue

                break

            remoteIP = get_remarkable_ip()

            remarkableRemote = connect_to_rm(remoteIP)

    edit_config(remarkableRemote=remarkableRemote, serverIP=serverHost, port=8080)

    x = threading.Thread(
        target=startUpdate, args=(availableVersions, serverHost), daemon=True
    )  # TODO: Get version automatically
    x.start()

    # Is it worth mapping the messages to a variable?
    if remarkableRemote is None:
        print("Enabling update service")
        subprocess.run("systemctl start update-engine", shell=True, text=True)

        updateProcess = subprocess.Popen(
            "update_engine_client -update",
            text=True,
            stdout=subprocess.PIPE,
            shell=True,
        )

        if updateProcess.wait() != 0:
            raise SystemExit(
                "There was an error updating :("
            )  # TODO: More verbose error handling!

        if "y" in input("Done! Would you like to shutdown?: ").lower():
            subprocess.run(["shutdown", "now"])
    else:
        print("Starting update service on device")
        remarkableRemote.exec_command("systemctl start update-engine")

        _stdin, stdout, _stderr = remarkableRemote.exec_command(
            "update_engine_client -update"
        )
        exit_status = stdout.channel.recv_exit_status()

        if exit_status != 0:
            raise SystemExit("There was an error updating :(")

        print("Success! Please restart the reMarkable device!")

elif choice == "download":
    version = version_lookup(version=args.version, device=deviceType)
    print(f"Downloading {version}")
    filename = updateman.get_version(version=version, device=deviceType)

    if filename is None:
        raise SystemExit("Error: Was not able to download firmware file!")
    elif filename == "Not in version list":
        raise SystemExit("Error: This version is not currently supported!")
    print(f"Done! ({filename})")

elif choice == "status":
    try:
        with open("/etc/remarkable.conf") as file:
            configContents = file.read()
        with open("/etc/version") as file:
            versionID = file.read().rstrip()
        with open("/usr/share/remarkable/update.conf") as file:
            versionContents = file.read().rstrip()

        beta = re.search("(?<=BetaProgram=).*", configContents).group()
        prev = re.search("(?<=PreviousVersion=).*", configContents).group()
        current = re.search(
            "(?<=REMARKABLE_RELEASE_VERSION=).*", versionContents
        ).group()

        print(
            f'You are running {current} [{versionID}]{"[BETA]" if beta else ""}, previous version was {prev}'
        )
    except Exception as error:
        print(
            f"Error: {error} (Maybe you aren't running this on the ReMarkable device?"
        )

elif choice == "restore":
    if "y" not in input("Are you sure you want to restore? (y/N) ").lower():
        raise SystemExit("Aborted!!!")

    if os.path.isfile(
        "/usr/share/remarkable/update.conf"
    ):  # TODO: This is repeated code...organise it!
        subprocess.run(restoreCode, shell=True, text=True)

        if "y" in input("Done! Would you like to shutdown?: ").lower():
            subprocess.run(["shutdown", "now"])

    elif remoteDepsMet == False:
        raise SystemExit(
            'Error: Detected as running on the remote device, but could not resolve dependencies. Please install them with "pip install paramiko netifaces"'
        )

    else:
        if len(get_host_ip()) == 1:
            print("Detected as USB connection")
            remoteIP = "10.11.99.1"
        else:
            print("Detected as WiFi connection")
            # remoteIP = get_remarkable_ip()
            remoteIP = "192.168.0.57"
        remarkableRemote = connect_to_rm(remoteIP)

        _stdin, stdout, _stderr = remarkableRemote.exec_command(restoreCode)
        stdout.channel.recv_exit_status()

        print("Done, Please reboot the device!")

elif choice == "list":
    print("\nRM2:")
    [print(codexID) for codexID in updateman.id_lookups_rm2]
    print("\nRM1:")
    [print(codexID) for codexID in updateman.id_lookups_rm1]

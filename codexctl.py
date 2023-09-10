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

### Setting variables ###
parser = argparse.ArgumentParser("Codexctl app")
parser.add_argument("--debug", action="store_true", help="Print debug info")
subparsers = parser.add_subparsers(dest="command", required=True)
install = subparsers.add_parser("install", help="Install the specified version (will download if not available on the device)")
download = subparsers.add_parser("download", help="Download the specified version firmware file")
status = subparsers.add_parser("status", help="Get the current version of the device and other information")
list_ = subparsers.add_parser("list", help="List all versions available for use")

install.add_argument("-v", "--version", help="Version to install", required=False)
download.add_argument("version", help="Version to download")

args = parser.parse_args()
updateman = UpdateManager()
choice = args.command


def get_rm_host_ip():
	try:
		for interface in ni.interfaces():
			for num in ni.ifaddresses(interface).values():
				for ip in num:
					if ip["addr"].startswith("10.11.99"):
						return ip["addr"]
	except Exception as error:
		pass

	raise SystemExit("Error: Could not find IP address of ReMarkable device")


def version_lookup(version):
	if version == "latest":
		return updateman.latest_version
	if version == "toltec":
		return updateman.latest_toltec_version
	elif version in updateman.id_lookups:
		return version

	raise SystemExit(
		"Invalid version! Examples: latest, toltec, 3.2.3.1595, 2.15.0.1067"
	)


def edit_config(remote, serverIP, port=8080):
	if remote:
		while True:
			password = input("Enter RM SSH password: ")

			client = paramiko.client.SSHClient()
			client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

			try:
				client.connect(
					"10.11.99.1", username="root", password=password
				)  # TODO: Only supports USB at the moment
			except paramiko.ssh_exception.AuthenticationException:
				print("Incorrect password given")

				continue
			break

		print("Connected to device")

		server_host_name = f"http://{serverIP}:{port}"
		ftp = client.open_sftp()  # or ssh

		with ftp.file(
			"/usr/share/remarkable/update.conf"
		) as update_conf_file:  # TODO: use toml, and / or confgi and support for modified .conf/ig files
			contents = update_conf_file.read().decode(
				"utf-8"
			)  # TODO: Doesn't support beta versions (fwiw modifying beta is against eula & tos - unrelated to changing versions tho!)
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


### Decision making ###
if choice == "install":
	prerequisitesMet = False

	while prerequisitesMet == False:
		avaliableVersions = scanUpdates()

		if args.version:
			version = version_lookup(args.version)

			for device, ids in avaliableVersions.items():
				if version in ids:
					avaliableVersions = {device: ids}
					prerequisitesMet = True
					break
			else:
				print(
					f"The version you specified is not on the device, attempting to download ({version})"
				)
				if updateman.get_version(version) == 'Not in version list':
					raise SystemExit("Error: This version is not supported!")
				
		else:
			prerequisitesMet = True
   
	if avaliableVersions == {}:
		raise SystemExit("No updates avaliable!")

	host = '0.0.0.0'
	remote = True 
 
	if os.path.isfile("/usr/share/remarkable/update.conf"):
		remote = False
	elif remoteDepsMet == False:
		raise SystemExit(
			'Error: Detected as running on the remote device, but could not resolve dependencies. Please install them with "pip install paramiko netifaces"'
		)
	else:
		host = get_rm_host_ip()
	
	edit_config(remote=remote, serverIP=host, port=8080)
	
	x = threading.Thread(
		target=startUpdate, args=(avaliableVersions, host), daemon=True
	)  # TODO: Get version automatically
	x.start()

	if remote == False:
		print("Enabling update service")
		subprocess.run("systemctl start update-engine", shell=True, text=True)

		updateProcess = subprocess.Popen(
			"update_engine_client -update", text=True, stdout=subprocess.PIPE, shell=True
		)

		if updateProcess.wait() != 0:
			raise SystemExit("There was an error updating :(") # TODO: More verbose error handling!

		if "y" in input("Done! Would you like to shutdown?").lower():
			subprocess.run(["shutdown", "now"])
	else:
		print('Update server has been started...please check for updates from the device') # TODO: Automatically check for updates

elif choice == "download":
	version = version_lookup(args.version)
	print(f"Downloading {version}")
	filename = updateman.get_version(version)
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


elif choice == "list":
	[print(codexID) for codexID in updateman.id_lookups]

# TODO: Add option to add to PATH
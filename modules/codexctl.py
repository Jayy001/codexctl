import argparse
import subprocess
import re
import threading
import os.path
import socket
import psutil
import sys
import tempfile
import shutil
import logging

from pathlib import Path
from loguru import logger

from modules.sync import RmWebInterfaceAPI
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


def get_host_ip():
	possible_ips = []
	try:
		for interface, snics in psutil.net_if_addrs().items():
			logger.debug(f"New interface found: {interface}")
			for snic in snics:
				if snic.family == socket.AF_INET:
					if snic.address.startswith("10.11.99"):
						return [snic.address]
					logger.debug(f"Adding new address: {snic.address}")
					possible_ips.append(snic.address)
	except Exception as error:
		logger.error(f"Error getting interfaces: {error}")

	return possible_ips


def version_lookup(version, device):
	logger.debug(f"Looking up {version} for ReMarkable {device}")
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
		logger.debug("Using authentication argument")
		try:
			if os.path.isfile(args.auth):
				logger.debug(f"Interpreting as key file location: {args.auth}")
				client.connect(ip, username="root", key_filename=args.auth)
			else:
				logger.debug(f"Interpreting as password: [REDACTED]")
				client.connect(ip, username="root", password=args.auth)

			print("Connected to device")
			return client

		except paramiko.ssh_exception.AuthenticationException:
			print("Incorrect password or ssh path given in arguments!")

	if "n" in input("Would you like to use a password to connect? (Y/n) ").lower():
		while True:
			key_path = input("Enter path to SSH key: ")

			if not os.path.isfile(key_path):
				print("Invalid path given")

				continue
			try:
				logger.debug(f"Attempting to connect with {key_path}")
				client.connect(ip, username="root", key_filename=key_path)
			except Exception as error:
				print("Error while connecting to device: {error}")

				continue
			break
	else:
		while True:
			password = input("Enter RM SSH password: ")

			try:
				logger.debug(f"Attempting to connect with {password}")
				client.connect(ip, username="root", password=password)
			except paramiko.ssh_exception.AuthenticationException:
				print("Incorrect password given")

				continue
			break

	print("Connected to device")
	return client


def set_server_config(contents, server_host_name):
	data_attributes = contents.split("\n")
	line = 0

	logger.debug(f"Contents are: {contents}")

	for i in range(0, len(data_attributes)):
		if data_attributes[i].startswith("[GENERAL]"):
			logger.debug("Found GENERAL= line")
			line = i + 1
		if not data_attributes[i].startswith("SERVER="):
			continue

		data_attributes[i] = f"#{data_attributes[i]}"
		logger.debug(f"Using {data_attributes[i]}")

	data_attributes.insert(line, f"SERVER={server_host_name}")
	converted = "\n".join(data_attributes)

	logger.debug("Converted contents are: {converted}")

	return converted


"""
This works as intended, but the remarkable device seems to ignore it...

def enable_web_over_usb(remarkable_remote=None):
	if remarkable_remote is None:
		with open(r'/home/root/.config/remarkable/xochitl.conf', 'r') as file:
			fileContents = file.read()
			fileContents = re.sub("WebInterfaceEnabled=.*", "WebInterfaceEnabled=true", fileContents)
  
		with open(r'/home/root/.config/remarkable/xochitl.conf', 'w') as file:
			file.write(fileContents)
			
	else:
		remarkable_remote.exec_command("sed -i 's/WebInterfaceEnabled=.*/WebInterfaceEnabled=true/g' /home/root/.config/remarkable/xochitl.conf")
"""


def edit_config(server_ip, port=8080, remarkable_remote=None):
	server_host_name = f"http://{server_ip}:{port}"
	logger.debug(f"Hostname is: {server_host_name}")

	if not remarkable_remote:
		logger.debug("Detected running on local device")
		with open("/usr/share/remarkable/update.conf", encoding="utf-8") as file:
			modified_conf_version = set_server_config(file.read(), server_host_name)

		with open("/usr/share/remarkable/update.conf", "w") as file:
			file.write(modified_conf_version)

		return

	logger.debug("Connecting to FTP")
	ftp = remarkable_remote.open_sftp()  # or ssh
	logger.debug("Connected")

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
	print(f"Downloading {version} to {args.out if args.out else 'downloads folder'}")
	filename = updateman.get_version(
		version=version, device=device_type, download_folder=args.out
	)

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

		logger.debug(f"IP of remarkable is {ip}")
		remarkable_remote = connect_to_rm(args, ip=ip)

		logger.debug("Connecting to FTP")
		ftp = remarkable_remote.open_sftp()  # or ssh
		logger.debug("Connected")

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

	logger.debug(f"Available versions found are: {available_versions}")
	for device, ids in available_versions.items():
		if version in ids:
			available_version = {device: ids}

			return available_version


def do_install(args, device_type):
	temp_path = None

	if args.serve_folder:  # update folder
		os.chdir(args.serve_folder)
	else:
		temp_path = tempfile.mkdtemp()
		os.chdir(temp_path)

	if not os.path.exists("updates"):
		os.mkdir("updates")

	logger.debug(f"Serve path: {os.getcwd()}")
	available_versions = scanUpdates()

	version = version_lookup(version=args.version, device=device_type)
	available_versions = get_available_version(version)

	if available_versions is None:
		print(
			f"The version firmware file you specified could not be found, attempting to download ({version})"
		)
		result = updateman.get_version(
			version=version,
			device=device_type,
			download_folder=f"{os.getcwd()}/updates",
		)

		logger.debug(f"Result of downloading version is {result}")

		if result is None:
			raise SystemExit("Error: Was not able to download firmware file!")

		if result == "Not in version list":
			raise SystemExit("Error: This version is not supported!")

		available_versions = get_available_version(version)
		if available_versions is None:
			raise SystemExit(
				"Error: Something went wrong trying to download update file!"
			)

	server_host = "0.0.0.0"
	remarkable_remote = None

	if not os.path.isfile("/usr/share/remarkable/update.conf") and not REMOTE_DEPS_MET:
		raise SystemExit(
			"Error: Detected as running on the remote device, but could not resolve dependencies. "
			'Please install them with "pip install -r requirements.txt'
		)

	server_host = get_host_ip()

	logger.debug(f"Server host is {server_host}")

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

	logger.debug("Editing config file")
	edit_config(remarkable_remote=remarkable_remote, server_ip=server_host, port=8080)

	print(
		f"Available versions to update to are: {available_versions}\nThe device will update to the latest one."
	)

	logger.debug("Starting server thread")
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
			stderr=subprocess.PIPE,
			shell=True,
		)

		if process.wait() != 0:
			print("".join(process.stderr.readlines()))

			raise SystemExit("There was an error updating :(")

		logger.debug(
			f'Stdout of update checking service is {"".join(process.stderr.readlines())}'
		)

		if "y" in input("Done! Would you like to shutdown?: ").lower():
			subprocess.run(["shutdown", "now"])
	else:
		print("Checking if device can reach server")
		_stdin, stdout, _stderr = remarkable_remote.exec_command(
			f"sleep 2 && echo | nc {server_host} 8080"
		)
		check = stdout.channel.recv_exit_status()

		logger.debug(f"Stdout of nc checking: {stdout.readlines()}")
		if check != 0:
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
			print("".join(_stderr.readlines()))
			raise SystemExit("There was an error updating :(")

		logger.debug(
			f'Stdout of update checking service is {"".join(_stderr.readlines())}'
		)

		print("Success! Please restart the reMarkable device!")

	if temp_path:
		logger.debug(f"Removing {temp_path}")
		shutil.rmtree(temp_path)


def do_restore(args):
	if "y" not in input("Are you sure you want to restore? (y/N) ").lower():
		raise SystemExit("Aborted!!!")

	if os.path.isfile("/usr/share/remarkable/update.conf"):
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

		logger.debug(f"Output of switch command: {stdout}")

		print("Done, Please reboot the device!")


def do_list():
	print("\nRM2:")
	[print(codexID) for codexID in updateman.id_lookups_rm2]
	print("\nRM1:")
	[print(codexID) for codexID in updateman.id_lookups_rm1]


def do_backup(args):
	print(
		"Please make sure the web-interface is enabled in the remarkable settings!\nStarting backup..."
	)

	rmWeb = RmWebInterfaceAPI(BASE="http://10.11.99.1/", logger=logger)
	rmWeb.sync(
		localFolder=args.local,
		remoteFolder=args.remote,
		recursive=not args.no_recursion,
		overwrite=not args.no_overwrite,
	)


def main():
	parser = argparse.ArgumentParser("Codexctl app")
	parser.add_argument("--debug", action="store_true", help="Print debug info")
	parser.add_argument("--rm1", action="store_true", default=False, help="Use rm1")
	parser.add_argument(
		"--auth", required=False, help="Specify password or SSH key for SSH"
	)
	parser.add_argument("--verbose", required=False, help="Enable verbose logging", action="store_true")

	subparsers = parser.add_subparsers(dest="command")
	subparsers.required = True  # This fixes a bug with older versions of python

	install = subparsers.add_parser(
		"install",
		help="Install the specified version (will download if not available on the device)",
	)
	download = subparsers.add_parser(
		"download", help="Download the specified version firmware file"
	)
	backup = subparsers.add_parser(
		"backup", help="Download remote files to local directory"
	)
	subparsers.add_parser(
		"status", help="Get the current version of the device and other information"
	)
	subparsers.add_parser(
		"restore", help="Restores to previous version installed on device"
	)
	subparsers.add_parser("list", help="List all versions available for use")

	install.add_argument("version", help="Version to install")
	install.add_argument(
		"-sf",
		"--serve-folder",
		help="Location of folder containing update folder & files",
		default=None,
	)

	download.add_argument("version", help="Version to download")
	download.add_argument("--out", help="Folder to download to", default=None)

	backup.add_argument(
		"-r",
		"--remote",
		help="Remote directory to backup. Defaults to download folder",
		default="",
	)
	backup.add_argument(
		"-l",
		"--local",
		help="Local directory to backup to. Defaults to download folder",
		default="./",
	)

	backup.add_argument(
		"-nr",
		"--no-recursion",
		help="Disables recursively backup remote directory",
		action="store_true",
	)
	backup.add_argument(
		"-no-ow", "--no-overwrite", help="Disables overwrite", action="store_true"
	)

	args = parser.parse_args()
	level = "ERROR"
	
	if args.verbose:
		level = "DEBUG"
 
	logger.remove()
	logger.add(sys.stderr, level=level)
	logging.basicConfig(level=logging.DEBUG if args.verbose else logging.ERROR) # For paramioko

	global updateman
	updateman = UpdateManager(logger=logger)
 
	logger.debug(f"Remote deps met: {REMOTE_DEPS_MET}")

	choice = args.command

	device_type = 2

	if args.rm1:
		device_type = 1

	logger.debug(f"Inputs are: {args}")

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

	elif choice == "backup":
		do_backup(args)


if __name__ == "__main__":
	main()

### Importing required general modules

import argparse
import os.path
import sys
import logging
import importlib
import tempfile
import shutil
import json

from pathlib import Path

try:
    from loguru import logger
except ImportError:
    logger = logging.getLogger(__name__)

if importlib.util.find_spec("requests") is None:
    raise ImportError(
        "Requests is required for accessing remote files. Please install it."
    )

from .modules.updates import UpdateManager


class Manager:
    def __init__(self, device, logger):
        """Initializes the Manager class for codexctl

        Args:
            device (str): Type of device that is running the script
            logger (logger): Logger object
        """
        self.device = device
        self.logger = logger
        self.updater = UpdateManager(logger)

    def call_func(self, function: str, args) -> None:
        """Runs a command based on the function name and arguments provided"""

        if "remarkable" not in self.device:
            remarkable_version = "remarkable1" if "rm1" in args else "remarkable2"
        else:
            remarkable_version = self.device

        version = args.get("version", None)

        if version == "latest":
            version = self.updater.get_latest_version(remarkable_version)
        elif version == "toltec":
            version = self.updater.toltec_latest

        ### Download functionalities
        if function == "list":
            print(
                f"""
ReMarkable 2:
{json.dumps(list(self.updater.remarkable2_versions.keys()), indent=4)}

ReMarkable 1:
{json.dumps(list(self.updater.remarkable1_versions.keys()), indent=4)}
            """
            )

        elif function == "download":
            logger.debug(f"Downloading version {version}")
            filename = self.updater.download_version(
                remarkable_version, version, args["out"]
            )

            if filename:
                print(f"Sucessfully downloaded to {filename}")

        ### Analysis functionalities
        elif function in ("mount", "extract"):
            try:
                from remarkable_update_fuse import UpdateFS
            except ImportError:
                raise ImportError(
                    "remarkable_update_fuse is required for mounting and extracting. Please install it. (Linux only!)"
                )

            if function == "extract":
                if not args["out"]:
                    args["out"] = os.getcwd() + "/extracted"

                logger.debug(f"Extracting {args['file']} to {args['out']}")
                from remarkable_update_fuse import UpdateImage

                image = UpdateImage(args["file"])
                with open(args["out"], "wb") as f:
                    f.write(image.read())
            else:
                if args["out"] is None:
                    args["out"] = "/opt/remarkable/"

                if not os.path.exists(args["out"]):
                    os.mkdir(args["out"])

                if not os.path.exists(args["filesystem"]):
                    raise SystemExit("Firmware file does not exist!")

                from remarkable_update_fuse import UpdateFS

                server = UpdateFS()
                server.parse(
                    args=[args["filesystem"], args["out"]], values=server, errex=1
                )
                server.main()

        ### WebInterface functionalities
        elif function in ("backup", "upload"):
            from .modules.sync import RmWebInterfaceAPI

            print(
                "Please make sure the web-interface is enabled in the remarkable settings!\nStarting upload..."
            )

            rmWeb = RmWebInterfaceAPI(BASE="http://10.11.99.1/", logger=logger)

            if function == "backup":
                rmWeb.sync(
                    localFolder=args["local"],
                    remoteFolder=args["remote"],
                    recursive=not args["no_recursion"],
                    overwrite=not args["no_overwrite"],
                )
            else:
                rmWeb.upload(input_paths=args["paths"], remoteFolder=args["remote"])

        ### Update & Version functionalities
        elif function in ("install", "status", "restore"):
            remote = False

            if "remarkable" not in self.device:
                if importlib.util.find_spec("paramiko") is None:
                    raise ImportError(
                        "Paramiko is required for SSH access. Please install it."
                    )
                if importlib.util.find_spec("psutil") is None:
                    raise ImportError(
                        "Psutil is required for SSH access. Please install it."
                    )
                remote = True

            from .modules.device import DeviceManager
            from .modules.server import get_available_version

            remarkable = DeviceManager(
                remote=remote,
                address=args["address"],
                logger=self.logger,
                authentication=args["pass"],
            )

            if function == "status":
                beta, prev, current = remarkable.get_device_status()
                print(
                    f"\nCurrent version: {current}\nSecondary version: {prev}\nBeta active: {beta}"
                )

            elif function == "restore":
                remarkable.restore_previous_version()
                print(
                    f"Device restored to previous version [{remarkable.get_device_status()[1]}]"
                )
                remarkable.reboot_device()
                print("Device rebooted...")

            else:
                temp_path = None
                orig_cwd = os.getcwd()

                # Do we have a specific folder to serve from?

                if args["serve_folder"]:
                    os.chdir(args["serve_folder"])

                else:
                    temp_path = tempfile.mkdtemp()
                    os.chdir(temp_path)

                if not os.path.exists("updates"):
                    os.mkdir("updates")

                # Downloading version if not available
                if get_available_version(version) is None:
                    print(
                        f"Version {version} not available in serve folder. Downloading..."
                    )

                    result = self.updater.download_version(
                        remarkable_version, version, "./updates"
                    )
                    if result:
                        print(f"Downloaded version {version} to {result}")

                    else:
                        raise SystemExit(f"Failed to download version {version}!")

                # Installing version
                version_available = get_available_version(version)

                if version_available is None:
                    print(
                        f"Version {version} still not available in serve folder. Exiting..."
                    )
                else:
                    remarkable.install_manual_update(version_available)

                os.chdir(orig_cwd)
                if temp_path:
                    logger.debug(f"Removing temporary folder {temp_path}")
                    shutil.rmtree(temp_path)


def main() -> None:
    """Main function for codexctl"""

    ### Setting up the argument parser
    parser = argparse.ArgumentParser("Codexctl")
    parser.add_argument(
        "--pass",
        "-p",
        required=False,
        help="Specify password or path to SSH key for remote access",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        required=False,
        help="Enable verbose logging",
        action="store_true",
    )
    parser.add_argument(
        "--address",
        "-a",
        required=False,
        help="Specify the address of the device",
        default=None,
    )

    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True  # This fixes a bug with older versions of python

    ### Install subcommand
    install = subparsers.add_parser(
        "install",
        help="Install the specified version (will download if not available on the device)",
    )
    install.add_argument("version", help="Version to install")
    install.add_argument(
        "-sf",
        "--serve-folder",
        help="Location of folder containing update folder & files",
        default=None,
    )

    ### Download subcommand
    download = subparsers.add_parser(
        "download", help="Download the specified version firmware file"
    )
    download.add_argument("version", help="Version to download")
    download.add_argument("--out", help="Folder to download to", default=None)
    download.add_argument(
        "--rm1", help="Download reMarkable 1 version", action="store_true"
    )

    ### Backup subcommand
    backup = subparsers.add_parser(
        "backup", help="Download remote files to local directory"
    )
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

    ### Extract subcommand
    extract = subparsers.add_parser(
        "extract", help="Extract the specified version update file"
    )
    extract.add_argument("file", help="Path to update file to extract", default=None)
    extract.add_argument("--out", help="Folder to extract to", default=None)

    ### Mount subcommand
    mount = subparsers.add_parser(
        "mount", help="Mount the specified version firmware filesystem"
    )
    mount.add_argument(
        "filesystem",
        help="Path to version firmware filesystem to extract",
        default=None,
    )
    mount.add_argument("--out", help="Folder to mount to", default=None)

    ### Upload subcommand
    upload = subparsers.add_parser(
        "upload", help="Upload folder/files to device (pdf only)"
    )
    upload.add_argument(
        "paths", help="Path to file(s)/folder to upload", default=None, nargs="+"
    )
    upload.add_argument(
        "-r",
        "--remote",
        help="Remote directory to upload to. Defaults to root folder",
        default="",
    )

    ### Status subcommand
    subparsers.add_parser(
        "status", help="Get the current version of the device and other information"
    )

    ### Restore subcommand
    subparsers.add_parser(
        "restore", help="Restores to previous version installed on device"
    )

    ### List subcommand
    subparsers.add_parser("list", help="List all available versions")

    ### Setting logging level
    args = parser.parse_args()
    logging_level, paramiko_level = (
        ("DEBUG", logging.DEBUG) if args.verbose else ("ERROR", logging.ERROR)
    )

    logger.remove()
    logger.add(sys.stderr, level=logging_level)
    logging.basicConfig(level=paramiko_level)

    ### Detecting device information
    device = None

    if os.path.exists("/sys/devices/soc0/machine"):
        with open("/sys/devices/soc0/machine") as machine_file:
            contents = machine_file.read().strip()

            if contents.startswith("reMarkable"):
                device = "reMarkable1" if "1" in contents else "reMarkable2"

    if device is None:
        device = sys.platform

    logger.debug(f"Running on platform: {device}")
    logger.debug(f"Running with args: {args}")

    ### Call function
    man = Manager(device, logger)
    man.call_func(args.command, vars(args))

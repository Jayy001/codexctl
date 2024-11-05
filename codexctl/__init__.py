### Importing required general modules

import argparse
import os.path
import sys
import logging
import importlib
import tempfile
import shutil
import json

from os import listdir

try:
    from loguru import logger
except ImportError:
    logger = logging.getLogger(__name__)

if importlib.util.find_spec("requests") is None:
    raise ImportError(
        "Requests is required for accessing remote files. Please install it."
    )

from .updates import UpdateManager


class Manager:
    """
    Main class for codexctl
    """

    def __init__(self, device: str, logger: logging.Logger) -> None:
        """Initializes the Manager class for codexctl

        Args:
            device (str): Type of device that is running the script
            logger (logger): Logger object
        """
        self.device = device
        self.logger = logger
        self.updater = UpdateManager(logger)

    def call_func(self, function: str, args: dict) -> None:
        """Runs a command based on the function name and arguments provided

        Args:
            function: The function to run
            args: What arguments to pass into the function
        """

        if "remarkable" not in self.device:
            remarkable_version = args.get("hardware")
        else:
            remarkable_version = self.device

        version = args.get("version", None)

        if version == "latest":
            version = self.updater.get_latest_version(remarkable_version)
        elif version == "toltec":
            version = self.updater.get_toltec_version(remarkable_version)

        ### Download functionalities
        if function == "list":
            print(
                f"""
ReMarkable Paper Pro:
{json.dumps(list(self.updater.remarkablepp_versions.keys()), indent=4)}

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

        ### Mounting functionalities
        elif function in ("extract", "mount"):
            try:
                from .analysis import get_update_image
            except ImportError:
                raise ImportError(
                    "remarkable_update_image is required for analysis. Please install it!"
                )

            if function == "extract":
                if sys.platform != "linux":
                    raise NotImplementedError

                if not args["out"]:
                    args["out"] = os.getcwd() + "/extracted"

                logger.debug(f"Extracting {args['file']} to {args['out']}")
                image, volume = get_update_image(args["file"])
                image.seek(0)

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

        ### Analysis functionalities
        elif function in ("cat", "ls"):
            try:
                from .analysis import get_update_image
            except ImportError:
                raise ImportError(
                    "remarkable_update_image is required for analysis. Please install it. (Linux only!)"
                )
            
            try:
                image, volume = get_update_image(args.file)
                inode = volume.inode_at(args.target_path)
                
            except FileNotFoundError:
                print(f"'{args.target_path}': No such file or directory")
                raise FileNotFoundError

            except OSError:
                print(f"'{args.target_path}': {os.strerror(e.errno)}")
                sys.exit(e.errno)

            if function == "cat":
                sys.stdout.buffer.write(inode.open().read())

            elif function == "ls":
                print(" ".join([x.name_str for x, _ in inode.opendir()]))

        ### WebInterface functionalities
        elif function in ("backup", "upload"):
            from .sync import RmWebInterfaceAPI

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

            from .device import DeviceManager
            from .server import get_available_version

            remarkable = DeviceManager(
                remote=remote,
                address=args["address"],
                logger=self.logger,
                authentication=args["password"],
            )

            if function == "status":
                beta, prev, current, version_id = remarkable.get_device_status()
                print(
                    f"\nCurrent version: {current}\nOld update engine: {prev}\nBeta active: {beta}\nVersion id: {version_id}"
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

                # We then check if the update file exists
                update_file = False
                update_file_requires_new_engine = UpdateManager.uses_new_update_engine(version)
                device_version_uses_new_engine = UpdateManager.uses_new_update_engine(remarkable.get_device_status()[2])

                #### PREVENT USERS FROM INSTALLING NON-COMPATIBLE IMAGES ####

                #TODO: Downgrade from versions above 3.11 to versions below 3.11 (We alredy know how to do this with #71)
                #TODO: Upgrade from versions below 3.11 to versions above 3.11 (Easy way: upgrade to 3.11.2.5 to get the new update engine, then upgrade again to the specific version)

                if device_version_uses_new_engine != update_file_requires_new_engine:
                    raise SystemError("Incompatible update file with current reMarkable update engine. See #71")

                #############################################################

                if update_file_requires_new_engine:
                    update_files = listdir("updates")
                    for file in update_files:
                        if version in file:
                            update_file = file

                            break
                else:
                    update_file = get_available_version(version)

                if not update_file:
                    print(
                        f"Version {version} not available in serve folder. Downloading..."
                    )

                    result = self.updater.download_version(
                        remarkable.hardware, version, "./updates"
                    )
                    if result:
                        print(f"Downloaded version {version} to {result}")

                        if new_engine:
                            update_file = result
                        else:
                            update_file = get_available_version(version)

                    else:
                        raise SystemExit(f"Failed to download version {version}!")

                if not update_file:
                    raise SystemExit("Could still not find update file!")

                if new_engine:
                    remarkable.install_sw_update(f"./updates/{update_file}")
                else:
                    remarkable.install_ohma_update(update_file)

                os.chdir(orig_cwd)
                if temp_path:
                    logger.debug(f"Removing temporary folder {temp_path}")
                    shutil.rmtree(temp_path)


def main() -> None:
    """Main function for codexctl"""

    ### Setting up the argument parser
    parser = argparse.ArgumentParser("Codexctl")
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
    parser.add_argument(
        "--password",
        "-p",
        required=False,
        help="Specify password or path to SSH key for remote access",
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
    download.add_argument("--out", "-o", help="Folder to download to", default=None)
    download.add_argument(
        "--hardware", "--h", help="Hardware to download for", required=True
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

    ### Cat subcommand
    cat = subparsers.add_parser(
        "cat", help="Cat the contents of a file inside an update image"
    )
    cat.add_argument("file", help="Path to update file to cat", default=None)
    cat.add_argument("target_path", help="Path inside the image to list", default=None)

    ### Ls subcommand
    ls = subparsers.add_parser("ls", help="List files inside an update image")
    ls.add_argument("file", help="Path to update file to extract", default=None)
    ls.add_argument("target_path", help="Path inside the image to list", default=None)

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

    try:
        logger.remove()
        logger.add(sys.stderr, level=logging_level)
        logging.basicConfig(level=paramiko_level)
    except AttributeError:  # For non-loguru
        logger.level = logging_level

    ### Detecting device information
    device = None

    if os.path.exists("/sys/devices/soc0/machine"):
        with open("/sys/devices/soc0/machine") as machine_file:
            contents = machine_file.read().strip()

            if "reMarkable" in contents:
                device = contents  # reMarkable 1, reMarkable 2, reMarkable Ferrari

    if device is None:
        device = sys.platform

    logger.debug(f"Running on platform: {device}")
    logger.debug(f"Running with args: {args}")

    ### Call function
    man = Manager(device, logger)
    man.call_func(args.command, vars(args))

### Importing required general modules

import argparse
import os.path
import sys
import logging
import importlib.util
import tempfile
import shutil
import json
import re

from typing import cast
from os import listdir

try:
    from loguru import logger
except ImportError:
    logger = logging.getLogger(__name__)

if importlib.util.find_spec("requests") is None:
    raise ImportError(
        "Requests is required for accessing remote files. Please install it."
    )

from .device import HardwareType
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

        try:
            remarkable_version = HardwareType.parse(self.device)
        except ValueError:
            hw = args.get("hardware")
            remarkable_version = HardwareType.parse(hw) if hw else None

        version = cast(str | None, args.get("version", None))

        if remarkable_version:
            if version == "latest":
                version = self.updater.get_latest_version(remarkable_version)
            elif version == "toltec":
                version = self.updater.get_toltec_version(remarkable_version)

        ### Download functionalities
        if function == "list":
            remarkable_pp_versions = "\n".join(
                self.updater.remarkablepp_versions.keys()
            )
            remarkable_ppm_versions = "\n".join(
                self.updater.remarkableppm_versions.keys()
            )
            remarkable_2_versions = "\n".join(self.updater.remarkable2_versions.keys())
            remarkable_1_versions = "\n".join(self.updater.remarkable1_versions.keys())

            version_blocks = []
            if remarkable_version is None or remarkable_version == HardwareType.RMPP:
                version_blocks.append(f"ReMarkable Paper Pro:\n{remarkable_pp_versions}")
            if remarkable_version is None or remarkable_version == HardwareType.RMPPM:
                version_blocks.append(f"ReMarkable Paper Pro Move:\n{remarkable_ppm_versions}")
            if remarkable_version is None or remarkable_version == HardwareType.RM2:
                version_blocks.append(f"ReMarkable 2:\n{remarkable_2_versions}")
            if remarkable_version is None or remarkable_version == HardwareType.RM1:
                version_blocks.append(f"ReMarkable 1:\n{remarkable_1_versions}")

            print("\n\n".join(version_blocks))

        elif function == "download":
            logger.debug(f"Downloading version {version}")
            assert remarkable_version is not None
            filename = self.updater.download_version(
                remarkable_version, version, args["out"]
            )

            if filename:
                print(f"Sucessfully downloaded to {filename}")

        ### Mounting functionalities
        elif function in ("extract", "mount"):
            if function == "extract":
                if not args["out"]:
                    args["out"] = os.getcwd() + "/extracted"

                logger.debug(f"Extracting {args['file']} to {args['out']}")

                # Check CPIO magic to route between SWU (CPIO) and old .signed format
                with open(args["file"], "rb") as f:
                    magic = f.read(6)

                if magic in (b'070701', b'070702'):
                    logger.info("Detected CPIO format (3.11+ SWU file)")
                    from .analysis import extract_swu_files

                    extract_swu_files(args["file"], output_dir=args["out"])
                    logger.info(f"Extracted SWU contents to {args['out']}")
                else:
                    logger.info("Detected old format (<3.11 .signed file)")
                    try:
                        from .analysis import get_update_image
                    except ImportError:
                        raise ImportError(
                            "remarkable_update_image is required for extracting old format files. Please install it!"
                        )

                    image, volume = get_update_image(args["file"])
                    image.seek(0)

                    with open(args["out"], "wb") as f:
                        f.write(image.read())
            else:
                try:
                    from .analysis import get_update_image
                    from remarkable_update_fuse import UpdateFS
                except ImportError:
                    raise ImportError(
                        "remarkable_update_image and remarkable_update_fuse are required for mounting. Please install them!"
                    )

                if args["out"] is None:
                    args["out"] = "/opt/remarkable/"

                if not os.path.exists(args["out"]):
                    os.mkdir(args["out"])

                if not os.path.exists(args["filesystem"]):
                    raise SystemExit("Firmware file does not exist!")

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
                image, volume = get_update_image(args["file"])
                inode = volume.inode_at(args["target_path"])

            except FileNotFoundError:
                print(f"{args['target_path']}: No such file or directory")
                raise FileNotFoundError

            except OSError as e:
                print(f"{args['target_path']}: {os.strerror(e.errno)}")
                sys.exit(e.errno)

            if function == "cat":
                sys.stdout.buffer.write(inode.open().read())

            elif function == "ls":
                print(" ".join([x.name_str for x, _ in inode.opendir()]))

        ### WebInterface functionalities
        elif function in ("backup", "upload"):
            from .sync import RmWebInterfaceAPI

            print(
                "Please make sure the web-interface is enabled in the remarkable settings!\nStarting upload"
            )

            rmWeb = RmWebInterfaceAPI(BASE="http://10.11.99.1/", logger=logger)

            if function == "backup":
                rmWeb.sync(
                    localFolder=args["local"],
                    remoteFolder=args["remote"],
                    recursive=not args["no_recursion"],
                    overwrite=not args["no_overwrite"],
                    incremental=args["incremental"],
                )
            else:
                rmWeb.upload(input_paths=args["paths"], remoteFolder=args["remote"])

        ### Update & Version functionalities
        elif function in ("install", "status", "restore"):
            remote = False

            if "reMarkable" not in self.device:
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

            if version == "latest":
                version = self.updater.get_latest_version(remarkable.hardware)
            elif version == "toltec":
                version = self.updater.get_toltec_version(remarkable.hardware)

            if function == "status":
                beta, prev, current, version_id, backup = remarkable.get_device_status()
                print(
                    f"\nCurrent version: {current}\nBackup version: {backup}\nOld update engine: {prev}\nBeta active: {beta}\nVersion id: {version_id}"
                )

            elif function == "restore":
                remarkable.restore_previous_version()
                print(
                    f"Device restored to previous version [{remarkable.get_device_status()[4]}]"
                )
                remarkable.reboot_device()
                print("Device rebooted")

            else:
                temp_path = None
                made_update_folder = False
                orig_cwd = os.getcwd()

                # Do we have a specific update file to serve?

                update_file = version if os.path.isfile(version) else None

                def version_lookup(version: str | None) -> re.Match[str] | None:
                    return re.search(r"\b\d+\.\d+\.\d+\.\d+\b", cast(str, version))

                version_number = None
                swu_hardware = None

                if update_file:
                    try:
                        # Quick magic check to skip expensive metadata extraction on old .signed files
                        with open(update_file, "rb") as f:
                            magic = f.read(6)

                        if magic in (b'070701', b'070702'):
                            from .analysis import get_swu_metadata
                            version_number, swu_hardware = get_swu_metadata(update_file)
                            logger.info(f"Extracted from SWU: version={version_number}, hardware={swu_hardware.name}")

                            if swu_hardware != remarkable.hardware:
                                raise SystemError(
                                    f"Hardware mismatch!\n"
                                    f"SWU file is for: {swu_hardware.name}\n"
                                    f"Connected device is: {remarkable.hardware.name}\n"
                                    f"Cannot install firmware for different hardware."
                                )
                    except ValueError as e:
                        logger.warning(f"Could not extract metadata from SWU: {e}")

                if not version_number:
                    version_match = version_lookup(version)
                    if not version_match:
                        version_match = version_lookup(
                            input(
                                "Failed to get the version number from the filename, please enter it: "
                            )
                        )
                        if not version_match:
                            raise SystemError("Invalid version!")

                    version_number = version_match.group()
                else:
                    version_number = str(version_number)

                update_file_requires_new_engine = UpdateManager.uses_new_update_engine(
                    version_number
                )
                device_version_uses_new_engine = UpdateManager.uses_new_update_engine(
                    remarkable.get_device_status()[2]
                )

                #### PREVENT USERS FROM INSTALLING NON-COMPATIBLE IMAGES ####

                if device_version_uses_new_engine:
                    if not update_file_requires_new_engine:
                        raise SystemError(
                            "Cannot downgrade to this version as it uses the old update engine, please manually downgrade."
                        )
                        # TODO: Implement manual downgrading.
                        # `codexctl download --out . 3.11.2.5`
                        # `codexctl extract --out 3.11.2.5.img 3.11.2.5_reMarkable2-qLFGoqPtPL.signed`
                        # `codexctl transfer 3.11.2.5.img ~/root`
                        # `dd if=/home/root/3.11.2.5.img of=/dev/mmcblk2p2` (depending on fallback partition)
                        # `codexctl restore`

                else:
                    if update_file_requires_new_engine:
                        raise SystemError(
                            "This version requires the new update engine, please upgrade your device to version 3.11.2.5 first."
                        )

                #############################################################

                bootloader_files_for_install = None

                if (device_version_uses_new_engine and
                    remarkable.hardware == HardwareType.RMPP):

                    current_version = remarkable.get_device_status()[2]

                    if UpdateManager.is_bootloader_boundary_downgrade(current_version, version_number):
                        print("\n" + "="*60)
                        print("WARNING: Bootloader Update Required")
                        print("="*60)
                        print(f"Current version: {current_version}")
                        print(f"Target version:  {version_number}")
                        print()
                        print("Downgrading from 3.22+ to <3.22 requires updating the")
                        print("bootloader on both partitions. This process will:")
                        print("  1. Download the current version's bootloader files")
                        print("  2. Download the target OS version")
                        print("  3. Install the target OS version")
                        print("  4. Update bootloader on both partitions")
                        print("  5. Reboot")
                        print()

                        response = input("Do you want to continue? (y/n): ")
                        if response.lower() != 'y':
                            raise SystemExit("Installation cancelled by user")

                        expected_swu_name = f"remarkable-production-memfault-image-{current_version}-{remarkable.hardware.new_download_hw}-public"
                        expected_swu_path = f"./{expected_swu_name}"

                        if os.path.isfile(expected_swu_path):
                            print(f"\nUsing existing {expected_swu_name} for bootloader extraction...")
                            current_swu_path = expected_swu_path
                        else:
                            print("\nDownloading current version's SWU for bootloader extraction...")
                            current_swu_path = self.updater.download_version(
                                remarkable.hardware,
                                current_version,
                                "./"
                            )

                        if not current_swu_path:
                            raise SystemError(
                                f"Failed to download current version {current_version} for bootloader extraction. "
                                f"This is required for safe downgrade across bootloader boundary."
                            )

                        print("Extracting bootloader files...")
                        from .analysis import extract_swu_files
                        bootloader_files_for_install = extract_swu_files(
                            current_swu_path,
                            filter_files=['update-bootloader.sh', 'imx-boot']
                        )

                        if not bootloader_files_for_install or len(bootloader_files_for_install) != 2:
                            raise SystemError("Failed to extract bootloader files from current version")

                        print(f"✓ Extracted update-bootloader.sh ({len(bootloader_files_for_install['update-bootloader.sh'])} bytes)")
                        print(f"✓ Extracted imx-boot ({len(bootloader_files_for_install['imx-boot'])} bytes)")
                        print()

                if not update_file_requires_new_engine:
                    if update_file:  # Check if file exists
                        if os.path.dirname(
                            os.path.abspath(update_file)
                        ) != os.path.abspath("updates"):
                            if not os.path.exists("updates"):
                                os.mkdir("updates")
                            shutil.move(update_file, "updates")
                            update_file = get_available_version(version)
                            made_update_folder = True  # Delete at end

                # If version was a valid location file, update_file will be the location else it'll be a version number

                if not update_file:
                    temp_path = tempfile.mkdtemp()
                    os.chdir(temp_path)

                    print(f"Version {version} not found. Attempting to download")

                    location = "./"
                    if not update_file_requires_new_engine:
                        location += "updates"

                    result = self.updater.download_version(
                        remarkable.hardware, version, location
                    )
                    if result:
                        print(f"Downloaded version {version} to {result}")

                        if device_version_uses_new_engine:
                            update_file = result
                        else:
                            update_file = get_available_version(version)

                    else:
                        raise SystemExit(
                            f"Failed to download version {version}! Does this version or location exist?"
                        )

                if device_version_uses_new_engine:
                    remarkable.install_sw_update(update_file, bootloader_files=bootloader_files_for_install)
                else:
                    remarkable.install_ohma_update(update_file)

                if made_update_folder:  # Move update file back out
                    shutil.move(os.listdir("updates")[0], "../")
                    shutil.rmtree("updates")

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
        dest="verbose",
    )
    parser.add_argument(
        "--address",
        "-a",
        required=False,
        help="Specify the address of the device",
        default=None,
        dest="address",
    )
    parser.add_argument(
        "--password",
        "-p",
        required=False,
        help="Specify password or path to SSH key for remote access",
        dest="password",
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True  # This fixes a bug with older versions of python

    ### Install subcommand
    install = subparsers.add_parser(
        "install",
        help="Install the specified version (will download if not available on the device)",
    )
    install.add_argument("version", help="Version (or location to file) to install")

    ### Download subcommand
    download = subparsers.add_parser(
        "download", help="Download the specified version firmware file"
    )
    download.add_argument("version", help="Version to download")
    download.add_argument("--out", "-o", help="Folder to download to", default=None)
    download.add_argument(
        "--hardware",
        "--device",
        "-d",
        help="Hardware to download for",
        required=True,
        dest="hardware",
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
        dest="remote",
    )
    backup.add_argument(
        "-l",
        "--local",
        help="Local directory to backup to. Defaults to download folder",
        default="./",
        dest="local",
    )
    backup.add_argument(
        "-R",
        "--no-recursion",
        help="Disables recursively backup remote directory",
        action="store_true",
        dest="no_recursion",
    )
    backup.add_argument(
        "-O",
        "--no-overwrite",
        help="Disables overwrite",
        action="store_true",
        dest="no_overwrite",
    )
    backup.add_argument(
        "-i",
        "--incremental",
        help="Overwrite out-of-date files only",
        action="store_true",
    )

    ### Cat subcommand
    cat = subparsers.add_parser(
        "cat", help="Cat the contents of a file inside a firmwareimage"
    )
    cat.add_argument("file", help="Path to update file to cat", default=None)
    cat.add_argument("target_path", help="Path inside the image to list", default=None)

    ### Ls subcommand
    ls = subparsers.add_parser("ls", help="List files inside a firmware image")
    ls.add_argument("file", help="Path to update file to extract", default=None)
    ls.add_argument("target_path", help="Path inside the image to list", default=None)

    ### Extract subcommand
    extract = subparsers.add_parser(
        "extract", help="Extract the specified version update file"
    )
    extract.add_argument("file", help="Path to update file to extract", default=None)
    extract.add_argument("--out", help="Folder to extract to", default=None, dest="out")

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
        dest="remote",
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
    list_ = subparsers.add_parser("list", help="List all available versions")
    list_.add_argument(
        "--hardware",
        "--device",
        "-d",
        help="Hardware to list for",
        dest="hardware",
    )

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
    try:
        man.call_func(args.command, vars(args))
    except SystemError as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)

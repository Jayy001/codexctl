import os
import requests
import sys
import json
import hashlib
import logging

from pathlib import Path
from datetime import datetime
from typing import cast


class UpdateManager:
    def __init__(self, logger: logging.Logger | None = None) -> None:
        """Manager for downloading update versions

        Args:
            logger (logger, optional): Logger object for logging. Defaults to None.
        """

        self.logger: logging.Logger = logger or cast(logging.Logger, logging)  # pyright:ignore [reportInvalidCast]

        self.remarkablepp_versions: dict[str, list[str]]
        self.remarkable2_versions: dict[str, list[str]]
        self.remarkable1_versions: dict[str, list[str]]
        self.external_provider_url: str
        (
            self.remarkablepp_versions,
            self.remarkable2_versions,
            self.remarkable1_versions,
            self.external_provider_url,
        ) = self.get_remarkable_versions()

    def get_remarkable_versions(
        self,
    ) -> tuple[dict[str, list[str]], dict[str, list[str]], dict[str, list[str]], str]:
        """Gets the avaliable versions for the device, by checking the local version-ids.json file and then updating it if necessary

        Returns:
            tuple: A tuple containing the version ids for the remarkablepp, remarkable2, remarkable1, toltec version and external provider (in that order)
        """

        if os.path.exists("data/version-ids.json"):
            file_location = "data/version-ids.json"

            self.logger.debug("Found version-ids at data/version-ids.json")

        else:
            if os.name == "nt":  # Windows
                folder_location = (os.getenv("APPDATA") or "") + "/codexctl"
            elif os.name in ("posix", "darwin"):  # Linux or MacOS
                folder_location = os.path.expanduser("~/.config/codexctl")
            else:
                raise SystemError("Unsupported OS")

            self.logger.debug(f"Version config folder location is {folder_location}")
            if not os.path.exists(folder_location):
                os.makedirs(folder_location, exist_ok=True)

            file_location = folder_location + "/version-ids.json"

            if not os.path.exists(file_location):
                self.update_version_ids(file_location)

        try:
            with open(file_location) as f:
                contents = json.load(f)  # pyright:ignore [reportAny]
                if not isinstance(contents, dict):
                    raise ValueError()

        except ValueError:
            raise SystemError(
                f"Version-ids.json @ {file_location} is corrupted! Please delete it and try again. Also, PLEASE open an issue on the repo showing the contents of the file."
            ) from None

        if (
            int(datetime.now().timestamp()) - contents["last-updated"]
            > 5256000  # 2 months
        ):
            self.update_version_ids(file_location)

            with open(file_location) as f:
                try:
                    contents = json.load(f)  # pyright:ignore [reportAny]
                    if not isinstance(contents, dict):
                        raise ValueError()

                except ValueError:
                    raise SystemError(
                        f"Version-ids.json @ {file_location} is corrupted! Please delete it and try again. Also, PLEASE open an issue on the repo showing the contents of the file."
                    ) from None

        self.logger.debug(f"Version ids contents are {contents}")

        return (
            cast(dict[str, list[str]], contents["remarkablepp"]),
            cast(dict[str, list[str]], contents["remarkable2"]),
            cast(dict[str, list[str]], contents["remarkable1"]),
            cast(str, contents["external-provider-url"]),
        )

    def update_version_ids(self, location: str) -> None:
        """Updates the version-ids.json file

        Args:
            location (str): Location to save the file

        Raises:
            SystemExit: If the file cannot be updated
        """
        try:
            with open(location, "w", newline="\n") as f:
                self.logger.debug("Downloading version-ids.json")
                contents = requests.get(  # pyright:ignore [reportAny]
                    "https://raw.githubusercontent.com/Jayy001/codexctl/main/data/version-ids.json"
                ).json()
                json.dump(contents, f, indent=4)
                _ = f.write("\n")
        except requests.exceptions.Timeout:
            raise SystemExit(
                "Connection timed out while downloading version-ids.json! Do you have an internet connection?"
            ) from None

        except Exception as error:
            raise SystemExit(
                f"Unknown error while downloading version-ids.json! {error}"
            ) from error

    def get_latest_version(self, device_type: str) -> str | None:
        """Gets the latest version available for the device

        Args:
            device_type (str): Type of the device (remarkablepp or remarkable2 or remarkable1)

        Returns:
            str: Latest version available for the device
        """
        if "1" in device_type:
            versions = self.remarkable1_versions
        elif "2" in device_type:
            versions = self.remarkable2_versions
        elif "ferrari" in device_type or "pp" in device_type:
            versions = self.remarkablepp_versions
        else:
            return None  # Explicit?

        return self.__max_version(list(versions.keys()))

    def get_toltec_version(self, device_type: str) -> str:
        """Gets the latest version available toltec for the device

        Args:
            device_type (str): Type of the device (remarkablepp or remarkable2 or remarkable1)

        Returns:
            str: Latest version available for the device
        """

        if "ferrari" in device_type:
            raise SystemExit("ReMarkable Paper Pro does not support toltec")
        elif "1" in device_type:
            device_type = "rm1"
        else:
            device_type = "rm2"

        response = requests.get("https://toltec-dev.org/stable/Compatibility")
        if response.status_code != 200:
            raise SystemExit(
                f"Error: Failed to get toltec compatibility table: {response.status_code}"
            )

        return self.__max_version(
            [
                x.split("=")[1]
                for x in response.text.splitlines()
                if x.startswith(f"{device_type}=")
            ]
        )

    def download_version(
        self,
        device_type: str,
        update_version: str,
        download_folder: str | Path | None = None,
    ) -> str | None:
        """Downloads the specified version of the update

        Args:
            device_type (str): Type of the device (remarkable2 or remarkable1)
            update_version (str): Id of version to download.
            download_folder (str, optional): Location of download folder. Defaults to download folder for OS.

        Returns:
            str | None: Location of the file if the download was successful, None otherwise
        """

        if download_folder is None:
            download_folder = Path(
                os.environ["XDG_DOWNLOAD_DIR"]
                if (
                    "XDG_DOWNLOAD_DIR" in os.environ
                    and os.path.exists(os.environ["XDG_DOWNLOAD_DIR"])
                )
                else Path.home() / "Downloads"
            )

        if not os.path.exists(download_folder):
            self.logger.error(
                f"Download folder {download_folder} does not exist! Creating it now."
            )
            os.makedirs(download_folder)

        BASE_URL = "https://updates-download.cloud.remarkable.engineering/build/reMarkable%20Device%20Beta/RM110"  # Default URL for v2 versions
        BASE_URL_V3 = "https://updates-download.cloud.remarkable.engineering/build/reMarkable%20Device/reMarkable"

        if (
            ("ferrari" in device_type.lower())
            or ("pro" in device_type)
            or ("pp" in device_type)
        ):
            version_lookup = self.remarkablepp_versions
        elif "1" in device_type:
            version_lookup = self.remarkable1_versions
        elif "2" in device_type:
            version_lookup = self.remarkable2_versions
            BASE_URL_V3 += "2"
        else:
            raise SystemError(
                f"Hardware version does not exist!: {device_type} (rm1,rm2,rmpp)"
            )

        if update_version not in version_lookup:
            self.logger.error(
                f"Version {update_version} not found in version-ids.json! Please update your version-ids.json file."
            )
            return

        version_id, version_checksum = version_lookup[update_version]
        version = tuple([int(x) for x in update_version.split(".")])
        if version >= (3,):
            BASE_URL = BASE_URL_V3

        if version <= (3, 11, 2, 5):
            file_name = f"{update_version}_reMarkable{'2' if '2' in device_type else ''}-{version_id}.signed"
            file_url = f"{BASE_URL}/{update_version}/{file_name}"

        else:
            file_url = self.external_provider_url.replace("REPLACE_ID", version_id)
            file_name = f"remarkable-production-memfault-image-{update_version}-{device_type.replace(' ', '-')}-public"

        self.logger.debug(f"File URL is {file_url}, File name is {file_name}")

        return self.__download_version_file(
            file_url, file_name, download_folder, version_checksum
        )

    def __download_version_file(
        self, uri: str, name: str, download_folder: str | Path, checksum: str
    ) -> str | None:
        """Downloads the version file from the server and checks the checksum

        Args:
            uri (str): Location to the file
            name (str): Name of the file
            download_folder (str): Location of download folder
            checksum (str): Sha256 Checksum of the file

        Returns:
            str | None: Location of the file if the checksum matches, None otherwise
        """
        response = requests.get(uri, stream=True)
        if response.status_code != 200:
            self.logger.error(f"Unable to download update file: {response.status_code}")
            return None

        file_length = response.headers.get("content-length")

        self.logger.debug(f"Downloading {name} from {uri} to {download_folder}")
        try:
            file_length = int(file_length or 0)

            if int(file_length) < 10000000:  # 10MB, invalid version file
                self.logger.error(
                    f"File {name} is too small to be a valid version file"
                )
                return None
        except TypeError:
            self.logger.error(
                f"Could not get content length for {name}. Do you have an internet connection?"
            )
            return None

        self.logger.debug(f"{name} is {file_length} bytes")

        filename = f"{download_folder}/{name}"
        with open(filename, "wb") as out_file:
            dl = 0

            data: bytes
            for data in response.iter_content(chunk_size=4096):  # pyright:ignore [reportAny]
                dl += len(data)
                _ = out_file.write(data)
                if sys.stdout.isatty():
                    done = int(50 * dl / file_length)
                    _ = sys.stdout.write("\r[%s%s]" % ("=" * done, " " * (50 - done)))
                    _ = sys.stdout.flush()

        if sys.stdout.isatty():
            print(end="\r\n")

        self.logger.debug(f"Downloaded {name}")

        with open(filename, "rb") as f:
            file_checksum = hashlib.sha256(f.read()).hexdigest()

        if file_checksum != checksum:
            os.remove(filename)
            self.logger.error(
                f"File checksum mismatch! Expected {checksum}, got {file_checksum}"
            )
            return None

        return filename

    @staticmethod
    def __max_version(versions: list[str]) -> str:
        """Returns the highest avaliable version from a list with semantic versioning"""
        return sorted(versions, key=lambda v: tuple(map(int, v.split("."))))[-1]

    @staticmethod
    def uses_new_update_engine(version: str) -> bool:
        """
        Checks if the version given is above 3.11 and so requires the newer update engine

        Args:
            version (str): version to check against

        Returns:
            bool: If it uses the new update engine or not
        """
        return int(version.split(".")[0]) >= 3 and int(version.split(".")[1]) >= 11

import os
import requests
import uuid
import sys
import json
import hashlib
import logging

from pathlib import Path
from datetime import datetime

import xml.etree.ElementTree as ET

from .device import HardwareType


class UpdateManager:
    def __init__(self, logger=None) -> None:
        """Manager for downloading update versions

        Args:
            logger (logger, optional): Logger object for logging. Defaults to None.
        """

        self.logger = logger

        if self.logger is None:
            self.logger = logging

        (
            self.remarkablepp_versions,
            self.remarkableppm_versions,
            self.remarkable2_versions,
            self.remarkable1_versions,
            self.external_provider_urls,
        ) = self.get_remarkable_versions()

    def get_remarkable_versions(self) -> tuple[dict, dict, dict, dict, list]:
        """Gets the avaliable versions for the device, by checking the local version-ids.json file and then updating it if necessary

        Returns:
            tuple: A tuple containing the version ids for the remarkablepp, remarkableppm, remarkable2, remarkable1, and external provider urls (in that order)
        """

        if os.path.exists("data/version-ids.json"):
            file_location = "data/version-ids.json"

            self.logger.debug("Found version-ids at data/version-ids.json")

        else:
            if os.name == "nt":  # Windows
                folder_location = os.getenv("APPDATA") + "/codexctl"
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
                contents = json.load(f)
        except ValueError:
            raise SystemError(
                f"Version-ids.json @ {file_location} is corrupted! Please delete it and try again. Also, PLEASE open an issue on the repo showing the contents of the file."
            )

        if (
            int(datetime.now().timestamp()) - contents["last-updated"]
            > 5256000  # 2 months
        ):
            self.update_version_ids(file_location)

            with open(file_location) as f:
                contents = json.load(f)

        self.logger.debug(f"Version ids contents are {contents}")

        provider_urls = contents.get("external-provider-urls", contents.get("external-provider-url"))
        if isinstance(provider_urls, str):
            provider_urls = [provider_urls]
        if provider_urls is None:
            raise SystemError(
                f"version-ids.json at {file_location} is missing external provider URLs. "
                "Please delete the file and try again, or open an issue on the repo."
            )

        return (
            contents["remarkablepp"],
            contents["remarkableppm"],
            contents["remarkable2"],
            contents["remarkable1"],
            provider_urls,
        )

    def update_version_ids(self, location: str) -> None:
        """Updates the version-ids.json file

        Args:
            location (str): Location to save the file

        Raises:
            SystemExit: If the file cannot be updated
        """
        with open(location, "w", newline="\n") as f:
            try:
                self.logger.debug("Downloading version-ids.json")
                contents = requests.get(
                    "https://raw.githubusercontent.com/Jayy001/codexctl/main/data/version-ids.json"
                ).json()
                json.dump(contents, f, indent=4)
                f.write("\n")
            except requests.exceptions.Timeout:
                raise SystemExit(
                    "Connection timed out while downloading version-ids.json! Do you have an internet connection?"
                )
            except Exception as error:
                raise SystemExit(
                    f"Unknown error while downloading version-ids.json! {error}"
                )

    def get_latest_version(self, hardware_type: HardwareType) -> str:
        """Gets the latest version available for the device

        Args:
            hardware_type (HardwareType enum): Type of the device

        Returns:
            str: Latest version available for the device
        """
        match hardware_type:
            case HardwareType.RM1:
                versions = self.remarkable1_versions
            case HardwareType.RM2:
                versions = self.remarkable2_versions
            case HardwareType.RMPP:
                versions = self.remarkablepp_versions
            case HardwareType.RMPPM:
                versions = self.remarkableppm_versions

        return self.__max_version(versions.keys())

    def get_toltec_version(self, hardware_type: HardwareType) -> str:
        """Gets the latest version available toltec for the device

        Args:
            hardware_type (HardwareType enum): Type of the device

        Returns:
            str: Latest version available for the device
        """

        try:
            toltec_type = hardware_type.toltec_type
        except ValueError as ex:
            raise SystemExit(*ex.args)

        response = requests.get("https://toltec-dev.org/stable/Compatibility")
        if response.status_code != 200:
            raise SystemExit(
                f"Error: Failed to get toltec compatibility table: {response.status_code}"
            )

        return self.__max_version(
            [
                x.split("=")[1]
                for x in response.text.splitlines()
                if x.startswith(f"{toltec_type}=")
            ]
        )

    def download_version(
        self, hardware_type: HardwareType, update_version: str, download_folder: str|None = None
    ) -> str | None:
        """Downloads the specified version of the update

        Args:
            hardware_type (HardwareType enum): Type of the device
            update_version (str): Id of version to download.
            download_folder (str, optional): Location of download folder. Defaults to download folder for OS.

        Returns:
            str | None: Location of the file if the download was successful, None otherwise
        """

        if download_folder is None:
            download_folder = str(Path(
                os.environ["XDG_DOWNLOAD_DIR"]
                if (
                    "XDG_DOWNLOAD_DIR" in os.environ
                    and os.path.exists(os.environ["XDG_DOWNLOAD_DIR"])
                )
                else Path.home() / "Downloads"
            ))

        if not os.path.exists(download_folder):
            self.logger.error(
                f"Download folder {download_folder} does not exist! Creating it now."
            )
            os.makedirs(download_folder)

        BASE_URL = "https://updates-download.cloud.remarkable.engineering/build/reMarkable%20Device%20Beta/RM110"  # Default URL for v2 versions
        BASE_URL_V3 = "https://updates-download.cloud.remarkable.engineering/build/reMarkable%20Device/reMarkable"

        match hardware_type:
            case HardwareType.RMPP:
                version_lookup = self.remarkablepp_versions

            case HardwareType.RMPPM:
                version_lookup = self.remarkableppm_versions

            case HardwareType.RM2:
                version_lookup = self.remarkable2_versions
                BASE_URL_V3 += "2"

            case HardwareType.RM1:
                version_lookup = self.remarkable1_versions

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
            file_name = f"{update_version}_{hardware_type.old_download_hw}-{version_id}.signed"
            file_url = f"{BASE_URL}/{update_version}/{file_name}"
            self.logger.debug(f"File URL is {file_url}, File name is {file_name}")
            return self.__download_version_file(
                file_url, file_name, download_folder, version_checksum
            )

        else:
            file_name = f"remarkable-production-memfault-image-{update_version}-{hardware_type.new_download_hw}-public"

            for provider_url in self.external_provider_urls:
                file_url = provider_url.replace("REPLACE_ID", version_id)
                self.logger.debug(f"Trying to download from {file_url}")

                result = self.__download_version_file(
                    file_url, file_name, download_folder, version_checksum
                )

                if result is not None:
                    self.logger.debug(f"Successfully downloaded from {provider_url}")
                    return result

                self.logger.debug(f"Failed to download from {provider_url}, trying next source...")

            self.logger.error(f"Failed to download {file_name} from all sources")
            return None

    def __generate_xml_data(self) -> str:
        """Generates and returns XML data for the update request"""
        params = {
            "installsource": "scheduler",
            "requestid": str(uuid.uuid4()),
            "sessionid": str(uuid.uuid4()),
            "machineid": "00".zfill(32),
            "oem": "RM100-753-12345",
            "appid": "98DA7DF2-4E3E-4744-9DE6-EC931886ABAB",
            "bootid": str(uuid.uuid4()),
            "current": "3.2.3.1595",
            "group": "Prod",
            "platform": "reMarkable2",
        }

        return """<?xml version="1.0" encoding="UTF-8"?>
<request protocol="3.0" version="{current}" requestid="{{{requestid}}}" sessionid="{{{sessionid}}}" updaterversion="0.4.2" installsource="{installsource}" ismachine="1">
    <os version="zg" platform="{platform}" sp="{current}_armv7l" arch="armv7l"></os>
    <app appid="{{{appid}}}" version="{current}" track="{group}" ap="{group}" bootid="{{{bootid}}}" oem="{oem}" oemversion="2.5.2" alephversion="{current}" machineid="{machineid}" lang="en-US" board="" hardware_class="" delta_okay="false" nextversion="" brand="" client="" >
        <updatecheck/>
    </app>
</request>""".format(**params)

    def __parse_response(self, resp: str) -> tuple[str, str, str] | None:
        """Parses the response from the update server and returns the file name, uri, and version if an update is available

        Args:
            resp (str): Response from the server

        Returns:
            tuple[str, str, str] | None: File name, uri, and version if an update is available, None otherwise
        """
        xml_data = ET.fromstring(resp)

        if "noupdate" in resp or xml_data is None:
            return None

        file_name = xml_data.find("app/updatecheck/manifest/packages/package").attrib[
            "name"
        ]
        file_uri = (
            f"{xml_data.find('app/updatecheck/urls/url').attrib['codebase']}{file_name}"
        )
        file_version = xml_data.find("app/updatecheck/manifest").attrib["version"]

        self.logger.debug(
            f"File version is {file_version}, file uri is {file_uri}, file name is {file_name}"
        )
        return file_version, file_uri, file_name

    def __download_version_file(
        self, uri: str, name: str, download_folder: str, checksum: str
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
            self.logger.debug(f"Unable to download update file: {response.status_code}")
            return None

        file_length = response.headers.get("content-length")

        self.logger.debug(f"Downloading {name} from {uri} to {download_folder}")
        try:
            file_length = int(file_length)

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

            for data in response.iter_content(chunk_size=4096):
                dl += len(data)
                out_file.write(data)
                if sys.stdout.isatty():
                    done = int(50 * dl / file_length)
                    sys.stdout.write("\r[%s%s]" % ("=" * done, " " * (50 - done)))
                    sys.stdout.flush()

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
    def __max_version(versions: list) -> str:
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

    @staticmethod
    def is_bootloader_boundary_downgrade(current_version: str, target_version: str) -> bool:
        """
        Checks if downgrade crosses the 3.22 bootloader boundary (3.22+ -> <3.22).

        Paper Pro devices require bootloader updates when downgrading from
        version 3.22 or higher to any version below 3.22.

        Args:
            current_version (str): Currently installed version
            target_version (str): Target version to install

        Returns:
            bool: True if crossing boundary downward (3.22+ -> <3.22)

        Raises:
            ValueError: If either version is empty or has invalid format
        """
        if not current_version or not current_version.strip():
            raise ValueError("current_version cannot be empty")
        if not target_version or not target_version.strip():
            raise ValueError("target_version cannot be empty")

        try:
            current_parts = [int(x) for x in current_version.split('.')]
            target_parts = [int(x) for x in target_version.split('.')]
        except ValueError as e:
            raise ValueError(f"Invalid version format: {e}") from e

        if len(current_parts) < 2 or len(target_parts) < 2:
            raise ValueError("Version must have at least 2 components (e.g., '3.22')")

        current_is_322_or_higher = current_parts >= [3, 22]
        target_is_below_322 = target_parts < [3, 22]

        return current_is_322_or_higher and target_is_below_322

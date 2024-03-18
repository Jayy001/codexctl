import os
import time
import requests
import re
import uuid
import sys
import json
import hashlib
import logging

from pathlib import Path
from datetime import datetime

import xml.etree.ElementTree as ET

UPDATE_URL = "https://remarkable.engineering/remarkable2/ota/latest"


class UpdateManager:
    def __init__(self, logger=None) -> None:
        """Manager for downloading update versions

        Args:
            logger (logger, optional): Logger object for logging. Defaults to None.
        """

        self.logger = logger

        if logging is None:
            self.logger = logging

        self.remarkable2_versions, self.remarkable1_versions, self.toltec_latest = (
            self.get_remarkable_versions()
        )

    def get_remarkable_versions(self) -> tuple[dict, dict, str]:
        """Gets the avaliable versions for the device, by checking the local version-ids.json file and then updating it if necessary

        Returns:
            tuple: A tuple containing the version ids for the remarkable2, remarkable1, and toltec (in that order)
        """

        if os.path.exists("Data/version-ids.json"):
            file_location = "Data/version-ids.json"

            self.logger.debug("Found version-ids at data/version-ids.json")

        else:
            if os.name == "nt":  # Windows
                folder_location = os.getenv("APPDATA") + "/codexctl"
            elif os.name == "posix" or "darwin":  # Linux or MacOS
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
            raise SystemExit(
                f"Version-ids.json @ {file_location} is corrupted! Please delete it and try again. Also, PLEASE open an issue on the repo showing the contents of the file."
            )

        if (
            int(datetime.now().timestamp()) - contents["last-updated"]
            > 2628000  # 1 month
        ):
            self.update_version_ids(file_location)

            with open(file_location) as f:
                contents = json.load(f)

        self.logger.debug(f"Version ids contents are {contents}")

        return contents["remarkable2"], contents["remarkable1"], contents["toltec"]

    def update_version_ids(self, location) -> None:
        """Updates the version-ids.json file

        Args:
            location (str): Location to save the file

        Raises:
            SystemExit: If the file cannot be updated
        """
        with open(location, "w") as f:
            try:
                self.logger.debug("Downloading version-ids.json")
                contents = requests.get(
                    "https://raw.githubusercontent.com/Jayy001/codexctl/main/data/version-ids.json"
                ).json()
                json.dump(contents, f)
            except requests.exceptions.Timeout:
                raise SystemExit(
                    "Connection timed out while downloading version-ids.json! Do you have an internet connection?"
                )
            except Exception as error:
                raise SystemExit(
                    f"Unknown error while downloading version-ids.json! {error}"
                )

    def get_latest_version(self, device_type) -> str:
        """Gets the latest version available for the device

        Args:
            device_type (str): Type of the device (remarkable2 or remarkable1)

        Returns:
            str: Latest version available for the device
        """
        if device_type == "remarkable2":
            versions = self.remarkable2_versions
        else:
            versions = self.remarkable1_versions

        return max(list(versions.keys()))

    def download_version(self, device_type, update_version, download_folder=None):
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

        if device_type == "remarkable1":
            versionLookup = self.remarkable1_versions
        else:
            versionLookup = self.remarkable2_versions
            BASE_URL_V3 += "2"

        if update_version not in versionLookup:
            self.logger.error(
                f"Version {update_version} not found in version-ids.json! Please update your version-ids.json file."
            )
            return

        if int(update_version.split(".")[0]) > 2:  # 3.X.X versions
            BASE_URL = BASE_URL_V3

        id = f"-{versionLookup[update_version][0]}"
        checksum = versionLookup[update_version][1]

        file_name = f"{update_version}_reMarkable{'2' if device_type == 'remarkable2' else ''}{id}.signed"
        file_url = f"{BASE_URL}/{update_version}/{file_name}"

        self.logger.debug(f"File URL is {file_url}, File name is {file_name}")

        return self.__download_version_file(
            file_url, file_name, download_folder, checksum
        )

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
</request>""".format(
            **params
        )

    def __parse_response(self, resp) -> tuple[str, str, str] | None:
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
        self, uri, name, download_folder, checksum
    ) -> str | None:
        """Downloads the version file from the server and checks the checksum

        Args:
            uri (str): Location to the file
            name (str): Name of the file
            download_folder (str): Location of download folder
            checksum (str): Checksum of the file

        Returns:
            str | None: Location of the file if the checksum matches, None otherwise
        """
        response = requests.get(uri, stream=True)
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

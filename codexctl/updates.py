import os, time, requests, re, uuid, sys, json, hashlib

from pathlib import Path
from datetime import datetime

import xml.etree.ElementTree as ET


class UpdateManager:
    def __init__(self, device_version=None, logger=None):
        self.updates_url = (
            "https://updates.cloud.remarkable.engineering/service/update2"
        )

        self.logger = logger
        self.DOWNLOAD_FOLDER = Path(
            os.environ["XDG_DOWNLOAD_DIR"]
            if (
                "XDG_DOWNLOAD_DIR" in os.environ
                and os.path.exists(os.environ["XDG_DOWNLOAD_DIR"])
            )
            else Path.home() / "Downloads"
        )
        self.device_version = (
            device_version if device_version else "3.2.3.1595"
        )  # Earliest 3.x.x version

        self.logger.debug(f"Download folder is {self.DOWNLOAD_FOLDER}")

        versions = self.get_version_ids()

        self.id_lookups_rm1 = versions["remarkable1"]
        self.id_lookups_rm2 = versions["remarkable2"]

        self.latest_toltec_version = versions["toltec"]
        self.latest_version = versions["latest"]

    def update_version_ids(self, location):
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
                    "Error: Connection timed out while downloading version-ids.json! Do you have an internet connection?"
                )
            except Exception as error:
                raise SystemExit(
                    f"Error: Unknown error while downloading version-ids.json! {error}"
                )

    def get_version_ids(self):
        if os.path.exists("data/version-ids.json"):
            file_location = "data/version-ids.json"
            self.logger.debug("Found version-ids at data/version-ids.json")
        else:
            if os.name == "nt":
                folder_location = os.getenv("APPDATA") + "/codexctl"
            elif os.name == "posix":
                folder_location = os.path.expanduser("~/.config/codexctl")

            self.logger.debug(f"Folder location is {folder_location}")
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
                f"Error: version-ids.json @ {file_location} is corrupted! Please delete it and try again."
            )

        if (
            int(datetime.now().timestamp()) - contents["last-updated"] > 2628000
        ):  # 1 month
            self.update_version_ids(file_location)
            with open(file_location) as f:
                contents = json.load(f)

        self.logger.debug(f"Contents are {contents}")
        return contents

    def get_version(self, device=2, version=None, download_folder=None):
        if download_folder is None:
            download_folder = self.DOWNLOAD_FOLDER

        # Check if download folder exists
        if not os.path.exists(download_folder):
            return "Download folder does not exist"

        if device == 1:
            versionDict = self.id_lookups_rm1
        else:
            versionDict = self.id_lookups_rm2

        if version is None:
            version = self.latest_version

        if version not in versionDict:
            return "Not in version list"

        BASE_URL = "https://updates-download.cloud.remarkable.engineering/build/reMarkable%20Device%20Beta/RM110"

        BASE_URL_V3 = "https://updates-download.cloud.remarkable.engineering/build/reMarkable%20Device/reMarkable2"
        BASE_URL_RM1_V3 = "https://updates-download.cloud.remarkable.engineering/build/reMarkable%20Device/reMarkable"

        if int(version.split(".")[0]) > 2:
            if device == 1:
                BASE_URL = BASE_URL_RM1_V3
            else:
                BASE_URL = BASE_URL_V3

        data = versionDict[version]
        id = f"-{data[0]}"
        checksum = data[1]
        if len(data) > 2:
            print(f"Warning for {version}: {data[2]}")

        file_name = f"{version}_reMarkable{'2' if device == 2 else ''}{id}.signed"
        file_url = f"{BASE_URL}/{version}/{file_name}"

        self.logger.debug(f"File URL is {file_url}, File name is {file_name}")
        return self.download_file(file_url, file_name, download_folder, checksum)

    def __get_latest_toltec_supported(self):
        site_body_html = requests.get("https://toltec-dev.org/").text  # or /raw ?
        m = re.search(
            r"Toltec does not support OS builds newer than (.*)\. You will soft-brick",
            site_body_html,
        )
        if m is None:
            return None

        return m.group(1).strip()

    def get_latest_version(self, device):  # Hardcoded for now
        # This is problematic...either we get the latest version from the RM directly or from the currently installed ones
        # The latter is more reliable, but the former is more accurate
        # We'll use the latter for now

        return self.latest_version

        if device == 2:
            return max([item for item in list(self.id_lookups_rm2.keys())])
        else:
            return max([item for item in list(self.id_lookups_rm1.keys())])
        """

        data = self._generate_xml_data()

        response = self._make_request(data)

        if response is None:  # or if not response
            return
        print(response)
        file_version, file_uri, file_name = self._parse_response(response)

        return 'file_version'
        """

    def _generate_xml_data(self):  # TODO: Support for remarkable1
        params = {
            "installsource": "scheduler",
            "requestid": str(uuid.uuid4()),
            "sessionid": str(uuid.uuid4()),
            "machineid": "00".zfill(32),
            "oem": "RM100-753-12345",
            "appid": "98DA7DF2-4E3E-4744-9DE6-EC931886ABAB",
            "bootid": str(uuid.uuid4()),
            "current": self.device_version,
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

    def _make_request(self, data):
        tries = 1

        while tries < 3:
            tries += 1

            self.logger.debug(
                f"Sending POST request to {self.updates_url} with data {data} [Try {tries}]"
            )

            response = requests.post(self.updates_url, data)

            if response.status_code == 429:
                print("Too many requests sent, retrying after 20")
                time.sleep(20)

                continue

            response.raise_for_status()

            break

        return response.text

    def _parse_response(self, resp):
        xml_data = ET.fromstring(resp)

        if "noupdate" in resp or xml_data is None:  # Is none?
            return None  # Or False maybe?

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

    def download_file(
        self, uri, name, download_folder, checksum
    ):  # Credit to https://stackoverflow.com/questions/15644964/python-progress-bar-and-downloads
        response = requests.get(uri, stream=True)
        total_length = response.headers.get("content-length")

        self.logger.debug(f"Downloading file from {uri} to {download_folder}/{name}")
        try:
            total_length = int(total_length)

            if int(total_length) < 10000000:  # 10MB
                return None
        except TypeError:
            return None

        self.logger.debug(f"Total length is {total_length}")

        filename = f"{download_folder}/{name}"
        with open(filename, "wb") as f:
            dl = 0

            for data in response.iter_content(chunk_size=4096):
                dl += len(data)
                f.write(data)
                if sys.stdout.isatty():
                    done = int(50 * dl / total_length)
                    sys.stdout.write("\r[%s%s]" % ("=" * done, " " * (50 - done)))
                    sys.stdout.flush()

        if sys.stdout.isatty():
            print(end="\r\n")

        self.logger.debug("Downloaded filename")

        if os.path.getsize(filename) != total_length:
            os.remove(filename)
            raise SystemExit("Error: File size mismatch! Is your connection stable?")

        with open(filename, "rb") as f:
            file_checksum = hashlib.sha256(f.read()).hexdigest()

            if file_checksum != checksum:
                os.remove(filename)
                raise SystemExit(
                    f"Error: File checksum mismatch! Expected {checksum}, got {file_checksum}"
                )

        return name

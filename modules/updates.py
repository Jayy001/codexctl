import os, time, requests, re, uuid, sys

from pathlib import Path

import xml.etree.ElementTree as ET


class UpdateManager:
	def __init__(
		self, device_version=None, logger=None
	):  
		self.updates_url = (
			"https://updates.cloud.remarkable.engineering/service/update2"
		)
  
		self.logger = logger
		self.DOWNLOAD_FOLDER = Path.home() / 'Downloads'
		self.device_version = device_version if device_version else "3.2.3.1595"
  
		self.logger.debug(f'Download folder is {self.DOWNLOAD_FOLDER}')
  
		self.id_lookups_rm1 = {
			"3.6.1.1894": "CGaIOXfzAA",
			"3.6.0.1865": "nnuJzg6Jj4",
			"3.5.2.1807": "UGWiACaUG0",
			"3.5.1.1798": "cR2nzMvbcW",
			"3.4.1.1790": "SgjzSG56eK",
			"3.4.0.1784": "yY5ri2SbLv",
			"3.3.2.1666": "Ak1sdSSGWD",
			"3.2.3.1595": "f99Lsgx3BG",
			"3.2.2.1581": "rsTV6U3FlH",
			"3.0.4.1305": "zo0ubu5Wle",
			"2.15.1.1189": "Xdvv3lBmE4", 
			"2.15.0.1067": "qbGuCuFIX7",
			"2.14.3.977": "uzKCb761HZ",
			"2.14.3.958": "DgsusjCrfd",
			"2.14.3.1047": "mQ3OMMnn0v",
			"2.14.3.1005": "nKHKu5aVAR",
			"2.14.1.866": "kPA6NrLNoo",
			"2.14.0.861": "r6qAtH141a",
			"2.13.0.758": "K7IjoRHW9V",
			"2.12.3.606": "DtbTMBso9w",
			"2.12.2.573": "F7KCxN9Zpp",
			"2.12.1.527": "xKvumVvxqC",
			"2.11.0.442": "3QEYXIWu4Z",
			"2.10.3.379": "2UgGBK40nD",
			"2.10.2.356": "Lp90j3g4at",
		}
		self.id_lookups_rm2 = {
			"3.6.1.1894": "T2dkdktE1H",
			"3.6.0.1865": "7wgexMSZP5",
			"3.5.2.1807": "3bZjC0Xn5C",
			"3.5.1.1798": "9CfoVp8qCU",
			"3.4.1.1790": "rYfHxYmwC8",
			"3.4.0.1784": "fD3GCOcU9m",
			"3.3.2.1666": "ihUirIf133",
			"3.2.3.1595": "fTtpld3Mvn",
			"3.2.2.1581": "dwyp884gLP",
			"3.0.4.1305": "tdwbuIzhYP",
			"2.15.1.1189": "wVbHkgKisg", 
			"2.15.0.1067": "lyC7KAjjSB",
			"2.14.3.977": "joPqAABTAW",
			"2.14.3.958": "B7yhC887i1",
			"2.14.3.1047": "RGLmy8Jb39",
			"2.14.3.1005": "4HCZ7J2Bse",
			"2.14.1.866": "JLWa2mnXu1",
			"2.14.0.861": "TfpToxrexR",
			"2.13.0.758": "2N5B5nvpZ4",
			"2.12.3.606": "XOSYryyJXI",
			"2.12.2.573": "XnE1EL7ojK",
			"2.12.1.527": "8OkCxOJFn9",
			"2.11.0.442": "tJDDwsDM4V",
			"2.10.3.379": "n16KxgSfCk",
			"2.10.2.356": "JLB6Ax3hnJ",
		}

		self.latest_toltec_version = "2.15.1.1189" 

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

		id = f"-{versionDict[version]}-"

		file_name = f"{version}_reMarkable{'2' if device == 2 else ''}{id}.signed"
		file_url = f"{BASE_URL}/{version}/{file_name}"

		self.logger.debug(f'File URL is {file_url}, File name is {file_name}')
		return self.download_file(file_url, file_name, download_folder)

	def __get_latest_toltec_supported(self):
		site_body_html = requests.get("https://toltec-dev.org/").text  # or /raw ?
		m = re.search(
			"Toltec does not support OS builds newer than (.*)\. You will soft-brick",
			site_body_html,
		)
		if m is None:
			return None

		return m.group(1).strip()

	def get_latest_version(self, device):
		# This is problematic...either we get the latest version from the RM directly or from the currently installed ones
		# The latter is more reliable, but the former is more accurate
		# We'll use the latter for now
		if device == 2:
			return max([item for item in list(self.id_lookups_rm2.keys())])
		else:
			return max([item for item in list(self.id_lookups_rm1.keys())])
		
		"""
		data = self._generate_xml_data()

		response = self._make_request(data)

		if response is None:  # or if not response
			return

		file_version, file_uri, file_name = self._parse_response(response)

		return file_version
		"""

	def _generate_xml_data(self): # TODO: Support for remarkable1
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

			self.logger.debug(f'Sending POST request to {self.updates_url} with data {data} [Try {tries}]')
                     
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

		self.logger.debug(f'File version is {file_version}, file uri is {file_uri}, file name is {file_name}')
		return file_version, file_uri, file_name

	
	def download_file(
		self, uri, name, download_folder
	):  # Credit to https://stackoverflow.com/questions/15644964/python-progress-bar-and-downloads
		response = requests.get(uri, stream=True)
		total_length = response.headers.get("content-length")
		
		self.logger.debug(f"Downloading file from {uri} to {download_folder}/{name}")
		try:
			total_length = int(total_length)

			if int(total_length) < 10000000: # 10MB
				return None
		except TypeError:
			return None

		self.logger.debug(f'Total length is {total_length}')
		with open(f"{download_folder}/{name}", "wb") as f:
			dl = 0
   
			for data in response.iter_content(chunk_size=4096):
				dl += len(data)
				f.write(data)
				done = int(50 * dl / total_length)
				sys.stdout.write("\r[%s%s]" % ("=" * done, " " * (50 - done)))
				sys.stdout.flush()
    
		print(end="\r\n")

		self.logger.debug(f"Downloaded {download_folder}/{name}")
		if os.path.getsize(f"{download_folder}/{name}") != total_length:
			raise SystemExit("Error: File size mismatch! Is your connection stable?")

		return name

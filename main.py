import uuid, requests, time, shutil, hashlib, re, subprocess, serve, paramiko, sys, toml, os

from threading import Thread

from rich.console import Console

console = Console()

from rich.progress import Progress
from rich.prompt import Prompt, Confirm

import xml.etree.ElementTree as ET

if not os.path.exists('updates'):
    os.mkdir('updates')

class updates_manager: # or checker
    def __init__(self, latest_version=None): #TODO: Patch notes
        self.updates_url = "https://updates.cloud.remarkable.engineering/service/update2"
        self.id_lookups = {
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
            "2.10.2.356": "JLB6Ax3hnJ"
        }

        if latest_version is None:
            self.latest_version = self.get_latest_update()[0] # Version
        else:
            self.latest_version = latest_version
        self.latest_toltec_version = self.get_latest_toltec_supported()

    def get_update(self, version=None):
        if version is None:
            version = self.latest_version

        if version in self.id_lookups:
            id = f"-{self.id_lookups[version]}-"
        else:
            id = ""

        file_name = f"{version}_reMarkable2{id}.signed"
        file_url = f"https://updates-download.cloud.remarkable.engineering/build/reMarkable%20Device%20Beta/RM110/{version}/{file_name}"

        return self.download_file(file_url, file_name)

    def get_latest_toltec_supported(self):
        console.print("Getting latest [yellow bold]toltec supported[/yellow bold] version")
        site_body_html = requests.get('https://toltec-dev.org/').text # or /raw ?

        return re.search('Toltec does not support OS builds newer than (.*)\. You will soft-brick', site_body_html).group(1).strip()

    def get_latest_update(self):
        data = self._generate_xml_data()

        response = self._make_request(data)

        if response is None:  # or if not response
            return

        parsed_data = self._parse_response(response)
        if parsed_data is None:
            return

        return parsed_data

    @staticmethod
    def _generate_xml_data(version='0.0.0.0'):
        params = {
            "installsource": "scheduler",
            "requestid": str(uuid.uuid4()),
            "sessionid": str(uuid.uuid4()),
            "machineid": '00'.zfill(32),
            "oem": 'RM100-753-12345',
            "appid": "98DA7DF2-4E3E-4744-9DE6-EC931886ABAB",
            "bootid": str(uuid.uuid4()),
            "current": version,
            "group": "Prod",
            "platform": "reMarkable2"
        }

        return """<?xml version="1.0" encoding="UTF-8"?>
<request protocol="3.0" version="{current}" requestid="{{{requestid}}}" sessionid="{{{sessionid}}}" updaterversion="0.4.2" installsource="{installsource}" ismachine="1">
    <os version="zg" platform="{platform}" sp="{current}_armv7l" arch="armv7l"></os>
    <app appid="{{{appid}}}" version="{current}" track="{group}" ap="{group}" bootid="{{{bootid}}}" oem="{oem}" oemversion="2.5.2" alephversion="{current}" machineid="{machineid}" lang="en-US" board="" hardware_class="" delta_okay="false" nextversion="" brand="" client="" >
        <updatecheck/>
    </app>
</request>""".format(**params)

    def _make_request(self, data):
        tries = 1

        while tries < 3:
            tries += 1

            response = requests.post(self.updates_url, data)

            if response.status_code == 429:
                console.print("Too many requests sent, retrying after 20")
                time.sleep(20)

                continue

            response.raise_for_status()

            break

        return response.text

    @staticmethod
    def _parse_response(resp):

        xml_data = ET.fromstring(resp)

        if "noupdate" in resp or xml_data is None:  # Is none?
            return None  # Or False maybe?

        file_name = xml_data.find('app/updatecheck/manifest/packages/package').attrib['name']
        file_uri = f"{xml_data.find('app/updatecheck/urls/url').attrib['codebase']}{file_name}"
        file_version = xml_data.find('app/updatecheck/manifest').attrib["version"]

        return file_version, file_uri, file_name

    @staticmethod
    def download_file(uri, name): #TODO: Access denied
        hash_md5 = hashlib.md5()

        with Progress() as progress: #TODO: Put in second `with` ?

            with requests.get(uri, stream=True) as resp: #TOOD: Error handling
                total_length = int(resp.headers.get('content-length', 0))

                downloading_task = progress.add_task(f"Downloading {name}", total=(total_length/8192) + 4)

                with open(f"updates/{name}", 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        progress.update(downloading_task, advance=1)
                        if chunk:
                            f.write(chunk)
                            hash_md5.update(chunk)
                            f.flush()

        return name, hash_md5.hexdigest()

driver = updates_manager() #TODO: Delete file after its done

version_choice = Prompt.ask("What version would you like to [green]upgrade[/green]/[red]downgrade[/red] to?", default=driver.latest_toltec_version)
if version_choice != 's':
    file, md5_checksum = driver.get_update(version_choice)

    console.print(f'I have MD5 Checksum: [blue]{md5_checksum}[/blue]\n')

if Confirm.ask('Would you like to update your device now?'):
    while True:
        password = Prompt.ask("Please enter your RMs SSH password", password=True)

        client = paramiko.client.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            client.connect('10.11.99.1', username='root', password=password) # TODO: Only supporst USB at the moment
        except paramiko.ssh_exception.AuthenticationException:
            console.print('[red] Incorrect password given [/red]')

            continue

        break

    console.print('[green] SUCCESS: Connected to the device[/green]')

    server_host_name = serve.get_host_name()
    ftp = client.open_sftp() # or ssh

    with ftp.file('/usr/share/remarkable/update.conf') as update_conf_file: # TODO: use toml, and / or confgi and support for modified .conf/ig files
        contents = update_conf_file.read().decode('utf-8') #TODO: Doesn't support beta versions (fwiw modifying beta is against eula & tos - unrelated to changing versions tho!)
        data_attributes = contents.split('\n')

        data_attributes[2] = f"SERVER={server_host_name}"

        modified_conf_version = '\n'.join(data_attributes) # add final ?

    with ftp.file('/usr/share/remarkable/update.conf', 'w+') as update_conf_file: # w/w+ mode
        update_conf_file.write(modified_conf_version)

    console.print('Modified update.conf file')

    ftp.close()

    console.print('Starting webserver')

    serve.start_server(server_host_name)

# TODO: Fully a

from http.server import HTTPServer, SimpleHTTPRequestHandler
import xml.etree.ElementTree as ET
import os
import hashlib
import binascii

response_ok = """<?xml version='1.0' encoding='UTF-8'?>
<response protocol="3.0" server="prod">
	<daystart elapsed_seconds="42548" elapsed_days="5179"/>
	<app status="ok" appid="{98DA7DF2-4E3E-4744-9DE6-EC931886ABAB}">
		<event status="ok"/>
		<ping status="ok"/>
	</app>
</response>
"""

response_template = """<?xml version="1.0" encoding="UTF-8"?>
 <response protocol="3.0" server="prod">
	<daystart elapsed_seconds="37145" elapsed_days="5179"/>
	<app status="ok" appid="{{98DA7DF2-4E3E-4744-9DE6-EC931886ABAB}}">
		<event status="ok"/>
		<updatecheck status="ok">
			<urls>
				<url codebase="{codebase_url}"/>
			</urls>
			<manifest version="{version}">
				<packages>
					<package required="true" hash="{update_sha1}" name="{update_name}" size="{update_size}"/>
				</packages>
				<actions>
					<action successsaction="default" sha256="{update_sha256}" event="postinstall" DisablePayloadBackoff="true"/>
				</actions>
			</manifest>
		</updatecheck>
		<ping status="ok"/>
	</app>
</response>
"""


def getupdateinfo(update_name: str) -> tuple[str, str, int]:
    full_path = os.path.join("updates", update_name)

    update_size = os.path.getsize(full_path)

    BUF_SIZE = 8192

    sha1 = hashlib.sha1()
    sha256 = hashlib.sha256()
    with open(full_path, "rb") as f:
        while True:
            data = f.read(BUF_SIZE)
            if not data:
                break
            sha1.update(data)
            sha256.update(data)
    update_sha1 = binascii.b2a_base64(sha1.digest(), newline=False).decode()
    update_sha256 = binascii.b2a_base64(sha256.digest(), newline=False).decode()
    return (update_sha1, update_sha256, update_size)


def get_available_version(version: str):
    available_versions = scanUpdates()

    for device, ids in available_versions.items():
        if version in ids:
            available_version = {device: ids}

            return available_version


def scanUpdates() -> dict[str, tuple[str, str]]:
    files = os.listdir("updates")
    versions: dict[str, tuple[str, str]] = {}

    for f in files:
        p = f.split("_")
        if len(p) != 2:
            continue
        t = p[1].split(".")
        if len(t) != 2:
            continue

        z = t[0].split("-")

        version = p[0]
        # print(version)
        product = z[0]

        if product not in versions or versions[product][0] < version:
            versions[product] = (version, f)

    return versions


class MySimpleHTTPRequestHandler(SimpleHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8")
        # print(body)
        print("Updating...")
        xml = ET.fromstring(body)
        updatecheck_node = xml.find("app/updatecheck")

        # check for update
        if updatecheck_node is not None:
            version = xml.attrib["version"]
            os = xml.find("os")
            if os is None:
                raise Exception("os tag missing from results")

            platform = os.attrib["platform"]
            print("requested: ", version)
            print("platform: ", platform)

            version, update_name = available_versions[platform]

            update_sha1, update_sha256, update_size = getupdateinfo(update_name)
            params = {
                "version": version,
                "update_name": f"updates/{update_name}",
                "update_sha1": update_sha1,
                "update_sha256": update_sha256,
                "update_size": str(update_size),
                "codebase_url": host_url,
            }

            response = response_template.format(**params)
            # print("Response:")
            # print(response)
            self.send_response(200)
            self.end_headers()
            _ = self.wfile.write(response.encode())
            return

        event_node = xml.find("app/event")
        if event_node is None:
            raise Exception("app/event tag missing from results")

        event_type = int(event_node.attrib["eventtype"])
        event_result = int(event_node.attrib["eventresult"])

        # post install status
        if event_result != 0:
            print("Update downloaded, please wait for device to install...")
            if "errorcode" in event_node.attrib:
                print("With errorcode:", event_node.attrib["errorcode"])
            return

        # update done
        if event_type == 14:
            print("OK Response:")
            print(response_ok)
            self.send_response(200)
            self.end_headers()
            _ = self.wfile.write(response_ok.encode())
            return


def startUpdate(versionsGiven: dict[str, tuple[str, str]], host: str, port: int = 8080):
    global available_versions
    global host_url  # I am aware globals are generally bad practice, but this is a quick and dirty solution

    host_url = f"http://{host}:{port}/"
    available_versions = versionsGiven

    if not available_versions:
        raise FileNotFoundError("Could not find any update files")

    handler = MySimpleHTTPRequestHandler
    print(f"Starting fake updater at {host}:{port}")
    try:
        httpd = HTTPServer((host, port), handler)
    except OSError:
        print("Error: Could not start fake updater. Is the port already in use?")
        return
    httpd.serve_forever()

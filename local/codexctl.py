#!/opt/bin/python
from updates import UpdateManager
from server import startUpdate, scanUpdates
from time import sleep 

import argparse
import subprocess
import re
import threading


### Setting variables ###
parser = argparse.ArgumentParser('Codexctl app')
parser.add_argument(
	'--debug',
	action='store_true',
	help='Print debug info'
)
subparsers = parser.add_subparsers(dest='command', required=True)
install = subparsers.add_parser('install')
download = subparsers.add_parser('download')
status = subparsers.add_parser('status')
list_ = subparsers.add_parser('list')

install.add_argument('-v', '--version', help='Version to install', required=False)
download.add_argument('version', help='Version to download')

args = parser.parse_args()
updateman = UpdateManager()
choice = args.command

def version_lookup(version):
	if version == 'latest':
		return updateman.latest_version
	if version == 'toltec':
		return updateman.latest_toltec_version
	elif version in updateman.id_lookups:
		return version 
	
	raise SystemExit('Invalid version! Examples: latest, toltec, 3.2.3.1595, 2.15.0.1067')

### Decision making ###
if choice == 'install':
	prerequisitesMet = False

	while not prerequisitesMet:
		avaliableVersions = scanUpdates()

		if args.version:
			version = version_lookup(args.version)

			for device, ids in avaliableVersions.items():
				if version in ids:
					avaliableVersions = {device:ids}
					prerequisitesMet = True
					break
			else:
				print(f'The version you specified has no update file, Downloading now ({version})')
				updateman.get_version(version)
		else:
			prerequisitesMet = True

	with open('/usr/share/remarkable/update.conf', encoding='utf-8') as file:
		contents = file.read()
		data_attributes = contents.split("\n")
		data_attributes[2] = f"SERVER=http://localhost:8000"
		modified_conf_version = "\n".join(data_attributes) 
	with open('/usr/share/remarkable/update.conf', 'w') as file: 
		file.write(modified_conf_version)
	
	print(avaliableVersions)

	x = threading.Thread(target=startUpdate, args=(avaliableVersions,), daemon=True) # TODO: Get version automatically
	x.start()
	
	print('Enabling update service')
	subprocess.run('systemctl start update-engine', shell=True, text=True)
	
	updateProcess = subprocess.Popen('update_engine_client -update', text=True, stdout=subprocess.PIPE, shell=True)

	if updateProcess.wait() != 0:
		raise SystemExit('There was an error')

	if 'y' in input('Done! Would you like to shutdown?').lower():
		subprocess.run(['shutdown', 'now'])
			

elif choice == 'download':
	version = version_lookup(args.version)
	print(f'Downloading {version}')
	filename = updateman.get_version(version)
	print(f'Done! ({filename})')

elif choice == 'status':
	try:
		with open('/etc/remarkable.conf') as file:
			configContents = file.read()
		with open('/etc/version') as file:
			versionID = file.read().rstrip()
		with open('/usr/share/remarkable/update.conf') as file:
			versionContents = file.read().rstrip()

		beta = re.search('(?<=BetaProgram=).*', configContents).group()
		prev = re.search('(?<=PreviousVersion=).*', configContents).group()
		current = re.search('(?<=REMARKABLE_RELEASE_VERSION=).*', versionContents).group()
		
		print(f'You are running {current} [{versionID}]{"[BETA]" if beta else ""}, previous version was {prev}')
	except Exception as error:
		print(f"Error: {error} (Maybe you aren't running this on the ReMarkable device?")


elif choice == 'list':
	[print(codexID) for codexID in updateman.id_lookups]
 

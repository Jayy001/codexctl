<p align="center">
<img src="media/demoLocal.gif">

# Codexctl
A utility program that helps to manage the remarkable device version utilizing [ddvks update server](https://github.com/ddvk/remarkable-update) 


## PLEASE READ BEFORE USING
If your remarkable device is at version >= 3.11, codexctl will not be able to automatically install updates on it due to a major overhaul in the update engine. You can still use the other functions like downloading the image files and then manually extracting it, using `dd` to write to the other partition and then using the `restore` command. More information can be found in https://github.com/Jayy001/codexctl/issues/71#issuecomment-2099115757.
---

### Installation & Use

You can find pre-compiled binaries on the [releases](https://github.com/Jayy001/codexctl/releases/) page. This includes a build for the reMarkable itself, as well as well as builds for linux, macOS, and Windows. It currently only has support for **command line interfaces** but a graphical interface is soon to come.

## Running from source

Codexctl can be run from source on both the reMarkable, as well as on a remote device.

### Running on reMarkable

```
git clone https://github.com/Jayy001/codexctl.git
cd codexctl
pip install -r requirements.txt
python codexctl.py --help
```

### Running on a remote device

This requires python 3.11 or newer.

```
git clone https://github.com/Jayy001/codexctl.git
cd codexctl
pip install wheel
pip install -r requirements.remote.txt
python codexctl.py --help
```

## Building executables from source

This requires python 3.11 or newer, python-venv, pip. Linux also requires libfuse-dev.

```
make executable
```

## Usage

The script is designed to have as little interactivity as possible, meaning arguments are directly taken from the command to run the script. 

```
❯ codexctl --help
usage: Codexctl app [-h] [--debug] [--rm1] [--auth AUTH] [--verbose] {install,download,backup,extract,mount,status,restore,list} ...

positional arguments:
  {install,download,backup,extract,mount,status,restore,list}
    install             Install the specified version (will download if not available on the device)
    download            Download the specified version firmware file
    backup              Download remote files to local directory
    extract             Extract the specified version update file
    mount               Mount the specified version firmware filesystem
    status              Get the current version of the device and other information
    restore             Restores to previous version installed on device
    list                List all versions available for use

options:
  -h, --help            show this help message and exit
  --debug               Print debug info
  --rm1                 Use rm1
  --auth AUTH           Specify password or SSH key for SSH
  --verbose             Enable verbose logging
```

# Examples
```
codexctl install latest # Downloads and installs latest version
codexctl download toltec # Downloads latest version that has full support for toltec
codexctl download 3.0.4.1305 --rm1 # Downloads 3.0.4.1305 firmware file for remarkable 1
codexctl status # Prints current & previous version (can only be used when running on device itself)
codexctl list # Lists all available versions 
python codexctl.py restore # Restores previous version
python codexctl.py --verbose # Enables logging
python codexctl.py --backup # Exports all files to local directory
python codexctl.py --backup -l root -r FM --no-recursion --no-overwrite # Exports all files from FM directory to root folder on localhost
python codexctl.py extract 3.8.0.1944_reMarkable2-7eGpAv7sYB.signed # Extracts contents to filesystem named "extracted"
python codexctl.py mount extracted /opt/remarkable # Mounts extracted filesystem to /opt/remarkable
python codexctl.py ls 3.8.0.1944_reMarkable2-7eGpAv7sYB.signed / # Lists the root directory of the update image
python codexctl.py cat 3.8.0.1944_reMarkable2-7eGpAv7sYB.signed /etc/version # Outputs the contents of /etc/version from the update image
```

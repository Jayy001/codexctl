

# Codexctl
A utility program that helps to manage the remarkable device version utilizing [ddvks update server](https://github.com/ddvk/remarkable-update) 

## Caveat for downgrading from 3.11.2.5 or greater to a version less than 3.11.2.5

If your reMarkable device is at or above 3.11.2.5 and you want to downgrade to a version below 3.11.2.5, codexctl cannot do this currently. Please refer to https://github.com/Jayy001/codexctl/issues/95#issuecomment-2305529048 for manual instructions.

## Paper Pro bootloader updates

When downgrading a Paper Pro device across the 3.20/3.22 firmware boundary, codexctl automatically handles bootloader updates. It will download the current version's firmware if needed and extract the necessary bootloader files (`update-bootloader.sh` and `imx-boot`) to ensure a safe downgrade.

## Installation

You can find pre-compiled binaries on the [releases](https://github.com/Jayy001/codexctl/releases/) page. This includes a build for the reMarkable itself, as well as well as builds for linux, macOS, and Windows. Alternatively, you can install directly from pypi with `pip install codexctl`. Codexctl currently only has support for a **command line interfaces** but a graphical interface is soon to come.

Finally, if you want to build it yourself, you can run `make executable` which requires python 3.11 or newer, python-venv and pip. Linux also requires libfuse-dev.

## General useage

```
❯ codexctl --help
usage: Codexctl [-h] [--verbose] [--address ADDRESS] [--password PASSWORD]
                {install,download,backup,cat,ls,extract,mount,upload,status,restore,list} ...

positional arguments:
  {install,download,backup,cat,ls,extract,mount,upload,status,restore,list}
    install             Install the specified version (will download if not available on the device)
    download            Download the specified version firmware file
    backup              Download remote files to local directory
    cat                 Cat the contents of a file inside a firmwareimage
    ls                  List files inside a firmware image
    extract             Extract the specified version update file
    mount               Mount the specified version firmware filesystem
    upload              Upload folder/files to device (pdf only)
    status              Get the current version of the device and other information
    restore             Restores to previous version installed on device
    list                List all available versions

options:
  -h, --help            show this help message and exit
  --verbose, -v         Enable verbose logging
  --address ADDRESS, -a ADDRESS
                        Specify the address of the device
  --password PASSWORD, -p PASSWORD
                        Specify password or path to SSH key for remote access
```

## Examples
- Installing the latest for device (will automatically figure out the version)
```
codexctl install latest
```
- Downloading rmpp version 3.15.4.2 to a folder named `out` and then installing it
```
codexctl download 3.15.4.2 --hardware rmpp -o out
codexctl install ./out/remarkable-ct-prototype-image-3.15.4.2-ferrari-public.swu
```
-  (Paper Pro Move) version 3.23.0.64 to a folder named `out`
```
codexctl download 3.23.0.64 --hardware rmppm -o out
codexctl install ./out/remarkable-production-image-3.23.0.64-chiappa-public.swu
```
- Backing up all documents to the cwd
```
codexctl backup 
```
- Backing up modified/newer documents only, overwrites out-of-date files on disk
```
codexctl backup --incremental
```
- Backing up only documents in a folder named "FM" to cwd, without overwriting any current files
```
codexctl backup -l root -r FM --no-recursion --no-overwrite
```
- Getting the version of the device and then switching to previous version
```
codexctl status
codexctl restore
```
- Download 3.8.0.1944 for rm2, then cat the /etc/version file from it
```
codexctl download 3.8.0.1944 --hardware rm2
codexctl cat 3.8.0.1944_reMarkable2-7eGpAv7sYB.signed /etc/version
```
- Extract a 3.11+ SWU firmware file to see its contents
```
codexctl extract remarkable-production-image-3.22.0.64-ferrari-public.swu -o extracted
```

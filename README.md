<p align="center">
<img src="demo.gif">

# Codexctl
A utility program that helps to manage the remarkable device version utilizing [ddvks update server](https://github.com/ddvk/remarkable-update) 

### Installation and use

This program is can be directly ran on the ReMarkable device as well as from a remote device such as your computer, it currently only has support for **command line interfaces** but a graphical interface is soon to come. The steps to install are closely similar apart from the couple of extra depedancies needed for running on a remote device. 

```
git clone https://github.com/Jayy001/codexctl.git 
cd codexctl
pip install requests
```

Thats it for running it directly on the remarkable. If you are running on a remote device you will need to run the following too,

```
pip install paramiko # This is for SSH access
pip install netifaces # This is for getting the IP of the remote host
```



The script is designed to have as little interactivity as possible (apart from entering the password when connecting  & managing remotely) meaning arguments are directly taken from the command to run the script. 

```
❯ python codexctl.py --help
usage: Codexctl app [-h] [--debug] {install,download,status,list} ...

positional arguments:
  {install,download,status,list}
    install             Install the specified version (will download if not available on the device)
    download            Download the specified version firmware file
    status              Get the current version of the device and other information
    list                List all versions available for use

options:
  -h, --help            show this help message and exit
  --debug               Print debug info
```



### Examples

```
python codexctl.py install --version latest # Downloads & installs the latest version 
python codexctl.py download --version toltec # Downloads the latest toltec version to updates folder
python codexctl.py install # Installs the most up to date version firmware found in updates folder
python codexctl.py list # Lists all avaliable versions
python codexctl.py status # Gives the current & previous versions installed 
```



## Limitations (PLEASE READ THIS!)

Currently only the *install* and *download* features are only available when running directly on the ReMarkable device itself as it utilizes reading the confirm files but there are plans to make this available when running from a remote device. Furthermore if installing from a remote device, it will not automate the process of checking for an update on the remarkable device so you will have to do one of the following once the update server is running:

1) SSH into the device, and run
```
systemctl start update-engine
update_engine_client -check_for_update
journalctl -u update-engine -f
reboot
```
2) Navigate to the devices "update" setting. Click check for updates and then reboot once its done.


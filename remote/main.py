import serve, paramiko, updates

from threading import Thread

from rich.console import Console

console = Console()

from rich.progress import Progress
from rich.prompt import Prompt, Confirm

driver = updates.update_manager()  # TODO: Delete file after its done

version_choice = Prompt.ask(
    "What version would you like to [green]upgrade[/green]/[red]downgrade[/red] to?",
    default=driver.latest_toltec_version,
)
if version_choice != "s":
    file, md5_checksum = driver.get_update(version_choice)

    console.print(f"I have MD5 Checksum: [blue]{md5_checksum}[/blue]\n")

if Confirm.ask("Would you like to update your device now?"):
    while True:
        password = Prompt.ask("Please enter your RMs SSH password", password=True)

        client = paramiko.client.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            client.connect(
                "10.11.99.1", username="root", password=password
            )  # TODO: Only supporst USB at the moment
        except paramiko.ssh_exception.AuthenticationException:
            console.print("[red] Incorrect password given [/red]")

            continue

        break

    console.print("[green] SUCCESS: Connected to the device[/green]")

    server_host_name = serve.get_host_name()
    ftp = client.open_sftp()  # or ssh

    with ftp.file(
        "/usr/share/remarkable/update.conf"
    ) as update_conf_file:  # TODO: use toml, and / or confgi and support for modified .conf/ig files
        contents = update_conf_file.read().decode(
            "utf-8"
        )  # TODO: Doesn't support beta versions (fwiw modifying beta is against eula & tos - unrelated to changing versions tho!)
        data_attributes = contents.split("\n")

        data_attributes[2] = f"SERVER={server_host_name}"

        modified_conf_version = "\n".join(data_attributes)  # add final ?

    with ftp.file(
        "/usr/share/remarkable/update.conf", "w+"
    ) as update_conf_file:  # w/w+ mode
        update_conf_file.write(modified_conf_version)

    console.print("Modified update.conf file")

    ftp.close()

    console.print("Starting webserver")

    serve.start_server(server_host_name)

# TODO: Fully a

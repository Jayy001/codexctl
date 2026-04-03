#!/usr/bin/env python3
"""
codexctl TUI - Terminal User Interface for reMarkable firmware management
Requires: pip install textual codexctl
"""

from textual.app import App, ComposeResult
from textual.widgets import (
    Header, Footer, Button, Static, Label, Input, Select, RichLog,
)
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.screen import ModalScreen
from textual.binding import Binding
from textual import work, on
from textual.reactive import reactive
import subprocess


HARDWARE_OPTIONS = [
    ("reMarkable 1",         "rm1"),
    ("reMarkable 2",         "rm2"),
    ("reMarkable Paper Pro", "rmpp"),
]


def run_codexctl(args: list[str], address: str = "", password: str = "") -> tuple[str, str, int]:
    cmd = ["codexctl"]
    if address:
        cmd += ["--address", address]
    if password:
        cmd += ["--password", password]
    cmd += args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return result.stdout, result.stderr, result.returncode
    except FileNotFoundError:
        return "", "codexctl not found — install with: pip install codexctl", 1
    except subprocess.TimeoutExpired:
        return "", "Command timed out (120 s).", 1
    except Exception as e:
        return "", str(e), 1


# ─── Confirm modal ────────────────────────────────────────────────────────────

class ConfirmScreen(ModalScreen):
    CSS = """
    ConfirmScreen { align: center middle; }
    #dialog {
        padding: 1 2; background: $surface;
        border: round $primary; width: 52; height: auto;
    }
    #dialog-msg  { margin-bottom: 1; }
    #dialog-btns { align: center middle; height: 3; }
    #dialog-btns Button { margin: 0 1; }
    """

    def __init__(self, message: str, **kw):
        super().__init__(**kw)
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self.message, id="dialog-msg")
            with Horizontal(id="dialog-btns"):
                yield Button("Confirm", id="ok",     variant="error")
                yield Button("Cancel",  id="cancel", variant="default")

    @on(Button.Pressed, "#ok")
    def do_ok(self):     self.dismiss(True)

    @on(Button.Pressed, "#cancel")
    def do_cancel(self): self.dismiss(False)


# ─── Main app ─────────────────────────────────────────────────────────────────

class CodexctlTUI(App):
    CSS = """
    Screen { background: $background; }
    Header { background: $primary-darken-3; }

    #sidebar {
        width: 22; background: $surface;
        border-right: solid $primary-darken-2;
        padding: 1 1;
    }
    #sidebar-title {
        text-align: center; text-style: bold;
        color: $primary; margin-bottom: 1;
    }
    .nav-btn {
        width: 100%; margin-bottom: 1;
        background: $surface; border: none;
    }
    .nav-btn:hover   { background: $primary-darken-2; }
    .nav-btn.-active { background: $primary; text-style: bold; }

    #conn-bar {
        height: 3; background: $surface-darken-1;
        padding: 0 1; border-bottom: solid $primary-darken-3;
    }
    .conn-lbl { width: auto; padding: 1 1 0 0; color: $text-muted; }
    .conn-inp { width: 24; margin-right: 1; }

    #main   { padding: 1 2; }
    #panel  { height: auto; }

    .sec-title { text-style: bold; color: $accent; margin-bottom: 1; }
    .card      {
        background: $surface; border: round $primary-darken-2;
        padding: 1 2; margin-bottom: 1;
    }
    .field-row { height: 3; margin-bottom: 1; }
    .field-lbl { width: 18; padding: 1 0; color: $text-muted; }
    .field-inp { width: 32; }
    .act-btn   { margin-top: 1; margin-right: 1; }

    #output-log {
        height: 11; border-top: solid $primary-darken-2;
        background: $surface-darken-1;
    }
    """

    BINDINGS = [
        Binding("q",      "quit",         "Quit"),
        Binding("ctrl+l", "clear_output", "Clear log"),
    ]

    _current_panel: reactive[str] = reactive("status")

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Horizontal(id="conn-bar"):
            yield Label("Address:",          classes="conn-lbl")
            yield Input(placeholder="10.11.99.1", id="inp-addr", classes="conn-inp")
            yield Label("Password/SSH key:", classes="conn-lbl")
            yield Input(placeholder="alpine", id="inp-pass", password=True, classes="conn-inp")

        with Horizontal():
            with Vertical(id="sidebar"):
                yield Static("⬡ codexctl", id="sidebar-title")
                for label, panel in [
                    ("📊 Status",    "status"),
                    ("📋 List",      "list"),
                    ("⬇  Download",  "download"),
                    ("⬆  Install",   "install"),
                    ("💾 Backup",    "backup"),
                    ("↩  Restore",   "restore"),
                    ("📤 Upload",    "upload"),
                    ("📦 Extract",   "extract"),
                    ("🔍 Cat",       "cat"),
                    ("📁 LS",        "ls"),
                ]:
                    yield Button(label, id=f"nav-{panel}", classes="nav-btn")

            with ScrollableContainer(id="main"):
                yield Vertical(id="panel")

        yield RichLog(id="output-log", markup=True, highlight=True)
        yield Footer()

    def on_mount(self) -> None:
        self._switch_panel("status")
        self.query_one("#nav-status").add_class("-active")

    # ── navigation ───────────────────────────────────────────────────────────

    @on(Button.Pressed, ".nav-btn")
    def _nav(self, event: Button.Pressed) -> None:
        name = event.button.id.removeprefix("nav-")
        for b in self.query(".nav-btn"):
            b.remove_class("-active")
        event.button.add_class("-active")
        self._switch_panel(name)

    def _switch_panel(self, name: str) -> None:
        self._current_panel = name
        panel = self.query_one("#panel", Vertical)
        panel.remove_children()
        {
            "status":   self._panel_status,
            "list":     self._panel_list,
            "download": self._panel_download,
            "install":  self._panel_install,
            "backup":   self._panel_backup,
            "restore":  self._panel_restore,
            "upload":   self._panel_upload,
            "extract":  self._panel_extract,
            "cat":      self._panel_cat,
            "ls":       self._panel_ls,
        }.get(name, self._panel_status)(panel)

    # ── panel builders ────────────────────────────────────────────────────────

    def _panel_status(self, p):
        p.mount(Static("Device Status", classes="sec-title"))
        p.mount(Static("Fetches firmware version and info from the connected device.", classes="card"))
        p.mount(Button("Get Status", id="btn-status", variant="primary", classes="act-btn"))

    def _panel_list(self, p):
        p.mount(Static("Available Firmware Versions", classes="sec-title"))
        row = Horizontal(classes="field-row")
        row.mount(Label("Hardware:", classes="field-lbl"))
        row.mount(Select([(l, v) for l, v in HARDWARE_OPTIONS],
                         id="sel-hw-list", allow_blank=True, classes="field-inp"))
        p.mount(row)
        p.mount(Button("List Versions", id="btn-list", variant="primary", classes="act-btn"))

    def _panel_download(self, p):
        p.mount(Static("Download Firmware", classes="sec-title"))
        self._field(p, "Version:",    "inp-dl-ver", "e.g. 3.15.4.2")
        row = Horizontal(classes="field-row")
        row.mount(Label("Hardware:", classes="field-lbl"))
        row.mount(Select([(l, v) for l, v in HARDWARE_OPTIONS],
                         id="sel-hw-dl", allow_blank=True, classes="field-inp"))
        p.mount(row)
        self._field(p, "Output dir:", "inp-dl-out", "./firmware")
        p.mount(Button("Download", id="btn-download", variant="primary", classes="act-btn"))

    def _panel_install(self, p):
        p.mount(Static("Install Firmware", classes="sec-title"))
        self._field(p, "Version / .swu:", "inp-inst-ver", "3.15.4.2 or ./file.swu")
        p.mount(Button("Install on Device", id="btn-install", variant="warning", classes="act-btn"))

    def _panel_backup(self, p):
        p.mount(Static("Backup Remote Files", classes="sec-title"))
        self._field(p, "Output dir:", "inp-bk-out", "./backup")
        p.mount(Button("Start Backup", id="btn-backup", variant="primary", classes="act-btn"))

    def _panel_restore(self, p):
        p.mount(Static("Restore Previous Version", classes="sec-title"))
        p.mount(Static("Reverts device to previously installed firmware.", classes="card"))
        p.mount(Button("Restore", id="btn-restore", variant="error", classes="act-btn"))

    def _panel_upload(self, p):
        p.mount(Static("Upload Files (PDF only)", classes="sec-title"))
        self._field(p, "Local path:", "inp-up-path", "/path/to/file.pdf")
        p.mount(Button("Upload", id="btn-upload", variant="primary", classes="act-btn"))

    def _panel_extract(self, p):
        p.mount(Static("Extract Firmware", classes="sec-title"))
        self._field(p, "Version / .swu:", "inp-ex-ver", "3.15.4.2 or ./file.swu")
        self._field(p, "Output dir:",     "inp-ex-out", "./extracted")
        p.mount(Button("Extract", id="btn-extract", variant="primary", classes="act-btn"))

    def _panel_cat(self, p):
        p.mount(Static("Cat File in Firmware Image", classes="sec-title"))
        self._field(p, "Firmware file:", "inp-cat-ver",  "3.15.4.2_reMarkable2-xxx.signed")
        self._field(p, "Inner path:",    "inp-cat-path", "/etc/version")
        p.mount(Button("Cat", id="btn-cat", variant="primary", classes="act-btn"))

    def _panel_ls(self, p):
        p.mount(Static("List Files in Firmware Image", classes="sec-title"))
        self._field(p, "Firmware file:", "inp-ls-ver", "3.15.4.2_reMarkable2-xxx.signed")
        p.mount(Button("List Files", id="btn-ls", variant="primary", classes="act-btn"))

    def _field(self, parent, label: str, inp_id: str, placeholder: str = ""):
        row = Horizontal(classes="field-row")
        row.mount(Label(label, classes="field-lbl"))
        row.mount(Input(placeholder=placeholder, id=inp_id, classes="field-inp"))
        parent.mount(row)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _conn(self) -> tuple[str, str]:
        try:
            addr = self.query_one("#inp-addr", Input).value.strip()
            pw   = self.query_one("#inp-pass", Input).value.strip()
        except Exception:
            addr, pw = "", ""
        return addr, pw

    def _val(self, wid: str) -> str:
        try:
            return self.query_one(f"#{wid}", Input).value.strip()
        except Exception:
            return ""

    def _sel(self, wid: str) -> str:
        try:
            v = self.query_one(f"#{wid}", Select).value
            return "" if v is Select.BLANK else str(v)
        except Exception:
            return ""

    def _write(self, text: str) -> None:
        """Write a line to the output log. Safe to call from any thread via call_from_thread."""
        self.query_one("#output-log", RichLog).write(text)

    def action_clear_output(self) -> None:
        self.query_one("#output-log", RichLog).clear()

    # ── button handlers ───────────────────────────────────────────────────────

    @on(Button.Pressed, "#btn-status")
    def _do_status(self): self._dispatch(["status"])

    @on(Button.Pressed, "#btn-list")
    def _do_list(self):
        args = ["list"]
        hw = self._sel("sel-hw-list")
        if hw: args += ["--hardware", hw]
        self._dispatch(args)

    @on(Button.Pressed, "#btn-download")
    def _do_download(self):
        ver = self._val("inp-dl-ver")
        if not ver: self._write("[red]⚠ Version is required.[/red]"); return
        args = ["download", ver]
        hw = self._sel("sel-hw-dl")
        if hw: args += ["--hardware", hw]
        out = self._val("inp-dl-out")
        if out: args += ["-o", out]
        self._dispatch(args)

    @on(Button.Pressed, "#btn-install")
    def _do_install(self):
        ver = self._val("inp-inst-ver")
        if not ver: self._write("[red]⚠ Version or path required.[/red]"); return
        self.push_screen(
            ConfirmScreen(f"Install '{ver}' on device?"),
            lambda ok: self._dispatch(["install", ver]) if ok else None,
        )

    @on(Button.Pressed, "#btn-backup")
    def _do_backup(self):
        args = ["backup"]
        out = self._val("inp-bk-out")
        if out: args += ["-o", out]
        self._dispatch(args)

    @on(Button.Pressed, "#btn-restore")
    def _do_restore(self):
        self.push_screen(
            ConfirmScreen("Restore previous firmware? This modifies your device."),
            lambda ok: self._dispatch(["restore"]) if ok else None,
        )

    @on(Button.Pressed, "#btn-upload")
    def _do_upload(self):
        path = self._val("inp-up-path")
        if not path: self._write("[red]⚠ File path required.[/red]"); return
        self._dispatch(["upload", path])

    @on(Button.Pressed, "#btn-extract")
    def _do_extract(self):
        ver = self._val("inp-ex-ver")
        if not ver: self._write("[red]⚠ Version or path required.[/red]"); return
        args = ["extract", ver]
        out = self._val("inp-ex-out")
        if out: args += ["-o", out]
        self._dispatch(args)

    @on(Button.Pressed, "#btn-cat")
    def _do_cat(self):
        ver  = self._val("inp-cat-ver")
        path = self._val("inp-cat-path")
        if not ver or not path:
            self._write("[red]⚠ Firmware file and inner path are both required.[/red]"); return
        self._dispatch(["cat", ver, path])

    @on(Button.Pressed, "#btn-ls")
    def _do_ls(self):
        ver = self._val("inp-ls-ver")
        if not ver: self._write("[red]⚠ Firmware file required.[/red]"); return
        self._dispatch(["ls", ver])

    # ── worker ────────────────────────────────────────────────────────────────

    def _dispatch(self, args: list[str]) -> None:
        addr, pw = self._conn()
        self._write(f"[bold cyan]» codexctl {' '.join(args)}[/bold cyan]")
        self._thread_run(args, addr, pw)

    @work(thread=True)
    def _thread_run(self, args: list[str], addr: str, pw: str) -> None:
        stdout, stderr, rc = run_codexctl(args, addr, pw)
        combined = (stdout + stderr).strip()
        if combined:
            self.call_from_thread(self._write, combined)
        colour = "green" if rc == 0 else "red"
        self.call_from_thread(self._write, f"[{colour}]exit {rc}[/{colour}]\n")


if __name__ == "__main__":
    CodexctlTUI().run()

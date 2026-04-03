#!/usr/bin/env python3
"""
codexctl GUI - Graphical User Interface for reMarkable firmware management
Requires: pip install PyQt6 codexctl
          (no system Tk/libtk needed)
"""

import sys
import subprocess
import threading

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTabWidget, QTextEdit, QComboBox,
    QFileDialog, QMessageBox, QFrame, QSizePolicy, QSpacerItem,
)
from PyQt6.QtGui import QFont, QColor, QPalette, QTextCharFormat, QTextCursor
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject


# ─── Colors ───────────────────────────────────────────────────────────────────

BG      = "#0f1117"
SURFACE = "#1a1d27"
CARD    = "#222536"
ACCENT  = "#6c8cff"
SUCCESS = "#34d399"
WARNING = "#fbbf24"
DANGER  = "#f87171"
TEXT    = "#e2e8f0"
MUTED   = "#64748b"
BORDER  = "#2e3347"
BTN     = "#2d3155"
BTN_H   = "#3d4370"

GLOBAL_CSS = f"""
QMainWindow, QWidget {{
    background-color: {BG};
    color: {TEXT};
    font-family: "JetBrains Mono", "Fira Code", "Consolas", monospace;
    font-size: 13px;
}}
QTabWidget::pane {{
    border: 1px solid {BORDER};
    background: {CARD};
    border-radius: 4px;
}}
QTabBar::tab {{
    background: {SURFACE};
    color: {MUTED};
    padding: 8px 16px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    font-size: 12px;
}}
QTabBar::tab:selected {{
    background: {CARD};
    color: {ACCENT};
    font-weight: bold;
}}
QTabBar::tab:hover {{
    background: {BTN};
    color: {TEXT};
}}
QLineEdit {{
    background: {SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 5px 8px;
    font-family: "JetBrains Mono", monospace;
}}
QLineEdit:focus {{
    border-color: {ACCENT};
}}
QComboBox {{
    background: {SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 5px 8px;
}}
QComboBox QAbstractItemView {{
    background: {SURFACE};
    color: {TEXT};
    selection-background-color: {BTN_H};
}}
QPushButton {{
    background: {BTN};
    color: {TEXT};
    border: none;
    border-radius: 4px;
    padding: 7px 18px;
    font-weight: bold;
    font-family: "JetBrains Mono", monospace;
}}
QPushButton:hover  {{ background: {ACCENT}; color: #ffffff; }}
QPushButton:pressed {{ background: {BTN_H}; }}
QPushButton.warning {{ color: {WARNING}; }}
QPushButton.warning:hover {{ background: #92400e; color: #ffffff; }}
QPushButton.danger {{ color: {DANGER}; }}
QPushButton.danger:hover {{ background: #991b1b; color: #ffffff; }}
QTextEdit {{
    background: {SURFACE};
    color: {SUCCESS};
    border: none;
    font-family: "JetBrains Mono", "Fira Code", monospace;
    font-size: 12px;
}}
QScrollBar:vertical {{
    background: {SURFACE}; width: 8px; border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER}; border-radius: 4px; min-height: 20px;
}}
QFrame#conn-bar {{
    background: {SURFACE};
    border-bottom: 1px solid {BORDER};
}}
QLabel.muted {{ color: {MUTED}; font-size: 12px; }}
QLabel.section {{ color: {ACCENT}; font-size: 14px; font-weight: bold; }}
QLabel.info {{ color: {MUTED}; font-size: 11px; }}
"""


# ─── Worker thread ────────────────────────────────────────────────────────────

class CmdWorker(QObject):
    line   = pyqtSignal(str, str)   # (text, colour)
    done   = pyqtSignal(int)

    def __init__(self, args, address, password):
        super().__init__()
        self.args = args
        self.address = address
        self.password = password

    def run(self):
        cmd = ["codexctl"]
        if self.address:
            cmd += ["--address", self.address]
        if self.password:
            cmd += ["--password", self.password]
        cmd += self.args

        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
            for ln in proc.stdout:
                self.line.emit(ln.rstrip(), TEXT)
            proc.wait()
            rc = proc.returncode
        except FileNotFoundError:
            self.line.emit(
                "ERROR: codexctl not found — install with: pip install codexctl", DANGER)
            rc = 1
        except Exception as e:
            self.line.emit(f"ERROR: {e}", DANGER)
            rc = 1

        self.done.emit(rc)


# ─── Main window ──────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("codexctl — reMarkable Firmware Manager")
        self.resize(980, 720)
        self.setMinimumSize(800, 560)
        self.setStyleSheet(GLOBAL_CSS)
        self._threads = []      # keep references alive

        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # title bar
        title_bar = QFrame()
        title_bar.setFixedHeight(52)
        title_bar.setStyleSheet(f"background: {BG}; padding: 0 16px;")
        tb_lay = QHBoxLayout(title_bar)
        tb_lay.setContentsMargins(16, 0, 16, 0)
        lbl = QLabel("⬡  codexctl")
        lbl.setStyleSheet(f"color: {ACCENT}; font-size: 20px; font-weight: bold;")
        tb_lay.addWidget(lbl)
        sub = QLabel("reMarkable Firmware Manager")
        sub.setStyleSheet(f"color: {MUTED}; font-size: 11px; padding-left: 10px;")
        tb_lay.addWidget(sub)
        tb_lay.addStretch()
        root_layout.addWidget(title_bar)

        # connection bar
        conn = QFrame()
        conn.setObjectName("conn-bar")
        conn.setFixedHeight(46)
        conn_lay = QHBoxLayout(conn)
        conn_lay.setContentsMargins(16, 0, 16, 0)
        conn_lay.setSpacing(8)

        self.addr_edit = self._conn_pair(conn_lay, "Address:", "10.11.99.1")
        self.pass_edit = self._conn_pair(conn_lay, "Password / SSH key:", "alpine", echo=QLineEdit.EchoMode.Password)
        conn_lay.addStretch()
        root_layout.addWidget(conn)

        # tabs
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        root_layout.addWidget(self.tabs, 1)

        self._build_tabs()

        # output log
        log_frame = QFrame()
        log_frame.setStyleSheet(f"background: {SURFACE}; border-top: 1px solid {BORDER};")
        log_lay = QVBoxLayout(log_frame)
        log_lay.setContentsMargins(0, 0, 0, 0)
        log_lay.setSpacing(0)

        log_header = QFrame()
        log_header.setStyleSheet(f"background: {BG}; padding: 2px 12px;")
        lh_lay = QHBoxLayout(log_header)
        lh_lay.setContentsMargins(12, 2, 12, 2)
        lh_lay.addWidget(QLabel("Output", styleSheet=f"color: {MUTED}; font-size: 11px;"))
        lh_lay.addStretch()
        clear_btn = QPushButton("Clear")
        clear_btn.setFixedSize(60, 22)
        clear_btn.setStyleSheet(f"background: transparent; color: {MUTED}; font-size: 11px; font-weight: normal;")
        clear_btn.clicked.connect(self._clear_log)
        lh_lay.addWidget(clear_btn)
        log_lay.addWidget(log_header)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(160)
        log_lay.addWidget(self.log)
        root_layout.addWidget(log_frame)

    # ── connection pair ───────────────────────────────────────────────────────

    def _conn_pair(self, layout, label, placeholder="", echo=None):
        lbl = QLabel(label)
        lbl.setProperty("class", "muted")
        layout.addWidget(lbl)
        edit = QLineEdit()
        edit.setPlaceholderText(placeholder)
        edit.setFixedWidth(200)
        if echo:
            edit.setEchoMode(echo)
        layout.addWidget(edit)
        return edit

    # ── tabs ──────────────────────────────────────────────────────────────────

    def _build_tabs(self):
        defs = [
            ("📊 Status",    self._tab_status),
            ("📋 List",      self._tab_list),
            ("⬇  Download",  self._tab_download),
            ("⬆  Install",   self._tab_install),
            ("💾 Backup",    self._tab_backup),
            ("↩  Restore",   self._tab_restore),
            ("📤 Upload",    self._tab_upload),
            ("📦 Extract",   self._tab_extract),
            ("🔍 Cat / LS",  self._tab_cat_ls),
        ]
        for label, builder in defs:
            w = QWidget()
            w.setStyleSheet(f"background: {CARD};")
            lay = QVBoxLayout(w)
            lay.setContentsMargins(20, 16, 20, 16)
            lay.setSpacing(10)
            builder(lay)
            lay.addStretch()
            self.tabs.addTab(w, label)

    # ── tab builders ──────────────────────────────────────────────────────────

    def _tab_status(self, lay):
        self._section(lay, "Device Status")
        self._info(lay, "Retrieves the current firmware version and other info over SSH.")
        lay.addWidget(self._btn("Get Status", self._run_status))

    def _tab_list(self, lay):
        self._section(lay, "Available Firmware Versions")
        self._info(lay, "List firmware versions available for your device model.")
        self.hw_list_cb = self._hw_row(lay)
        lay.addWidget(self._btn("List Versions", self._run_list))

    def _tab_download(self, lay):
        self._section(lay, "Download Firmware")
        self._info(lay, "Download a firmware .swu file to your machine.")
        self.dl_ver = self._field_row(lay, "Version:", "e.g. 3.15.4.2")
        self.hw_dl_cb = self._hw_row(lay)
        self.dl_out = self._field_row(lay, "Output dir:", "./firmware", browse_dir=True)
        lay.addWidget(self._btn("Download", self._run_download))

    def _tab_install(self, lay):
        self._section(lay, "Install Firmware")
        self._info(lay, "Install a firmware version (downloads if needed) onto the device.")
        self.inst_ver = self._field_row(lay, "Version / .swu:", "3.15.4.2 or ./file.swu",
                                        browse_file=True)
        b = self._btn("Install on Device", self._run_install)
        b.setProperty("class", "warning")
        b.setStyleSheet(f"QPushButton {{ color: {WARNING}; background: {BTN}; }}"
                        f"QPushButton:hover {{ background: #92400e; color: #fff; }}")
        lay.addWidget(b)

    def _tab_backup(self, lay):
        self._section(lay, "Backup Remote Files")
        self._info(lay, "Download documents and notebooks from the device.")
        self.bk_out = self._field_row(lay, "Output dir:", "./backup", browse_dir=True)
        lay.addWidget(self._btn("Start Backup", self._run_backup))

    def _tab_restore(self, lay):
        self._section(lay, "Restore Previous Version")
        self._info(lay, "Revert to the previously installed firmware.\n"
                   "⚠  This modifies your device firmware.")
        b = self._btn("Restore Previous", self._run_restore)
        b.setStyleSheet(f"QPushButton {{ color: {DANGER}; background: {BTN}; }}"
                        f"QPushButton:hover {{ background: #991b1b; color: #fff; }}")
        lay.addWidget(b)

    def _tab_upload(self, lay):
        self._section(lay, "Upload Files (PDF only)")
        self._info(lay, "Upload PDF files or folders to the reMarkable device.")
        self.up_path = self._field_row(lay, "Local path:", "/path/to/file.pdf",
                                       browse_file=True,
                                       file_filter="PDF files (*.pdf);;All files (*.*)")
        lay.addWidget(self._btn("Upload", self._run_upload))

    def _tab_extract(self, lay):
        self._section(lay, "Extract Firmware File")
        self._info(lay, "Extract the filesystem from a firmware .swu file.")
        self.ex_ver = self._field_row(lay, "Version / .swu:", "3.15.4.2 or ./file.swu",
                                      browse_file=True)
        self.ex_out = self._field_row(lay, "Output dir:", "./extracted", browse_dir=True)
        lay.addWidget(self._btn("Extract", self._run_extract))

    def _tab_cat_ls(self, lay):
        self._section(lay, "Cat — Read File inside Firmware")
        self.cat_ver  = self._field_row(lay, "Firmware file:", "3.15.4.2_reMarkable2-xxx.signed",
                                        browse_file=True)
        self.cat_path = self._field_row(lay, "Inner path:",   "/etc/version")
        lay.addWidget(self._btn("Cat File", self._run_cat))

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {BORDER};")
        lay.addWidget(sep)

        self._section(lay, "LS — List Files in Firmware")
        self.ls_ver = self._field_row(lay, "Firmware file:", "3.15.4.2_reMarkable2-xxx.signed",
                                      browse_file=True)
        lay.addWidget(self._btn("List Files", self._run_ls))

    # ── widget helpers ────────────────────────────────────────────────────────

    def _section(self, lay, text):
        lbl = QLabel(text)
        lbl.setProperty("class", "section")
        lbl.setStyleSheet(f"color: {ACCENT}; font-size: 14px; font-weight: bold;")
        lay.addWidget(lbl)

    def _info(self, lay, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        lbl.setWordWrap(True)
        lay.addWidget(lbl)

    def _btn(self, text, slot, width=None):
        b = QPushButton(text)
        if width:
            b.setFixedWidth(width)
        b.clicked.connect(slot)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        return b

    def _field_row(self, lay, label, placeholder="",
                   browse_dir=False, browse_file=False, file_filter="All files (*.*)"):
        row = QWidget(); row.setStyleSheet(f"background: {CARD};")
        rl = QHBoxLayout(row); rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(8)
        lbl = QLabel(label); lbl.setFixedWidth(140)
        lbl.setStyleSheet(f"color: {MUTED}; font-size: 12px;")
        rl.addWidget(lbl)
        edit = QLineEdit(); edit.setPlaceholderText(placeholder); edit.setFixedWidth(340)
        rl.addWidget(edit)
        if browse_dir:
            def pick(e=edit):
                d = QFileDialog.getExistingDirectory(self, "Choose directory")
                if d: e.setText(d)
            rl.addWidget(self._btn("Browse…", pick, 80))
        elif browse_file:
            def pick(e=edit, ff=file_filter):
                p, _ = QFileDialog.getOpenFileName(self, "Choose file", filter=ff)
                if p: e.setText(p)
            rl.addWidget(self._btn("Browse…", pick, 80))
        rl.addStretch()
        lay.addWidget(row)
        return edit

    def _hw_row(self, lay):
        row = QWidget(); row.setStyleSheet(f"background: {CARD};")
        rl = QHBoxLayout(row); rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(8)
        lbl = QLabel("Hardware:"); lbl.setFixedWidth(140)
        lbl.setStyleSheet(f"color: {MUTED}; font-size: 12px;")
        rl.addWidget(lbl)
        cb = QComboBox(); cb.setFixedWidth(220)
        cb.addItem("(auto-detect)", "")
        cb.addItem("reMarkable 1",  "rm1")
        cb.addItem("reMarkable 2",  "rm2")
        cb.addItem("Paper Pro",     "rmpp")
        rl.addStretch()
        lay.addWidget(row)
        rl.insertWidget(1, cb)
        return cb

    # ── logging ───────────────────────────────────────────────────────────────

    def _write(self, text: str, colour: str = TEXT):
        cur = self.log.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(colour))
        cur.setCharFormat(fmt)
        cur.insertText(text + "\n")
        self.log.setTextCursor(cur)
        self.log.ensureCursorVisible()

    def _clear_log(self):
        self.log.clear()

    # ── connections ───────────────────────────────────────────────────────────

    def _conn(self):
        return self.addr_edit.text().strip(), self.pass_edit.text().strip()

    def _val(self, edit: QLineEdit) -> str:
        return edit.text().strip()

    def _hw(self, cb: QComboBox) -> str:
        return cb.currentData() or ""

    def _confirm(self, msg: str) -> bool:
        dlg = QMessageBox(self)
        dlg.setWindowTitle("Confirm")
        dlg.setText(msg)
        dlg.setStandardButtons(
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        dlg.setDefaultButton(QMessageBox.StandardButton.Cancel)
        dlg.setStyleSheet(f"background: {SURFACE}; color: {TEXT};")
        return dlg.exec() == QMessageBox.StandardButton.Ok

    def _warn(self, msg: str):
        QMessageBox.warning(self, "Missing input", msg)

    # ── run helper ────────────────────────────────────────────────────────────

    def _run(self, args: list[str]):
        addr, pw = self._conn()
        self._write(f"» codexctl {' '.join(args)}", ACCENT)
        worker = CmdWorker(args, addr, pw)
        thread = QThread()
        worker.moveToThread(thread)
        worker.line.connect(self._write)
        worker.done.connect(lambda rc: self._write(
            f"exit {rc}", SUCCESS if rc == 0 else DANGER))
        worker.done.connect(thread.quit)
        thread.started.connect(worker.run)
        thread.start()
        # keep alive
        self._threads.append((thread, worker))
        thread.finished.connect(lambda t=thread, w=worker: self._threads.remove((t, w))
                                if (t, w) in self._threads else None)

    # ── command runners ───────────────────────────────────────────────────────

    def _run_status(self):   self._run(["status"])

    def _run_list(self):
        args = ["list"]
        hw = self._hw(self.hw_list_cb)
        if hw: args += ["--hardware", hw]
        self._run(args)

    def _run_download(self):
        ver = self._val(self.dl_ver)
        if not ver: self._warn("Version is required."); return
        args = ["download", ver]
        hw = self._hw(self.hw_dl_cb)
        if hw: args += ["--hardware", hw]
        out = self._val(self.dl_out)
        if out: args += ["-o", out]
        self._run(args)

    def _run_install(self):
        ver = self._val(self.inst_ver)
        if not ver: self._warn("Version or .swu path is required."); return
        if not self._confirm(f"Install '{ver}' on the device?"): return
        self._run(["install", ver])

    def _run_backup(self):
        args = ["backup"]
        out = self._val(self.bk_out)
        if out: args += ["-o", out]
        self._run(args)

    def _run_restore(self):
        if not self._confirm("Restore previous firmware?\nThis modifies your device."): return
        self._run(["restore"])

    def _run_upload(self):
        path = self._val(self.up_path)
        if not path: self._warn("File path is required."); return
        self._run(["upload", path])

    def _run_extract(self):
        ver = self._val(self.ex_ver)
        if not ver: self._warn("Version or .swu path is required."); return
        args = ["extract", ver]
        out = self._val(self.ex_out)
        if out: args += ["-o", out]
        self._run(args)

    def _run_cat(self):
        ver  = self._val(self.cat_ver)
        path = self._val(self.cat_path)
        if not ver or not path:
            self._warn("Firmware file and inner path are both required."); return
        self._run(["cat", ver, path])

    def _run_ls(self):
        ver = self._val(self.ls_ver)
        if not ver: self._warn("Firmware file is required."); return
        self._run(["ls", ver])


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

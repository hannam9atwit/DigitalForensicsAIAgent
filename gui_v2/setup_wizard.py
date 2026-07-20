"""
gui_v2/setup_wizard.py

The first-run safety net for local AI.

The Windows installer normally sets everything up: it installs Ollama silently
and lays the model files down (Full installer) or pulls them on first launch
(Lite installer). This wizard only appears when that path didn't finish —
the user skipped Ollama during install, deleted the model, or is running from
source. It installs Ollama and pulls the default model, or lets the user skip
to rule-based mode.

All Ollama probing and process work is delegated to core.ollama_runtime so the
wizard holds no knowledge of paths or ports.
"""

import os
import platform
import subprocess
import tempfile
import urllib.request

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QTextEdit,
    QVBoxLayout,
)

from core import ollama_runtime

# Permanent latest-stable URL — never pins a stale version.
OLLAMA_WINDOWS_URL = "https://ollama.com/download/OllamaSetup.exe"
OLLAMA_LINUX_INSTALL_CMD = "curl -fsSL https://ollama.com/install.sh | sh"


class _SetupWorker(QObject):
    progress = Signal(str)
    done = Signal(bool)

    def run(self):
        try:
            system = platform.system()
            self.progress.emit(f"[*] Detected OS: {system}")

            if ollama_runtime.is_installed():
                self.progress.emit("[+] Ollama already installed.")
            else:
                self.progress.emit("[*] Ollama not found — installing...")
                if system == "Windows":
                    self._install_windows()
                elif system == "Linux":
                    self._install_linux()
                else:
                    self.progress.emit("[!] Unsupported OS for automatic install.")
                    self.done.emit(False)
                    return

            self.progress.emit("[*] Starting the Ollama service...")
            if not ollama_runtime.start_server():
                raise RuntimeError(
                    "Ollama installed but its service did not start. "
                    "Try launching Ollama once from the Start Menu, then reopen this app.")

            model = ollama_runtime.DEFAULT_MODEL
            if ollama_runtime.model_available(model):
                self.progress.emit(f"[+] Model {model} already present.")
            else:
                self.progress.emit(
                    f"[*] Downloading model {model} (~2 GB — this may take a while)...")
                if not ollama_runtime.pull_model(
                        model, on_progress=lambda s: self.progress.emit(f"    {s}")):
                    raise RuntimeError(f"model pull failed for {model}")

            self.progress.emit("[✓] Setup complete — local AI is ready.")
            self.done.emit(True)

        except Exception as error:
            self.progress.emit(f"[!] Setup failed: {error}")
            self.done.emit(False)

    def _install_windows(self):
        installer_path = os.path.join(tempfile.gettempdir(), "OllamaSetup.exe")
        self.progress.emit("[*] Downloading OllamaSetup.exe...")

        def report(count, block_size, total_size):
            if total_size > 0:
                percent = min(count * block_size * 100 // total_size, 100)
                self.progress.emit(f"    Downloading... {percent}%")

        urllib.request.urlretrieve(OLLAMA_WINDOWS_URL, installer_path, report)

        # Ollama's installer is Inno Setup: /VERYSILENT is its silent flag.
        # (/S is the NSIS flag and would open the interactive installer.)
        self.progress.emit("[*] Installing Ollama silently...")
        subprocess.run(
            [installer_path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
            check=True)
        self.progress.emit("[+] Ollama installed.")

    def _install_linux(self):
        self.progress.emit("[*] Running Ollama install script (requires sudo)...")
        result = subprocess.run(
            OLLAMA_LINUX_INSTALL_CMD, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr or "install script failed")
        self.progress.emit("[+] Ollama installed.")


class SetupWizard(QDialog):
    """Modal first-run dialog: install local AI, or skip to rule-based mode."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("First-Time Setup — Local AI")
        self.setMinimumSize(560, 420)
        self.setModal(True)
        self._thread = None
        self._worker = None
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        header = QLabel("<b style='font-size:16pt'>Local AI Setup</b>")
        layout.addWidget(header)

        description = QLabel(
            "This app uses a local language model (via Ollama) to write the case "
            "overview, plain-language explanations, and the investigation report. "
            "Everything runs on this machine — evidence never leaves it.\n\n"
            "Setup will:\n"
            "  • Install Ollama (if not already installed)\n"
            f"  • Download the {ollama_runtime.DEFAULT_MODEL} model (~2 GB)\n\n"
            "You can skip this and use the built-in rule-based text instead; "
            "local AI can be enabled later from Settings.")
        description.setWordWrap(True)
        layout.addWidget(description)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(170)
        self.log.setStyleSheet("font-family: monospace; font-size: 12px;")
        layout.addWidget(self.log)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        buttons = QHBoxLayout()
        self.install_button = QPushButton("Install local AI (Ollama + model)")
        self.install_button.setStyleSheet("padding: 8px; font-weight: bold;")
        self.install_button.clicked.connect(self._start)
        buttons.addWidget(self.install_button)

        self.skip_button = QPushButton("Skip — use rule-based mode")
        self.skip_button.clicked.connect(self.reject)
        buttons.addWidget(self.skip_button)
        layout.addLayout(buttons)

        self.close_button = QPushButton("Continue to the app")
        self.close_button.setVisible(False)
        self.close_button.clicked.connect(self.accept)
        layout.addWidget(self.close_button)

    def _start(self):
        self.install_button.setEnabled(False)
        self.skip_button.setEnabled(False)
        self.progress_bar.setVisible(True)

        self._thread = QThread()
        self._worker = _SetupWorker()
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._append_log)
        self._worker.done.connect(self._finished)
        self._worker.done.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)

        self._thread.start()

    def _append_log(self, message: str):
        self.log.append(message)
        scrollbar = self.log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _finished(self, success: bool):
        self.progress_bar.setVisible(False)
        if success:
            self.install_button.setVisible(False)
            self.skip_button.setVisible(False)
            self.close_button.setVisible(True)
        else:
            self.install_button.setEnabled(True)
            self.skip_button.setEnabled(True)
            self.install_button.setText("Retry setup")

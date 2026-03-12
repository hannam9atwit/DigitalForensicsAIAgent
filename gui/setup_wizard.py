"""
setup_wizard.py

First-run wizard shown when Ollama is not detected.
Handles downloading and installing Ollama, then pulling the model.
Works on both Windows and Linux.
"""

import sys
import os
import platform
import subprocess
import threading
import urllib.request
import urllib.error

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QTextEdit, QDialogButtonBox, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QObject, QThread
from PySide6.QtGui import QFont


OLLAMA_MODEL   = "llama3.1:8b"
OLLAMA_VERSION = "0.3.14"

OLLAMA_WINDOWS_URL = (
    f"https://github.com/ollama/ollama/releases/download/"
    f"v{OLLAMA_VERSION}/OllamaSetup.exe"
)
OLLAMA_LINUX_INSTALL_CMD = "curl -fsSL https://ollama.com/install.sh | sh"


# ---------------------------------------------------------------------------
# Worker — runs in a QThread so the UI stays responsive
# ---------------------------------------------------------------------------

class SetupWorker(QObject):
    progress = Signal(str)   # log message
    done     = Signal(bool)  # success/failure

    def run(self):
        try:
            system = platform.system()
            self.progress.emit(f"[*] Detected OS: {system}")

            if not self._ollama_installed():
                self.progress.emit("[*] Ollama not found — installing...")
                if system == "Windows":
                    self._install_windows()
                elif system == "Linux":
                    self._install_linux()
                else:
                    self.progress.emit("[!] Unsupported OS for automatic install.")
                    self.done.emit(False)
                    return
            else:
                self.progress.emit("[+] Ollama already installed.")

            self.progress.emit(f"[*] Pulling model: {OLLAMA_MODEL}  (this may take several minutes)")
            self._pull_model()

            self.progress.emit("[✓] Setup complete! The app will now use local AI.")
            self.done.emit(True)

        except Exception as e:
            self.progress.emit(f"[!] Setup failed: {e}")
            self.done.emit(False)

    # ── Install ──────────────────────────────────────────────────────────────

    def _ollama_installed(self) -> bool:
        import shutil
        if shutil.which("ollama"):
            return True
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        candidate = os.path.join(local_app_data, "Programs", "Ollama", "ollama.exe")
        return os.path.exists(candidate)

    def _install_windows(self):
        import tempfile
        self.progress.emit("[*] Downloading OllamaSetup.exe...")
        tmp = os.path.join(tempfile.gettempdir(), "OllamaSetup.exe")

        def reporthook(count, block_size, total_size):
            if total_size > 0:
                pct = int(count * block_size * 100 / total_size)
                self.progress.emit(f"    Downloading... {min(pct, 100)}%")

        urllib.request.urlretrieve(OLLAMA_WINDOWS_URL, tmp, reporthook)
        self.progress.emit("[*] Running installer (follow any UAC prompts)...")
        subprocess.run([tmp, "/S"], check=True)   # /S = silent install
        self.progress.emit("[+] Ollama installed.")

    def _install_linux(self):
        self.progress.emit("[*] Running Ollama install script (requires sudo)...")
        result = subprocess.run(
            OLLAMA_LINUX_INSTALL_CMD,
            shell=True,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr or "Install script failed")
        self.progress.emit("[+] Ollama installed.")

    # ── Model pull ───────────────────────────────────────────────────────────

    def _find_ollama(self) -> str:
        """
        Returns the full path to the ollama executable.
        Checks PATH first, then the default Windows install location.
        """
        import shutil
        path = shutil.which("ollama")
        if path:
            return path

        # Default Ollama install location on Windows
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        candidate = os.path.join(local_app_data, "Programs", "Ollama", "ollama.exe")
        if os.path.exists(candidate):
            return candidate

        raise RuntimeError(
            "ollama.exe not found. Please restart the app after installation, "
            "or install Ollama manually from https://ollama.com"
        )

    def _pull_model(self):
        ollama_exe = self._find_ollama()
        self.progress.emit(f"[*] Found Ollama at: {ollama_exe}")

        import re
        ansi_escape = re.compile(r'(\x9B|\x1B\[)[0-?]*[ -/]*[@-~]|\x1B[^[\x1B]*|\[[?][0-9]*[lh]')

        proc = subprocess.Popen(
            [ollama_exe, "pull", OLLAMA_MODEL],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",  # never crash on weird characters
            env={**os.environ, "NO_COLOR": "1", "TERM": "dumb"}  # tell Ollama to skip fancy output
        )

        last_line = ""
        for line in proc.stdout:
            # Strip ANSI escape sequences
            clean = ansi_escape.sub("", line).strip()
            if not clean:
                continue
            # Ollama repeats the same status line many times — only emit when it changes
            if clean != last_line:
                self.progress.emit(f"    {clean}")
                last_line = clean

        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"ollama pull exited with code {proc.returncode}")


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class SetupWizard(QDialog):
    """
    Modal dialog shown on first run when Ollama is not available.
    The user can trigger setup or skip (app falls back to deterministic output).
    """

    setup_complete = Signal()   # emitted when Ollama + model are ready

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("First-Time Setup — Local AI")
        self.setMinimumSize(560, 400)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Header
        header = QLabel("Local AI Setup")
        font = QFont()
        font.setPointSize(16)
        font.setBold(True)
        header.setFont(font)
        layout.addWidget(header)

        # Description
        desc = QLabel(
            "Forensic AI Agent uses a local language model (Llama 3.2 3B via Ollama) "
            "to generate investigative narratives — no internet connection or API key required "
            "after setup.\n\n"
            f"Setup will:\n"
            f"  1. Install Ollama (if not already installed)\n"
            f"  2. Download the {OLLAMA_MODEL} model (~2 GB)\n\n"
            "This only runs once. You can skip and use the built-in rule-based narrative instead."
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Log output
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(160)
        self.log.setStyleSheet("font-family: monospace; font-size: 12px;")
        layout.addWidget(self.log)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)   # indeterminate
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Buttons
        btn_row = QHBoxLayout()
        self.install_btn = QPushButton("Install Ollama + Download Model")
        self.install_btn.setStyleSheet("padding: 8px; font-weight: bold;")
        self.install_btn.clicked.connect(self.start_setup)
        btn_row.addWidget(self.install_btn)

        self.skip_btn = QPushButton("Skip (use rule-based narrative)")
        self.skip_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.skip_btn)

        layout.addLayout(btn_row)

        self.close_btn = QPushButton("Close")
        self.close_btn.setVisible(False)
        self.close_btn.clicked.connect(self.accept)
        layout.addWidget(self.close_btn)

    def start_setup(self):
        self.install_btn.setEnabled(False)
        self.skip_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self._append_log("[*] Starting setup...")

        self.thread = QThread()
        self.worker = SetupWorker()
        self.worker.moveToThread(self.thread)

        self.worker.progress.connect(self._append_log)
        self.worker.done.connect(self._setup_done)
        self.thread.started.connect(self.worker.run)
        self.thread.start()

    def _append_log(self, msg: str):
        self.log.append(msg)
        self.log.verticalScrollBar().setValue(
            self.log.verticalScrollBar().maximum()
        )

    def _setup_done(self, success: bool):
        self.thread.quit()
        self.thread.wait()
        self.progress_bar.setVisible(False)

        if success:
            self.close_btn.setVisible(True)
            self.setup_complete.emit()
        else:
            self.skip_btn.setEnabled(True)
            self._append_log("[~] You can close this and use the rule-based narrative.")
            self.skip_btn.setText("Close (use rule-based narrative)")
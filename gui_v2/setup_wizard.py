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
    QDialog, QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QTextEdit,
    QVBoxLayout,
)

from core import ollama_runtime
from . import theme

# Permanent latest-stable URL — never pins a stale version.
OLLAMA_WINDOWS_URL = "https://ollama.com/download/OllamaSetup.exe"
OLLAMA_LINUX_INSTALL_CMD = "curl -fsSL https://ollama.com/install.sh | sh"


class _SetupWorker(QObject):
    progress = Signal(str)   # detailed log line (shown behind "show details")
    phase = Signal(str)      # clean step status for the themed UI
    pct = Signal(int)        # model-download percentage (0-100), -1 = indeterminate
    done = Signal(bool)

    def run(self):
        try:
            system = platform.system()
            self.progress.emit(f"[*] Detected OS: {system}")

            if ollama_runtime.is_installed():
                self.phase.emit("Ollama is already installed.")
                self.progress.emit("[+] Ollama already installed.")
            else:
                self.phase.emit("Installing Ollama…")
                self.pct.emit(-1)
                self.progress.emit("[*] Ollama not found — installing...")
                if system == "Windows":
                    self._install_windows()
                elif system == "Linux":
                    self._install_linux()
                else:
                    self.phase.emit("This OS can't install Ollama automatically.")
                    self.progress.emit("[!] Unsupported OS for automatic install.")
                    self.done.emit(False)
                    return

            self.phase.emit("Starting the local AI service…")
            self.pct.emit(-1)
            self.progress.emit("[*] Starting the Ollama service...")
            if not ollama_runtime.start_server():
                raise RuntimeError(
                    "Ollama installed but its service did not start. "
                    "Try launching Ollama once from the Start Menu, then reopen this app.")

            model = ollama_runtime.DEFAULT_MODEL
            if ollama_runtime.model_available(model):
                self.phase.emit(f"Model {model} is already downloaded.")
                self.progress.emit(f"[+] Model {model} already present.")
            else:
                self.phase.emit(f"Downloading the model ({model}, ~2 GB)…")
                self.progress.emit(
                    f"[*] Downloading model {model} (~2 GB — this may take a while)...")
                if not ollama_runtime.pull_model(
                        model, on_progress=self._on_pull_progress):
                    raise RuntimeError(f"model pull failed for {model}")

            self.phase.emit("Local AI is ready.")
            self.progress.emit("[✓] Setup complete — local AI is ready.")
            self.done.emit(True)

        except Exception as error:
            self.phase.emit(f"Setup couldn't finish: {error}")
            self.progress.emit(f"[!] Setup failed: {error}")
            self.done.emit(False)

    def _on_pull_progress(self, status: str):
        self.progress.emit(f"    {status}")
        # pull_model reports "<status> — NN%" when a percentage is known.
        if "%" in status:
            try:
                percent = int(status.rsplit("—", 1)[-1].strip().rstrip("%"))
                self.pct.emit(percent)
            except (ValueError, IndexError):
                pass


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
    """First-run local-AI setup, presented as a themed multi-step flow.

    The install/start/pull logic lives in _SetupWorker (unchanged). This class
    is presentation only: themed steps, one clean status line, a real
    percentage bar for the model download and an indeterminate bar for steps
    whose duration is unknown, with the detailed log tucked behind a
    "show details" expander.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._P = theme.GUIDED
        self.setWindowTitle("Local AI Setup — AIRforensics")
        self.setMinimumSize(560, 460)
        self.setModal(True)
        self.setStyleSheet(f"QDialog {{ background: {self._P['bg']}; }}")
        self._build()

    def _build(self):
        from . import widgets as w
        P = self._P
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 22)
        layout.setSpacing(14)

        layout.addWidget(w.label("Local AI Setup", size=20,
                                 weight=theme.W_SEMIBOLD, color=P["text"]))
        layout.addWidget(w.body(
            "AIRforensics uses a language model running on this machine to write "
            "case overviews, plain-language explanations, and the report. "
            "Everything stays local — evidence never leaves this computer.",
            size=12.5, color=P["text2"], lh=1.5))

        steps = QFrame()
        steps.setObjectName("cardAlt")
        sv = QVBoxLayout(steps)
        sv.setContentsMargins(16, 14, 16, 14)
        sv.setSpacing(6)
        for text in ("1.  Install Ollama, the local AI runtime",
                     f"2.  Download the model ({ollama_runtime.DEFAULT_MODEL}, ~2 GB)",
                     "3.  Start it and hand off to the app"):
            sv.addWidget(w.body(text, size=12, color=P["text2"], lh=1.4))
        layout.addWidget(steps)

        self._phase = w.body("Ready to set up local AI.", size=13,
                             weight=theme.W_MEDIUM, color=P["text"])
        layout.addWidget(self._phase)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{ background: {P['panelAlt']}; border: none;
                            border-radius: 3px; }}
            QProgressBar::chunk {{ background: {P['accent']};
                                   border-radius: 3px; }}
        """)
        layout.addWidget(self.progress_bar)

        # Detailed log, collapsed by default.
        self._details_button = QPushButton("Show details")
        self._details_button.setFlat(True)
        self._details_button.setStyleSheet(
            f"color: {P['text3']}; text-align: left; border: none;")
        self._details_button.clicked.connect(self._toggle_details)
        layout.addWidget(self._details_button)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(120)
        self.log.setVisible(False)
        self.log.setStyleSheet(
            f"font-family: monospace; font-size: 11px; color: {P['text3']}; "
            f"background: {P['panelAlt']}; border: 1px solid {P['line']};")
        layout.addWidget(self.log)

        layout.addStretch(1)

        buttons = QHBoxLayout()
        self.install_button = QPushButton("Install local AI")
        self.install_button.setObjectName("primary")
        self.install_button.clicked.connect(self._start)
        buttons.addWidget(self.install_button)

        self.skip_button = QPushButton("Skip — use rule-based mode")
        self.skip_button.clicked.connect(self.reject)
        buttons.addWidget(self.skip_button)
        layout.addLayout(buttons)

        self.close_button = QPushButton("Continue to the app")
        self.close_button.setObjectName("primary")
        self.close_button.setVisible(False)
        self.close_button.clicked.connect(self.accept)
        layout.addWidget(self.close_button)

    def _toggle_details(self):
        showing = not self.log.isVisible()
        self.log.setVisible(showing)
        self._details_button.setText("Hide details" if showing else "Show details")

    def _start(self):
        self.install_button.setEnabled(False)
        self.skip_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # indeterminate until a % arrives

        # Tracked in thread_registry so it survives even if the dialog is closed
        # mid-install, rather than being freed with the dialog while running.
        from . import thread_registry
        thread = QThread()
        worker = _SetupWorker()
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.progress.connect(self._append_log)
        worker.phase.connect(self._phase.setText)
        worker.pct.connect(self._set_pct)
        worker.done.connect(self._finished)
        worker.done.connect(worker.deleteLater)
        worker.done.connect(thread.quit)
        thread_registry.track(thread, worker)
        thread.start()

    def _set_pct(self, percent: int):
        if percent < 0:
            self.progress_bar.setRange(0, 0)  # indeterminate
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(percent)

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

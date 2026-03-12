"""
gui_main.py — application entry point.

On startup:
  1. Shows a splash screen
  2. Checks if Ollama is running with the required model
  3. If not, offers the setup wizard (user can skip)
  4. Launches the main window
"""

import sys
import shutil
import urllib.request
import json

from PySide6.QtWidgets import QApplication, QSplashScreen
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt, QTimer

from gui.main_window import MainWindow
from gui.setup_wizard import SetupWizard

OLLAMA_MODEL = "llama3.2:3b"


def ollama_ready() -> bool:
    """Return True if Ollama is running and the model is available."""
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            body = json.loads(resp.read().decode())
        models = [m.get("name", "") for m in body.get("models", [])]
        return any(OLLAMA_MODEL.split(":")[0] in m for m in models)
    except Exception:
        return False


def start_gui():
    app = QApplication(sys.argv)

    # ── Splash ────────────────────────────────────────────────
    splash_pix = QPixmap("assets/splash.png")
    if splash_pix.isNull():
        # Fallback: plain coloured splash if image is missing
        from PySide6.QtGui import QColor
        splash_pix = QPixmap(480, 200)
        splash_pix.fill(QColor("#1e1e2e"))

    splash = QSplashScreen(splash_pix)
    splash.showMessage(
        "Loading Forensic AI Agent…",
        Qt.AlignCenter | Qt.AlignBottom,
        Qt.white
    )
    splash.show()
    app.processEvents()

    # ── Ollama check → wizard or main window ─────────────────
    def after_splash():
        splash.hide()

        if not ollama_ready():
            wizard = SetupWizard()
            # Whether the user installs or skips, we open the main window after
            wizard.exec()   # blocks until closed

        window = MainWindow()
        window.show()
        splash.finish(window)

    QTimer.singleShot(900, after_splash)
    sys.exit(app.exec())


if __name__ == "__main__":
    start_gui()
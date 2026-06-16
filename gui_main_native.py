"""
gui_main_native.py — entry point for the NATIVE PySide6 console (no server).

Run from your project root:

    python gui_main_native.py

This replaces the web GUI + local server with a pure Qt application. It loads
the bundled demo case on launch so the interface is populated; use
File ▸ Open Artifact to run the real pipeline on your own evidence.
"""

import sys
from PySide6.QtWidgets import QApplication

from gui_v2.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Forensic AI Agent")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

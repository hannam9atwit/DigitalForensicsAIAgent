"""
gui_main_native.py — entry point for the native PySide6 console.

    python gui_main_native.py

Launches into the empty state. Create a case via File ▸ New Case to run the real
pipeline on your own evidence, or Case ▸ Open Demo Case to explore the interface
with the bundled fixture.
"""

import sys

from PySide6.QtWidgets import QApplication


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Forensic AI Agent")

    # Fonts must be registered before any widget is constructed — theme.SANS and
    # theme.MONO are read when widgets build their QFonts, and a widget created
    # first would keep the fallback face.
    from gui_v2 import theme
    sans, mono = theme.load_fonts()
    if sans != "Lexend" or mono != "IBM Plex Mono":
        print(f"[~] bundled fonts unavailable — using {sans} / {mono}. "
              f"Expected TTFs in assets/fonts/.")

    from gui_v2.main_window import MainWindow
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

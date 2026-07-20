"""
gui_main_native.py — the application entry point.

    python gui_main_native.py

Startup sequence:
  1. Register bundled fonts (must precede any widget construction).
  2. Silently bring local AI up: if Ollama is installed but its server is
     stopped, start it. No dialogs, no blocking downloads.
  3. If local AI isn't ready at all (Ollama missing, or model absent), offer
     the one-time setup wizard. Skipping it is fine — the app falls back to
     rule-based text and the wizard can be re-run from Settings later.
  4. Launch into the empty state. File ▸ New Case runs the real pipeline;
     Case ▸ Open Demo Case explores the interface on the bundled fixture.
"""

import sys

from PySide6.QtWidgets import QApplication


def _skip_marker_path():
    import os
    from gui_v2.case_store import app_data_dir
    return os.path.join(app_data_dir(), ".ai_setup_skipped")


def _setup_was_skipped() -> bool:
    import os
    return os.path.exists(_skip_marker_path())


def _remember_setup_skipped():
    """The user chose rule-based mode; don't re-ask on every launch.
    Settings offers a path back to the wizard."""
    with open(_skip_marker_path(), "w", encoding="utf-8") as marker:
        marker.write("re-run local AI setup from Settings\n")


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Forensic AI Agent")

    from gui_v2 import theme
    sans, mono = theme.load_fonts()
    if sans != "Lexend" or mono != "IBM Plex Mono":
        print(f"[~] bundled fonts unavailable — using {sans} / {mono}. "
              f"Expected TTFs in assets/fonts/.")

    from core import ollama_runtime
    health = ollama_runtime.ensure_ready()
    if not health["model_ready"] and not _setup_was_skipped():
        from gui_v2.setup_wizard import SetupWizard
        from PySide6.QtWidgets import QDialog
        if SetupWizard().exec() != QDialog.Accepted:
            _remember_setup_skipped()

    from gui_v2.main_window import MainWindow
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

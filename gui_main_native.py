"""
gui_main_native.py — the application entry point.

    python gui_main_native.py

Startup sequence:
  1. Register fonts and theme on the UI thread (cheap), then show a themed
     splash immediately.
  2. Run the slow launch work off the UI thread (checking Ollama, starting its
     server if installed but stopped, warming an already-present model), with
     each phase reported to the splash so the window never looks frozen.
  3. When startup finishes, close the splash and show the main window. If local
     AI isn't ready AND the user hasn't chosen to skip the wizard, offer the
     one-time setup wizard — the only place the 2 GB model download is proposed.

The skip marker means only "don't NAG me with the full wizard", never "stop
checking Ollama". Detection runs on every launch regardless of the marker, so a
user who skipped once still gets automatic detection when Ollama later becomes
healthy.
"""

import os
import sys

from PySide6.QtWidgets import QApplication


def _skip_marker_path():
    from gui_v2.case_store import app_data_dir
    return os.path.join(app_data_dir(), ".ai_setup_skipped")


def _setup_was_skipped() -> bool:
    return os.path.exists(_skip_marker_path())


def _remember_setup_skipped():
    """The user chose rule-based mode; don't re-open the wizard every launch.
    This suppresses only the wizard dialog — detection still runs each time."""
    with open(_skip_marker_path(), "w", encoding="utf-8") as marker:
        marker.write("Suppresses the setup wizard dialog only. Local AI "
                     "detection still runs on every launch.\n")


def _clear_skip_marker():
    """AI became healthy on its own; the skip marker is stale, so remove it."""
    try:
        os.remove(_skip_marker_path())
    except OSError:
        pass


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("AIRforensics")

    from gui_v2 import theme
    from PySide6.QtGui import QIcon
    app.setWindowIcon(QIcon(theme.assets_path("app.ico")))
    sans, mono = theme.load_fonts()
    if sans != "Lexend" or mono != "IBM Plex Mono":
        print(f"[~] bundled fonts unavailable — using {sans} / {mono}. "
              f"Expected TTFs in assets/fonts/.")

    from gui_v2.startup import SplashScreen, StartupWorker
    splash = SplashScreen()
    splash.show()
    app.processEvents()

    worker = StartupWorker()
    worker.phase.connect(splash.set_status)
    worker.finished.connect(
        lambda health: _finish_launch(splash, health))
    # Keep a reference so the worker isn't garbage-collected mid-run.
    app._startup_worker = worker
    worker.start()

    sys.exit(app.exec())


def _finish_launch(splash, health):
    """Close the splash, decide on the wizard, and show the main window."""
    if health.get("model_ready") and _setup_was_skipped():
        _clear_skip_marker()

    from gui_v2.main_window import MainWindow
    window = MainWindow()
    # Hold a reference on the app so the window survives past this callback.
    QApplication.instance()._main_window = window

    show_wizard = not health.get("model_ready") and not _setup_was_skipped()
    splash.close()
    window.show()

    if show_wizard:
        from gui_v2.setup_wizard import SetupWizard
        from PySide6.QtWidgets import QDialog
        if SetupWizard(window).exec() != QDialog.Accepted:
            _remember_setup_skipped()


if __name__ == "__main__":
    main()

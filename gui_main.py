import sys
from PySide6.QtWidgets import QApplication, QSplashScreen
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt, QTimer

from gui.main_window import MainWindow


def start_gui():
    app = QApplication(sys.argv)

    # Load splash image
    splash_pix = QPixmap("assets/splash.png")
    splash = QSplashScreen(splash_pix)
    splash.showMessage(
        "Loading Forensic AI Agent...",
        Qt.AlignCenter | Qt.AlignBottom,
        Qt.white
    )
    splash.show()

    # Delay to show splash
    QTimer.singleShot(800, lambda: launch_main_window(app, splash))

    sys.exit(app.exec())


def launch_main_window(app, splash):
    window = MainWindow()
    window.show()
    splash.finish(window)


if __name__ == "__main__":
    start_gui()

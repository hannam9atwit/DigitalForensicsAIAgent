"""
gui_v2/startup.py

A themed splash screen that runs the slow parts of launch OFF the UI thread and
reports each phase back to a responsive splash, so the window never freezes and
the user always sees what is loading.

Why off-thread and not a freeze-detector: a blocked UI thread cannot draw a
splash or a popup, so detecting a freeze from that same thread and trying to
show something can't work. The fix is to prevent the freeze — do the slow work
(checking Ollama, starting the server, warming the model) on a daemon thread
and push status back with a queued signal, exactly the pattern ai_worker.py
uses.

Phases, each its own status line:
    Loading interface   → fonts, theme (done on the UI thread before the splash
                          hands off; cheap)
    Checking local AI   → is_installed / server_running
    Starting service    → start_server, if installed but stopped
    Warming the model   → warm_model, if the model is present
    Ready               → close splash, show main window

Consent is preserved: this auto-STARTS what is installed and WARMS a model
that is already present, but never downloads the 2 GB model — that stays in the
setup wizard.
"""

import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QLabel, QProgressBar, QVBoxLayout, QWidget,
)

from . import theme

P = theme.GUIDED


class StartupWorker(QObject):
    """Runs launch phases on a daemon thread, reporting status to the splash."""

    phase = Signal(str)       # human-readable status line
    finished = Signal(dict)   # final readiness dict

    def start(self):
        thread = threading.Thread(target=self._run, daemon=True, name="startup")
        thread.start()

    def _run(self):
        from core import ollama_runtime
        model = ollama_runtime.DEFAULT_MODEL

        self.phase.emit("Checking local AI…")
        installed = ollama_runtime.is_installed()
        running = ollama_runtime.server_running()

        if installed and not running:
            self.phase.emit("Starting local AI service…")
            running = ollama_runtime.start_server()

        if running and ollama_runtime.model_available(model):
            self.phase.emit("Warming the model…")
            ollama_runtime.warm_model(model)

        self.phase.emit("Ready")
        self.finished.emit(ollama_runtime.readiness(model))


class SplashScreen(QWidget):
    """A themed, frameless splash matching the app's visual language."""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setFixedSize(440, 260)
        self._build()

    def _build(self):
        self.setStyleSheet(f"background: {P['panel']};")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setStyleSheet(
            f"background: {P['panel']}; border: 1px solid {P['line']};")
        v = QVBoxLayout(card)
        v.setContentsMargins(36, 34, 36, 30)
        v.setSpacing(0)

        title = QLabel("AIRforensics")
        title.setStyleSheet(
            f"color: {P['text']}; font-size: 26px; font-weight: 700;")
        v.addWidget(title)

        subtitle = QLabel("Digital forensics investigation console")
        subtitle.setStyleSheet(f"color: {P['text3']}; font-size: 12px;")
        v.addWidget(subtitle)

        v.addStretch(1)

        self._status = QLabel("Loading interface…")
        self._status.setStyleSheet(f"color: {P['text2']}; font-size: 12.5px;")
        v.addWidget(self._status)
        v.addSpacing(10)

        self._bar = QProgressBar()
        self._bar.setRange(0, 0)  # indeterminate: honest "working"
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(4)
        self._bar.setStyleSheet(f"""
            QProgressBar {{ background: {P['panelAlt']}; border: none;
                            border-radius: 2px; }}
            QProgressBar::chunk {{ background: {P['accent']};
                                   border-radius: 2px; }}
        """)
        v.addWidget(self._bar)

        outer.addWidget(card)

    def set_status(self, text: str):
        self._status.setText(text)

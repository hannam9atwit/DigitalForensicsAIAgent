"""
gui_v2/screens/settings.py

Settings — examiner identity and the AI engine.

The API key field is the one place the app touches a network, so it says so
plainly: blank means fully offline, the key is held in memory only, and evidence
files never leave the machine regardless. Understating that would undercut the
product's central claim.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QLineEdit, QPushButton, QVBoxLayout, QWidget

from core import ollama_runtime

from .. import theme, widgets as w
from ..content import RAIL_STATIC
from ..rail import RailPayload
from .base import Screen

P = theme.GUIDED


class SettingsScreen(Screen):
    id = "settings"

    changed = Signal(dict)

    def __init__(self, case, settings, parent=None):
        super().__init__(case, parent)
        self.settings = settings
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        host, lay = w.page(max_width=560)
        root.addWidget(w.scroll_area(host))

        lay.addWidget(w.screen_title("Settings"))

        ident = w.Card(pad=17, spacing=10)
        ident.head("EXAMINER IDENTITY")
        self._name = self._field(ident, "Name", self.settings.get("examiner", ""))
        self._id = self._field(ident, "Examiner ID",
                               self.settings.get("examiner_id", ""), mono=True)
        self._agency = self._field(ident, "Agency", self.settings.get("agency", ""))
        lay.addWidget(ident)

        ai = w.Card(pad=17, spacing=0)
        ai.head("AI ENGINE", right=self._status_label())
        ai.add(w.spacer(h=6))

        ai.add(w.label("Engine", size=12, color=P["text2"]))
        self._provider = QComboBox()
        self._provider.addItem("Ollama — local model (default)", "ollama")
        self._provider.addItem("Anthropic Claude — cloud, needs API key", "anthropic")
        self._provider.addItem("OpenAI ChatGPT — cloud, needs API key", "openai")
        self._provider.addItem("Google Gemini — cloud, needs API key", "gemini")
        self._provider.addItem("Rule-based only — no AI", "none")
        current = self.settings.get("ai_provider", "ollama")
        self._provider.setCurrentIndex(
            max(0, self._provider.findData(current)))
        self._provider.currentIndexChanged.connect(self._emit)
        ai.add(self._provider)
        ai.add(w.spacer(h=8))

        ai.add(w.label("Ollama model", size=12, color=P["text2"]))
        self._model = QLineEdit(self.settings.get("ollama_model", "llama3.2:3b"))
        self._model.setObjectName("mono")
        self._model.setPlaceholderText("llama3.2:3b")
        self._model.textChanged.connect(self._emit)
        ai.add(self._model)
        ai.add(w.spacer(h=4))
        ai.add(w.body(
            "Any model available to your local Ollama install works here — "
            "pull one with <b>ollama pull &lt;name&gt;</b> first.",
            size=11, color=P["text3"], lh=1.5, rich=True))

        setup_button = QPushButton("Run local AI setup…")
        setup_button.clicked.connect(self._open_setup_wizard)
        ai.add(w.spacer(h=6))
        ai.add(setup_button)

        # One-click re-detect: starts the server if it's asleep and re-probes
        # models, then updates the status line. This is the honest fix for
        # "it didn't detect Ollama" — no reinstall needed.
        recheck = QPushButton("Re-check / reconnect")
        recheck.clicked.connect(self._recheck_ai)
        self._recheck_button = recheck
        ai.add(w.spacer(h=4))
        ai.add(recheck)

        self._ai_detail = w.body("Checking local AI…", size=11,
                                 color=P["text3"], lh=1.5)
        ai.add(w.spacer(h=4))
        ai.add(self._ai_detail)
        self._refresh_ai_detail_async()

        ai.add(w.spacer(h=4))
        ai.add(w.hline())
        ai.add(w.kv_row("Fallback order",
                        "Chosen engine → Rule-based (automatic)"))
        ai.add(w.spacer(h=10))
        ai.add(w.label("Cloud API key (used only for the cloud engine selected above)",
                       size=12, color=P["text2"]))
        self._key = QLineEdit(self.settings.get("cloud_api_key", ""))
        self._key.setEchoMode(QLineEdit.Password)
        self._key.setPlaceholderText("API key…  (blank = fully offline)")
        self._key.textChanged.connect(self._emit)
        ai.add(self._key)
        ai.add(w.body(
            "Held in memory only — never written to disk. With a key set, only your "
            "questions and findings summaries are sent; <b>evidence files never leave "
            "this machine.</b>",
            size=11, color=P["text3"], lh=1.5, rich=True))
        lay.addWidget(ai)
        lay.addStretch(1)

    def _field(self, card, label, value, mono=False):
        card.add(w.label(label, size=12, color=P["text2"]))
        e = QLineEdit(value)
        if mono:
            e.setObjectName("mono")
        e.textChanged.connect(self._emit)
        card.add(e)
        return e

    def _refresh_ai_detail_async(self):
        """Probe readiness off-thread and update both the status chip and the
        detail line, so building the Settings screen never blocks on Ollama
        network calls. (Settings is constructed eagerly on every case open, so
        a synchronous probe here would stall every case-entry.)"""
        from PySide6.QtCore import QObject, QThread, Signal
        model = self.settings.get("ollama_model", "llama3.2:3b")

        class _DetailProbe(QObject):
            ready = Signal(object)   # the readiness() health dict

            def run(self):
                self.ready.emit(ollama_runtime.readiness(model))

        self._detail_thread = QThread()
        self._detail_probe = _DetailProbe()
        self._detail_probe.moveToThread(self._detail_thread)
        self._detail_thread.started.connect(self._detail_probe.run)
        self._detail_probe.ready.connect(self._apply_health)
        self._detail_probe.ready.connect(self._detail_thread.quit)
        self._detail_thread.finished.connect(self._detail_thread.deleteLater)
        self._detail_thread.start()

    def _apply_health(self, health):
        """Update the status chip and the detail line from one probe result.
        Runs on the UI thread (queued signal)."""
        self._ai_detail.setText(self._detail_for_health(health))
        text, color = self._status_text_color(health)
        self._status_lbl.setText(text)
        self._status_lbl.setStyleSheet(f"color: {color}; background: transparent;")

    def _detail_for_health(self, health):
        if health["model_loaded"]:
            return "Local AI is running and the model is loaded and ready."
        if health["model_ready"]:
            return ("Local AI is running; the model is installed and will load "
                    "on first use.")
        if health["running"]:
            return ("Ollama is running but the model isn't downloaded yet. Use "
                    "Run local AI setup to download it.")
        if health["installed"]:
            return ("Ollama is installed but its server isn't running. Use "
                    "Re-check to start it.")
        return ("Ollama isn't installed. Use Run local AI setup to install it, "
                "or keep using rule-based mode.")

    def _recheck_ai(self):
        """Start the server if needed and re-probe, off the UI thread.

        Uses a QObject + signal to deliver the result back to the UI thread.
        A cross-thread QTimer.singleShot does NOT reliably fire (a QTimer
        belongs to the thread that creates it), which previously left the
        status stuck on "Re-checking…" forever.
        """
        from PySide6.QtCore import QObject, QThread, Signal

        self._ai_detail.setText("Re-checking local AI…")
        self._recheck_btn_disable()

        model = self.settings.get("ollama_model", "llama3.2:3b")

        class _Probe(QObject):
            done = Signal(object)   # the readiness() health dict, or None on timeout

            def run(self):
                # A hard wall-clock cap: whatever any single network call does,
                # re-check reports back within this window instead of leaving
                # the status stuck on "Checking…". The probe runs in its own
                # thread with a watchdog that reports a timeout result.
                import threading

                result = {"health": None, "finished": False}

                def probe():
                    try:
                        result["health"] = ollama_runtime.ensure_ready(model)
                    except Exception:
                        pass
                    result["finished"] = True

                worker = threading.Thread(target=probe, daemon=True)
                worker.start()
                worker.join(timeout=45)
                self.done.emit(result["health"] if result["finished"] else None)

        self._recheck_thread = QThread()
        self._recheck_probe = _Probe()
        self._recheck_probe.moveToThread(self._recheck_thread)
        self._recheck_thread.started.connect(self._recheck_probe.run)
        self._recheck_probe.done.connect(self._recheck_finished)
        self._recheck_probe.done.connect(self._recheck_thread.quit)
        self._recheck_thread.finished.connect(self._recheck_thread.deleteLater)
        self._recheck_thread.start()

    def _recheck_btn_disable(self):
        if hasattr(self, "_recheck_button"):
            self._recheck_button.setEnabled(False)
            self._recheck_button.setText("Checking…")

    def _recheck_finished(self, health):
        # Back on the UI thread (queued signal): apply the health the probe
        # already gathered, rather than re-probing synchronously here.
        if health is None:
            self._ai_detail.setText(
                "Re-check timed out. Ollama may be busy or unresponsive. Make "
                "sure Ollama is running (open it from the Start Menu), then try "
                "again.")
        else:
            self._apply_health(health)
        if hasattr(self, "_recheck_button"):
            self._recheck_button.setEnabled(True)
            self._recheck_button.setText("Re-check / reconnect")

    def _status_text_color(self, health):
        """The status chip's text and colour for a readiness health dict."""
        if health["model_ready"]:
            return "● LOCAL MODEL RUNNING", P["good"]
        if health["running"]:
            return "● OLLAMA UP · MODEL MISSING", P["sevMedium"]
        if health["installed"]:
            return "● OLLAMA INSTALLED · STOPPED", P["sevMedium"]
        return "● LOCAL AI NOT INSTALLED", P["text3"]

    def _status_label(self):
        """A placeholder status chip. The real state is probed off-thread by
        _refresh_ai_detail_async and applied in _apply_health, so building the
        screen never blocks on an Ollama network call."""
        self._status_lbl = w.label("● CHECKING LOCAL AI…", size=9,
                                   weight=theme.W_SEMIBOLD, mono=True,
                                   color=P["text3"])
        return self._status_lbl

    def _open_setup_wizard(self):
        from ..setup_wizard import SetupWizard
        SetupWizard(self).exec()

    def _emit(self):
        self.settings.update({
            "examiner": self._name.text().strip(),
            "examiner_id": self._id.text().strip(),
            "agency": self._agency.text().strip(),
            "cloud_api_key": self._key.text().strip(),
            "ai_provider": self._provider.currentData(),
            "ollama_model": self._model.text().strip() or "llama3.2:3b",
        })
        self.changed.emit(self.settings)

    def rail(self) -> RailPayload:
        title, blocks, steps = RAIL_STATIC["settings"]
        return RailPayload(title, list(blocks), list(steps))

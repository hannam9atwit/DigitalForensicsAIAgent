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
        self._provider.addItem("Anthropic — cloud, needs API key", "anthropic")
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

        ai.add(w.spacer(h=4))
        ai.add(w.hline())
        ai.add(w.kv_row("Fallback order",
                        "Chosen engine → Rule-based (automatic)"))
        ai.add(w.spacer(h=10))
        ai.add(w.label("Anthropic API key (optional)", size=12, color=P["text2"]))
        self._key = QLineEdit(self.settings.get("anthropic_api_key", ""))
        self._key.setEchoMode(QLineEdit.Password)
        self._key.setPlaceholderText("sk-ant-…  (blank = fully offline)")
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

    def _status_label(self):
        """Live local-AI status, evaluated once when the screen builds."""
        health = ollama_runtime.readiness(
            self.settings.get("ollama_model", "llama3.2:3b"))
        if health["model_ready"]:
            text, color = "● LOCAL MODEL RUNNING", P["good"]
        elif health["running"]:
            text, color = "● OLLAMA UP · MODEL MISSING", P["sevMedium"]
        elif health["installed"]:
            text, color = "● OLLAMA INSTALLED · STOPPED", P["sevMedium"]
        else:
            text, color = "● LOCAL AI NOT INSTALLED", P["text3"]
        return w.label(text, size=9, weight=theme.W_SEMIBOLD, mono=True,
                       color=color)

    def _open_setup_wizard(self):
        from ..setup_wizard import SetupWizard
        SetupWizard(self).exec()

    def _emit(self):
        self.settings.update({
            "examiner": self._name.text().strip(),
            "examiner_id": self._id.text().strip(),
            "agency": self._agency.text().strip(),
            "anthropic_api_key": self._key.text().strip(),
            "ai_provider": self._provider.currentData(),
            "ollama_model": self._model.text().strip() or "llama3.2:3b",
        })
        self.changed.emit(self.settings)

    def rail(self) -> RailPayload:
        title, blocks, steps = RAIL_STATIC["settings"]
        return RailPayload(title, list(blocks), list(steps))

"""
gui_v2/screens/settings.py

Settings — examiner identity and the AI engine.

The API key field is the one place the app touches a network, so it says so
plainly: blank means fully offline, the key is held in memory only, and evidence
files never leave the machine regardless. Understating that would undercut the
product's central claim.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget, QLineEdit

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

        engine = self.case.get("caseMeta", {}).get("aiEngine", {})
        ai = w.Card(pad=17, spacing=0)
        ai.head("AI ENGINE",
                right=w.label("● LOCAL MODEL RUNNING", size=9,
                              weight=theme.W_SEMIBOLD, mono=True, color=P["good"]))
        ai.add(w.spacer(h=6))
        ai.add(w.kv_row("Default engine",
                        f"Ollama · {engine.get('model','llama3.2:3b')} (on this machine)"))
        ai.add(w.hline())
        ai.add(w.kv_row("Fallback order",
                        engine.get("fallback", "Local → Cloud key (if set) → Rule-based")))
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

    def _emit(self):
        self.settings.update({
            "examiner": self._name.text().strip(),
            "examiner_id": self._id.text().strip(),
            "agency": self._agency.text().strip(),
            "anthropic_api_key": self._key.text().strip(),
        })
        self.changed.emit(self.settings)

    def rail(self) -> RailPayload:
        title, blocks, steps = RAIL_STATIC["settings"]
        return RailPayload(title, list(blocks), list(steps))

"""
gui_v2/screens/base.py

Common base for every screen.

Screens own their selection and describe it; they never touch the rail, the
sidebar or each other directly. They emit two signals and the window wires the
rest:

    rail_changed(RailPayload)  — "my selection changed, here is the explanation"
    navigate(screen_id, arg)   — "take the user there, with this selected"

That is what makes the cross-navigation in the design (finding → evidence,
timeline row → finding, chat citation → anywhere) work without the screens
importing one another.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from ..rail import RailPayload


class Screen(QWidget):
    """Base screen. Subclasses set `id` and implement build() and rail()."""

    rail_changed = Signal(object)
    navigate = Signal(str, object)

    id = ""

    def __init__(self, case: dict, parent=None):
        super().__init__(parent)
        self.case = case
        self.setObjectName("page")

    # ── hooks ─────────────────────────────────────────────────────────────────

    def rail(self) -> RailPayload:
        """The explanation for whatever is currently selected."""
        return RailPayload()

    def push_rail(self):
        self.rail_changed.emit(self.rail())

    def on_show(self, arg=None):
        """Called when the window switches to this screen.

        `arg` is the optional selection target from navigate() — a finding id,
        an artifact id, a timeline timestamp.
        """
        if arg is not None:
            self.select(arg)
        self.push_rail()

    def select(self, arg):
        """Select `arg`. Screens with no selection model ignore it."""

    # ── helpers ───────────────────────────────────────────────────────────────

    def find_finding(self, fid):
        for f in self.case.get("findings", []):
            if f.get("id") == fid:
                return f
        return None

    def find_artifact(self, eid):
        for e in self.case.get("evidence", []):
            if e.get("id") == eid:
                return e
        return None

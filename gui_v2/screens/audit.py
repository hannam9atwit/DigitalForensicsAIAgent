"""
gui_v2/screens/audit.py

The audit trail — append-only, and the screen says so.

This is the least glamorous screen and one of the most important: it is the
artifact that makes the rest defensible. The design colours actions by who did
what (examiner actions in rust, verifications and completions in green, system
steps in grey) so the trail is scannable without reading every row.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QWidget

from .. import theme, widgets as w
from ..content import RAIL_STATIC
from ..rail import RailPayload
from .base import Screen

P = theme.GUIDED

KIND_COLOR = {"user": "accent", "ok": "good", "sys": "text2"}


class AuditScreen(Screen):
    id = "audit"

    def __init__(self, case, parent=None):
        super().__init__(case, parent)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        host, lay = w.page()
        root.addWidget(w.scroll_area(host))
        self._lay = lay

        lay.addWidget(w.screen_title("Audit trail"))
        lay.addWidget(w.body(
            "Every action taken on this case, in order. The log is append-only — "
            "nothing can be edited or removed, which is what makes it defensible.",
            size=13, color=P["text2"]))

        self._table = QWidget()
        self._table.setObjectName("card")
        self._tv = QVBoxLayout(self._table)
        self._tv.setContentsMargins(0, 0, 0, 0)
        self._tv.setSpacing(0)
        lay.addWidget(self._table)
        lay.addStretch(1)

        self.refresh()

    def refresh(self):
        w.clear_layout(self._tv)
        self._tv.addWidget(self._header())
        for i, a in enumerate(self.case.get("audit", []), start=1):
            self._tv.addWidget(self._row(i, a))

    def _header(self):
        head = QWidget()
        head.setObjectName("thead")
        head.setAttribute(Qt.WA_StyledBackground, True)
        h = QHBoxLayout(head)
        h.setContentsMargins(16, 8, 16, 8)
        h.setSpacing(12)
        for text, width in (("#", 34), ("TIMESTAMP", 118), ("ACTOR", 78),
                            ("ACTION", 150)):
            lb = w.micro_label(text)
            lb.setFixedWidth(width)
            h.addWidget(lb)
        h.addWidget(w.micro_label("DETAIL"), 1)
        return head

    def _row(self, n, a):
        # Real cases carry audit entries as (ts, who, act, detail) tuples; the
        # demo fixture carries dicts with a colour hint. Accept both.
        if isinstance(a, dict):
            ts, who, act, detail = a["ts"], a["who"], a["act"], a["detail"]
            kind = a.get("kind", "sys")
        else:
            ts, who, act, detail = a
            kind = ("ok" if act in ("HASH_VERIFIED", "ANALYSIS_COMPLETE")
                    else "sys" if who == "system" else "user")

        row = QWidget()
        row.setObjectName("trow")
        row.setAttribute(Qt.WA_StyledBackground, True)
        h = QHBoxLayout(row)
        h.setContentsMargins(16, 8, 16, 8)
        h.setSpacing(12)

        num = w.label(f"{n:03d}", size=10, mono=True, color=P["text3"])
        num.setFixedWidth(34)
        h.addWidget(num, 0, Qt.AlignTop)

        t = w.label(ts, size=10.5, mono=True, color=P["text3"])
        t.setFixedWidth(118)
        h.addWidget(t, 0, Qt.AlignTop)

        wh = w.label(who, size=11.5, color=P["text2"])
        wh.setFixedWidth(78)
        h.addWidget(wh, 0, Qt.AlignTop)

        ac = w.label(act, size=10, weight=theme.W_SEMIBOLD, mono=True,
                     color=P[KIND_COLOR.get(kind, "text2")])
        ac.setFixedWidth(150)
        h.addWidget(ac, 0, Qt.AlignTop)

        h.addWidget(w.body(detail, size=12, color=P["text2"], lh=1.4), 1)
        return row

    def rail(self) -> RailPayload:
        title, blocks, steps = RAIL_STATIC["audit"]
        return RailPayload(title, list(blocks), list(steps))

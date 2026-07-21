"""
gui_v2/screens/timeline.py

The unified, multi-source timeline.

Two things here are load-bearing for the brief's "nothing currently means
anything" problem:

  * Every row carries a plain-English "what it means" next to the raw artifact.
    A row that says only `Filesystem — /$AttrDef` tells an examiner nothing.
  * System noise ($MFT, $Bitmap, $LogFile — present on every Windows volume and
    not evidence) is filtered out by default, behind an explicit, counted toggle.
    Hiding it silently would be its own problem, so the footer always states how
    many records are hidden and why.

Rows are composed widgets rather than a QTableWidget: the design's significant
rows carry a 3px left edge and the meaning column wraps, neither of which a
table view does without a custom delegate.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QWidget, QLineEdit, QPushButton,
    QGraphicsOpacityEffect,
)

from .. import theme, widgets as w
from ..content import TL_SOURCES, TOTAL_EVENTS, HIDDEN_NOISE, RAIL_STATIC
from ..rail import RailPayload
from .base import Screen

P = theme.GUIDED

# Wide enough for the longest source tag ("DOWNLOADS") at 8.5px mono.
SRC_W = 84


class TimelineRow(QWidget):
    """One timeline event."""

    clicked = Signal(str)

    def __init__(self, ev, parent=None):
        super().__init__(parent)
        self.ev = ev
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self._selected = False

        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 12, 0)
        h.setSpacing(0)

        # significance edge — the design's cue for "start with these"
        edge = QWidget()
        edge.setFixedWidth(3)
        edge.setStyleSheet(
            "background: %s;" % (P["sevCritical"] if ev.get("rel") == "sig"
                                 else "transparent"))
        h.addWidget(edge)

        inner = QWidget()
        ih = QHBoxLayout(inner)
        ih.setContentsMargins(9, 9, 0, 9)
        ih.setSpacing(12)

        ts = w.label(ev["ts"], size=10.5, mono=True, color=P["text3"])
        ts.setFixedWidth(118)
        ih.addWidget(ts, 0, Qt.AlignTop)

        src = w.label(ev["src"].upper(), size=8.5, weight=theme.W_SEMIBOLD, mono=True,
                      color=P[theme.SRC_COLORS.get(ev["src"], "text2")])
        src.setFixedWidth(SRC_W)
        ih.addWidget(src, 0, Qt.AlignTop)

        ih.addWidget(w.body(ev["label"], size=12.5, weight=theme.W_REGULAR, lh=1.35), 3)
        ih.addWidget(w.body(ev["mean"], size=12, color=P["text2"], lh=1.35), 3)
        h.addWidget(inner, 1)

        # Noise renders at half opacity — present, but visibly not the story.
        # A graphics effect is the only way to fade a whole subtree in Qt;
        # setWindowOpacity applies to top-level windows only.
        if ev.get("rel") == "noise":
            fade = QGraphicsOpacityEffect(self)
            fade.setOpacity(0.5)
            self.setGraphicsEffect(fade)

        self._apply()

    def set_selected(self, on):
        self._selected = bool(on)
        self._apply()

    def _apply(self):
        bg = P["accentTint"] if self._selected else "transparent"
        hover = P["accentTint"] if self._selected else P["panelAlt"]
        self.setStyleSheet(
            f"TimelineRow {{ background: {bg}; "
            f"border-bottom: 1px solid {P['bg']}; }}"
            f"TimelineRow:hover {{ background: {hover}; }}")

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self.ev["ts"])
        super().mouseReleaseEvent(e)


class TimelineScreen(Screen):
    id = "timeline"

    def __init__(self, case, parent=None):
        super().__init__(case, parent)
        self.src = "All"
        self.noise = False
        self.query = ""
        self.sel = None
        self._page_limit = self.PAGE_SIZE
        self.rows = {}
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        host, lay = w.page()
        root.addWidget(w.scroll_area(host))

        lay.addWidget(w.screen_title("Unified timeline"))
        lay.addWidget(w.body(
            "Every artifact merged into one sequence on one clock. Routine system "
            "records are hidden so real activity stands out.",
            size=13, color=P["text2"]))

        lay.addWidget(self._filters())

        self._table = QWidget()
        self._table.setObjectName("card")
        self._tv = QVBoxLayout(self._table)
        self._tv.setContentsMargins(0, 0, 0, 0)
        self._tv.setSpacing(0)
        lay.addWidget(self._table)

        self._note = w.body("", size=11, color=P["text3"], lh=1.45)
        lay.addWidget(self._note)
        lay.addStretch(1)

        self._render()

    def _filters(self):
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)

        self._pills = {}
        for s in TL_SOURCES:
            b = QPushButton(s)
            b.setObjectName("pill")
            b.setCursor(QCursor(Qt.PointingHandCursor))
            b.setProperty("on", "true" if s == self.src else "false")
            b.clicked.connect(lambda _=False, src=s: self.set_source(src))
            self._pills[s] = b
            h.addWidget(b)

        h.addWidget(w.vline())

        noise_n = sum(1 for e in self.case.get("events", []) if e.get("rel") == "noise")
        self._noise_box = w.CheckRow(f"Show system noise ({noise_n})", checked=False,
                                     size=14, text_size=12)
        self._noise_box.toggled.connect(self.set_noise)
        h.addWidget(self._noise_box)

        h.addStretch(1)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter events…")
        self._search.setFixedWidth(200)
        self._search.textChanged.connect(self.set_query)
        h.addWidget(self._search)
        return box

    # ── filtering ─────────────────────────────────────────────────────────────

    def _show_more_button(self, remaining):
        from PySide6.QtWidgets import QPushButton
        step = min(self.PAGE_SIZE, remaining)
        button = QPushButton(f"Show {step} more  ·  {remaining:,} not shown")
        button.setObjectName("pill")
        button.setCursor(QCursor(Qt.PointingHandCursor))
        button.clicked.connect(self._show_more)
        return button

    def _show_more(self):
        self._page_limit += self.PAGE_SIZE
        self._render()

    def _shown(self):
        out = []
        q = self.query.lower()
        for e in self.case.get("events", []):
            if not self.noise and e.get("rel") == "noise":
                continue
            if self.src != "All" and e.get("src") != self.src:
                continue
            if q and q not in f"{e.get('label','')} {e.get('mean','')} {e['ts']}".lower():
                continue
            out.append(e)
        return out

    # Render at most this many rows at once. Filtering happens over the full
    # data list (fast); only the realized widgets are capped, which is what
    # keeps an 11k-event case from building tens of thousands of widgets and
    # freezing. "Show more" reveals the next page.
    PAGE_SIZE = 200

    def _render(self):
        w.clear_layout(self._tv)
        self.rows.clear()

        self._tv.addWidget(self._header())
        shown = self._shown()
        visible = shown[:self._page_limit]
        for e in visible:
            row = TimelineRow(e)
            row.clicked.connect(self.select)
            self.rows[e["ts"]] = row
            self._tv.addWidget(row)

        remaining = len(shown) - len(visible)
        if remaining > 0:
            self._tv.addWidget(self._show_more_button(remaining))

        if not shown:
            empty = w.body("No events match these filters.", size=12.5, color=P["text3"])
            empty.setAlignment(Qt.AlignCenter)
            empty.setContentsMargins(0, 28, 0, 28)
            self._tv.addWidget(empty)

        total = self.case.get("caseMeta", {}).get("pipeline", {}).get(
            "eventsParsed", TOTAL_EVENTS)
        hidden = sum(1 for e in self.case.get("events", []) if e.get("rel") == "noise")
        # The demo case stands in for a 18,402-event run, so its hidden-noise
        # count is the real pipeline's, not the fixture's four sample rows.
        if self.case.get("demo"):
            hidden = HIDDEN_NOISE
        if self.noise:
            note = (f"Showing {len(shown)} of {total:,} events — including routine "
                    f"system records.")
        else:
            note = (f"Showing {len(shown)} of {total:,} events — {hidden:,} routine "
                    f"system records hidden ($MFT, $Bitmap and similar exist on every "
                    f"Windows volume and are not evidence).")
        self._note.setText(
            f'<div style="line-height:145%; font-size:11px; color:{P["text3"]};">'
            f'{note}</div>')

        if self.sel in self.rows:
            self.rows[self.sel].set_selected(True)

    def _header(self):
        head = QWidget()
        head.setObjectName("thead")
        head.setAttribute(Qt.WA_StyledBackground, True)
        h = QHBoxLayout(head)
        h.setContentsMargins(24, 8, 12, 8)
        h.setSpacing(12)
        ts = w.micro_label("TIME")
        ts.setFixedWidth(118)
        h.addWidget(ts)
        sc = w.micro_label("SOURCE")
        sc.setFixedWidth(SRC_W)
        h.addWidget(sc)
        h.addWidget(w.micro_label("WHAT HAPPENED"), 3)
        h.addWidget(w.micro_label("WHAT IT MEANS"), 3)
        return head

    # ── state ─────────────────────────────────────────────────────────────────

    def set_source(self, src):
        self.src = src
        self._page_limit = self.PAGE_SIZE
        for s, b in self._pills.items():
            b.setProperty("on", "true" if s == src else "false")
            b.style().unpolish(b)
            b.style().polish(b)
        self._render()

    def set_noise(self, on):
        self.noise = bool(on)
        self._page_limit = self.PAGE_SIZE
        self._render()

    def set_query(self, text):
        self.query = text or ""
        self._page_limit = self.PAGE_SIZE
        self._render()

    def select(self, ts):
        self.sel = ts
        # A deep-link may target an event the current filters hide.
        if ts not in self.rows and any(e["ts"] == ts for e in self.case.get("events", [])):
            self.src = "All"
            self.query = ""
            self._search.blockSignals(True)
            self._search.clear()
            self._search.blockSignals(False)
            self.set_source("All")
        for k, row in self.rows.items():
            row.set_selected(k == ts)
        self.push_rail()

    def _event(self, ts):
        for e in self.case.get("events", []):
            if e["ts"] == ts:
                return e
        return None

    def rail(self) -> RailPayload:
        e = self._event(self.sel) if self.sel else None
        if not e:
            title, blocks, steps = RAIL_STATIC["timeline"]
            return RailPayload(title, list(blocks), list(steps))

        why = e.get("mean", "") + "."
        if e.get("rel") == "sig":
            why += " It is marked significant because it directly supports a finding."
        elif e.get("rel") == "noise":
            why += " It is system noise — shown only because you enabled it."

        chips, head = [], "SEE THE EVIDENCE"
        if e.get("fid"):
            head = "RELATED FINDING"
            chips = [(e["fid"], e["fid"])]
        return RailPayload(
            title="This event — in plain terms",
            blocks=[("WHAT IS THIS?",
                     f"{e.get('label','')} ({e['ts']}, from the "
                     f"{e.get('src','').lower()} source)."),
                    ("WHY AM I SEEING IT?", why)],
            chips=chips, chip_head=head,
        )

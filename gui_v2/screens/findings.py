"""
gui_v2/screens/findings.py

Findings — the most important screen.

Findings are grouped by incident phase rather than listed by severity, because
the question an examiner actually has is "what happened, in order", not "what
scored highest". The phase spine gives that narrative shape.

Each card is deliberately thin: severity, title, one-line summary. The depth —
what happened, why it matters, how confident and why, what to do next, which
artifacts back it — lives in the rail and appears on selection. That is the
progressive disclosure the brief asks for: skimmable in ten seconds, or read in
full, without those being two different screens.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QWidget, QFrame

from .. import theme, widgets as w
from ..rail import RailPayload
from .base import Screen

P = theme.GUIDED


_SEV_ORDER = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}


def _severity_rank(finding):
    sev = finding.get("sev", finding.get("severity", "LOW"))
    if isinstance(sev, int):
        return sev
    return _SEV_ORDER.get(str(sev).upper(), 0)


class FindingsScreen(Screen):
    id = "findings"

    def __init__(self, case, parent=None):
        super().__init__(case, parent)
        self.sel = None
        self.cards = {}
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        host, lay = w.page(max_width=760)
        root.addWidget(w.scroll_area(host))

        all_findings = self.case.get("findings", [])
        # Cap realized cards: a large automated run can yield thousands of
        # findings, and one widget per finding freezes the screen. The most
        # severe render first; the rest are reachable via "show more".
        self._render_cap = 150
        findings = sorted(
            all_findings,
            key=lambda f: -_severity_rank(f))[:self._render_cap]
        self._overflow = len(all_findings) - len(findings)
        has_phases = bool(self.case.get("phases"))
        lay.addWidget(w.screen_title("What the evidence shows"))
        lay.addWidget(w.body(
            "Each finding is a plain-English statement of something that happened"
            + (", grouped into the phases of the incident. " if has_phases else ". ")
            + "Select one to see the full reasoning, how confident it is and why, "
              "and what to do next.",
            size=13, color=P["text2"]))

        if not findings:
            lay.addWidget(self._zero_state())
            lay.addStretch(1)
            return

        # The AI's reasoning over the findings as a whole — what they
        # collectively indicate — drawn from the deep dive's synthesis. The
        # deterministic finding list below renders immediately; this card shows
        # a placeholder until the reasoning lands, then updates in place. The
        # demo fixture has no dive, so it keeps the reference's clean layout.
        if not self.case.get("demo"):
            lay.addWidget(self._reasoning_card())

        # The phase spine is the demo case's narrative structure. A real
        # analysis has no notion of incident phases, and inventing them would
        # assert something the evidence does not say — so those findings render
        # as a flat list, and anything left over by a partial phase mapping
        # still gets shown rather than silently dropped.
        phases = self.case.get("phases") or []
        placed = set()
        for ph in phases:
            items = [f for f in findings if f.get("phase") == ph["n"]]
            if not items:
                continue
            placed.update(f["id"] for f in items)
            lay.addWidget(self._phase_block(ph, items))

        rest = [f for f in findings if f["id"] not in placed]
        if rest and phases:
            lay.addWidget(self._phase_block(
                {"name": "Other findings", "when": "",
                 "desc": "Not attributed to a phase of the incident."}, rest))
        elif rest:
            for f in rest:
                card = self._card(f)
                self.cards[f["id"]] = card
                lay.addWidget(card)

        if self._overflow > 0:
            note = w.body(
                f"Showing the {len(findings)} most severe of "
                f"{len(all_findings):,} findings. Refine the case or use the "
                f"timeline to reach the rest.",
                size=12, color=P["text3"])
            note.setContentsMargins(0, 12, 0, 0)
            lay.addWidget(note)

        lay.addStretch(1)
        self.select(findings[0]["id"])

    def _reasoning_card(self):
        card = w.Card(pad=16, spacing=8)
        card.head("WHAT THE EVIDENCE SHOWS")
        self._assessment_label = w.body(self._assessment_text(), size=12.5,
                                        color=P["text2"], lh=1.6)
        card.add(self._assessment_label)
        return card

    def _assessment_text(self):
        """The AI's collective reading of the findings when the dive has
        produced it; otherwise an honest placeholder that says it is coming."""
        synthesis = self.case.get("synthesis") or {}
        text = synthesis.get("findings_assessment") or synthesis.get("narrative")
        if text:
            return text
        count = len(self.case.get("findings", []))
        return (f"{count} finding{'' if count == 1 else 's'} are listed below. "
                f"The AI's reasoning over how they relate and what they "
                f"collectively indicate will appear here once the background "
                f"analysis reaches it.")

    def refresh_ai(self):
        """Called by the window as deep-dive insights arrive — swap the reasoning
        text in without rebuilding the finding list."""
        label = getattr(self, "_assessment_label", None)
        if label is None:
            return
        text = self._assessment_text()
        esc = (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        label.setText(
            f'<div style="line-height:160%; font-family:{theme.SANS_STACK}; '
            f'font-size:12.5px; color:{P["text2"]};">{esc}</div>')

    def _zero_state(self):
        """A case with nothing to report still has to look finished, not broken."""
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 60, 0, 60)
        v.setSpacing(8)
        v.setAlignment(Qt.AlignCenter)
        t = w.label("No findings", size=16, weight=theme.W_SEMIBOLD)
        t.setAlignment(Qt.AlignCenter)
        v.addWidget(t)
        msg = w.body(
            "The analysis completed and nothing crossed the reporting threshold — "
            "the timeline is still available.",
            size=12.5, color=P["text2"])
        msg.setAlignment(Qt.AlignCenter)
        msg.setMaximumWidth(420)
        v.addWidget(msg, 0, Qt.AlignCenter)
        return box

    def _phase_block(self, ph, items):
        """One phase: spine marker + connector, header, then its findings."""
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 6, 0, 0)
        h.setSpacing(14)

        # the spine: a rust square with a soft connector running down from it
        spine = QWidget()
        spine.setFixedWidth(10)
        sv = QVBoxLayout(spine)
        sv.setContentsMargins(0, 4, 0, 0)
        sv.setSpacing(0)
        dot = QFrame()
        dot.setFixedSize(10, 10)
        dot.setStyleSheet(f"background: {P['accent']}; border-radius: 3px;")
        sv.addWidget(dot)
        conn = QFrame()
        conn.setFixedWidth(2)
        conn.setStyleSheet(f"background: {P['lineSoft']}; border: none;")
        sv.addWidget(conn, 1, Qt.AlignHCenter)
        h.addWidget(spine)

        col = QWidget()
        v = QVBoxLayout(col)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(10)
        head.addWidget(w.label(ph["name"], size=15, weight=theme.W_SEMIBOLD))
        head.addWidget(w.label(ph["when"], size=10, color=P["text3"], mono=True))
        head.addStretch(1)
        v.addLayout(head)
        v.addWidget(w.body(ph["desc"], size=12, color=P["text2"], lh=1.4))
        v.addWidget(w.spacer(h=2))

        for f in items:
            card = self._card(f)
            self.cards[f["id"]] = card
            v.addWidget(card)

        v.addWidget(w.spacer(h=8))
        h.addWidget(col, 1)
        return box

    def _card(self, f):
        card = w.SelectableCard(pad=13, spacing=0)
        h = QHBoxLayout()
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(12)

        sev = w.sev_tag(f.get("sev", "LOW"))
        sev.setAlignment(Qt.AlignTop)
        h.addWidget(sev, 0, Qt.AlignTop)

        col = QWidget()
        v = QVBoxLayout(col)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(3)
        v.addWidget(w.label(f.get("title", ""), size=13.5, weight=theme.W_MEDIUM,
                            wrap=True))
        v.addWidget(w.body(f.get("short", ""), size=12, color=P["text2"], lh=1.4))
        h.addWidget(col, 1)

        h.addWidget(w.label(f["id"], size=10, color=P["text3"], mono=True),
                    0, Qt.AlignTop)

        card.v.addLayout(h)
        card.clicked.connect(lambda fid=f["id"]: self.select(fid))
        return card

    # ── selection ─────────────────────────────────────────────────────────────

    def select(self, fid):
        if fid not in self.cards:
            return
        self.sel = fid
        for k, card in self.cards.items():
            card.set_selected(k == fid)
        self.push_rail()

    def rail(self) -> RailPayload:
        f = self.find_finding(self.sel)
        if not f:
            return RailPayload(
                "Findings — in plain terms",
                [("WHAT IS THIS?", "Everything the analysis concluded, grouped into "
                                   "the phases of the incident."),
                 ("WHY AM I SEEING IT?", "Select a finding to see what happened, why "
                                         "it matters, and what to do next.")])
        return RailPayload(
            title=f"{f['id']} — in plain terms",
            blocks=[("WHAT IS THIS?", f.get("what", "")),
                    ("WHY AM I SEEING IT?", f.get("why", ""))],
            steps=list(f.get("next", [])),
            chips=[(eid, eid) for eid in f.get("ev", [])],
            chip_head="SEE THE EVIDENCE",
        )

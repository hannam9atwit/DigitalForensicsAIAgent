"""
gui_v2/screens/report.py

Report — the old "AI Narrative" tab, reconceived as a composition surface.

The examiner curates: they choose which findings go in, add their own remarks,
and only then export. The preview updates live so the consequence of excluding a
finding is visible before the PDF exists. The framing throughout is that this is
a legal document the examiner signs — the model drafts, the examiner is
accountable — which is why the export is recorded in the audit trail.

Georgia is used for the paper preview's headings only. It ships with Windows and
macOS; if it is absent Qt falls back through the serif stack, which is
acceptable for a preview whose real output is the PDF.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QWidget, QFrame, QPlainTextEdit, QLabel,
)

from .. import theme, widgets as w
from ..content import RAIL_STATIC
from ..rail import RailPayload
from .base import Screen

P = theme.GUIDED

SERIF = "Georgia, 'Times New Roman', serif"


class ReportScreen(Screen):
    id = "report"

    export_requested = Signal()

    def __init__(self, case, parent=None):
        super().__init__(case, parent)
        rep = case.get("report", {})
        self.include = dict(rep.get("include", {}))
        self.order = list(rep.get("order", [f["id"] for f in case.get("findings", [])]))
        self.notes = ""
        self.exported = False
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        host, lay = w.page()
        root.addWidget(w.scroll_area(host))

        lay.addWidget(w.screen_title("Report"))
        lay.addWidget(w.body(
            "The narrative is drafted by the local model; you decide what it says and "
            "what goes in. The PDF is a legal document, so everything here is logged.",
            size=13, color=P["text2"]))

        cols = QHBoxLayout()
        cols.setContentsMargins(0, 0, 0, 0)
        cols.setSpacing(22)
        cols.addWidget(self._left())
        cols.addWidget(self._paper(), 1)
        lay.addLayout(cols)
        lay.addStretch(1)

    # ── left column ───────────────────────────────────────────────────────────

    def _left(self):
        col = QWidget()
        col.setFixedWidth(280)
        v = QVBoxLayout(col)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(14)

        inc = w.Card(pad=15, spacing=9)
        inc.head("WHAT GOES IN")
        self._checks = {}
        for fid in self.order:
            f = self.find_finding(fid)
            if not f:
                continue
            row = w.CheckRow(f.get("title", fid), checked=self.include.get(fid, True),
                             text_size=12, wrap=True)
            row.toggled.connect(lambda on, i=fid: self._toggle(i, on))
            self._checks[fid] = row
            inc.add(row)
        v.addWidget(inc)

        notes = w.Card(pad=15, spacing=9)
        notes.head("YOUR REMARKS")
        self._notes = QPlainTextEdit()
        self._notes.setPlaceholderText(
            "Anything the reader needs context on — scope, limitations, "
            "corroboration still outstanding…")
        self._notes.setFixedHeight(110)
        self._notes.textChanged.connect(self._notes_changed)
        notes.add(self._notes)
        v.addWidget(notes)

        self._export_btn = w.primary_button("Export PDF report",
                                            self.export_requested.emit)
        v.addWidget(self._export_btn)

        self._confirm = QFrame()
        self._confirm.setObjectName("noticeGood")
        cv = QVBoxLayout(self._confirm)
        cv.setContentsMargins(11, 9, 11, 9)
        self._confirm_lbl = w.body("", size=11.5, color=P["good"], lh=1.4)
        cv.addWidget(self._confirm_lbl)
        self._confirm.hide()
        v.addWidget(self._confirm)

        v.addStretch(1)
        return col

    def _toggle(self, fid, on):
        self.include[fid] = bool(on)
        self._render_paper()

    def _notes_changed(self):
        self.notes = self._notes.toPlainText()
        self._render_paper()

    def mark_exported(self, filename):
        self.exported = True
        self._confirm_lbl.setText(
            f'<div style="line-height:140%; font-size:11.5px; color:{P["good"]};">'
            f'✓ {filename} exported — recorded in the audit trail.</div>')
        self._confirm.show()

    # ── paper preview ─────────────────────────────────────────────────────────

    def _paper(self):
        wrap = QWidget()
        wv = QVBoxLayout(wrap)
        wv.setContentsMargins(0, 0, 0, 0)

        self._sheet = QFrame()
        self._sheet.setObjectName("paper")
        self._sheet.setMaximumWidth(660)
        self._pv = QVBoxLayout(self._sheet)
        self._pv.setContentsMargins(48, 44, 48, 44)
        self._pv.setSpacing(0)
        wv.addWidget(self._sheet)
        wv.addStretch(1)

        self._render_paper()
        return wrap

    def included_findings(self):
        """The findings the examiner chose, in report order.

        Order matters: the report leads with the critical findings rather than
        whatever order the pipeline emitted, so the export must read this rather
        than re-filter the raw list.
        """
        out = []
        for fid in self.order:
            if not self.include.get(fid):
                continue
            f = self.find_finding(fid)
            if f:
                out.append(f)
        return out

    def _included(self):
        return self.included_findings()

    def _render_paper(self):
        w.clear_layout(self._pv)
        meta = self.case.get("caseMeta", {})
        rep = self.case.get("report", {})

        self._pv.addWidget(w.label(
            f"{meta.get('id','—')} · {meta.get('agency','—')} · CONFIDENTIAL",
            size=9, mono=True, color=P["text3"]))
        self._pv.addWidget(self._serif(rep.get("title", "Report of Digital Forensic "
                                                        "Examination"), 23, 700, 8))

        byline = w.body(rep.get("byline", ""), size=11.5, color=P["text2"], lh=1.4)
        byline.setContentsMargins(0, 6, 0, 14)
        self._pv.addWidget(byline)

        rule = QFrame()
        rule.setFixedHeight(2)
        rule.setStyleSheet(f"background: {P['text']}; border: none;")
        self._pv.addWidget(rule)

        self._pv.addWidget(self._serif("1. Executive Summary", 14.5, 700, 20))
        self._pv.addWidget(w.body(rep.get("summary", ""), size=12.5, lh=1.7))

        included = self._included()
        self._pv.addWidget(self._serif(f"2. Findings ({len(included)} included)",
                                       14.5, 700, 20))
        if not included:
            self._pv.addWidget(w.body(
                "No findings are currently included. Tick at least one on the left.",
                size=12.5, color=P["text3"], lh=1.7))
        for i, f in enumerate(included, start=1):
            self._pv.addWidget(self._finding_entry(i, f))

        if self.notes.strip():
            self._pv.addWidget(self._serif("3. Examiner Remarks", 14.5, 700, 20))
            self._pv.addWidget(w.body(self.notes.strip(), size=12.5, lh=1.7))

        wrapper = QWidget()
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 26, 0, 0)
        wl.setSpacing(12)
        wl.addWidget(w.hline(P["line"]))
        foot = rep.get("footer", "").replace("\n", "<br>")
        wl.addWidget(w.body(foot, size=8.5, color=P["text3"], lh=1.7, rich=True))
        self._pv.addWidget(wrapper)

    def _serif(self, text, size, weight, top):
        """A report-paper heading. Georgia is the only serif in the design and
        it is confined to this preview."""
        lb = QLabel(str(text))
        f = QFont()
        f.setFamilies(["Georgia", "Times New Roman", "serif"])
        f.setPixelSize(int(size))
        f.setWeight(QFont.Weight(weight))
        lb.setFont(f)
        lb.setWordWrap(True)
        lb.setStyleSheet(f"color: {P['text']}; background: transparent;")
        lb.setContentsMargins(0, top, 0, 0)
        return lb

    def _finding_entry(self, num, f):
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 12, 0, 0)
        v.setSpacing(4)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(8)
        head.addWidget(w.label(f"{num}. {f.get('title','')}", size=13,
                               weight=theme.W_SEMIBOLD, wrap=True), 1)
        head.addWidget(w.label(
            f.get("sev", ""), size=8, weight=theme.W_SEMIBOLD, mono=True,
            color=P[theme.SEV_KEY.get(str(f.get("sev", "")).upper(), "good")]),
            0, Qt.AlignTop)
        v.addLayout(head)

        v.addWidget(w.body(f.get("what", ""), size=12.5, lh=1.7))
        v.addWidget(w.label(
            f"{f['id']} · ATT&CK {f.get('mitre','—')} · "
            f"Evidence {', '.join(f.get('ev', [])) or '—'}",
            size=9, mono=True, color=P["text3"]))
        return box

    def rail(self) -> RailPayload:
        title, blocks, steps = RAIL_STATIC["report"]
        return RailPayload(title, list(blocks), list(steps))

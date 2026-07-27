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

import threading

from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QWidget, QFrame, QPlainTextEdit, QLabel,
    QApplication,
)

from .. import theme, widgets as w
from ..content import RAIL_STATIC
from ..rail import RailPayload
from .base import Screen

P = theme.GUIDED

SERIF = "Georgia, 'Times New Roman', serif"


class _NarrativeJob(QObject):
    """Re-runs narrative generation off the UI thread and reports progress back.

    Same rationale as gui_v2/ai_worker.py: a daemon threading.Thread rather than
    a QThread, because generation is a set of blocking HTTP calls that cannot be
    interrupted mid-flight — a daemon thread simply dies with the process at
    close. Results and per-section progress cross back to the UI thread via
    queued Qt signals, which is thread-safe by design.
    """

    progress = Signal(str, int, int)   # section_name, done, total
    done     = Signal(str, object)     # markdown, ai_status
    failed   = Signal(str)             # error text

    def __init__(self, ai_config: dict, narrative_input: dict, parent=None):
        super().__init__(parent)
        self._ai_config = ai_config or {}
        self._input = narrative_input
        self._engine = None
        self._cancelled = False

    def start(self):
        threading.Thread(target=self._run, daemon=True,
                         name="narrative-regen").start()

    def cancel(self):
        """Stop the in-flight draft. Safe from the UI thread. The section loop
        checks the flag between sections and unwinds without writing a partial
        narrative; the request the workers are blocked on is left to its own
        timeout, but the daemon threads never hold up interpreter exit."""
        self._cancelled = True
        engine = self._engine
        if engine is not None:
            engine.cancel()

    def _run(self):
        from ai.refinement_engine import GenerationCancelled
        from ai.narrative_engine import NarrativeEngine
        try:
            engine = NarrativeEngine(self._ai_config)
            self._engine = engine
            if self._cancelled:          # cancelled between construction and here
                engine.cancel()
            markdown = engine.generate(self._input, on_progress=self._on_progress)
        except GenerationCancelled:
            return                       # torn down — leave the narrative as-is
        except Exception as e:           # noqa: BLE001
            if not self._cancelled:
                self.failed.emit(str(e))
            return
        self.done.emit(markdown, engine.ai_status)

    def _on_progress(self, name, done, total):
        # Runs on the daemon thread; Qt queues the emit onto the UI thread.
        # Drop late progress once cancelled so a dying screen gets no updates.
        if not self._cancelled:
            self.progress.emit(name, done, total)


class ReportScreen(Screen):
    id = "report"

    export_requested = Signal()
    narrative_updated = Signal(object)   # {"markdown", "ai_status"} after a re-draft

    def __init__(self, case, parent=None):
        super().__init__(case, parent)
        rep = case.get("report", {})
        self.include = dict(rep.get("include", {}))
        self.order = list(rep.get("order", [f["id"] for f in case.get("findings", [])]))
        self.notes = ""
        self.exported = False
        self._regen_job = None
        self._build()

        # Stop an in-flight re-draft if this screen goes away (case reopened,
        # stack rebuilt) or the app closes mid-generation — otherwise the
        # section workers would keep running against a screen that no longer
        # exists. cancel() only sets a flag, so both hooks are safe to fire even
        # as the widget is being torn down.
        self.destroyed.connect(lambda *_: self._cancel_regen())
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._cancel_regen)

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

        lay.addWidget(self._ai_status_row())

        cols = QHBoxLayout()
        cols.setContentsMargins(0, 0, 0, 0)
        cols.setSpacing(22)
        cols.addWidget(self._left())
        cols.addWidget(self._paper(), 1)
        lay.addLayout(cols)
        lay.addStretch(1)

    # ── AI status + regenerate ──────────────────────────────────────────────────

    def _ai_status_row(self):
        """The top strip: who drafted the narrative on the left, a Regenerate
        action on the right. During a re-draft the left side shows live
        per-section progress in place of the banner."""
        host = QWidget()
        row = QHBoxLayout(host)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)

        self._banner_box = QWidget()
        self._banner_lay = QVBoxLayout(self._banner_box)
        self._banner_lay.setContentsMargins(0, 0, 0, 0)
        self._banner_lay.setSpacing(3)
        row.addWidget(self._banner_box, 1)

        self._regen_btn = w.link_button("Regenerate narrative", self._regenerate)
        if not self.case.get("narrativeInput"):
            self._regen_btn.setEnabled(False)
            self._regen_btn.setToolTip("Run the analysis first to draft a narrative.")
        row.addWidget(self._regen_btn, 0, Qt.AlignTop)

        self._render_banner()
        return host

    def _render_banner(self):
        """Draw the honesty banner from the case's current AI status.

        This whole screen frames the narrative as the model's draft, so when the
        model did not run — or timed out on some sections — that has to be
        visible before the examiner reads a word of it: green when the local
        model drafted it, amber when it fell back to rule-based text.
        """
        w.clear_layout(self._banner_lay)
        status = (self.case.get("narrative") or {}).get("ai_status")
        if not status:
            return

        frame = QFrame()
        v = QVBoxLayout(frame)
        v.setContentsMargins(13, 10, 13, 10)
        v.setSpacing(3)

        if status.get("used_llm"):
            frame.setObjectName("noticeGood")
            model = status.get("model") or "the local model"
            degraded = status.get("degraded") or []
            line = f"✓ Drafted by {model}"
            if degraded:
                line += (f" · {len(degraded)} section"
                         f"{'' if len(degraded) == 1 else 's'} rule-based (timed out)")
            v.addWidget(w.body(line, size=12, color=P["good"], lh=1.4))
            if degraded:
                v.addWidget(w.body("Timed out: " + ", ".join(degraded),
                                   size=10.5, color=P["text3"], lh=1.4))
        else:
            frame.setObjectName("noticeWarn")
            reason = status.get("reason") or "the local model was unavailable"
            v.addWidget(w.body(f"⚠ Rule-based — AI unavailable: {reason}",
                               size=12, color=P["sevMedium"], lh=1.4))
            detail = (status.get("detail") or "").strip()
            if detail:
                v.addWidget(w.body(detail, size=10.5, color=P["text3"], lh=1.4))
        self._banner_lay.addWidget(frame)

    def _regenerate(self):
        """Re-draft the narrative off the UI thread, showing per-section
        progress. Disabled while a draft is in flight so it can't overlap."""
        narrative_input = self.case.get("narrativeInput")
        if not narrative_input:
            return
        self._regen_btn.setEnabled(False)
        self._show_progress("preparing", 0, 10)

        job = _NarrativeJob(getattr(self, "ai_config", {}) or {}, narrative_input)
        job.progress.connect(self._show_progress)
        job.done.connect(self._regen_done)
        job.failed.connect(self._regen_failed)
        self._regen_job = job          # hold a reference so it outlives this call
        job.start()

    def _cancel_regen(self):
        """Cancel any in-flight re-draft. Reads only plain attributes so it is
        safe to call from teardown, when the widget's C++ half may be gone."""
        job = getattr(self, "_regen_job", None)
        if job is not None:
            job.cancel()

    def _show_progress(self, section_name, done, total):
        w.clear_layout(self._banner_lay)
        frame = QFrame()
        frame.setObjectName("noticeGood")
        v = QVBoxLayout(frame)
        v.setContentsMargins(13, 10, 13, 10)
        v.setSpacing(3)
        v.addWidget(w.body(f"Generating report… {done} of {total}",
                           size=12, color=P["text"], lh=1.4))
        v.addWidget(w.body(f"Last section: {section_name}",
                           size=10.5, color=P["text3"], lh=1.4))
        self._banner_lay.addWidget(frame)

    def _regen_done(self, markdown, ai_status):
        # Parse the fresh draft into the demo report's fixed prose slots exactly
        # as data_adapter does, so a re-draft feeds the preview and the export
        # the same way a first-pass analysis would.
        from ..data_adapter import narrative_slots
        slots = narrative_slots(markdown)
        payload = {"markdown": markdown, "ai_status": ai_status,
                   "executive_summary": slots["executive_summary"],
                   "conclusion": slots["conclusion"]}
        # Mutate the shared case in place so the preview, the export path and
        # the audit-visible banner all see the fresh draft.
        self.case["narrative"] = payload
        if slots["executive_summary"]:
            from ..report_pdf import _clean
            self.case.setdefault("report", {})["summary"] = \
                _clean(slots["executive_summary"])
        self._render_banner()
        self._render_paper()
        self._regen_btn.setEnabled(True)
        self.narrative_updated.emit(payload)   # let the window persist it

    def _regen_failed(self, error):
        w.clear_layout(self._banner_lay)
        frame = QFrame()
        frame.setObjectName("noticeWarn")
        v = QVBoxLayout(frame)
        v.setContentsMargins(13, 10, 13, 10)
        v.addWidget(w.body(f"⚠ Regeneration failed: {error}",
                           size=12, color=P["sevMedium"], lh=1.4))
        self._banner_lay.addWidget(frame)
        self._regen_btn.setEnabled(True)

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

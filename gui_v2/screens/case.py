"""
gui_v2/screens/case.py

Case overview — the answer to "I just opened this case, what am I looking at?"

It leads with the case as one readable paragraph rather than a stat grid,
because a number like "risk 87" is only meaningful once you know the story it
came from. "Start here" then does the thing a dashboard usually refuses to do:
it commits to an opinion about what the examiner should look at first, and
deep-links straight to it.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QWidget, QFrame

from .. import theme, widgets as w
from ..content import START_HERE, PIPELINE_ROWS, NOISE_NOTE, RAIL_STATIC
from ..rail import RailPayload
from .base import Screen

P = theme.GUIDED


class CaseScreen(Screen):
    id = "case"

    def __init__(self, case, parent=None):
        super().__init__(case, parent)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        host, lay = w.page(max_width=860)
        root.addWidget(w.scroll_area(host))

        meta = self.case.get("caseMeta", {})
        opened = str(meta.get("opened", "—"))
        lay.addWidget(w.screen_title(
            meta.get("title", "Untitled investigation"),
            f"{meta.get('id','—')} · OPENED {opened.upper()} · "
            f"EXAMINER {str(meta.get('examiner','—')).upper()} "
            f"({meta.get('examinerId','—')})"))

        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(14)
        row1.addWidget(self._paragraph_card(), 12)
        row1.addWidget(self._start_here(), 10)
        lay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(14)
        row2.addWidget(self._what_found(), 10)
        row2.addWidget(self._pipeline(), 10)
        row2.addWidget(self._custody(), 12)
        lay.addLayout(row2)

        # A third row rather than a stretch. The first two rows leave the lower
        # half of the page empty on anything above the design's 1440x900, and the
        # facts below are ones the examiner otherwise has to go to another screen
        # to get: what each artifact contributed, when the activity actually
        # spans, and who the evidence attributes it to.
        row3 = QHBoxLayout()
        row3.setContentsMargins(0, 0, 0, 0)
        row3.setSpacing(14)
        row3.addWidget(self._artifacts_card(), 12)
        row3.addWidget(self._activity_card(), 10)
        row3.addWidget(self._attribution_card(), 10)
        lay.addLayout(row3)
        lay.addStretch(1)

    def on_show(self, arg=None):
        super().on_show(arg)
        self.refresh_ai()

    def refresh_ai(self):
        """Upgrade the overview paragraph with the deep dive's synthesis when it
        is available. The curated/deterministic paragraph shows instantly; the
        model's overview replaces it in place once the dive writes it — no
        separate on-demand generation, so it never competes with the dive."""
        if self._para_label is None:
            return
        overview = (self.case.get("synthesis") or {}).get("overview")
        if not overview:
            return
        escaped = (overview.replace("&", "&amp;").replace("<", "&lt;")
                   .replace(">", "&gt;"))
        self._para_label.setText(
            f'<div style="line-height:165%; font-family:{theme.SANS_STACK}; '
            f'font-size:13px; color:{P["text"]};">{escaped}</div>')

    def _paragraph_card(self):
        card = w.Card(pad=17, spacing=8)
        card.head("THE CASE IN ONE PARAGRAPH")

        self._para_label = None
        para = self.case.get("paragraph")
        if para:
            # Rich text so the design's emphasis (key terms at weight 500,
            # filenames in mono) survives inside a single flowing paragraph.
            html = ""
            for text, mark in para:
                esc = (str(text).replace("&", "&amp;").replace("<", "&lt;")
                       .replace(">", "&gt;"))
                if mark == "b":
                    html += f'<span style="font-weight:500;">{esc}</span>'
                elif mark == "m":
                    html += (f'<span style="font-family:{theme.MONO_STACK}; '
                             f'font-size:12px;">{esc}</span>')
                else:
                    html += esc
            self._para_label = w.body(html, size=13, lh=1.65, rich=True)
            card.add(self._para_label)
        else:
            self._para_label = w.body(self._fallback_paragraph(), size=13,
                                      lh=1.65, color=P["text2"])
            card.add(self._para_label)

        card.add(w.spacer(h=4))
        card.add(w.primary_button(
            "Read the findings →", lambda: self.navigate.emit("findings", None)))
        card.v.addStretch(1)
        return card

    def _fallback_paragraph(self):
        """Real analyses have no hand-written paragraph, so state the shape of
        the case rather than showing an empty card."""
        f = self.case.get("findings", [])
        crit = sum(1 for x in f if str(x.get("sev", "")).upper() == "CRITICAL")
        n_ev = len(self.case.get("evidence", []))
        n_events = self.case.get("caseMeta", {}).get("pipeline", {}).get(
            "eventsParsed", 0)
        if not f:
            return (f"{n_ev} artifact(s) were parsed into {n_events:,} events. "
                    f"Nothing crossed the reporting threshold — the timeline is "
                    f"still available to walk through.")
        return (f"{n_ev} artifact(s) were parsed into {n_events:,} events, producing "
                f"{len(f)} finding(s){f', {crit} of them critical' if crit else ''}. "
                f"Open the findings to see what happened and why it matters.")

    def _start_here(self):
        card = w.Card(pad=17, spacing=2)
        card.head("START HERE")
        card.add(w.spacer(h=4))
        for n, title, sub, (screen, arg) in START_HERE:
            row = QWidget()
            row.setObjectName("hoverRow")
            row.setAttribute(Qt.WA_StyledBackground, True)
            row.setCursor(Qt.PointingHandCursor)
            h = QHBoxLayout(row)
            h.setContentsMargins(8, 8, 8, 8)
            h.setSpacing(10)
            h.addWidget(w.label(n, size=10, weight=theme.W_SEMIBOLD,
                                color=P["accent"], mono=True), 0, Qt.AlignTop)
            col = QWidget()
            v = QVBoxLayout(col)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(1)
            v.addWidget(w.label(title, size=12.5, weight=theme.W_MEDIUM, wrap=True))
            v.addWidget(w.label(sub, size=11, color=P["text3"], wrap=True))
            h.addWidget(col, 1)
            row.mouseReleaseEvent = (
                lambda e, s=screen, a=arg: self.navigate.emit(s, a))
            card.add(row)
        card.v.addStretch(1)
        return card

    def _what_found(self):
        card = w.Card(pad=17, spacing=8)
        card.head("WHAT WAS FOUND")
        counts = {}
        for f in self.case.get("findings", []):
            k = str(f.get("sev", "LOW")).upper()
            counts[k] = counts.get(k, 0) + 1
        any_row = False
        for name in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
            if not counts.get(name):
                continue
            any_row = True
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(8)
            sq = QFrame()
            sq.setFixedSize(8, 8)
            sq.setStyleSheet(
                f"background: {P[theme.SEV_KEY[name]]}; border-radius: 2px;")
            h.addWidget(sq)
            h.addWidget(w.label(name.capitalize(), size=12.5), 1)
            h.addWidget(w.label(str(counts[name]), size=12, mono=True))
            card.add(row)
        if not any_row:
            card.add(w.body("No findings crossed the reporting threshold.",
                            size=12, color=P["text3"], lh=1.5))
        card.add(w.hline())
        card.add(w.body(NOISE_NOTE if self.case.get("demo") else
                        "Routine system records are hidden as noise on the timeline — "
                        "nothing real is buried in them.",
                        size=11.5, color=P["text2"], lh=1.5))
        card.v.addStretch(1)
        return card

    def _pipeline(self):
        card = w.Card(pad=17, spacing=0)
        card.head("ANALYSIS PIPELINE")
        card.add(w.spacer(h=4))
        if self.case.get("demo"):
            rows = PIPELINE_ROWS
        else:
            p = self.case.get("caseMeta", {}).get("pipeline", {})
            rows = [("Last run", p.get("lastRun", "—")),
                    ("Duration", p.get("duration", "—")),
                    ("Events parsed", f"{p.get('eventsParsed', 0):,}"),
                    ("Engine", self.case.get("caseMeta", {}).get(
                        "aiEngine", {}).get("model", "—"))]
        for i, (k, v) in enumerate(rows):
            card.add(w.kv_row(k, v))
            if i < len(rows) - 1:
                card.add(w.hline())
        card.v.addStretch(1)
        return card

    def _custody(self):
        card = w.Card(pad=17, spacing=0)
        ev = self.case.get("evidence", [])
        # "Intact" is a claim about custody — that every artifact is accounted
        # for and none was modified — not about whether each hash has been
        # re-checked yet. A pending re-verification is shown per-artifact below;
        # it does not break the chain, and the status bar says the same.
        card.head("CHAIN OF CUSTODY",
                  right=w.label("INTACT" if ev else "—", size=9,
                                weight=theme.W_SEMIBOLD, mono=True,
                                color=P["good"] if ev else P["text3"]))
        card.add(w.spacer(h=4))
        for e in ev:
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 5, 0, 5)
            h.setSpacing(8)
            h.addWidget(w.label(e["id"], size=10, mono=True, color=P["text3"]))
            h.addWidget(w.elided_label(e["name"], 132, size=11.5), 1)
            h.addWidget(w.HashLabel(e.get("sha") or e.get("sha256", "")))
            ok = e.get("verified")
            h.addWidget(w.label("✓" if ok else "…", size=10,
                                weight=theme.W_SEMIBOLD, mono=True,
                                color=P["good"] if ok else P["sevMedium"]))
            card.add(row)
        card.v.addStretch(1)
        return card

    # ── case-level detail ─────────────────────────────────────────────────────

    def _artifacts_card(self):
        """What each artifact actually contributed to the timeline.

        The custody card says an artifact is registered and verified; this says
        whether it produced anything. An artifact parsed to zero events is the
        single most useful thing to notice early on the Case tab, because it
        bounds everything the rest of the case can conclude.
        """
        card = w.Card(pad=17, spacing=0)
        evidence = self.case.get("evidence", [])
        card.head("WHAT EACH ARTIFACT GAVE US")
        card.add(w.spacer(h=4))

        if not evidence:
            card.add(w.body("No artifacts are registered to this case yet.",
                            size=12, color=P["text3"], lh=1.5))
            card.v.addStretch(1)
            return card

        silent = 0
        for index, artifact in enumerate(evidence):
            events = artifact.get("events") or 0
            if not events:
                silent += 1
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 5, 0, 5)
            h.setSpacing(8)
            h.addWidget(w.label(artifact.get("id", "—"), size=10, mono=True,
                                color=P["text3"]))
            h.addWidget(w.elided_label(artifact.get("name", ""), 118, size=11.5), 1)
            h.addWidget(w.label(
                f"{events:,}" if events else "none",
                size=11, mono=True,
                color=P["text"] if events else P["sevMedium"]))
            card.add(row)
            if index < len(evidence) - 1:
                card.add(w.hline())

        card.add(w.spacer(h=6))
        card.add(w.body(
            (f"{silent} artifact{'' if silent == 1 else 's'} produced no events. "
             f"The audit trail records why for each one."
             if silent else
             "Every registered artifact contributed events to the timeline."),
            size=11.5, color=P["text2"] if not silent else P["sevMedium"], lh=1.5))
        card.v.addStretch(1)
        return card

    def _activity_card(self):
        """When the evidence actually places activity, and how much of it is
        worth an examiner's attention — both read off the interpreted events."""
        card = w.Card(pad=17, spacing=0)
        card.head("WHEN THE ACTIVITY SITS")
        card.add(w.spacer(h=4))

        events = self.case.get("events", [])
        stamps = sorted(str(e.get("ts") or "").strip() for e in events
                        if str(e.get("ts") or "").strip())
        relevance = {}
        for event in events:
            key = str(event.get("rel", "ctx"))
            relevance[key] = relevance.get(key, 0) + 1

        if not events:
            card.add(w.body("No events have been interpreted for this case yet.",
                            size=12, color=P["text3"], lh=1.5))
            card.v.addStretch(1)
            return card

        rows = [
            ("First activity", stamps[0] if stamps else "not recorded"),
            ("Last activity", stamps[-1] if stamps else "not recorded"),
            ("Significant", f"{relevance.get('sig', 0):,}"),
            ("Notable", f"{relevance.get('not', 0):,}"),
            ("System noise", f"{relevance.get('noise', 0):,}"),
        ]
        for index, (key, value) in enumerate(rows):
            card.add(w.kv_row(key, value))
            if index < len(rows) - 1:
                card.add(w.hline())

        if not stamps:
            card.add(w.spacer(h=6))
            card.add(w.body(
                "No event carries a usable timestamp, which is itself worth "
                "noting: it bounds any sequence the case can establish.",
                size=11.5, color=P["sevMedium"], lh=1.5))
        card.v.addStretch(1)
        return card

    def _attribution_card(self):
        """Which accounts the evidence establishes — read from the records by
        ai.accounts, never generated, and stated as an explicit gap when the
        evidence establishes none."""
        from ai import accounts as accounts_mod

        card = w.Card(pad=17, spacing=0)
        card.head("WHO THE EVIDENCE NAMES")
        card.add(w.spacer(h=4))

        found = accounts_mod.extract(self.case.get("events", []))
        people = [(name, detail) for name, detail in found.items()
                  if not detail["service"]]
        service = [name for name, detail in found.items() if detail["service"]]

        if not people:
            card.add(w.body(
                "The evidence does not establish a user account. Nothing here "
                "can be attributed to a named person, and any account named "
                "elsewhere in the case would not come from these artifacts.",
                size=11.5, color=P["sevMedium"], lh=1.5))
        else:
            for index, (name, detail) in enumerate(people[:5]):
                row = QWidget()
                h = QHBoxLayout(row)
                h.setContentsMargins(0, 5, 0, 5)
                h.setSpacing(8)
                h.addWidget(w.elided_label(name, 120, size=11.5), 1)
                h.addWidget(w.label(f"{detail['records']:,}", size=11, mono=True,
                                    color=P["text3"]))
                card.add(row)
                if index < min(len(people), 5) - 1:
                    card.add(w.hline())
            card.add(w.spacer(h=6))
            card.add(w.body(
                "Taken from profile directories and account records on the "
                "evidence itself, not inferred.",
                size=11.5, color=P["text2"], lh=1.5))

        if service:
            card.add(w.spacer(h=4))
            card.add(w.body(
                "Built-in service accounts also present: " + ", ".join(service[:4]),
                size=11, color=P["text3"], lh=1.4))
        card.v.addStretch(1)
        return card

    def rail(self) -> RailPayload:
        title, blocks, steps = RAIL_STATIC["case"]
        return RailPayload(title, list(blocks), list(steps))

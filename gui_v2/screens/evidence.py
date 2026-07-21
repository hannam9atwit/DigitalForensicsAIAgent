"""
gui_v2/screens/evidence.py

Evidence, with the tiered sealed viewer.

The viewer exists so an examiner can inspect potentially malicious evidence
without ever executing it, and the design's rule is that the containment must be
legible rather than implied. So the safety affordances here are unconditional,
not error states: the READ-ONLY pill is always on the viewer header, the sealed
note always sits under the tier ladder, and the blocked-remote-content caption
is always under the rendered browser table. If any of them only appeared when
something was wrong, their absence would carry no meaning.

The three tiers are a ladder of how deep to look, not different screens:
  1  raw bytes and metadata      — the safest look
  2  parsed, rendered records    — remote content never fetched
  3  the image's directory tree  — deleted and recovered entries marked
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QWidget, QFrame

from .. import theme, widgets as w
from ..content import (
    TIERS, SEALED_NOTE, EVIDENCE_SAFE_BLOCK, EVIDENCE_STEPS,
)
from ..rail import RailPayload


def _human_size(num_bytes):
    """Render a byte count as a readable size (real measured file size)."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{num_bytes} B"
from .base import Screen

P = theme.GUIDED

# Sized so the tier ladder and viewer fit the 932px between the sidebar and the
# rail at the design's 1440 window. Measured, not assumed.
#
# The binding constraint is a 16-byte hex row: 406px at the design's 11px mono,
# which would overflow and put a horizontal scrollbar on the page at the very
# size the design targets. At 10px the row is 348px and everything fits, with
# the metadata column 10px under the design's 230 to leave a little slack.
TIER_W = 212
META_W = 220
HEX_SIZE = 10


class EvidenceScreen(Screen):
    id = "evidence"

    def __init__(self, case, parent=None):
        super().__init__(case, parent)
        self.sel = None
        self.tier = 1
        self.art_cards = {}
        self.tier_cards = {}
        self._ai_jobs = []
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        host, lay = w.page()
        root.addWidget(w.scroll_area(host))

        lay.addWidget(w.screen_title("Evidence"))
        lay.addWidget(w.body(
            "Every artifact was hashed the moment it came in and is opened read-only. "
            "Pick one, then choose how deeply you want to look at it.",
            size=13, color=P["text2"]))

        # Artifact selector. A horizontal row rather than a grid: a grid gives
        # every column the same width, which truncates the longer artifact names
        # and sizes while leaving the shorter ones padded.
        sel_row = QWidget()
        srl = QHBoxLayout(sel_row)
        srl.setContentsMargins(0, 0, 0, 0)
        srl.setSpacing(10)
        arts = self.case.get("evidence", [])
        for e in arts:
            card = self._artifact_card(e)
            self.art_cards[e["id"]] = card
            srl.addWidget(card)
        srl.addStretch(1)
        lay.addWidget(sel_row)

        # tier ladder + viewer
        cols = QHBoxLayout()
        cols.setContentsMargins(0, 0, 0, 0)
        cols.setSpacing(22)
        cols.addWidget(self._tier_ladder())
        self.viewer = _Viewer()
        cols.addWidget(self.viewer, 1)
        lay.addLayout(cols)
        lay.addStretch(1)

        if arts:
            self.select(arts[0]["id"])

    def _artifact_card(self, e):
        card = w.SelectableCard(pad=11, spacing=2)
        card.setMinimumWidth(150)
        card.v.addWidget(w.label(e["name"], size=11.5, weight=theme.W_SEMIBOLD,
                                 mono=True))
        card.v.addWidget(w.label(f"{e.get('kindLabel', '')} · {e.get('size', '')}",
                                 size=10.5, color=P["text3"]))
        ok = e.get("verified")
        card.v.addWidget(w.label("✓ VERIFIED" if ok else "… PENDING", size=8.5,
                                 weight=theme.W_SEMIBOLD, mono=True,
                                 color=P["good"] if ok else P["sevMedium"]))
        card.clicked.connect(lambda eid=e["id"]: self.select(eid))
        return card

    def _tier_ladder(self):
        col = QWidget()
        col.setFixedWidth(TIER_W)
        v = QVBoxLayout(col)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        v.addWidget(w.micro_label("HOW DEEP TO LOOK"))

        for i, (name, desc) in enumerate(TIERS, start=1):
            card = w.SelectableCard(pad=10, spacing=4)
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)
            mark = QFrame()
            mark.setFixedSize(9, 9)
            row.addWidget(mark, 0, Qt.AlignVCenter)
            row.addWidget(w.label(name, size=12.5, weight=theme.W_MEDIUM), 1)
            card.v.addLayout(row)
            card.v.addWidget(w.body(desc, size=11, color=P["text3"], lh=1.4))
            card.clicked.connect(lambda t=i: self.set_tier(t))
            card._mark = mark
            self.tier_cards[i] = card
            v.addWidget(card)

        v.addWidget(w.spacer(h=4))
        v.addWidget(w.Callout(SEALED_NOTE))
        v.addStretch(1)
        return col

    # ── selection ─────────────────────────────────────────────────────────────

    def select(self, eid):
        if eid not in self.art_cards:
            return
        self.sel = eid
        for k, c in self.art_cards.items():
            c.set_selected(k == eid)
        self._refresh_viewer()
        self.push_rail()
        self._request_ai_meaning()

    def set_tier(self, tier):
        self.tier = tier
        self._refresh_viewer()
        self.push_rail()

    def _refresh_viewer(self):
        for i, c in self.tier_cards.items():
            on = (i == self.tier)
            c.set_selected(on)
            c._mark.setStyleSheet(
                f"background: {P['accent'] if on else P['line']}; border-radius: 3px;")
        e = self.find_artifact(self.sel)
        if e:
            self.viewer.show_artifact(e, self.tier, self.case)

    def _request_ai_meaning(self):
        """Generate the "what it means" note for the selected artifact.

        The deterministic plain/role text is already on screen; when the model
        finishes — and the user is still on the same artifact — push_rail()
        swaps the richer interpretation in. Results cache on the artifact dict
        so re-selection is instant.
        """
        artifact = self.find_artifact(self.sel)
        if not artifact or artifact.get("ai_meaning") or not self.ai_config:
            return

        from ..ai_worker import SurfaceJob
        job = SurfaceJob(self.ai_config)
        job.result_ready.connect(self._ai_meaning_ready)
        # Anchor against GC while the daemon thread runs; keep only recent jobs.
        self._ai_jobs = self._ai_jobs[-8:] + [job]
        job.run("what_it_means", token=artifact["id"], fallback="",
                artifact=artifact, case=self.case)

    def _ai_meaning_ready(self, artifact_id, text):
        if not text:
            return
        artifact = self.find_artifact(artifact_id)
        if artifact:
            artifact["ai_meaning"] = text
        if artifact_id == self.sel:
            self.push_rail()

    def rail(self) -> RailPayload:
        e = self.find_artifact(self.sel)
        if not e:
            return RailPayload("Evidence", [
                ("WHAT IS THIS?", "The artifacts registered to this case, with their "
                                  "chain-of-custody status.")])

        blocks = [("WHAT IS THIS?", e.get("plain", "")),
                  ("WHY AM I SEEING IT?", e.get("role", ""))]
        if e.get("ai_meaning"):
            blocks.append(("WHAT IT MEANS", e["ai_meaning"]))
        blocks.append(EVIDENCE_SAFE_BLOCK)

        return RailPayload(
            title=f"{e['name']} — in plain terms",
            blocks=blocks,
            steps=list(EVIDENCE_STEPS),
        )


class _Viewer(QFrame):
    """The sealed viewer panel: header with a permanent read-only pill, and a
    body that swaps by tier and artifact kind."""

    case = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        head = QWidget()
        hl = QHBoxLayout(head)
        hl.setContentsMargins(16, 12, 14, 12)
        self._title = w.label("", size=13, weight=theme.W_MEDIUM)
        hl.addWidget(self._title, 1)
        hl.addWidget(w.Pill("READ-ONLY"))
        v.addWidget(head)
        v.addWidget(w.hline(P["line"]))

        self._body_host = QWidget()
        self._body = QVBoxLayout(self._body_host)
        self._body.setContentsMargins(16, 14, 16, 16)
        self._body.setSpacing(12)
        v.addWidget(self._body_host, 1)

    def show_artifact(self, e, tier, case=None):
        self._case_ref = case or {}
        w.clear_layout(self._body)
        self._title.setText(f"{e['name']} · {e.get('kindLabel', '')} · "
                            f"{TIERS[tier - 1][0]}")
        if tier == 1:
            self._tier1(e)
        elif tier == 2:
            self._tier2(e)
        else:
            self._tier3(e)
        self._body.addStretch(1)

    # ── tier 1 · raw ──────────────────────────────────────────────────────────

    def _tier1(self, e):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(14)

        hexbox = QFrame()
        hexbox.setObjectName("cardAlt")
        hv = QVBoxLayout(hexbox)
        hv.setContentsMargins(14, 12, 14, 12)
        hv.setSpacing(2)

        # Real bytes from the selected artifact — read read-only, nothing
        # hardcoded. The signature line at the bottom is detected from those
        # bytes, not assumed from the file name.
        from ..artifact_viewer import raw_preview
        preview = raw_preview(e.get("_path", ""))
        self._raw_preview_cache = preview  # used by the metadata column below

        if preview.get("error"):
            hv.addWidget(w.body(preview["error"], size=11, color=P["sevMedium"],
                                lh=1.4))
        else:
            # 10px keeps a 16-byte row inside the viewer width at 1440.
            for offset, hex_part, ascii_part in preview["hex_lines"][:20]:
                hv.addWidget(w.label(
                    f"{offset}  {hex_part}  {ascii_part}",
                    size=HEX_SIZE, mono=True, color=P["text2"],
                    weight=theme.W_REGULAR))
            hv.addWidget(w.spacer(h=4))
            hv.addWidget(w.label(
                f"SIGNATURE  {preview['signature']}",
                size=HEX_SIZE, mono=True, color=P["good"],
                weight=theme.W_MEDIUM))
        row.addWidget(hexbox, 1)

        meta = QWidget()
        meta.setFixedWidth(META_W)
        mv = QVBoxLayout(meta)
        mv.setContentsMargins(0, 0, 0, 0)
        mv.setSpacing(0)
        # Prefer the real on-disk size we just measured; fall back to the
        # stored label only if the file could not be read.
        preview = getattr(self, "_raw_preview_cache", {})
        real_size = e.get("size", "—")
        if preview.get("size_bytes") is not None:
            real_size = _human_size(preview["size_bytes"])

        rows = [
            ("File", e["name"]), ("Size", real_size),
            ("SHA-256", e.get("sha", "—") or "—"),
            ("Intake", e.get("intake", "—")),
            ("Integrity", "Verified ✓" if e.get("verified") else "Pending"),
            ("Access", "Read-only"),
        ]
        for i, (k, val) in enumerate(rows):
            color = None
            if k == "Integrity":
                color = P["good"] if e.get("verified") else P["sevMedium"]
            if k == "Access":
                color = P["good"]
            mv.addWidget(w.kv_row(k, val, value_color=color))
            if i < len(rows) - 1:
                mv.addWidget(w.hline())
        mv.addStretch(1)
        row.addWidget(meta)
        self._body.addLayout(row)
        self._derived_events(e)

    def _derived_events(self, e):
        """The events this artifact contributed to the timeline.

        This is the per-artifact drill-down: metadata and bytes above, the
        artifact's own share of the timeline here. Events carry the id of the
        artifact they were parsed from, so this is a real filter, not a guess.
        """
        events = [ev for ev in (self.case or {}).get("events", [])
                  if ev.get("artifact") == e.get("id")]

        self._body.addWidget(w.spacer(h=6))
        self._body.addWidget(w.micro_label(
            f"EVENTS FROM THIS ARTIFACT ({len(events)})"))
        self._body.addWidget(w.hline(P["line"]))

        if not events:
            self._body.addWidget(w.body(
                "This artifact contributed no events to the timeline. If that "
                "is unexpected, the audit trail records why its parser produced "
                "nothing.", size=11.5, color=P["text3"], lh=1.45))
            return

        for event in events[:25]:
            line = QHBoxLayout()
            line.setContentsMargins(0, 6, 0, 6)
            line.setSpacing(12)
            stamp = w.label(str(event.get("ts", "")), size=10.5, mono=True,
                            color=P["text3"])
            stamp.setFixedWidth(140)
            line.addWidget(stamp)
            line.addWidget(w.body(str(event.get("label", "")), size=11.5,
                                  weight=theme.W_REGULAR, lh=1.3), 1)
            self._body.addLayout(line)
            self._body.addWidget(w.hline())

        if len(events) > 25:
            self._body.addWidget(w.body(
                f"Showing the first 25 of {len(events):,}. The full sequence is "
                f"on the Timeline screen.", size=11, color=P["text3"], lh=1.4))
        self._derived_events(e)

    def _derived_events(self, e):
        """The events this artifact produced, shown with the artifact itself.

        This is the drill-down link between an artifact and the timeline: the
        examiner sees what this specific file contributed to the case without
        leaving the evidence screen. Events carry their originating artifact
        id through the pipeline, so the filter is exact rather than guessed.
        """
        case = getattr(self, "_case_ref", None) or {}
        events = [ev for ev in case.get("events", [])
                  if ev.get("artifact") == e.get("id")]
        if not events:
            return

        self._body.addWidget(w.spacer(h=10))
        self._body.addWidget(w.micro_label(
            f"EVENTS FROM THIS ARTIFACT ({len(events):,})"))
        self._body.addWidget(w.hline(P["line"]))

        significant = [ev for ev in events if ev.get("rel") != "noise"]
        for ev in (significant or events)[:12]:
            line = QHBoxLayout()
            line.setContentsMargins(0, 5, 0, 5)
            line.setSpacing(10)
            stamp = w.label(str(ev.get("ts", "")), size=10.5, mono=True,
                            color=P["text3"])
            stamp.setFixedWidth(130)
            line.addWidget(stamp)
            line.addWidget(w.body(str(ev.get("label", "")), size=11.5,
                                  weight=theme.W_REGULAR, lh=1.3), 1)
            self._body.addLayout(line)
            self._body.addWidget(w.hline())

        shown = min(len(significant or events), 12)
        if len(events) > shown:
            self._body.addWidget(w.body(
                f"Showing {shown} of {len(events):,}. Open the Timeline to see "
                f"all events from this artifact in sequence.",
                size=11, color=P["text3"], lh=1.4))

    # ── tier 2 · rendered ─────────────────────────────────────────────────────

    def _tier2(self, e):
        """Rendered view: real parsed records from the actual artifact.

        The old fixture tables are gone. Records come from the parser that
        matches the artifact's kind; a kind with no parser shows an honest
        message rather than borrowed sample rows.
        """
        from ..artifact_viewer import rendered_records
        result = rendered_records(e.get("_path", ""), e.get("kind", ""))

        if not result["supported"] or not result["columns"]:
            self._tier2_message(result["note"] or result.get("error", ""))
            return

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 6)
        head.setSpacing(12)
        for text in result["columns"]:
            head.addWidget(w.micro_label(text.upper()), 1)
        self._body.addLayout(head)
        self._body.addWidget(w.hline(P["line"]))

        # Cap realized rows so a large capture can't stall the panel.
        for record in result["rows"][:150]:
            row = QHBoxLayout()
            row.setContentsMargins(0, 6, 0, 6)
            row.setSpacing(12)
            for cell in record:
                row.addWidget(
                    w.body(str(cell), size=11.5, weight=theme.W_REGULAR, lh=1.3), 1)
            self._body.addLayout(row)
            self._body.addWidget(w.hline())

        caption = result["note"]
        if len(result["rows"]) > 150:
            caption += f" · showing first 150 of {len(result['rows'])}"
        if caption:
            self._body.addWidget(w.spacer(h=2))
            self._body.addWidget(w.body(caption, size=11, color=P["text3"], lh=1.4))

    def _tier2_message(self, message):
        box = QFrame()
        box.setObjectName("dashed")
        v = QVBoxLayout(box)
        v.setContentsMargins(20, 34, 20, 34)
        v.setSpacing(6)
        t = w.label("No rendered view for this artifact", size=13,
                    weight=theme.W_MEDIUM, color=P["text2"])
        t.setAlignment(Qt.AlignCenter)
        v.addWidget(t)
        msg = w.body(message or "Use Raw preview to inspect the bytes directly.",
                     size=12, color=P["text3"], lh=1.45)
        msg.setAlignment(Qt.AlignCenter)
        msg.setMaximumWidth(380)
        v.addWidget(msg, 0, Qt.AlignCenter)
        self._body.addWidget(box)

    # ── tier 3 · browse ───────────────────────────────────────────────────────

    def _tier3(self, e):
        """Browse the files: the real filesystem walked from a disk image.

        For non-disk artifacts this tier is honestly disabled with the reason.
        Deleted/recovered entries are marked.
        """
        from ..artifact_viewer import file_tree
        result = file_tree(e.get("_path", ""), e.get("kind", ""))

        if not result["supported"]:
            self._tier2_message(result["note"])
            return
        if result.get("error"):
            self._tier2_message(result["error"])
            return

        entries = result["entries"]
        if not entries:
            self._tier2_message("The image parsed but no files were listed at "
                                "the volume root.")
            return

        tree = QFrame()
        tree.setObjectName("cardAlt")
        tv = QVBoxLayout(tree)
        tv.setContentsMargins(12, 12, 12, 12)
        tv.setSpacing(3)

        for entry in entries[:400]:
            line = QWidget()
            lh = QHBoxLayout(line)
            lh.setContentsMargins(0, 0, 0, 0)
            lh.setSpacing(6)
            icon = "[D] " if entry["is_dir"] else "    "
            color = P["sevCritical"] if entry["deleted"] else P["text2"]
            lh.addWidget(w.label(f"{icon}{entry['name']}", size=11, mono=True,
                                 color=color))
            if entry["deleted"]:
                lh.addWidget(w.Tag("DELETED", P["sevCritical"]))
            lh.addStretch(1)
            tv.addWidget(line)
        tv.addStretch(1)
        self._body.addWidget(tree)

        caption = result["note"]
        if len(entries) > 400:
            caption += " · showing first 400"
        self._body.addWidget(w.body(
            caption + ". Files are read from the image as data; nothing is "
            "extracted or executed.",
            size=11, color=P["text3"], lh=1.4))

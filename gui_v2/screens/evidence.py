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
    TIERS, SEALED_NOTE, HEX_LINES, HISTORY_ROWS, HISTORY_CAPTION, REGISTRY_ROWS,
    TREE_ROWS, ARCHIVE_ROWS, ARCHIVE_NOTICE, EVIDENCE_SAFE_BLOCK, EVIDENCE_STEPS,
)
from ..rail import RailPayload
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
            self.viewer.show_artifact(e, self.tier)

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

    def show_artifact(self, e, tier):
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
        for i, line in enumerate(HEX_LINES):
            last = (i == len(HEX_LINES) - 1)
            # 10px, not the design's 11: a 16-byte row is 406px at 11px, which
            # pushes the viewer past the width available between the sidebar and
            # the rail at 1440. 10px brings the row to 348px and the column fits.
            hv.addWidget(w.label(
                line, size=HEX_SIZE, mono=True,
                color=P["good"] if last else P["text2"],
                weight=theme.W_MEDIUM if last else theme.W_REGULAR))
        row.addWidget(hexbox, 1)

        meta = QWidget()
        meta.setFixedWidth(META_W)
        mv = QVBoxLayout(meta)
        mv.setContentsMargins(0, 0, 0, 0)
        mv.setSpacing(0)
        rows = [
            ("File", e["name"]), ("Size", e.get("size", "—")),
            ("SHA-256", (e.get("sha", "")[:16] + "…") if e.get("sha") else "—"),
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

    # ── tier 2 · rendered ─────────────────────────────────────────────────────

    def _tier2(self, e):
        kind = e.get("kind")
        if kind == "browser":
            self._browser_table()
        elif kind == "registry":
            self._registry_tree()
        else:
            self._tier2_empty()

    def _browser_table(self):
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 6)
        head.setSpacing(12)
        for text, width in (("TIME", 110), ("VISITED / SEARCHED", 0), ("MEANING", 90)):
            lb = w.micro_label(text)
            if width:
                lb.setFixedWidth(width)
            head.addWidget(lb, 0 if width else 1)
        self._body.addLayout(head)
        self._body.addWidget(w.hline(P["line"]))

        for t, q, tag, warn in HISTORY_ROWS:
            row = QHBoxLayout()
            row.setContentsMargins(0, 7, 0, 7)
            row.setSpacing(12)
            ts = w.label(t, size=10.5, mono=True, color=P["text3"])
            ts.setFixedWidth(110)
            row.addWidget(ts)
            row.addWidget(w.body(q, size=12.5, weight=theme.W_REGULAR, lh=1.3), 1)
            chip = w.Tag(tag, P["sevCritical"] if warn else P["accent"])
            chip.setFixedWidth(90)
            row.addWidget(chip)
            self._body.addLayout(row)
            self._body.addWidget(w.hline())

        self._body.addWidget(w.spacer(h=2))
        self._body.addWidget(w.body(HISTORY_CAPTION, size=11, color=P["text3"], lh=1.4))

    def _registry_tree(self):
        box = QFrame()
        box.setObjectName("cardAlt")
        v = QVBoxLayout(box)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(3)
        for text, pad, hot in REGISTRY_ROWS:
            lb = w.label(text, size=11, mono=True,
                         color=P["sevCritical"] if hot else P["text2"],
                         weight=theme.W_SEMIBOLD if hot else theme.W_REGULAR)
            lb.setContentsMargins(pad * 18, 0, 0, 0)
            v.addWidget(lb)
        self._body.addWidget(box)
        self._body.addWidget(w.body(
            "Parsed from the hive file — the registry is read as data, never loaded "
            "into this machine's own registry.",
            size=11, color=P["text3"], lh=1.4))

    def _tier2_empty(self):
        box = QFrame()
        box.setObjectName("dashed")
        v = QVBoxLayout(box)
        v.setContentsMargins(20, 34, 20, 34)
        v.setSpacing(6)
        t = w.label("Nothing to render at this level", size=13,
                    weight=theme.W_MEDIUM, color=P["text2"])
        t.setAlignment(Qt.AlignCenter)
        v.addWidget(t)
        msg = w.body(
            "A disk image has no single record set to render. Use "
            "<b>Browse the files</b> to walk its folders, or <b>Raw preview</b> to "
            "read bytes.",
            size=12, color=P["text3"], lh=1.45, rich=True)
        msg.setAlignment(Qt.AlignCenter)
        msg.setMaximumWidth(360)
        v.addWidget(msg, 0, Qt.AlignCenter)
        self._body.addWidget(box)

    # ── tier 3 · browse ───────────────────────────────────────────────────────

    def _tier3(self, e):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(14)

        tree = QFrame()
        tree.setObjectName("cardAlt")
        tree.setFixedWidth(320)
        tv = QVBoxLayout(tree)
        tv.setContentsMargins(12, 12, 12, 12)
        tv.setSpacing(4)
        for text, pad, deleted, tag in TREE_ROWS:
            line = QWidget()
            lh = QHBoxLayout(line)
            # 12px per level, not 16: at depth 4 a filename plus its
            # DELETED/CARVED tag no longer fits the 320px tree column.
            lh.setContentsMargins(pad * 12, 0, 0, 0)
            lh.setSpacing(6)
            lh.addWidget(w.label(text, size=11, mono=True,
                                 color=P["sevCritical"] if deleted else P["text2"]))
            if tag:
                lh.addWidget(w.Tag(tag, P["sevCritical"]))
            lh.addStretch(1)
            tv.addWidget(line)
        tv.addStretch(1)
        row.addWidget(tree)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(12)

        notice = QFrame()
        notice.setObjectName("noticeBad")
        nv = QVBoxLayout(notice)
        nv.setContentsMargins(12, 11, 12, 11)
        nv.addWidget(w.body(ARCHIVE_NOTICE, size=12, color=P["text2"], lh=1.5))
        rv.addWidget(notice)

        rv.addWidget(w.micro_label("INSIDE THE ARCHIVE (31 FILES)"))
        rv.addWidget(w.hline(P["line"]))
        for name, size in ARCHIVE_ROWS:
            line = QHBoxLayout()
            line.setContentsMargins(0, 6, 0, 6)
            line.addWidget(w.label(name, size=11.5, mono=True, color=P["text2"]), 1)
            line.addWidget(w.label(size, size=10.5, mono=True, color=P["text3"]))
            rv.addLayout(line)
            rv.addWidget(w.hline())
        rv.addStretch(1)
        row.addWidget(right, 1)
        self._body.addLayout(row)

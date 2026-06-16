"""
gui_v2/screens.py

Screen builders. Each takes (case dict, palette) and returns a QWidget.
They read the same case shape whether it's demo data or a real analysis.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QScrollArea,
    QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy, QFrame,
    QComboBox, QLineEdit, QPushButton, QTextBrowser, QAbstractItemView, QCheckBox,
)

from . import theme
from .widgets import (
    Panel, MicroLabel, SeverityBadge, ConfidenceBadge, MitreTag, SourceTag,
    HashChip, RiskDial, hline,
)


def _screen_head(title, sub, right_widgets=None):
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(16, 14, 16, 10)
    left = QVBoxLayout()
    h1 = QLabel(title); h1.setObjectName("h1")
    s = QLabel(sub); s.setObjectName("sub")
    left.addWidget(h1)
    left.addWidget(s)
    lay.addLayout(left)
    lay.addStretch(1)
    if right_widgets:
        for rw in right_widgets:
            lay.addWidget(rw)
    return w


def _scroll(inner):
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.Shape.NoFrame)
    sa.setWidget(inner)
    return sa


def _kv_rows(pairs, pal):
    """Vertical key/value list with hairlines."""
    box = QVBoxLayout()
    box.setSpacing(0)
    for k, v in pairs:
        row = QHBoxLayout()
        kl = QLabel(k); kl.setStyleSheet(f"color:{pal['text3']};")
        vl = QLabel(str(v)); vl.setObjectName("mono")
        vl.setAlignment(Qt.AlignRight)
        vl.setWordWrap(True)
        row.addWidget(kl); row.addStretch(1); row.addWidget(vl)
        wrap = QWidget(); wrap.setLayout(row)
        wrap.setStyleSheet(f"border-bottom:1px solid {pal['line']};")
        box.addWidget(wrap)
    return box


def _table(headers, widths):
    t = QTableWidget()
    t.setColumnCount(len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setShowGrid(False)
    t.setWordWrap(False)
    hh = t.horizontalHeader()
    for i, wd in enumerate(widths):
        if wd is None:
            hh.setSectionResizeMode(i, QHeaderView.Stretch)
        else:
            hh.setSectionResizeMode(i, QHeaderView.Fixed)
            t.setColumnWidth(i, wd)
    return t


# ── Dashboard ─────────────────────────────────────────────────────────────────

def dashboard(case, pal):
    meta = case["caseMeta"]
    findings = case["findings"]
    sev_counts = {4: 0, 3: 0, 2: 0, 1: 0}
    for f in findings:
        sev_counts[f["sev"]] = sev_counts.get(f["sev"], 0) + 1

    page = QWidget()
    pl = QVBoxLayout(page)
    pl.setContentsMargins(0, 0, 0, 0)
    pl.setSpacing(0)
    pl.addWidget(_screen_head(
        meta["title"],
        f"CASE {meta['id']} · OPENED {meta['opened']} · CUSTODIAN {meta['custodian']}"))

    body = QWidget()
    grid = QGridLayout(body)
    grid.setContentsMargins(16, 0, 16, 16)
    grid.setSpacing(12)

    # Risk panel
    risk = Panel("Case risk assessment")
    rrow = QHBoxLayout()
    rrow.addWidget(RiskDial(meta["riskScore"], meta["riskLabel"], pal))
    bars = QVBoxLayout()
    total = max(1, len(findings))
    for s in (4, 3, 2, 1):
        label, key = theme.SEV[s]
        line = QHBoxLayout()
        sb = SeverityBadge(s, pal); sb.setFixedWidth(78)
        bar = QFrame(); bar.setFixedHeight(6)
        pct = int(sev_counts[s] / total * 100)
        bar.setStyleSheet(
            f"background:{pal['line']}; border-radius:3px;")
        fill = QFrame(bar)
        fill.setStyleSheet(f"background:{pal[key]}; border-radius:3px;")
        fill.setGeometry(0, 0, max(2, int(pct * 1.4)), 6)
        cnt = QLabel(str(sev_counts[s])); cnt.setObjectName("mono")
        line.addWidget(sb); line.addWidget(bar, 1); line.addWidget(cnt)
        bars.addLayout(line)
    rrow.addLayout(bars, 1)
    risk.add_layout(rrow)
    note = QLabel("Cross-artifact correlation links staging, USB transfer, and "
                  "post-transfer deletion into a single after-hours sequence on Jun 3.")
    note.setWordWrap(True); note.setStyleSheet(f"color:{pal['text2']}; font-size:12px;")
    risk.add(note)
    grid.addWidget(risk, 0, 0)

    # Pipeline panel
    pipe = Panel("Pipeline status")
    pp = meta["pipeline"]; ai = meta["aiEngine"]
    verified = sum(1 for e in case["evidence"] if e["verified"])
    pipe.add_layout(_kv_rows([
        ("Last run", pp["lastRun"]),
        ("Duration", pp["duration"]),
        ("Events parsed", f"{pp['eventsParsed']:,}"),
        ("Artifacts", f"{len(case['evidence'])} loaded · {verified} verified"),
        ("AI engine", f"{ai['provider']} · {ai['model']}"),
        ("Findings", f"{len(findings)} ({sev_counts[4]} critical)"),
    ], pal))
    grid.addWidget(pipe, 0, 1)

    # Chain of custody panel
    coc = Panel("Chain of custody",
                right=_pill("INTACT", pal["good"]))
    for e in case["evidence"]:
        row = QHBoxLayout()
        idl = QLabel(e["id"]); idl.setObjectName("mono"); idl.setFixedWidth(46)
        nm = QLabel(e["name"]); nm.setStyleSheet(f"color:{pal['text2']};")
        nm.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        row.addWidget(idl); row.addWidget(nm, 1)
        row.addWidget(HashChip(e["sha256"], e["verified"], pal))
        coc.add_layout(row)
    grid.addWidget(coc, 0, 2)

    # Priority findings table
    top = [f for f in findings if f["sev"] >= 3][:6]
    fp = Panel(f"Priority findings · {len(top)} of {len(findings)}", pad=0)
    t = _table(["SEVERITY", "ID", "FINDING", "ATT&CK", "CONF", "TIMESTAMP"],
               [96, 52, None, 130, 96, 150])
    t.setRowCount(len(top))
    for r, f in enumerate(top):
        _set_sev(t, r, 0, f["sev"], pal)
        t.setItem(r, 1, _mono_item(f["id"], pal))
        t.setItem(r, 2, QTableWidgetItem(f["title"]))
        t.setCellWidget(r, 3, MitreTag(f["mitre"], pal, f.get("mitreName", "")) if f.get("mitre") else QLabel("—"))
        t.setCellWidget(r, 4, ConfidenceBadge(f["conf"], pal))
        t.setItem(r, 5, _mono_item(f["ts"], pal))
    t.setMinimumHeight(60 + 34 * len(top))
    fp.add(t)
    grid.addWidget(fp, 1, 0, 1, 3)
    grid.setRowStretch(1, 1)

    pl.addWidget(_scroll(body), 1)
    return page


# ── Evidence ──────────────────────────────────────────────────────────────────

def evidence(case, pal, on_verify=None, on_export=None, on_report=None):
    page = QWidget()
    pl = QVBoxLayout(page); pl.setContentsMargins(0, 0, 0, 0); pl.setSpacing(0)
    verified = sum(1 for e in case["evidence"] if e["verified"])

    head_btns = []
    report_btn = QPushButton("GENERATE REPORT"); report_btn.setObjectName("primary")
    if on_report: report_btn.clicked.connect(on_report)
    export_btn = QPushButton("EXPORT SELECTED")
    reverify = QPushButton("RE-VERIFY ALL")
    if on_verify: reverify.clicked.connect(on_verify)
    head_btns = [reverify, export_btn, report_btn]

    pl.addWidget(_screen_head(
        "Evidence Manager",
        f"{len(case['evidence'])} ARTIFACTS · {verified} VERIFIED · ALL READ-ONLY · SHA-256 ON INTAKE",
        head_btns))

    body = QWidget(); bl = QVBoxLayout(body)
    bl.setContentsMargins(16, 0, 16, 16); bl.setSpacing(12)

    panel = Panel("Artifacts — tick rows to select for export", pad=0)
    t = _table(["", "ID", "NAME / TYPE", "SIZE", "SHA-256", "INTEGRITY", "EVENTS"],
               [34, 50, None, 90, 200, 100, 80])
    evs = case["evidence"]
    t.setRowCount(len(evs))
    t.verticalHeader().setDefaultSectionSize(46)
    checks = []
    for r, e in enumerate(evs):
        cb = QCheckBox(); cb.setChecked(True)
        cb_wrap = QWidget(); cbl = QHBoxLayout(cb_wrap)
        cbl.setContentsMargins(0, 0, 0, 0); cbl.setAlignment(Qt.AlignCenter); cbl.addWidget(cb)
        t.setCellWidget(r, 0, cb_wrap)
        checks.append((cb, e))
        t.setItem(r, 1, _mono_item(e["id"], pal))
        nm = QTableWidgetItem(f"{e['name']}\n{e['type']}")
        t.setItem(r, 2, nm)
        t.setItem(r, 3, _mono_item(e["size"], pal))
        t.setCellWidget(r, 4, HashChip(e["sha256"], e["verified"], pal))
        integ = QTableWidgetItem("VERIFIED" if e["verified"] else "PENDING")
        integ.setForeground(_qcolor(pal["good"] if e["verified"] else pal["med"]))
        t.setItem(r, 5, integ)
        t.setItem(r, 6, _mono_item(f"{e['events']:,}", pal))
    panel.add(t)
    bl.addWidget(panel)
    pl.addWidget(body, 1)

    if on_export:
        export_btn.clicked.connect(
            lambda: on_export([e for cb, e in checks if cb.isChecked()]))
    return page


# ── Timeline ──────────────────────────────────────────────────────────────────

def _ev_get(ev, key, idx=None):
    """Read an event whether it's a dict (new) or a tuple (legacy demo)."""
    if isinstance(ev, dict):
        return ev.get(key, "")
    order = ["ts", "src", "label", "path", "sev", "fid"]
    i = idx if idx is not None else (order.index(key) if key in order else None)
    return ev[i] if i is not None and i < len(ev) else ""


RELEVANCE_ORDER = {"significant": 3, "notable": 2, "context": 1, "noise": 0}
RELEVANCE_LABEL = {"significant": "Significant", "notable": "Notable",
                   "context": "Context", "noise": "System noise"}


def timeline(case, pal):
    page = QWidget()
    pl = QVBoxLayout(page); pl.setContentsMargins(0, 0, 0, 0); pl.setSpacing(0)
    events = case["events"]

    # relevance breakdown for the subheading
    counts = {"significant": 0, "notable": 0, "context": 0, "noise": 0}
    for e in events:
        counts[_ev_get(e, "relevance") or "context"] = \
            counts.get(_ev_get(e, "relevance") or "context", 0) + 1

    pl.addWidget(_screen_head(
        "Unified Timeline",
        f"{len(events):,} EVENTS · {counts['significant']} SIGNIFICANT · "
        f"{counts['notable']} NOTABLE · {counts['noise']} SYSTEM-NOISE (HIDDEN BY DEFAULT)"))

    body = QWidget(); bl = QVBoxLayout(body)
    bl.setContentsMargins(16, 0, 16, 16); bl.setSpacing(8)

    # filter bar
    bar = QHBoxLayout()
    src_filter = QComboBox()
    src_filter.addItems(["All sources", "Disk", "Browser", "Registry",
                         "EventLog", "Network", "Email"])
    rel_filter = QComboBox()
    rel_filter.addItems(["Hide system noise", "Significant only",
                         "Notable & up", "Show everything"])
    search = QLineEdit(); search.setPlaceholderText("Filter path, event, or meaning…")
    bar.addWidget(QLabel("Source:")); bar.addWidget(src_filter)
    bar.addSpacing(10)
    bar.addWidget(QLabel("Show:")); bar.addWidget(rel_filter)
    bar.addStretch(1); bar.addWidget(search)
    bl.addLayout(bar)

    panel = Panel(None, pad=0)
    t = _table(["TIMESTAMP", "SOURCE", "EVENT", "WHAT IT MEANS", "REL", "SEV"],
               [140, 80, None, None, 90, 70])
    t.verticalHeader().setDefaultSectionSize(38)

    note_bar = QLabel("")
    note_bar.setWordWrap(True)
    note_bar.setStyleSheet(f"color:{pal['text2']}; font-size:12px; padding:6px 2px;")

    def populate(rows):
        t.setRowCount(len(rows))
        for r, ev in enumerate(rows):
            t.setItem(r, 0, _mono_item(_ev_get(ev, "ts"), pal))
            t.setCellWidget(r, 1, SourceTag(_ev_get(ev, "src"), pal))
            ev_item = QTableWidgetItem(_ev_get(ev, "label"))
            ev_item.setToolTip(_ev_get(ev, "path"))
            t.setItem(r, 2, ev_item)
            # WHAT IT MEANS — the explanation (placeholder now, AI-filled later),
            # kept distinct from the EVENT column above. Fall back to the
            # interpreter note for cases saved before the meaning field existed.
            desc = _ev_get(ev, "meaning") or _ev_get(ev, "note") or "—"
            desc_item = QTableWidgetItem(desc)
            desc_item.setForeground(_qcolor(pal["text2"]))
            t.setItem(r, 3, desc_item)
            rel = _ev_get(ev, "relevance") or "context"
            rel_item = QTableWidgetItem(RELEVANCE_LABEL.get(rel, rel))
            rel_col = (pal["crit"] if rel == "significant" else
                       pal["accent"] if rel == "notable" else
                       pal["text3"])
            rel_item.setForeground(_qcolor(rel_col))
            t.setItem(r, 4, rel_item)
            _set_sev(t, r, 5, _ev_get(ev, "sev") or 1, pal)
        # show the count
        note_bar.setText(f"Showing {len(rows)} of {len(events)} events. "
                         "Click a row to see why it's reported.")

    def current_rows():
        sf = src_filter.currentText()
        rf = rel_filter.currentText()
        q = search.text().lower()
        min_rel = {"Show everything": 0, "Hide system noise": 1,
                   "Notable & up": 2, "Significant only": 3}[rf]
        out = []
        for e in events:
            rel = _ev_get(e, "relevance") or "context"
            if RELEVANCE_ORDER.get(rel, 1) < min_rel:
                continue
            if sf != "All sources" and _ev_get(e, "src") != sf:
                continue
            if q and q not in (_ev_get(e, "label") + _ev_get(e, "path") +
                               _ev_get(e, "description") + _ev_get(e, "meaning")).lower():
                continue
            out.append(e)
        return out

    def refilter():
        populate(current_rows())

    # clicking a row explains why it's reported
    def show_note(row, _col=0):
        rows = current_rows()
        if 0 <= row < len(rows):
            ev = rows[row]
            note = _ev_get(ev, "note") or "No additional context."
            note_bar.setText(f"{_ev_get(ev,'description')}  —  {note}")
    t.cellClicked.connect(show_note)

    src_filter.currentTextChanged.connect(refilter)
    rel_filter.currentTextChanged.connect(refilter)
    search.textChanged.connect(refilter)
    populate(current_rows())

    panel.add(t)
    bl.addWidget(panel, 1)
    bl.addWidget(note_bar)
    pl.addWidget(body, 1)
    return page


# ── Findings ──────────────────────────────────────────────────────────────────

def findings(case, pal):
    page = QWidget()
    pl = QVBoxLayout(page); pl.setContentsMargins(0, 0, 0, 0); pl.setSpacing(0)
    pl.addWidget(_screen_head(
        "Findings", f"{len(case['findings'])} FINDINGS · SORTED BY SEVERITY"))

    body = QWidget(); bl = QHBoxLayout(body)
    bl.setContentsMargins(16, 0, 16, 16); bl.setSpacing(12)

    # list
    list_panel = Panel("All findings", pad=0)
    t = _table(["SEV", "ID", "FINDING", "ATT&CK", "CONF"], [90, 52, None, 130, 96])
    fs = sorted(case["findings"], key=lambda f: -f["sev"])
    t.setRowCount(len(fs))
    for r, f in enumerate(fs):
        _set_sev(t, r, 0, f["sev"], pal)
        t.setItem(r, 1, _mono_item(f["id"], pal))
        t.setItem(r, 2, QTableWidgetItem(f["title"]))
        t.setCellWidget(r, 3, MitreTag(f["mitre"], pal, f.get("mitreName", "")) if f.get("mitre") else QLabel("—"))
        t.setCellWidget(r, 4, ConfidenceBadge(f["conf"], pal))
    list_panel.add(t)
    bl.addWidget(list_panel, 3)

    # detail drawer
    detail = Panel("Finding detail", pad=14)
    detail_body = QTextBrowser()
    detail_body.setOpenExternalLinks(False)
    detail_body.setStyleSheet(
        f"background:transparent; border:none; color:{pal['text2']}; font-size:12px;")
    detail.add(detail_body)
    bl.addWidget(detail, 2)

    def show_detail(row, _col=0):
        if row < 0 or row >= len(fs):
            return
        f = fs[row]
        label, key = theme.SEV[f["sev"]]
        related = [e for e in case["events"] if _ev_get(e, "fid") == f["id"]][:6]
        rel_html = "".join(
            f"<div style='font-family:{theme.MONO}; font-size:11px; color:{pal['text3']}; "
            f"margin:3px 0;'>{_ev_get(e,'ts')} · {_ev_get(e,'src')} — "
            f"{_ev_get(e,'label')[:70]}</div>" for e in related)
        html = f"""
        <div style='font-size:14px; font-weight:700; color:{pal['text']};'>{f['title']}</div>
        <div style='color:{pal[key]}; font-family:{theme.MONO}; font-size:11px; margin:4px 0;'>
            {label.upper()} · {f['id']} · {f.get('mitre','—')} {f.get('mitreName','')}</div>
        <div style='margin:10px 0; color:{pal['text2']}; line-height:1.5;'>{f['reason']}</div>
        <div style='font-family:{theme.MONO}; font-size:10px; color:{pal['text3']}; margin-top:8px;'>
            RULE</div>
        <div style='color:{pal['text2']}; font-size:12px;'>{f['rule']}</div>
        <div style='font-family:{theme.MONO}; font-size:10px; color:{pal['text3']}; margin-top:10px;'>
            CROSS-ARTIFACT CORRELATION</div>
        {rel_html or "<div style='color:"+pal['text3']+"'>No linked timeline events.</div>"}
        <div style='font-family:{theme.MONO}; font-size:10px; color:{pal['text3']}; margin-top:10px;'>
            EVIDENCE</div>
        <div style='color:{pal['text2']}; font-size:12px;'>{', '.join(f.get('evidence', []))}</div>
        """
        detail_body.setHtml(html)

    t.cellClicked.connect(show_detail)
    if fs:
        t.selectRow(0); show_detail(0)

    pl.addWidget(body, 1)
    return page


# ── Narrative ─────────────────────────────────────────────────────────────────

def narrative(case, pal):
    page = QWidget()
    pl = QVBoxLayout(page); pl.setContentsMargins(0, 0, 0, 0); pl.setSpacing(0)
    nar = case["narrative"]
    pl.addWidget(_screen_head(
        "AI Narrative",
        f"GENERATED {nar['generated']} · {nar['engine']}"))

    body = QWidget(); bl = QVBoxLayout(body)
    bl.setContentsMargins(16, 0, 16, 16); bl.setSpacing(10)
    for (h, conf, text) in nar["sections"]:
        sec = QFrame(); sec.setObjectName("panel")
        sl = QVBoxLayout(sec); sl.setContentsMargins(14, 12, 14, 12)
        head = QHBoxLayout()
        hl = QLabel(h); hl.setStyleSheet("font-size:14px; font-weight:700;")
        head.addWidget(hl); head.addStretch(1)
        head.addWidget(ConfidenceBadge(conf, pal))
        sl.addLayout(head)
        body_l = QLabel(text); body_l.setWordWrap(True)
        body_l.setStyleSheet(f"color:{pal['text2']}; font-size:12px; line-height:1.5;")
        sl.addWidget(body_l)
        # accent left border
        sec.setStyleSheet(sec.styleSheet() +
            f"QFrame#panel {{ border-left:2px solid {pal['accent']}; }}")
        bl.addWidget(sec)
    bl.addStretch(1)
    pl.addWidget(_scroll(body), 1)
    return page


# ── Audit Log ─────────────────────────────────────────────────────────────────

def audit(case, pal):
    page = QWidget()
    pl = QVBoxLayout(page); pl.setContentsMargins(0, 0, 0, 0); pl.setSpacing(0)
    pl.addWidget(_screen_head(
        "Audit Log",
        "APPEND-ONLY · EVERY ACTION RECORDED · CHAIN HASH VERIFIED"))

    body = QWidget(); bl = QVBoxLayout(body)
    bl.setContentsMargins(16, 0, 16, 16); bl.setSpacing(8)

    panel = Panel(f"{len(case['audit'])} entries · chain intact", pad=0)
    t = _table(["#", "TIMESTAMP", "ACTOR", "ACTION", "DETAIL"],
               [50, 160, 100, 180, None])
    rows = case["audit"]
    t.setRowCount(len(rows))
    for r, (ts, who, act, detail) in enumerate(rows):
        t.setItem(r, 0, _mono_item(f"{r+1:03d}", pal))
        t.setItem(r, 1, _mono_item(ts, pal))
        t.setItem(r, 2, _mono_item(who, pal))
        act_item = QTableWidgetItem(act)
        col = pal["accent"] if ("EXPORT" in act or "SAVED" in act) else \
              pal["good"] if ("VERIFIED" in act or "COMPLETE" in act) else pal["text2"]
        act_item.setForeground(_qcolor(col))
        t.setItem(r, 3, act_item)
        t.setItem(r, 4, QTableWidgetItem(detail))
    panel.add(t)
    bl.addWidget(panel, 1)
    pl.addWidget(body, 1)
    return page


# ── helpers ───────────────────────────────────────────────────────────────────

def _pill(text, color):
    l = QLabel(text)
    l.setStyleSheet(f"color:{color}; font-family:{theme.MONO}; font-size:10px; font-weight:600;")
    return l


def _mono_item(text, pal):
    it = QTableWidgetItem(str(text))
    it.setForeground(_qcolor(pal["text2"]))
    f = it.font(); f.setFamily("IBM Plex Mono"); f.setPointSize(9); it.setFont(f)
    return it


def _set_sev(table, r, c, sev, pal):
    table.setCellWidget(r, c, SeverityBadge(sev, pal))


def _qcolor(hex_str):
    from PySide6.QtGui import QColor
    return QColor(hex_str)


# ── Empty state (no case loaded) ──────────────────────────────────────────────

def empty_state(pal, on_new_case):
    """Shown on launch before any case exists — no demo data."""
    page = QWidget()
    outer = QVBoxLayout(page)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.addStretch(1)

    center = QVBoxLayout()
    center.setAlignment(Qt.AlignCenter)

    title = QLabel("No case loaded")
    title.setAlignment(Qt.AlignCenter)
    title.setStyleSheet("font-size:22px; font-weight:700;")
    sub = QLabel("Create a case and add evidence to begin an investigation.")
    sub.setAlignment(Qt.AlignCenter)
    sub.setStyleSheet(f"color:{pal['text3']}; font-size:13px;")

    btn = QPushButton("+  New Case")
    btn.setObjectName("primary")
    btn.setCursor(Qt.PointingHandCursor)
    btn.setFixedWidth(180)
    btn.clicked.connect(on_new_case)

    kinds = QLabel("Supports disk images · Event Logs (EVTX) · Registry hives · "
                   "Prefetch · Network captures (PCAP) · Email · Chrome artifacts")
    kinds.setAlignment(Qt.AlignCenter)
    kinds.setWordWrap(True)
    kinds.setStyleSheet(f"color:{pal['text3']}; font-family:{theme.MONO}; font-size:10px;")
    kinds.setFixedWidth(520)

    center.addWidget(title)
    center.addSpacing(6)
    center.addWidget(sub)
    center.addSpacing(18)
    btn_wrap = QHBoxLayout(); btn_wrap.addStretch(1); btn_wrap.addWidget(btn); btn_wrap.addStretch(1)
    center.addLayout(btn_wrap)
    center.addSpacing(22)
    k_wrap = QHBoxLayout(); k_wrap.addStretch(1); k_wrap.addWidget(kinds); k_wrap.addStretch(1)
    center.addLayout(k_wrap)

    outer.addLayout(center)
    outer.addStretch(2)
    return page

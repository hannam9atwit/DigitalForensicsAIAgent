"""
gui_v2/report_pdf.py

The exported PDF — the actual deliverable the Report screen composes.

It mirrors the paper preview rather than being a separate design: same serif
headings, same rust accent, same section order, same footer. What the examiner
saw is what they get.

The document is written to be read by someone who is not a forensic examiner —
a lawyer, HR, a court. So each finding leads with what happened in plain English
and only then cites its technique and evidence, and the chain-of-custody and
read-only statements are stated explicitly rather than assumed.

    pip install reportlab
"""

import datetime

ACCENT = "#B3572D"
TEXT = "#1B1B1F"
TEXT2 = "#55555E"
TEXT3 = "#8B8B96"
LINE = "#E4E4EA"

SEV_HEX = {
    "CRITICAL": "#C24B51", "HIGH": "#C0763A", "MEDIUM": "#A88A3A", "LOW": "#3D8B63",
    # tolerate the pipeline's numeric severities
    4: "#C24B51", 3: "#C0763A", 2: "#A88A3A", 1: "#3D8B63",
}
SEV_LABEL = {4: "CRITICAL", 3: "HIGH", 2: "MEDIUM", 1: "LOW"}


def _sev(f):
    s = f.get("sev", "LOW")
    return SEV_LABEL.get(s, s) if not isinstance(s, str) else s.upper()


def _esc(t):
    return (str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _get(ev, key, default=""):
    """Read an event whether it is a dict or a legacy tuple."""
    if isinstance(ev, dict):
        return ev.get(key, default)
    order = ["ts", "src", "label", "path", "sev", "fid"]
    return ev[order.index(key)] if key in order and order.index(key) < len(ev) else default


def generate_report(case: dict, out_path: str) -> str:
    """Build the PDF at out_path from the case dict. Returns out_path.

    `case["findings"]` is expected to be already filtered to what the examiner
    chose to include; `case["examinerNotes"]` carries their remarks.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
        PageBreak,
    )

    meta = case.get("caseMeta", {})
    rep = case.get("report", {})
    findings = case.get("findings", [])
    evidence = case.get("evidence", [])
    events = case.get("events", [])
    audit = case.get("audit", [])
    notes = (case.get("examinerNotes") or "").strip()

    base = getSampleStyleSheet()

    def st(name, parent="Normal", **kw):
        return ParagraphStyle(name, parent=base[parent], **kw)

    s_letter = st("Letter", fontName="Courier", fontSize=7.5,
                  textColor=colors.HexColor(TEXT3), spaceAfter=6)
    s_title = st("Title2", fontName="Times-Bold", fontSize=21,
                 textColor=colors.HexColor(TEXT), spaceAfter=4, leading=25)
    s_byline = st("Byline", fontSize=9, textColor=colors.HexColor(TEXT2),
                  spaceAfter=8, leading=13)
    s_h2 = st("H2", fontName="Times-Bold", fontSize=13.5,
              textColor=colors.HexColor(TEXT), spaceBefore=16, spaceAfter=5)
    s_body = st("Body", fontSize=9.5, leading=15, spaceAfter=5,
                textColor=colors.HexColor(TEXT))
    s_fname = st("FName", fontSize=10.5, leading=14, spaceAfter=2,
                 textColor=colors.HexColor(TEXT))
    s_src = st("Src", fontName="Courier", fontSize=7.5,
               textColor=colors.HexColor(TEXT3), spaceAfter=9)
    s_small = st("Small", fontSize=8, textColor=colors.HexColor(TEXT2), leading=12)
    s_foot = st("Foot", fontName="Courier", fontSize=7,
                textColor=colors.HexColor(TEXT3), leading=11)
    # Table cells only wrap when they hold a Paragraph; a bare string overflows
    # into the neighbouring column instead.
    s_cell = st("Cell", fontSize=7, leading=9.5, textColor=colors.HexColor(TEXT))

    def cell(text):
        return Paragraph(_esc(text), s_cell)

    doc = SimpleDocTemplate(
        out_path, pagesize=A4,
        leftMargin=2.2 * cm, rightMargin=2.2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
        title=f"Forensic Report {meta.get('id','')}",
        author=str(meta.get("examiner", "")))
    story = []

    # ── letterhead ────────────────────────────────────────────────────────────
    story.append(Paragraph(
        f"{_esc(meta.get('id','—'))} &middot; {_esc(meta.get('agency','—'))} "
        f"&middot; CONFIDENTIAL", s_letter))
    story.append(Paragraph(_esc(rep.get("title", "Report of Digital Forensic "
                                                "Examination")), s_title))
    story.append(Paragraph(_esc(rep.get("byline", "")), s_byline))
    story.append(HRFlowable(width="100%", thickness=1.4,
                            color=colors.HexColor(TEXT), spaceAfter=2))

    # ── 1. executive summary ──────────────────────────────────────────────────
    story.append(Paragraph("1. Executive Summary", s_h2))
    story.append(Paragraph(_esc(rep.get("summary", "")), s_body))

    # ── 2. findings ───────────────────────────────────────────────────────────
    story.append(Paragraph(f"2. Findings ({len(findings)} included)", s_h2))
    if not findings:
        story.append(Paragraph(
            "No findings were included in this report.", s_body))
    for i, f in enumerate(findings, start=1):
        sev = _sev(f)
        story.append(Paragraph(
            f"{i}. {_esc(f.get('title',''))} "
            f'<font size="7" color="{SEV_HEX.get(sev, TEXT2)}">'
            f'<b>{_esc(sev)}</b></font>', s_fname))
        story.append(Paragraph(
            _esc(f.get("what") or f.get("reason") or ""), s_body))
        bits = [f.get("id", "")]
        if f.get("mitre") and f.get("mitre") != "—":
            name = f.get("mitreName")
            bits.append(f"ATT&amp;CK {_esc(f['mitre'])}"
                        + (f" ({_esc(name)})" if name else ""))
        if f.get("conf"):
            bits.append(f"Confidence {_esc(f['conf'])}")
        refs = f.get("ev") or f.get("evidence") or []
        if refs:
            bits.append("Evidence " + _esc(", ".join(refs)))
        story.append(Paragraph(" &middot; ".join(bits), s_src))

    # ── 3. examiner remarks ───────────────────────────────────────────────────
    if notes:
        story.append(Paragraph("3. Examiner Remarks", s_h2))
        for para in notes.split("\n"):
            if para.strip():
                story.append(Paragraph(_esc(para), s_body))

    # ── chain of custody ──────────────────────────────────────────────────────
    story.append(Paragraph("Chain of Custody", s_h2))
    story.append(Paragraph(
        "Every artifact below was fingerprinted with SHA-256 on intake and "
        "opened read-only. No evidence file was modified or executed at any "
        "point during the examination.", s_small))
    story.append(Spacer(1, 0.25 * cm))
    coc = [["ID", "Artifact", "Type", "Size", "SHA-256 (intake)", "Integrity"]]
    for e in evidence:
        h = e.get("sha") or e.get("sha256", "")
        coc.append([
            e.get("id", ""), cell(e.get("name", "")),
            cell(e.get("kindLabel") or e.get("type", "")), e.get("size", ""),
            (h[:12] + "…" + h[-6:]) if h else "—",
            "VERIFIED" if e.get("verified") else "PENDING",
        ])
    t = Table(coc, colWidths=[1.2 * cm, 3.6 * cm, 3.4 * cm, 1.8 * cm, 4.4 * cm,
                              2.2 * cm], repeatRows=1)
    t.setStyle(_table_style(colors))
    story.append(t)

    # ── appendices ────────────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph("Appendix A — Event Timeline", s_h2))

    # System noise is summarised, not listed: pages of $MFT records would bury
    # the events that matter, which is the problem this redesign set out to fix.
    sig = [e for e in events if _get(e, "rel", _get(e, "relevance", "")) != "noise"]
    hidden = len(events) - len(sig)
    if hidden:
        story.append(Paragraph(
            f"{hidden} routine NTFS system-metadata records ($MFT, $Bitmap and "
            f"similar, present on every Windows volume) are omitted as "
            f"non-evidential. The {len(sig)} interpreted events below are those "
            f"bearing on the case.", s_small))
        story.append(Spacer(1, 0.25 * cm))

    tl = [["Timestamp", "Source", "What happened", "What it means"]]
    for e in sig:
        tl.append([
            cell(_get(e, "ts")), cell(_get(e, "src")),
            cell(str(_get(e, "label"))),
            cell(str(_get(e, "mean") or _get(e, "meaning")
                     or _get(e, "description"))),
        ])
    if len(tl) == 1:
        tl.append(["—", "—", cell("No interpreted events were recorded."), ""])
    t = Table(tl, colWidths=[2.9 * cm, 1.8 * cm, 5.6 * cm, 6.3 * cm], repeatRows=1)
    t.setStyle(_table_style(colors))
    story.append(t)

    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("Appendix B — Audit Trail", s_h2))
    story.append(Paragraph(
        "This log is append-only. It records every action taken on the case.",
        s_small))
    story.append(Spacer(1, 0.25 * cm))
    au = [["#", "Timestamp", "Actor", "Action", "Detail"]]
    for i, a in enumerate(audit, start=1):
        if isinstance(a, dict):
            ts, who, act, detail = a["ts"], a["who"], a["act"], a["detail"]
        else:
            ts, who, act, detail = a
        au.append([f"{i:03d}", cell(ts), cell(who), cell(act), cell(str(detail))])
    t = Table(au, colWidths=[1 * cm, 3 * cm, 2.2 * cm, 3.6 * cm, 6.8 * cm],
              repeatRows=1)
    t.setStyle(_table_style(colors))
    story.append(t)

    story.append(Spacer(1, 0.5 * cm))
    story.append(HRFlowable(width="100%", thickness=0.5,
                            color=colors.HexColor(LINE), spaceAfter=6))
    for line in str(rep.get("footer", "")).split("\n"):
        story.append(Paragraph(_esc(line), s_foot))

    def _page(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Courier", 6.5)
        canvas.setFillColor(colors.HexColor(TEXT3))
        canvas.drawString(2.2 * cm, 1.2 * cm,
                          f"Forensic AI Agent · Case {meta.get('id','')} · "
                          f"CONFIDENTIAL")
        canvas.drawRightString(A4[0] - 2.2 * cm, 1.2 * cm, f"Page {doc_.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_page, onLaterPages=_page)
    return out_path


def _table_style(colors):
    from reportlab.platypus import TableStyle
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F8F8FA")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor(TEXT3)),
        ("FONTNAME", (0, 0), (-1, 0), "Courier-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor(TEXT)),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor(LINE)),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#EFEFF3")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ])

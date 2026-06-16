"""
gui_v2/report_pdf.py

Generates a professional forensic investigation report (PDF) populated from a
case dict — the same shape the GUI screens render. Uses reportlab.

Layout:
  - Cover block (case id, title, examiner, agency, date, risk badge)
  - Case summary stats (evidence / findings by severity / events)
  - Chain of custody table (artifacts + SHA-256 + verified)
  - AI narrative sections
  - Findings detail (severity, MITRE, confidence, reasoning, evidence)
  - Full timeline appendix
  - Audit trail appendix

    pip install reportlab
"""

import datetime

SEV_LABEL = {4: "Critical", 3: "High", 2: "Medium", 1: "Low"}
SEV_HEX = {4: "#C0392B", 3: "#D35400", 2: "#B7950B", 1: "#1E8449"}
ACCENT = "#2C3E70"


def _ev(ev, key):
    """Read an event whether dict (current) or legacy tuple."""
    if isinstance(ev, dict):
        return ev.get(key, "")
    order = ["ts", "src", "label", "path", "sev", "fid"]
    return ev[order.index(key)] if key in order and order.index(key) < len(ev) else ""


def generate_report(case: dict, out_path: str) -> str:
    """Build the PDF at out_path from the case dict. Returns out_path."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, PageBreak,
    )

    meta = case["caseMeta"]
    findings = case.get("findings", [])
    evidence = case.get("evidence", [])
    events = case.get("events", [])
    narrative = case.get("narrative", {})
    audit = case.get("audit", [])

    sev_counts = {4: 0, 3: 0, 2: 0, 1: 0}
    for f in findings:
        sev_counts[f.get("sev", 1)] = sev_counts.get(f.get("sev", 1), 0) + 1

    base = getSampleStyleSheet()

    def st(name, parent="Normal", **kw):
        return ParagraphStyle(name, parent=base[parent], **kw)

    s_cover = st("Cover", "Title", fontSize=22, textColor=colors.white,
                 alignment=TA_CENTER, spaceAfter=2)
    s_coversub = st("CoverSub", fontSize=11, textColor=colors.HexColor("#AEB7C8"),
                    alignment=TA_CENTER)
    s_h2 = st("H2", fontSize=14, textColor=colors.HexColor(ACCENT),
              spaceBefore=14, spaceAfter=6, fontName="Helvetica-Bold")
    s_h3 = st("H3", fontSize=11, textColor=colors.HexColor(ACCENT),
              spaceBefore=8, spaceAfter=3, fontName="Helvetica-Bold")
    s_body = st("Body", fontSize=9.5, leading=14, spaceAfter=6,
                textColor=colors.HexColor("#1A1A2E"))
    s_small = st("Small", fontSize=8, textColor=colors.HexColor("#555577"))

    def esc(t):
        return (str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    doc = SimpleDocTemplate(out_path, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm,
                            title=f"Forensic Report {meta['id']}")
    story = []

    # ── cover ──────────────────────────────────────────────────────────────────
    cover = Table([[Paragraph("FORENSIC INVESTIGATION REPORT", s_cover)],
                   [Paragraph(esc(meta["title"]), s_coversub)]],
                  colWidths=[17*cm])
    cover.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#1E2A52")),
        ("TOPPADDING", (0, 0), (-1, 0), 22),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 18),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
    ]))
    story.append(cover)
    story.append(Spacer(1, 0.4*cm))

    risk = meta.get("riskScore", 0)
    risk_label = meta.get("riskLabel", "—")
    info = Table([
        ["Case number", meta["id"], "Risk score", f"{risk}/100 ({risk_label})"],
        ["Examiner", f"{meta['examiner']} ({meta['examinerId']})", "Opened", meta["opened"]],
        ["Agency", meta.get("agency", "—"), "Report date",
         datetime.datetime.now().strftime("%Y-%m-%d %H:%M")],
    ], colWidths=[3*cm, 5.5*cm, 3*cm, 5.5*cm])
    info.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#555577")),
        ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#555577")),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTNAME", (3, 0), (3, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, colors.HexColor("#DDDDE5")),
    ]))
    story.append(info)
    story.append(Spacer(1, 0.4*cm))

    # ── summary stats ──────────────────────────────────────────────────────────
    verified = sum(1 for e in evidence if e.get("verified"))
    stat = Table([[
        Paragraph(f"<b>{len(evidence)}</b><br/>Artifacts", _statstyle(st, colors)),
        Paragraph(f"<b>{verified}</b><br/>Verified", _statstyle(st, colors)),
        Paragraph(f"<b>{sev_counts[4]+sev_counts[3]}</b><br/>Critical/High", _statstyle(st, colors)),
        Paragraph(f"<b>{len(findings)}</b><br/>Findings", _statstyle(st, colors)),
        Paragraph(f"<b>{len(events)}</b><br/>Events", _statstyle(st, colors)),
    ]], colWidths=[3.4*cm]*5)
    stat.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor(SEV_HEX[4])),
        ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#1E8449")),
        ("BACKGROUND", (2, 0), (2, 0), colors.HexColor(SEV_HEX[3])),
        ("BACKGROUND", (3, 0), (3, 0), colors.HexColor(ACCENT)),
        ("BACKGROUND", (4, 0), (4, 0), colors.HexColor("#555577")),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    story.append(stat)
    story.append(Spacer(1, 0.5*cm))

    # ── chain of custody ───────────────────────────────────────────────────────
    story.append(Paragraph("Chain of Custody", s_h2))
    story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor(ACCENT)))
    coc = [["ID", "Artifact", "Type", "Size", "SHA-256 (intake)", "Integrity"]]
    for e in evidence:
        h = e.get("sha256", "")
        coc.append([e["id"], esc(e["name"]), esc(e.get("type", "")), e.get("size", ""),
                    (h[:10] + "…" + h[-8:]) if h else "—",
                    "VERIFIED" if e.get("verified") else "PENDING"])
    coc_t = Table(coc, colWidths=[1.2*cm, 4*cm, 3.6*cm, 1.8*cm, 4.4*cm, 2*cm], repeatRows=1)
    coc_t.setStyle(_table_style(colors))
    story.append(coc_t)
    story.append(Spacer(1, 0.3*cm))

    # ── narrative ──────────────────────────────────────────────────────────────
    if narrative.get("sections"):
        story.append(Paragraph("Investigative Narrative", s_h2))
        story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor(ACCENT)))
        story.append(Paragraph(f"Generated by {esc(narrative.get('engine','—'))}", s_small))
        story.append(Spacer(1, 0.15*cm))
        for sec in narrative["sections"]:
            h, conf, text = sec
            story.append(Paragraph(esc(h), s_h3))
            story.append(Paragraph(esc(text), s_body))

    # ── findings ───────────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph("Findings", s_h2))
    story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor(ACCENT)))
    if not findings:
        story.append(Paragraph("No findings were identified.", s_body))
    for f in sorted(findings, key=lambda x: -x.get("sev", 1)):
        sev = f.get("sev", 1)
        pill = Table([[Paragraph(
            f"<b>{f['id']} · {SEV_LABEL[sev].upper()}</b> &nbsp; {esc(f.get('title',''))}",
            st("Pill", fontSize=10, textColor=colors.white))]], colWidths=[17*cm])
        pill.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(SEV_HEX[sev])),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(Spacer(1, 0.15*cm))
        story.append(pill)
        meta_line = []
        if f.get("mitre"):
            meta_line.append(f"<b>MITRE ATT&amp;CK:</b> {esc(f['mitre'])} {esc(f.get('mitreName',''))}")
        meta_line.append(f"<b>Confidence:</b> {esc(f.get('conf','—'))}")
        meta_line.append(f"<b>Time:</b> {esc(f.get('ts','—'))}")
        if f.get("evidence"):
            meta_line.append(f"<b>Evidence:</b> {esc(', '.join(f['evidence']))}")
        story.append(Paragraph(" &nbsp;|&nbsp; ".join(meta_line), s_small))
        if f.get("reason"):
            story.append(Paragraph(esc(f["reason"]), s_body))
        if f.get("rule"):
            story.append(Paragraph(f"<i>{esc(f['rule'])}</i>", s_small))

    story.append(PageBreak())

    # ── timeline appendix ──────────────────────────────────────────────────────
    story.append(Paragraph("Appendix A — Event Timeline", s_h2))
    story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor(ACCENT)))
    # report on the events that carry meaning; pure NTFS system-noise is summarised
    # rather than listed row-by-row so the appendix stays readable.
    sig = [e for e in events if _ev(e, "relevance") != "noise"]
    noise_n = len(events) - len(sig)
    if noise_n:
        story.append(Paragraph(
            f"{noise_n} standard NTFS system-metadata events (present on every "
            f"Windows volume) are omitted from this listing as non-evidential. "
            f"{len(sig)} interpreted events are shown below.", s_small))
        story.append(Spacer(1, 0.15*cm))
    tl = [["Timestamp", "Source", "Event", "What it means", "Sev"]]
    for ev in sig:
        means = _ev(ev, "meaning") or _ev(ev, "note") or _ev(ev, "description")
        tl.append([_ev(ev, "ts"), _ev(ev, "src"),
                   esc(str(_ev(ev, "label"))[:60]),
                   esc(str(means)[:70]),
                   SEV_LABEL.get(_ev(ev, "sev"), "")])
    if len(tl) == 1:
        tl.append(["—", "—", "No non-system events were recorded.", "", ""])
    tl_t = Table(tl, colWidths=[3.1*cm, 1.8*cm, 5.2*cm, 5.3*cm, 1.6*cm], repeatRows=1)
    tl_t.setStyle(_table_style(colors))
    story.append(tl_t)
    story.append(Spacer(1, 0.3*cm))

    # ── audit appendix ─────────────────────────────────────────────────────────
    story.append(Paragraph("Appendix B — Audit Trail", s_h2))
    story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor(ACCENT)))
    au = [["Timestamp", "Actor", "Action", "Detail"]]
    for a in audit:
        ts, who, act, detail = a
        au.append([ts, who, act, esc(detail[:80])])
    au_t = Table(au, colWidths=[3.4*cm, 2.4*cm, 3.6*cm, 7.6*cm], repeatRows=1)
    au_t.setStyle(_table_style(colors))
    story.append(au_t)

    # footer with page numbers
    def _footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#999999"))
        canvas.drawString(2*cm, 1.2*cm,
                          f"Forensic AI Agent · Case {meta['id']} · CONFIDENTIAL")
        canvas.drawRightString(19*cm, 1.2*cm, f"Page {doc_.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return out_path


def _statstyle(st, colors):
    from reportlab.lib.enums import TA_CENTER
    return st("Stat", fontSize=9, textColor=colors.white, alignment=TA_CENTER)


def _table_style(colors):
    from reportlab.platypus import TableStyle
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2C3E70")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#F2F4F9")]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#DDDDE5")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ])

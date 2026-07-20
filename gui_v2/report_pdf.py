"""
gui_v2/report_pdf.py

The exported PDF — the actual deliverable the Report screen composes.

The document is written to be read by someone who is not a forensic examiner:
a lawyer, HR, a court. Each finding leads with plain English and only then
gives the technical detail; the chain of custody shows complete hashes; and
the closing section states plainly that this is a preliminary automated
assessment for examiner review, not a legal determination.

════════════════════════════════════════════════════════════════════════════
AI INSERTION SLOTS — for the narrative layer (populate these, nothing else):

    case["narrative"]["executive_summary"]  -> Section 1 paragraph
    finding["explanation"]                  -> per-finding plain-language text
    finding["technical"]                    -> per-finding technical detail
    case["narrative"]["conclusion"]         -> Conclusion narrative

Every slot has a deterministic fallback built from the case data, so the
report is always complete and never breaks when a slot is empty. All text —
AI-written or not — passes through _clean() at render time, which strips
markdown characters, converts raw epoch timestamps to human dates, and
removes em-dashes. Do not rely on the AI producing well-formed output.
════════════════════════════════════════════════════════════════════════════

    pip install reportlab
"""

import datetime
import re

ACCENT = "#B3572D"
TEXT = "#1B1B1F"
TEXT2 = "#55555E"
TEXT3 = "#8B8B96"
LINE = "#E4E4EA"

SEV_HEX = {
    "CRITICAL": "#C24B51", "HIGH": "#C0763A", "MEDIUM": "#A88A3A", "LOW": "#3D8B63",
    4: "#C24B51", 3: "#C0763A", 2: "#A88A3A", 1: "#3D8B63",
}
SEV_LABEL = {4: "CRITICAL", 3: "HIGH", 2: "MEDIUM", 1: "LOW"}
SEV_RANK = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}

SEV_MEANING = {
    "CRITICAL": "direct evidence of the central harmful activity in this case",
    "HIGH": "strong evidence that materially advances the case narrative",
    "MEDIUM": "supporting evidence that is circumstantial on its own",
    "LOW": "context that informs the case without indicating wrongdoing",
}

# NTFS volumes carry a creation timestamp that often surfaces as apparent
# "activity" decades old; flag it rather than presenting it as an event.
_NTFS_PLACEHOLDER_YEARS = (2008, 2009)

_MARKDOWN_CHARS = re.compile(r"(\*\*|__|\*|`|^#+\s*|^\s*[•▪‣]\s*)", re.MULTILINE)
_EPOCH_PATTERN = re.compile(r"\b(1[0-9]{9})\b")
_MULTISPACE = re.compile(r"[ \t]{2,}")


def _sev(finding):
    value = finding.get("sev", "LOW")
    return SEV_LABEL.get(value, value) if not isinstance(value, str) else value.upper()


def _esc(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def _epoch_to_date(match):
    stamp = int(match.group(1))
    try:
        moment = datetime.datetime.utcfromtimestamp(stamp)
    except (ValueError, OSError, OverflowError):
        return match.group(1)
    rendered = moment.strftime("%Y-%m-%d %H:%M:%S")
    if moment.year in _NTFS_PLACEHOLDER_YEARS:
        return f"{rendered} (volume-creation placeholder)"
    return rendered


def _clean(text):
    """Render-time sanitizer applied to every free-text string.

    Strips markdown characters, converts bare epoch timestamps to human
    dates, replaces em/en-dashes with plain punctuation, and collapses the
    whitespace those removals leave behind. AI text is never trusted to be
    well-formed; deterministic text goes through the same door so the rule
    holds everywhere.
    """
    cleaned = str(text)
    cleaned = _MARKDOWN_CHARS.sub("", cleaned)
    cleaned = _EPOCH_PATTERN.sub(_epoch_to_date, cleaned)
    cleaned = cleaned.replace(" — ", ", ").replace("—", ", ")
    cleaned = cleaned.replace(" – ", ", ").replace("–", "-")
    cleaned = _MULTISPACE.sub(" ", cleaned)
    return cleaned.strip()


def _plural(count, noun):
    return f"{count} {noun}{'' if count == 1 else 's'}"


def _get(event, key, default=""):
    """Read an event whether it is a dict or a legacy tuple."""
    if isinstance(event, dict):
        return event.get(key, default)
    order = ["ts", "src", "label", "path", "sev", "fid"]
    if key in order and order.index(key) < len(event):
        return event[order.index(key)]
    return default


# Preserved alias: external notes/tools refer to this helper as _ev().
_ev = _get


_ATTRIBUTE_SUFFIX = re.compile(r"\s*\(\$(FILE_NAME|STANDARD_INFORMATION|SI|FN)\)\s*$",
                               re.IGNORECASE)


def _dedupe_events(events):
    """Collapse NTFS attribute variants and exact repeats to one row each.

    $FILE_NAME and $STANDARD_INFORMATION both emit an event for the same file
    action, so every file otherwise appears two or three times. Rows are
    keyed on (timestamp, label-with-attribute-suffix-stripped); the first
    occurrence wins and its label is shown without the suffix.
    """
    seen = set()
    unique_events = []
    for event in events:
        label = str(_get(event, "label"))
        base_label = _ATTRIBUTE_SUFFIX.sub("", label)
        key = (str(_get(event, "ts")), base_label.lower())
        if key in seen:
            continue
        seen.add(key)
        if isinstance(event, dict) and base_label != label:
            event = {**event, "label": base_label}
        unique_events.append(event)
    return unique_events


def _interpretation(event):
    """The 'what it means' cell, only when it adds something.

    The source data sometimes carries the label copied into the meaning
    field; printing the same sentence twice side by side tells the reader
    nothing, so an interpretation identical to the event text renders blank.
    """
    label = str(_get(event, "label")).strip()
    meaning = str(_get(event, "mean") or _get(event, "meaning")
                  or _get(event, "description") or "").strip()
    if not meaning or meaning.lower() == label.lower():
        return ""
    return meaning


def _deterministic_summary(meta, findings, evidence, events):
    """Executive-summary fallback: examined, found, how serious."""
    sev_counts = {}
    for finding in findings:
        label = _sev(finding)
        sev_counts[label] = sev_counts.get(label, 0) + 1

    examined = (f"This examination covered {_plural(len(evidence), 'artifact')} "
                f"and interpreted {len(events):,} events.")

    if not findings:
        found = ("No findings crossed the reporting threshold. The interpreted "
                 "timeline remains available in Appendix A for review.")
        seriousness = ""
    else:
        breakdown = ", ".join(
            f"{count} {label.lower()}" for label, count in sorted(
                sev_counts.items(), key=lambda item: -SEV_RANK.get(item[0], 0)))
        found = (f"The analysis produced {_plural(len(findings), 'finding')} "
                 f"({breakdown}).")
        top = _top_finding(findings)
        seriousness = (f"The most significant is {top.get('id', '')}: "
                       f"{top.get('title', '')}."
                       if top else "")

    risk = meta.get("riskLabel") or ""
    score = meta.get("riskScore")
    risk_line = (f"Overall assessed risk is {risk.lower()} "
                 f"({score}/100)." if risk and score is not None else "")

    return " ".join(part for part in
                    (examined, found, seriousness, risk_line) if part)


def _top_finding(findings):
    if not findings:
        return None
    return max(findings, key=lambda f: SEV_RANK.get(_sev(f), 0))


def _finding_plain_fallback(finding):
    """Plain-language paragraph built from the finding's own fields."""
    what = finding.get("what") or finding.get("short") or finding.get("reason") or ""
    return what


def _finding_technical_fallback(finding):
    """Technical paragraph: the reasoning plus the mechanism."""
    return finding.get("why") or ""


def _severity_reason(finding):
    label = _sev(finding)
    return SEV_MEANING.get(label, "evidence relevant to the case")


def _confidence_reason(finding):
    conf = str(finding.get("conf", "")).strip()
    if not conf:
        return ""
    reasons = {
        "high": "multiple independent artifacts corroborate it",
        "medium": "the evidence is recorded but rests partly on interpretation",
        "low": "the evidence is circumstantial and needs corroboration",
    }
    reason = reasons.get(conf.lower(), "")
    return f"{conf}" + (f", because {reason}" if reason else "")


def _deterministic_conclusion(meta, findings):
    """Conclusion-narrative fallback: the collective read of the evidence."""
    if not findings:
        return ("Across the artifacts examined, no activity crossed the "
                "reporting threshold. Absence of findings at this threshold is "
                "not proof of absence of activity; the interpreted timeline "
                "should still be reviewed.")

    top = _top_finding(findings)
    high_confidence = sum(1 for f in findings
                          if str(f.get("conf", "")).lower() == "high")
    parts = [
        (f"Taken together, the {_plural(len(findings), 'finding')} form a "
         f"consistent picture, anchored by {top.get('id', '')} "
         f"({top.get('title', '')})."),
    ]
    if high_confidence:
        parts.append(f"{_plural(high_confidence, 'finding')} carry high "
                     f"confidence, resting on directly recorded artifacts.")
    caption = (meta.get("riskCaption") or "").strip()
    if caption:
        parts.append(caption)
    return " ".join(parts)


def _chunk_hash(digest):
    """Full 64-char hash in 8-character groups so it wraps and stays legible."""
    digest = str(digest)
    return " ".join(digest[i:i + 8] for i in range(0, len(digest), 8))


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
        SimpleDocTemplate, Paragraph, Spacer, Table, HRFlowable, PageBreak,
    )

    meta = case.get("caseMeta", {})
    rep = case.get("report", {})
    narrative = case.get("narrative", {}) or {}
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
    s_title = st("Title2", fontName="Times-Bold", fontSize=22,
                 textColor=colors.HexColor(TEXT), spaceAfter=4, leading=26)
    s_byline = st("Byline", fontSize=9, textColor=colors.HexColor(TEXT2),
                  spaceAfter=10, leading=13)
    s_h2 = st("H2", fontName="Times-Bold", fontSize=14,
              textColor=colors.HexColor(TEXT), spaceBefore=18, spaceAfter=6)
    s_h3 = st("H3", fontName="Helvetica-Bold", fontSize=9,
              textColor=colors.HexColor(TEXT2), spaceBefore=8, spaceAfter=3)
    s_body = st("Body", fontSize=9.5, leading=15, spaceAfter=6,
                textColor=colors.HexColor(TEXT))
    s_bullet = st("Bullet2", fontSize=9.5, leading=14, spaceAfter=3,
                  leftIndent=14, bulletIndent=4,
                  textColor=colors.HexColor(TEXT))
    s_fname = st("FName", fontName="Helvetica-Bold", fontSize=10.5, leading=14,
                 spaceBefore=10, spaceAfter=3, textColor=colors.HexColor(TEXT))
    s_src = st("Src", fontName="Courier", fontSize=7.5,
               textColor=colors.HexColor(TEXT3), spaceBefore=2, spaceAfter=4)
    s_small = st("Small", fontSize=8, textColor=colors.HexColor(TEXT2), leading=12)
    s_foot = st("Foot", fontName="Courier", fontSize=7,
                textColor=colors.HexColor(TEXT3), leading=11)
    s_cell = st("Cell", fontSize=7, leading=9.5, textColor=colors.HexColor(TEXT))
    s_hash = st("Hash", fontName="Courier", fontSize=6.4, leading=8.5,
                textColor=colors.HexColor(TEXT))

    def cell(text):
        return Paragraph(_esc(_clean(text)), s_cell)

    def body(text, style=s_body):
        return Paragraph(_esc(_clean(text)), style)

    def bullets(items):
        return [Paragraph(_esc(_clean(item)), s_bullet, bulletText="–")
                for item in items]

    doc = SimpleDocTemplate(
        out_path, pagesize=A4,
        leftMargin=2.2 * cm, rightMargin=2.2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
        title=f"Forensic Report {meta.get('id', '')}",
        author=str(meta.get("examiner", "")))
    story = []

    # Sections number themselves so an omitted section (e.g. no examiner
    # remarks) never leaves a gap in the sequence.
    section_counter = {"n": 0}

    def section(title):
        section_counter["n"] += 1
        return Paragraph(f"{section_counter['n']}. {title}", s_h2)

    # ── letterhead ───────────────────────────────────────────────────────────
    story.append(Paragraph(
        f"{_esc(meta.get('id', '-'))} &middot; {_esc(meta.get('agency', '-'))} "
        f"&middot; CONFIDENTIAL", s_letter))
    story.append(Paragraph(
        _esc(_clean(rep.get("title", "Report of Digital Forensic Examination"))),
        s_title))
    story.append(Paragraph(_esc(_clean(rep.get("byline", ""))), s_byline))
    story.append(HRFlowable(width="100%", thickness=1.4,
                            color=colors.HexColor(TEXT), spaceAfter=2))

    # ── 1. executive summary ─────────────────────────────────────────────────
    story.append(section("Executive Summary"))
    summary_text = (narrative.get("executive_summary") or "").strip() \
        or _deterministic_summary(meta, findings, evidence, events)
    story.append(body(summary_text))

    if findings:
        story.append(Paragraph("Key findings", s_h3))
        story.extend(bullets(
            f"{f.get('id', '')} ({_sev(f)}): {f.get('short') or f.get('title', '')}"
            for f in findings))

        next_steps = _collect_next_steps(findings)
        if next_steps:
            story.append(Paragraph("Recommended actions", s_h3))
            story.extend(bullets(next_steps[:5]))

    # ── 2. findings ──────────────────────────────────────────────────────────
    story.append(section(
        f"Findings ({_plural(len(findings), 'finding')} included)"))
    findings_section_number = section_counter["n"]
    if not findings:
        story.append(body("No findings were included in this report."))

    for index, finding in enumerate(findings, start=1):
        severity = _sev(finding)
        story.append(Paragraph(
            f"{findings_section_number}.{index}&nbsp;&nbsp;"
            f"{_esc(_clean(finding.get('title', '')))} "
            f'<font size="7.5" color="{SEV_HEX.get(severity, TEXT2)}">'
            f"<b>{_esc(severity)}</b></font>", s_fname))
        story.append(Paragraph(
            f"Severity {_esc(severity.lower())}: "
            f"{_esc(_severity_reason(finding))}.", s_small))

        plain = (finding.get("explanation") or "").strip() \
            or _finding_plain_fallback(finding)
        if plain:
            story.append(Paragraph("What was found", s_h3))
            story.append(body(plain))

        technical = (finding.get("technical") or "").strip() \
            or _finding_technical_fallback(finding)
        if technical:
            story.append(Paragraph("Technical detail", s_h3))
            story.append(body(technical))

        next_actions = finding.get("next") or []
        if next_actions:
            story.append(Paragraph("What the examiner should do next", s_h3))
            story.extend(bullets(next_actions))

        trailer_bits = [finding.get("id", "")]
        conf = _confidence_reason(finding)
        if conf:
            trailer_bits.append(f"Confidence {_esc(_clean(conf))}")
        if finding.get("mitre") and finding.get("mitre") != "-":
            mitre_name = finding.get("mitreName")
            trailer_bits.append(
                f"ATT&amp;CK {_esc(finding['mitre'])}"
                + (f" ({_esc(_clean(mitre_name))})" if mitre_name else ""))
        refs = finding.get("ev") or finding.get("evidence") or []
        if refs:
            trailer_bits.append("Evidence " + _esc(", ".join(refs)))
        story.append(Paragraph(" &middot; ".join(trailer_bits), s_src))

    # ── 3. examiner remarks ──────────────────────────────────────────────────
    if notes:
        story.append(section("Examiner Remarks"))
        for paragraph in notes.split("\n"):
            if paragraph.strip():
                story.append(body(paragraph))

    # ── 4. conclusion ────────────────────────────────────────────────────────
    story.append(section("Conclusion"))
    conclusion_text = (narrative.get("conclusion") or "").strip() \
        or _deterministic_conclusion(meta, findings)
    story.append(body(conclusion_text))

    story.append(Paragraph("Assessment recap", s_h3))
    recap = _recap_rows(meta, findings)
    recap_table = Table(
        [[Paragraph(f"<b>{_esc(label)}</b>", s_cell), cell(value)]
         for label, value in recap],
        colWidths=[4.2 * cm, 12.4 * cm])
    recap_table.setStyle(_table_style(colors, header=False))
    story.append(recap_table)
    story.append(Spacer(1, 0.2 * cm))
    story.append(body(
        "This is a preliminary automated assessment produced for examiner "
        "review. It is not a legal determination, and its findings should be "
        "verified against the underlying artifacts before being relied upon.",
        s_small))

    # ── chain of custody ─────────────────────────────────────────────────────
    story.append(Paragraph("Chain of Custody", s_h2))
    story.append(body(
        "Every artifact below was fingerprinted with SHA-256 on intake and "
        "opened read-only. No evidence file was modified or executed at any "
        "point during the examination. Hashes are shown complete, in "
        "8-character groups for legibility.", s_small))
    story.append(Spacer(1, 0.25 * cm))

    custody = [["ID", "Artifact", "Type / Size", "SHA-256 (intake, complete)",
                "Integrity"]]
    for artifact in evidence:
        digest = artifact.get("sha") or artifact.get("sha256", "")
        custody.append([
            artifact.get("id", ""),
            cell(artifact.get("name", "")),
            cell(f"{artifact.get('kindLabel') or artifact.get('type', '')}\n"
                 f"{artifact.get('size', '')}"),
            Paragraph(_esc(_chunk_hash(digest)) if digest else "-", s_hash),
            "VERIFIED" if artifact.get("verified") else "PENDING",
        ])
    custody_table = Table(
        custody,
        colWidths=[1.2 * cm, 3.4 * cm, 2.8 * cm, 7.2 * cm, 2 * cm],
        repeatRows=1)
    custody_table.setStyle(_table_style(colors))
    story.append(custody_table)

    # ── appendix A: timeline ─────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph("Appendix A: Event Timeline", s_h2))

    visible = [e for e in events
               if _get(e, "rel", _get(e, "relevance", "")) != "noise"]
    hidden_count = len(events) - len(visible)
    deduped = _dedupe_events(visible)
    collapsed_count = len(visible) - len(deduped)

    caption_parts = []
    if hidden_count:
        caption_parts.append(
            f"{hidden_count} routine NTFS system-metadata records ($MFT, "
            f"$Bitmap and similar, present on every Windows volume) are "
            f"omitted as non-evidential.")
    if collapsed_count:
        caption_parts.append(
            f"{collapsed_count} NTFS attribute variants ($FILE_NAME rows "
            f"duplicating the same file action) are collapsed so each event "
            f"appears once.")
    caption_parts.append(
        f"The {len(deduped)} interpreted events below are those bearing on "
        f"the case.")
    story.append(body(" ".join(caption_parts), s_small))
    story.append(Spacer(1, 0.25 * cm))

    timeline = [["Timestamp", "Source", "Event", "Interpretation"]]
    for event in deduped:
        timeline.append([
            cell(_get(event, "ts")), cell(_get(event, "src")),
            cell(str(_get(event, "label"))),
            cell(_interpretation(event)),
        ])
    if len(timeline) == 1:
        timeline.append(["-", "-", cell("No interpreted events were recorded."),
                         ""])
    timeline_table = Table(
        timeline, colWidths=[2.9 * cm, 1.8 * cm, 6 * cm, 5.9 * cm],
        repeatRows=1)
    timeline_table.setStyle(_table_style(colors))
    story.append(timeline_table)

    # ── appendix B: audit trail ──────────────────────────────────────────────
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("Appendix B: Audit Trail", s_h2))
    story.append(body(
        "This log is append-only. It records every action taken on the case.",
        s_small))
    story.append(Spacer(1, 0.25 * cm))

    audit_rows = [["#", "Timestamp", "Actor", "Action", "Detail"]]
    for index, entry in enumerate(audit, start=1):
        if isinstance(entry, dict):
            ts, who, act, detail = (entry["ts"], entry["who"], entry["act"],
                                    entry["detail"])
        else:
            ts, who, act, detail = entry
        audit_rows.append([f"{index:03d}", cell(ts), cell(who), cell(act),
                           cell(str(detail))])
    audit_table = Table(
        audit_rows, colWidths=[1 * cm, 3 * cm, 2.2 * cm, 3.6 * cm, 6.8 * cm],
        repeatRows=1)
    audit_table.setStyle(_table_style(colors))
    story.append(audit_table)

    story.append(Spacer(1, 0.5 * cm))
    story.append(HRFlowable(width="100%", thickness=0.5,
                            color=colors.HexColor(LINE), spaceAfter=6))
    for line in str(rep.get("footer", "")).split("\n"):
        story.append(Paragraph(_esc(_clean(line)), s_foot))

    def _page(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Courier", 6.5)
        canvas.setFillColor(colors.HexColor(TEXT3))
        canvas.drawString(2.2 * cm, 1.2 * cm,
                          f"AIRforensics · Case {meta.get('id', '')} · "
                          f"CONFIDENTIAL")
        canvas.drawRightString(A4[0] - 2.2 * cm, 1.2 * cm, f"Page {doc_.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_page, onLaterPages=_page)
    return out_path


def _collect_next_steps(findings):
    """Prioritized next steps: highest-severity findings' actions first,
    de-duplicated in order."""
    ordered = sorted(findings, key=lambda f: -SEV_RANK.get(_sev(f), 0))
    steps = []
    for finding in ordered:
        for step in finding.get("next") or []:
            if step not in steps:
                steps.append(step)
    return steps


def _recap_rows(meta, findings):
    sev_counts = {}
    for finding in findings:
        label = _sev(finding)
        sev_counts[label] = sev_counts.get(label, 0) + 1
    breakdown = ", ".join(
        f"{count} {label.lower()}" for label, count in sorted(
            sev_counts.items(), key=lambda item: -SEV_RANK.get(item[0], 0))) \
        or "none"

    top = _top_finding(findings)
    steps = _collect_next_steps(findings)

    risk_label = meta.get("riskLabel") or "-"
    risk_score = meta.get("riskScore")
    risk_value = (f"{risk_label} ({risk_score}/100)"
                  if risk_score is not None else risk_label)

    return [
        ("Overall risk", risk_value),
        ("Findings", f"{len(findings)} total: {breakdown}"),
        ("Most significant",
         f"{top.get('id', '')}: {top.get('title', '')}" if top else "none"),
        ("Priority next step", steps[0] if steps else "review the timeline"),
    ]


def _table_style(colors, header=True):
    from reportlab.platypus import TableStyle
    rules = [
        ("FONTNAME", (0, 1 if header else 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("TEXTCOLOR", (0, 1 if header else 0), (-1, -1),
         colors.HexColor(TEXT)),
        ("LINEBELOW", (0, 1 if header else 0), (-1, -1), 0.25,
         colors.HexColor("#EFEFF3")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
    if header:
        rules += [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F8F8FA")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor(TEXT3)),
            ("FONTNAME", (0, 0), (-1, 0), "Courier-Bold"),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor(LINE)),
        ]
    return TableStyle(rules)

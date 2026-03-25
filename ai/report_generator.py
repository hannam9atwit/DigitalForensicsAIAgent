"""
ai/report_generator.py

Generates both a Markdown report and a styled PDF report.
PDF uses reportlab (pure Python, no external dependencies beyond pip install).

Install:  pip install reportlab
"""

import os
import re
import datetime
import reportlab
from reportlab.lib.units import cm
from reportlab.platypus import Spacer, Paragraph

SEVERITY_LABELS = {4: "Critical", 3: "High", 2: "Medium", 1: "Low"}
SEVERITY_COLORS_HEX = {4: "#c0392b", 3: "#e67e22", 2: "#e6b800", 1: "#27ae60"}


class ReportGenerator:

    def generate(self, analysis_result, output_path="forensic_report.md"):
        print("[*] Generating forensic report...")

        md_path  = output_path
        pdf_path = output_path.replace(".md", ".pdf")

        md_text = self._build_markdown(analysis_result)

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_text)

        try:
            self._build_pdf(analysis_result, md_text, pdf_path)
            print(f"[+] PDF report: {pdf_path}")
        except ImportError:
            print("[~] reportlab not installed — PDF skipped. Run: pip install reportlab")
        except Exception as e:
            print(f"[~] PDF generation failed: {e}")

        return md_path

    # ── Markdown ──────────────────────────────────────────────────────────────

    def _build_markdown(self, result: dict) -> str:
        findings  = result.get("findings", [])
        anomalies = result.get("anomalies", [])
        timeline  = result.get("timeline", {}).get("events", [])
        narrative = result.get("narrative", "")
        summary   = result.get("summary", {})

        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            "# Forensic Analysis Report",
            f"*Generated: {now}*",
            "",
            "---",
            "",
        ]

        # AI Narrative (the main body)
        if narrative:
            lines.append(narrative)
            lines.append("")
            lines.append("---")
            lines.append("")

        # Raw findings appendix
        lines.append("## Appendix A — Raw Findings")
        groups = {4: [], 3: [], 2: [], 1: []}
        for f in findings:
            groups.setdefault(f.get("severity", 1), []).append(f)

        for sev in [4, 3, 2, 1]:
            label = SEVERITY_LABELS.get(sev, str(sev))
            lines.append(f"### {label} Severity ({len(groups[sev])} findings)")
            if not groups[sev]:
                lines.append("*None.*")
            else:
                for f in sorted(groups[sev], key=lambda x: x.get("timestamp") or 0):
                    reason = f.get("reason") or f.get("path") or "(no details)"
                    lines.append(f"- **{f['type']}** — {reason}")
            lines.append("")

        # Anomalies appendix
        lines.append("## Appendix B — Raw Anomalies")
        if not anomalies:
            lines.append("*No anomalies detected.*")
        else:
            for a in sorted(anomalies, key=lambda x: x.get("severity", 1), reverse=True):
                sev_label = SEVERITY_LABELS.get(a.get("severity", 1), "Low")
                reason    = a.get("reason") or "(no details)"
                lines.append(f"- **[{sev_label}] {a['type']}** — {reason}")
        lines.append("")

        return "\n".join(lines)

    # ── PDF ───────────────────────────────────────────────────────────────────

    def _build_pdf(self, result: dict, md_text: str, pdf_path: str):
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, HRFlowable,
            Table, TableStyle, PageBreak,
        )
        from reportlab.lib.enums import TA_LEFT, TA_CENTER

        doc = SimpleDocTemplate(
            pdf_path,
            pagesize=A4,
            leftMargin=2.2*cm, rightMargin=2.2*cm,
            topMargin=2.5*cm,  bottomMargin=2.5*cm,
        )

        # ── Colour palette ────────────────────────────────────────────────────
        DARK_BG    = colors.HexColor("#1e1e2e")
        ACCENT     = colors.HexColor("#89b4fa")
        TEXT       = colors.HexColor("#1a1a2e")
        SUBTLE     = colors.HexColor("#555577")
        SEV_COLORS = {
            4: colors.HexColor("#c0392b"),
            3: colors.HexColor("#e67e22"),
            2: colors.HexColor("#e6b800"),
            1: colors.HexColor("#27ae60"),
        }

        # ── Styles ────────────────────────────────────────────────────────────
        base = getSampleStyleSheet()

        def style(name, parent="Normal", **kw):
            s = ParagraphStyle(name, parent=base[parent], **kw)
            return s

        s_title = style("ReportTitle", "Title",
                        fontSize=24, textColor=colors.white,
                        spaceAfter=6, alignment=TA_CENTER)
        s_subtitle = style("Subtitle", fontSize=11,
                           textColor=colors.HexColor("#aaaacc"),
                           spaceAfter=4, alignment=TA_CENTER)
        s_h2   = style("H2", fontSize=14, textColor=ACCENT,
                       spaceBefore=14, spaceAfter=6, fontName="Helvetica-Bold")
        s_h3   = style("H3", fontSize=11, textColor=ACCENT,
                       spaceBefore=10, spaceAfter=4, fontName="Helvetica-Bold")
        s_body = style("Body", fontSize=9.5, textColor=TEXT,
                       leading=14, spaceAfter=6)
        s_code = style("Code", fontSize=8, fontName="Courier",
                       textColor=colors.HexColor("#334455"),
                       backColor=colors.HexColor("#f0f0f8"),
                       leftIndent=10, spaceAfter=4, leading=12)
        s_bullet = style("Bullet", fontSize=9.5, textColor=TEXT,
                         leading=13, leftIndent=14, spaceAfter=3,
                         bulletIndent=4)

        story = []

        # ── Cover block ───────────────────────────────────────────────────────
        cover_data = [[
            Paragraph("FORENSIC INVESTIGATION REPORT", s_title),
        ]]
        cover_table = Table(cover_data, colWidths=[16.6*cm])
        cover_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), DARK_BG),
            ("TOPPADDING",    (0, 0), (-1, -1), 20),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 20),
            ("LEFTPADDING",   (0, 0), (-1, -1), 16),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 16),
            ("ROUNDEDCORNERS", [6]),
        ]))
        story.append(cover_table)
        story.append(Spacer(1, 0.3*cm))

        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        story.append(Paragraph(f"Generated: {now} | Forensic AI Agent", s_subtitle))
        story.append(Spacer(1, 0.5*cm))

        # ── Summary stats bar ─────────────────────────────────────────────────
        summary   = result.get("summary", {})
        findings  = result.get("findings", [])
        anomalies = result.get("anomalies", [])

        crit_count = len([f for f in findings if f.get("severity", 1) >= 3])
        anom_count = len(anomalies)
        wiped      = sum(1 for e in result.get("timeline", {}).get("events", [])
                         if e.get("metadata_wiped"))

        stats_data = [
            [
                Paragraph(f"<b>{crit_count}</b><br/>Critical/High<br/>Findings",
                          style("SC", fontSize=10, textColor=colors.white, alignment=TA_CENTER)),
                Paragraph(f"<b>{anom_count}</b><br/>Anomalies<br/>Detected",
                          style("SA", fontSize=10, textColor=colors.white, alignment=TA_CENTER)),
                Paragraph(f"<b>{wiped}</b><br/>Wiped<br/>Records",
                          style("SW", fontSize=10, textColor=colors.white, alignment=TA_CENTER)),
                Paragraph(f"<b>{len(findings)}</b><br/>Total<br/>Findings",
                          style("ST", fontSize=10, textColor=colors.white, alignment=TA_CENTER)),
            ]
        ]
        stats_table = Table(stats_data, colWidths=[4.15*cm]*4)
        stats_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), SEV_COLORS[4]),
            ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#1565c0")),
            ("BACKGROUND", (2, 0), (2, 0), SEV_COLORS[3]),
            ("BACKGROUND", (3, 0), (3, 0), SUBTLE),
            ("TOPPADDING",    (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(stats_table)
        story.append(Spacer(1, 0.6*cm))
        story.append(HRFlowable(width="100%", thickness=1,
                                color=ACCENT, spaceAfter=10))

        # ── Narrative sections ────────────────────────────────────────────────
        narrative = result.get("narrative", "")
        if narrative:
            story += self._render_narrative(narrative, s_h2, s_h3, s_body,
                                            s_code, s_bullet)

        story.append(PageBreak())

        # ── Appendix A — Raw Findings ─────────────────────────────────────────
        story.append(Paragraph("Appendix A — Raw Findings by Severity", s_h2))
        story.append(HRFlowable(width="100%", thickness=0.5,
                                color=ACCENT, spaceAfter=6))

        groups = {4: [], 3: [], 2: [], 1: []}
        for f in findings:
            groups.setdefault(f.get("severity", 1), []).append(f)

        for sev in [4, 3, 2, 1]:
            label   = SEVERITY_LABELS[sev]
            sev_col = SEV_COLORS[sev]
            if not groups[sev]:
                continue

            # Severity header pill
            pill_data = [[Paragraph(
                f"<b>{label.upper()} — {len(groups[sev])} finding(s)</b>",
                style(f"Pill{sev}", fontSize=9.5,
                      textColor=colors.white, alignment=TA_CENTER))]]
            pill = Table(pill_data, colWidths=[16.6*cm])
            pill.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), sev_col),
                ("TOPPADDING",    (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]))
            story.append(pill)
            story.append(Spacer(1, 0.15*cm))

            # Finding rows
            for f in sorted(groups[sev], key=lambda x: x.get("timestamp") or 0):
                reason = f.get("reason") or f.get("path") or "(no details)"
                story.append(Paragraph(
                    f"<b>{f['type']}</b> — {self._esc(reason)}", s_body))

            story.append(Spacer(1, 0.3*cm))

        # ── Appendix B — Anomalies ────────────────────────────────────────────
        story.append(Paragraph("Appendix B — Anomalies", s_h2))
        story.append(HRFlowable(width="100%", thickness=0.5,
                                color=ACCENT, spaceAfter=6))
        if not anomalies:
            story.append(Paragraph("No anomalies detected.", s_body))
        else:
            for a in sorted(anomalies, key=lambda x: x.get("severity", 1), reverse=True):
                sev_label = SEVERITY_LABELS.get(a.get("severity", 1), "Low")
                reason    = a.get("reason") or "(no details)"
                story.append(Paragraph(
                    f"<b>[{sev_label}] {a['type']}</b> — {self._esc(reason)}", s_body))

        doc.build(story)

    # ── Markdown → ReportLab flowables ───────────────────────────────────────

    def _render_narrative(self, text, s_h2, s_h3, s_body, s_code, s_bullet):
        flowables = []
        for line in text.split("\n"):
            stripped = line.strip()
            if not stripped:
                flowables.append(Spacer(1, 0.15*cm))
                continue
            if stripped == "---":
                from reportlab.platypus import HRFlowable
                from reportlab.lib import colors
                flowables.append(HRFlowable(
                    width="100%", thickness=0.5,
                    color=colors.HexColor("#89b4fa"), spaceAfter=6))
                continue
            if stripped.startswith("## "):
                flowables.append(Paragraph(stripped[3:], s_h2))
            elif stripped.startswith("### "):
                flowables.append(Paragraph(stripped[4:], s_h3))
            elif stripped.startswith(("- ", "• ", "* ")):
                content = self._md_inline(stripped[2:])
                flowables.append(Paragraph(f"• {content}", s_bullet))
            elif re.match(r"^\d+\. ", stripped):
                content = self._md_inline(re.sub(r"^\d+\. ", "", stripped))
                num     = re.match(r"^(\d+)\. ", stripped).group(1)
                flowables.append(Paragraph(f"{num}. {content}", s_bullet))
            elif stripped.startswith("|"):
                # Markdown table — render as plain text for simplicity
                flowables.append(Paragraph(
                    self._esc(stripped), s_code))
            else:
                flowables.append(Paragraph(self._md_inline(stripped), s_body))
        return flowables

    @staticmethod
    def _md_inline(text: str) -> str:
        """Convert **bold** and `code` to ReportLab XML tags."""
        text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
        text = re.sub(r"`(.+?)`", r"<font name='Courier'>\1</font>", text)
        return text

    @staticmethod
    def _esc(text: str) -> str:
        """Escape characters that break ReportLab XML parsing."""
        return (str(text)
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))

    def group_findings_by_severity(self, findings):
        groups = {4: [], 3: [], 2: [], 1: []}
        for f in findings:
            groups.setdefault(f.get("severity", 1), []).append(f)
        return groups
from ai.refinement_engine import RefinementEngine


class NarrativeEngine:
    """
    Generates a human-readable narrative based on structured findings,
    anomalies, and timeline events.

    When an ANTHROPIC_API_KEY is set, the RefinementEngine will send the
    structured data to Claude and return a genuine LLM-written narrative.
    When no key is present, the deterministic fallback is used instead.
    """

    def __init__(self):
        self.refiner = RefinementEngine()

    def generate(self, analysis: dict) -> str:
        findings  = analysis.get("findings", [])
        anomalies = analysis.get("anomalies", [])
        timeline  = analysis.get("timeline", {}).get("events", [])
        summary   = analysis.get("summary", {})

        # Build the structured markdown scaffold — used as the fallback
        # narrative and as context for the LLM prompt.
        narrative = []

        narrative.append("## AI Narrative Summary\n")
        narrative.append(self._generate_overview(summary, findings, anomalies))
        narrative.append("\n")

        narrative.append("## Key Findings Explained\n")
        narrative.append(self._generate_findings_story(findings))
        narrative.append("\n")

        narrative.append("## Anomaly Interpretation\n")
        narrative.append(self._generate_anomaly_story(anomalies))
        narrative.append("\n")

        narrative.append("## Timeline Narrative\n")
        narrative.append(self._generate_timeline_story(timeline))
        narrative.append("\n")

        narrative.append("## Recommendations\n")
        narrative.append(self._generate_recommendations(findings, anomalies))

        raw = "\n".join(narrative)

        # Pass BOTH the raw scaffold AND the full structured analysis to the
        # refiner so the LLM has maximum context, and the fallback has text.
        refined = self.refiner.refine(raw, analysis=analysis)
        return refined

    # ============================================================
    # Narrative scaffold builders (used for fallback + LLM context)
    # ============================================================

    def _generate_overview(self, summary, findings, anomalies):
        fc = summary.get("finding_count", len(findings))
        ac = summary.get("anomaly_count", len(anomalies))
        return (
            f"The forensic analysis identified **{fc} findings** and "
            f"**{ac} anomalies**. These signals indicate notable filesystem "
            f"activity, including deleted files, timestamp inconsistencies, "
            f"and unusual NTFS metadata behavior. The following sections "
            f"provide a detailed narrative interpretation of these events."
        )

    def _generate_findings_story(self, findings):
        if not findings:
            return "No significant findings were detected.\n"
        lines = []
        for f in findings:
            reason = f.get("reason") or f.get("path")
            lines.append(f"- **{f['type']}** — {reason}")
        return "\n".join(lines)

    def _generate_anomaly_story(self, anomalies):
        if not anomalies:
            return "No anomalies were detected.\n"
        lines = []
        for a in anomalies:
            reason = a.get("reason") or a.get("path")
            lines.append(f"- **{a['type']}** — {reason}")
        return "\n".join(lines)

    def _generate_timeline_story(self, timeline):
        if not timeline:
            return "No timeline events were available.\n"

        lines = []
        lines.append(
            "The timeline shows a sequence of filesystem events, including "
            "file creations, deletions, metadata updates, and system activity bursts."
        )

        earliest = timeline[0]["timestamp"]
        latest   = timeline[-1]["timestamp"]
        lines.append(
            f"The earliest recorded event occurred at timestamp `{earliest}`, "
            f"and the latest at `{latest}`."
        )

        burst_count = sum(1 for e in timeline if e["timestamp"] == earliest)
        if burst_count > 10:
            lines.append(
                f"A significant cluster of events occurred around `{earliest}`, "
                f"suggesting system initialization or mass file operations."
            )

        return "\n".join(lines)

    def _generate_recommendations(self, findings, anomalies):
        recs = []

        if any(f["type"] == "deleted_user_file" for f in findings):
            recs.append("- Recover deleted files using `icat` or carving tools.")

        if any(f["type"] == "timestamp_anomaly" for f in findings):
            recs.append("- Investigate potential timestomping or anti-forensic behavior.")

        if any(f["type"] == "orphaned_file" for f in findings):
            recs.append("- Examine orphaned MFT entries for unlinked file remnants.")

        if any(f["type"] == "alternate_data_stream" for f in findings):
            recs.append("- Extract and inspect NTFS alternate data streams for hidden payloads.")

        if any(f["type"] == "large_badclus_stream" for f in findings):
            recs.append("- Investigate $BadClus:$Bad stream — possible anti-forensic bad cluster manipulation.")

        if any(a["type"] == "large_file" for a in anomalies):
            recs.append("- Inspect unusually large files for hidden or embedded data.")

        if any(a["type"] == "activity_burst" for a in anomalies):
            recs.append("- Review activity bursts for mass file creation or deletion events.")

        if any(a["type"] == "rare_extension" for a in anomalies):
            recs.append("- Investigate rare file extensions — may indicate obfuscated or uncommon file types.")

        if not recs:
            recs.append("- No specific recommendations. System appears normal.")

        return "\n".join(recs)
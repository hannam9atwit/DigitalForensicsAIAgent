import os
import json
import urllib.request
import urllib.error


class RefinementEngine:
    """
    Refines the structured forensic narrative using an LLM (Claude).
    Falls back to deterministic formatting if the API call fails or
    no API key is configured.
    """

    ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
    MODEL = "claude-opus-4-6"

    # System prompt: sets the LLM's role and output contract
    SYSTEM_PROMPT = """You are a senior digital forensics analyst writing an investigative report.
You will be given structured forensic data including findings, anomalies, and a timeline from a disk/browser analysis.
Your job is to produce a clear, professional narrative that:
- Explains what happened on the system in plain English
- Highlights the most significant findings and what they imply
- Calls out any signs of anti-forensic behavior, data deletion, or suspicious activity
- Groups related events into a coherent story rather than listing facts
- Uses precise forensic terminology where appropriate
- Ends with concrete, prioritized recommendations for the investigator

Write in a formal but readable tone. Use markdown headers and bullet points where they improve clarity.
Do NOT invent facts not present in the data. If the data is sparse, say so honestly.
Do NOT include any preamble like "Here is the narrative" — start directly with the report content."""

    def __init__(self):
        self.api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    def refine(self, raw_narrative: str, analysis: dict = None) -> str:
        """
        If an API key is available and analysis data is provided, call Claude
        to generate a real LLM narrative. Otherwise fall back to the
        deterministic formatter.

        Parameters
        ----------
        raw_narrative : str
            The pre-built markdown string from NarrativeEngine.
        analysis : dict, optional
            The full analysis dict (findings, anomalies, timeline, summary).
            When provided, this is sent to the LLM instead of the raw_narrative
            string, giving the model richer structured input.
        """
        if self.api_key and analysis is not None:
            try:
                return self._call_llm(analysis)
            except Exception as e:
                print(f"[!] LLM refinement failed: {e} — falling back to deterministic output")

        return self._deterministic_format(raw_narrative)

    # =========================================================
    # LLM Path
    # =========================================================

    def _call_llm(self, analysis: dict) -> str:
        """
        Builds a concise forensic context payload and sends it to Claude.
        We summarise rather than dump raw data to keep token usage sane.
        """
        prompt = self._build_prompt(analysis)

        payload = json.dumps({
            "model": self.MODEL,
            "max_tokens": 2048,
            "system": self.SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }).encode("utf-8")

        req = urllib.request.Request(
            self.ANTHROPIC_API_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01"
            },
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))

        # Extract text from the response content blocks
        texts = [
            block["text"]
            for block in body.get("content", [])
            if block.get("type") == "text"
        ]

        if not texts:
            raise ValueError("LLM returned no text content")

        return "\n".join(texts)

    def _build_prompt(self, analysis: dict) -> str:
        """
        Converts the analysis dict into a concise, token-efficient prompt.
        Caps findings/anomalies/timeline to avoid blowing the context window
        on large disk images.
        """
        summary = analysis.get("summary", {})
        findings = analysis.get("findings", [])
        anomalies = analysis.get("anomalies", [])
        timeline_events = analysis.get("timeline", {}).get("events", [])

        MAX_FINDINGS = 50
        MAX_ANOMALIES = 30
        MAX_TIMELINE  = 40

        # Slim each finding down to only the fields the LLM needs
        def slim_finding(f):
            return {
                "type":      f.get("type"),
                "severity":  f.get("severity"),
                "path":      f.get("path"),
                "reason":    f.get("reason"),
                "timestamp": f.get("timestamp"),
            }

        def slim_event(e):
            return {
                "timestamp": e.get("timestamp"),
                "source":    e.get("source"),
                "path":      e.get("path"),
                "size":      e.get("size"),
            }

        context = {
            "summary": summary,
            "findings": [slim_finding(f) for f in findings[:MAX_FINDINGS]],
            "findings_total": len(findings),
            "anomalies": [slim_finding(a) for a in anomalies[:MAX_ANOMALIES]],
            "anomalies_total": len(anomalies),
            "timeline_sample": [slim_event(e) for e in timeline_events[:MAX_TIMELINE]],
            "timeline_total": len(timeline_events),
        }

        return (
            "Please analyse the following forensic data and write a full investigative narrative.\n\n"
            f"```json\n{json.dumps(context, indent=2, default=str)}\n```"
        )

    # =========================================================
    # Deterministic Fallback
    # =========================================================

    def _deterministic_format(self, raw_narrative: str) -> str:
        """
        Original rule-based formatter, used when the LLM is unavailable.
        """
        paragraphs = raw_narrative.split("\n")
        refined = []

        for p in paragraphs:
            p = p.strip()
            if not p:
                continue

            if p.startswith("##"):
                refined.append(p)
                continue

            if p.startswith("- "):
                refined.append(p.replace("- ", "• "))
                continue

            if p.lower().startswith("the forensic analysis"):
                refined.append(
                    "An overview of the system's activity reveals several notable forensic signals. "
                    + p
                )
                continue

            refined.append(p)

        return "\n".join(refined)
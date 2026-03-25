"""
ai/refinement_engine.py

LLM integration layer for the forensic narrative engine.

Generates the forensic report one section at a time using few-shot prompting.
Supports two backends in priority order:
  1. Ollama (local, llama3.2:3b) — runs fully offline after first setup
  2. Anthropic Claude API — used when ANTHROPIC_API_KEY is set
  3. Deterministic fallback — used when no LLM is available
"""

import os
import json
import datetime
import urllib.request
from collections import Counter


# Shared persona prepended to every LLM call
_PERSONA = (
    "You are a digital forensics examiner writing a formal investigation report. "
    "IMPORTANT RULES:\n"
    "- Write ONLY the report text. Do not describe, explain, or comment on the data format.\n"
    "- Do NOT mention JSON, arrays, objects, properties, or data structures.\n"
    "- Do NOT say 'here is a breakdown', 'here are observations', or 'if you would like'.\n"
    "- Do NOT ask questions or offer to help further.\n"
    "- Write in English only. Write as the analyst who ran the investigation.\n"
    "- Be specific: name file paths, timestamps, and counts directly from the evidence.\n"
    "- Every sentence must state a forensic conclusion, not describe the data."
)

# Few-shot example injected into every section prompt
_FEW_SHOT = """
EXAMPLE OF WRONG OUTPUT (never do this):
"This is a JSON array of objects. Each object has properties: type, severity, reason, timestamp. There are 21 objects in the array. If you would like me to help process this data, feel free to ask."

EXAMPLE OF CORRECT OUTPUT (always do this):
"Twenty-one deleted directories were identified that still contain active child entries. This pattern is consistent with a deliberate but incomplete deletion attempt, where the parent directory was removed while its contents remained accessible. The absence of timestamps across all entries indicates the MFT metadata was subsequently wiped, a recognised anti-forensic technique."

Now write the section below. Begin writing the report immediately after "REPORT TEXT:".
"""


class RefinementEngine:

    OLLAMA_URL   = "http://localhost:11434/api/generate"
    OLLAMA_MODEL = "llama3.2:3b"

    ANTHROPIC_URL   = "https://api.anthropic.com/v1/messages"
    ANTHROPIC_MODEL = "claude-sonnet-4-5"

    def __init__(self):
        self.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    # ── Public entry point ────────────────────────────────────────────────────

    def refine(self, raw_narrative: str, analysis: dict = None) -> str:
        if analysis is None:
            return self._deterministic_format(raw_narrative)

        use_ollama    = self._ollama_available()
        use_anthropic = bool(self.anthropic_api_key)

        if not use_ollama and not use_anthropic:
            print("[~] No LLM available — using deterministic fallback")
            return self._deterministic_format(raw_narrative)

        ctx = self._build_context(analysis)

        sections = [
            ("## 1. Executive Summary",       self._prompt_executive_summary),
            ("## 2. Investigative Context",    self._prompt_investigative_context),
            ("## 3. Critical Findings",        self._prompt_critical_findings),
            ("## 4. Supporting Findings",      self._prompt_supporting_findings),
            ("## 5. Anomaly Analysis",         self._prompt_anomaly_analysis),
            ("## 6. Timeline Reconstruction",  self._prompt_timeline),
            ("## 7. Anti-Forensic Indicators", self._prompt_antiforensic),
            ("## 8. Browser Forensic Summary", self._prompt_browser),
            ("## 9. Evidence Preservation",    self._prompt_preservation),
            ("## 10. Conclusion",              self._prompt_conclusion),
        ]

        parts = []
        for heading, prompt_fn in sections:
            print(f"[*] Generating: {heading}")
            prompt = prompt_fn(ctx)
            try:
                if use_ollama:
                    text = self._call_ollama(prompt)
                elif use_anthropic:
                    text = self._call_anthropic(prompt)
                else:
                    text = "*(Section unavailable — no LLM configured)*"

                text = self._strip_preamble(text)

            except Exception as e:
                print(f"[!] LLM failed for {heading}: {e}")
                text = f"*Section could not be generated: {e}*"

            parts.append(f"{heading}\n\n{text.strip()}")

        return "\n\n---\n\n".join(parts)

    # ── LLM callers ───────────────────────────────────────────────────────────

    def _call_ollama(self, prompt: str) -> str:
        full_prompt = f"{_PERSONA}\n\n{_FEW_SHOT}\n\n{prompt}\n\nREPORT TEXT:"

        payload = json.dumps({
            "model":  self.OLLAMA_MODEL,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": 0.15,
                "num_predict": 600,
                "stop": ["---", "NOTE:", "IMPORTANT:", "If you"],
            },
        }).encode("utf-8")

        req = urllib.request.Request(
            self.OLLAMA_URL, data=payload,
            headers={"Content-Type": "application/json"}, method="POST")

        with urllib.request.urlopen(req, timeout=300) as resp:
            body = json.loads(resp.read().decode())

        text = body.get("response", "").strip()
        if not text:
            raise ValueError("Ollama returned empty response")
        return text

    def _call_anthropic(self, prompt: str) -> str:
        full_prompt = f"{_FEW_SHOT}\n\n{prompt}\n\nREPORT TEXT:"

        payload = json.dumps({
            "model":      self.ANTHROPIC_MODEL,
            "max_tokens": 1000,
            "system":     _PERSONA,
            "messages":   [{"role": "user", "content": full_prompt}],
        }).encode("utf-8")

        req = urllib.request.Request(
            self.ANTHROPIC_URL, data=payload,
            headers={
                "Content-Type":      "application/json",
                "x-api-key":         self.anthropic_api_key,
                "anthropic-version": "2023-06-01",
            }, method="POST")

        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode())

        texts = [b["text"] for b in body.get("content", []) if b.get("type") == "text"]
        if not texts:
            raise ValueError("Anthropic returned no text")
        return "\n".join(texts)

    def _ollama_available(self) -> bool:
        try:
            req = urllib.request.Request(
                "http://localhost:11434/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                body = json.loads(resp.read().decode())
            models = [m.get("name", "") for m in body.get("models", [])]
            print("[DEBUG] Ollama models found:", models)
            for preferred in ["llama3.2", "llama3.1", "llama"]:
                if any(preferred in m for m in models):
                    if any("llama3.2" in m for m in models):
                        self.OLLAMA_MODEL = "llama3.2:3b"
                    elif any("llama3.1" in m for m in models):
                        self.OLLAMA_MODEL = "llama3.1:8b"
                    print(f"[*] Using Ollama model: {self.OLLAMA_MODEL}")
                    return True
            return False
        except Exception as e:
            print("[DEBUG] Ollama check failed:", e)
            return False

    # ── Preamble stripper ─────────────────────────────────────────────────────

    def _strip_preamble(self, text: str) -> str:
        """Remove any boilerplate the model outputs before the actual report text."""
        if "REPORT TEXT:" in text:
            text = text.split("REPORT TEXT:", 1)[-1]

        bad_starts = (
            "here is", "here's", "below is", "the following",
            "this is a", "this data", "based on the",
            "i have", "i will", "let me", "sure,", "certainly",
            "of course", "as requested",
        )
        lines = text.strip().split("\n")
        while lines:
            first = lines[0].strip().lower()
            if any(first.startswith(b) for b in bad_starts) or first == "":
                lines.pop(0)
            else:
                break

        return "\n".join(lines).strip()

    # ── Context builder ───────────────────────────────────────────────────────

    def _build_context(self, analysis: dict) -> dict:
        findings        = analysis.get("findings", [])
        anomalies       = analysis.get("anomalies", [])
        timeline_events = analysis.get("timeline", {}).get("events", [])
        browser         = analysis.get("browser", {})

        SYSTEM_PREFIXES = (
            "/$", "$MFT", "$Bitmap", "$Boot", "$LogFile", "$BadClus",
            "$Secure", "$Extend", "$UpCase", "$AttrDef", "$Volume", "$MFTMirr",
        )

        def is_sys(path):
            p = (path or "").lstrip("/")
            return any(p.startswith(s.lstrip("/")) for s in SYSTEM_PREFIXES)

        def fmt_ts(ts):
            if not ts:
                return "unknown"
            try:
                return datetime.datetime.utcfromtimestamp(int(ts)).strftime(
                    "%Y-%m-%d %H:%M:%S UTC")
            except Exception:
                return str(ts)

        def fmt_sz(sz):
            if not sz:
                return None
            try:
                sz = int(sz)
                if sz >= 1_073_741_824: return f"{sz/1_073_741_824:.2f} GB"
                if sz >= 1_048_576:     return f"{sz/1_048_576:.2f} MB"
                if sz >= 1_024:         return f"{sz/1_024:.2f} KB"
                return f"{sz} bytes"
            except Exception:
                return str(sz)

        def finding_to_sentence(f):
            ftype  = f.get("type", "unknown")
            path   = f.get("path", "unknown path")
            ts     = fmt_ts(f.get("timestamp"))
            sz     = fmt_sz(f.get("size"))
            reason = f.get("reason", "")
            sev    = {4: "CRITICAL", 3: "HIGH", 2: "MEDIUM", 1: "LOW"}.get(
                f.get("severity", 1), "LOW")

            parts = [f"[{sev}] {ftype}: {reason}"]
            if path and path != "unknown path":
                parts.append(f"Path: {path}")
            if ts and ts != "unknown":
                parts.append(f"Timestamp: {ts}")
            if sz:
                parts.append(f"Size: {sz}")
            return " | ".join(parts)

        def anomaly_to_sentence(a):
            atype  = a.get("type", "unknown")
            reason = a.get("reason", "")
            count  = a.get("event_count")
            start  = fmt_ts(a.get("start"))
            sev    = {3: "HIGH", 2: "MEDIUM", 1: "LOW"}.get(a.get("severity", 1), "LOW")

            parts = [f"[{sev}] {atype}: {reason}"]
            if count:
                parts.append(f"Event count: {count}")
            if start and start != "unknown":
                parts.append(f"First seen: {start}")
            return " | ".join(parts)

        critical   = [f for f in findings if f.get("severity", 1) >= 3]
        supporting = [f for f in findings if f.get("severity", 1) < 3]

        user_events = [
            e for e in timeline_events
            if not is_sys(e.get("path", "")) and e.get("timestamp", 0) != 0
        ][:30]

        wiped_count = sum(1 for e in timeline_events if e.get("metadata_wiped"))
        rare_exts   = [a for a in anomalies if a.get("type") == "rare_extension"]
        other_a     = [a for a in anomalies if a.get("type") != "rare_extension"]

        critical_sentences   = [finding_to_sentence(f) for f in critical]
        supporting_sentences = [finding_to_sentence(f) for f in supporting[:20]]
        anomaly_sentences    = [anomaly_to_sentence(a) for a in other_a[:15]]

        timeline_lines = []
        for e in user_events:
            ts   = fmt_ts(e.get("timestamp"))
            path = e.get("path", "")
            sz   = fmt_sz(e.get("size"))
            src  = e.get("source", "disk")
            line = f"{ts} | {src} | {path}"
            if sz:
                line += f" | {sz}"
            timeline_lines.append(line)

        return {
            "summary": {
                "total_findings":   len(findings),
                "critical_count":   len(critical),
                "supporting_count": len(supporting),
                "anomaly_count":    len(anomalies),
                "wiped_records":    wiped_count,
                "total_events":     len(timeline_events),
                "user_events":      len(user_events),
            },
            "critical_findings":   critical_sentences,
            "supporting_findings": supporting_sentences,
            "anomalies":           anomaly_sentences,
            "rare_ext_count":      len(rare_exts),
            "rare_ext_examples":   list({a.get("extension") for a in rare_exts if a.get("extension")})[:8],
            "timeline_lines":      timeline_lines,
            "browser": {
                "visit_count":    len(browser.get("visits", [])),
                "download_count": len(browser.get("downloads", [])),
                "cookie_count":   len(browser.get("cookies", [])),
            },
        }

    # ── Section prompts ───────────────────────────────────────────────────────

    def _prompt_executive_summary(self, ctx: dict) -> str:
        s = ctx["summary"]
        findings_text = "\n".join(ctx["critical_findings"]) if ctx["critical_findings"] \
            else "No critical findings identified."
        return (
            f"Write the Executive Summary section of a forensic investigation report.\n"
            f"Write exactly 4 sentences of prose. No bullet points. No headings.\n"
            f"Sentence 1: What type of system this appears to be and who the subject is.\n"
            f"Sentence 2: The most critical finding identified.\n"
            f"Sentence 3: Whether anti-forensic activity was detected.\n"
            f"Sentence 4: The overall risk level — choose one: Critical / High / Medium / Low / Clean.\n\n"
            f"Evidence facts:\n"
            f"- {s['critical_count']} critical/high severity findings\n"
            f"- {s['supporting_count']} medium/low severity findings\n"
            f"- {s['anomaly_count']} anomalies detected\n"
            f"- {s['wiped_records']} files with wiped MFT metadata\n"
            f"- {s['user_events']} user-relevant filesystem events recovered\n\n"
            f"Critical findings:\n{findings_text}"
        )

    def _prompt_investigative_context(self, ctx: dict) -> str:
        s = ctx["summary"]
        b = ctx["browser"]
        return (
            f"Write the Investigative Context section of a forensic report.\n"
            f"Write 3 short paragraphs. No bullet points.\n"
            f"Paragraph 1: What was examined — a disk image processed with SleuthKit fls and mactime.\n"
            f"Paragraph 2: What data was available — state the event counts and browser data status.\n"
            f"Paragraph 3: Key limitations — what could not be determined and why.\n\n"
            f"Facts:\n"
            f"- Total timeline events: {s['total_events']}\n"
            f"- User-relevant events: {s['user_events']}\n"
            f"- Files with zeroed/wiped metadata: {s['wiped_records']}\n"
            f"- Browser visits: {b['visit_count']}, downloads: {b['download_count']}, cookies: {b['cookie_count']}\n"
        )

    def _prompt_critical_findings(self, ctx: dict) -> str:
        if not ctx["critical_findings"]:
            return (
                "Write one sentence stating that no critical or high severity findings "
                "were identified in this investigation."
            )
        findings_text = "\n".join(f"- {f}" for f in ctx["critical_findings"])
        return (
            f"Write the Critical Findings section of a forensic report.\n"
            f"For each finding listed below, write a short paragraph (3-4 sentences).\n"
            f"Start each paragraph with '### ' followed by a bold label.\n"
            f"In each paragraph state: what the finding is, why it is forensically significant, "
            f"and what action the investigator should take.\n"
            f"Do not describe data formats. Write conclusions.\n\n"
            f"Findings to cover:\n{findings_text}"
        )

    def _prompt_supporting_findings(self, ctx: dict) -> str:
        if not ctx["supporting_findings"]:
            return "Write one sentence stating no medium or low severity findings were identified."
        findings_text = "\n".join(f"- {f}" for f in ctx["supporting_findings"])
        return (
            f"Write the Supporting Findings section of a forensic report.\n"
            f"Write a short paragraph summarising the lower-severity findings as a group.\n"
            f"Then list them in a markdown table with columns: Severity | Type | Path | Notes.\n"
            f"Keep Notes to one sentence per row. Do not describe data formats.\n\n"
            f"Findings:\n{findings_text}"
        )

    def _prompt_anomaly_analysis(self, ctx: dict) -> str:
        anomaly_text = "\n".join(f"- {a}" for a in ctx["anomalies"]) \
            if ctx["anomalies"] else "No anomalies detected."
        rare_text = (
            f"{ctx['rare_ext_count']} files with rare single-occurrence extensions: "
            f"{', '.join(ctx['rare_ext_examples'])}"
        ) if ctx["rare_ext_count"] else "No rare extensions detected."
        return (
            f"Write the Anomaly Analysis section of a forensic report.\n"
            f"Write in analytical prose — 3 to 5 paragraphs. No bullet points.\n"
            f"For each anomaly type, state what it means forensically and whether it suggests "
            f"normal system behaviour or deliberate action. Do not describe data formats.\n\n"
            f"Anomalies detected:\n{anomaly_text}\n\n"
            f"Extension anomalies: {rare_text}"
        )

    def _prompt_timeline(self, ctx: dict) -> str:
        if not ctx["timeline_lines"]:
            return (
                "Write one paragraph stating that no user-relevant timeline events with "
                "valid timestamps were recovered. Note this is consistent with MFT metadata "
                "wiping, which is itself a significant forensic indicator."
            )
        events_text = "\n".join(ctx["timeline_lines"])
        return (
            f"Write the Timeline Reconstruction section of a forensic report.\n"
            f"Write 3-4 paragraphs grouping events into phases (e.g. Normal Activity, "
            f"Suspicious Activity, Deletion Phase). Name specific paths and timestamps.\n"
            f"Label each conclusion as CONFIRMED or INFERRED. Do not describe data formats.\n\n"
            f"Timeline events (format: timestamp | source | path | size):\n{events_text}"
        )

    def _prompt_antiforensic(self, ctx: dict) -> str:
        s = ctx["summary"]
        findings_text = "\n".join(f"- {f}" for f in ctx["critical_findings"]) \
            if ctx["critical_findings"] else "None identified."
        return (
            f"Write the Anti-Forensic Indicators section of a forensic report.\n"
            f"For each indicator below, write one line: the indicator name, then "
            f"PRESENT / ABSENT / INCONCLUSIVE, then one sentence of justification.\n"
            f"End with one paragraph giving an overall anti-forensic assessment.\n\n"
            f"Indicators to assess:\n"
            f"- Timestomping\n"
            f"- Secure deletion / file wiping\n"
            f"- Alternate Data Streams (ADS)\n"
            f"- Bad cluster manipulation\n"
            f"- Orphaned MFT entries\n"
            f"- Mass deletion events\n"
            f"- File extension spoofing\n\n"
            f"Key facts:\n"
            f"- {s['wiped_records']} files have fully zeroed MFT timestamps and size\n"
            f"- Critical findings:\n{findings_text}"
        )

    def _prompt_browser(self, ctx: dict) -> str:
        b = ctx["browser"]
        if b["visit_count"] == 0 and b["download_count"] == 0:
            return (
                "Write two sentences stating that no browser artefacts were available "
                "for analysis and that this limits the investigation's ability to "
                "reconstruct online activity."
            )
        return (
            f"Write the Browser Forensic Summary section of a forensic report.\n"
            f"Write 2-3 paragraphs covering: browsing patterns and volume, any downloads "
            f"that correlate with disk findings, and any evidence of counter-forensics research.\n\n"
            f"Browser data: {b['visit_count']} visits, {b['download_count']} downloads, "
            f"{b['cookie_count']} cookies"
        )

    def _prompt_preservation(self, ctx: dict) -> str:
        findings_text = "\n".join(f"- {f}" for f in ctx["critical_findings"][:5]) \
            if ctx["critical_findings"] else "No critical findings."
        anomaly_text  = "\n".join(f"- {a}" for a in ctx["anomalies"][:4]) \
            if ctx["anomalies"] else "No anomalies."
        return (
            f"Write the Evidence Preservation Recommendations section of a forensic report.\n"
            f"Write a numbered list of 5 to 7 specific, actionable steps.\n"
            f"Each step must name a specific action, tool, or command.\n"
            f"Reference specific paths or inodes from the findings where possible.\n"
            f"Include at least one SleuthKit command example (e.g. icat, fls).\n\n"
            f"Based on these findings:\n{findings_text}\n\n"
            f"And these anomalies:\n{anomaly_text}"
        )

    def _prompt_conclusion(self, ctx: dict) -> str:
        s = ctx["summary"]
        findings_text = "\n".join(f"- {f}" for f in ctx["critical_findings"]) \
            if ctx["critical_findings"] else "No critical findings."
        return (
            f"Write the Conclusion section of a forensic report.\n"
            f"Write 3 paragraphs.\n"
            f"Paragraph 1: Summarise the overall forensic picture in plain English.\n"
            f"Paragraph 2: State your confidence level (High / Medium / Low) and justify it.\n"
            f"Paragraph 3: State what additional evidence would most change the conclusions.\n\n"
            f"Summary:\n"
            f"- {s['critical_count']} critical findings, {s['anomaly_count']} anomalies\n"
            f"- {s['wiped_records']} wiped metadata records\n"
            f"- {s['user_events']} user-relevant events recovered\n\n"
            f"Critical findings:\n{findings_text}"
        )

    # ── Deterministic fallback ────────────────────────────────────────────────

    def _deterministic_format(self, raw_narrative: str) -> str:
        refined = []
        for p in raw_narrative.split("\n"):
            p = p.strip()
            if not p:
                continue
            if p.startswith("##"):
                refined.append(p)
            elif p.startswith("- "):
                refined.append("• " + p[2:])
            else:
                refined.append(p)
        return "\n".join(refined)

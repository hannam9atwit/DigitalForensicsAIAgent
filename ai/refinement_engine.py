import os
import json
import urllib.request
import urllib.error


# ---------------------------------------------------------------------------
# RefinementEngine
#
# Priority order for narrative generation:
#   1. Ollama local LLM  (offline, no key needed — primary for packaged app)
#   2. Anthropic Claude  (if ANTHROPIC_API_KEY is set — optional upgrade)
#   3. Deterministic formatter (always works — last resort fallback)
# ---------------------------------------------------------------------------

class RefinementEngine:

    # ── Ollama config ──────────────────────────────────────────────────────
    OLLAMA_URL   = "http://localhost:11434/api/chat"
    OLLAMA_MODEL = "llama3.1:8b"

    # ── Anthropic config (optional fallback / upgrade path) ────────────────
    ANTHROPIC_URL   = "https://api.anthropic.com/v1/messages"
    ANTHROPIC_MODEL = "claude-opus-4-6"

    SYSTEM_PROMPT = """You are a senior digital forensics analyst writing an investigative report for law enforcement or legal proceedings.

    You will receive structured forensic findings, anomalies, and a timeline summary.

    Your response MUST follow this exact structure:

    ## Executive Summary
    A 2-3 sentence overview of what happened on this system and the most critical concerns.

    ## Critical Findings
    For each finding with severity 3 or 4, explain what it means in plain English, why it is significant, and what an investigator should do about it. If there are no high severity findings, say so clearly.

    ## Suspicious Activity
    Describe any patterns across the findings and anomalies that suggest deliberate action — data deletion, anti-forensic behavior, file hiding, or unusual access patterns.

    ## Timeline of Key Events
    Summarise the most significant events in chronological order. Skip routine system files ($MFT, $Bitmap, $Boot, $LogFile, $BadClus, $Secure, $Extend, $UpCase, $AttrDef). Only include user files, deleted files, anomalies, and suspicious events.

    ## Recommendations
    A numbered, prioritized list of concrete next steps for the investigator.

    RULES:
    - Do NOT describe what NTFS system files are. Ignore $MFT, $Bitmap, $Boot, $LogFile, $BadClus, $Secure, $Extend, $UpCase, $AttrDef entirely.
    - Do NOT explain what the data format is.
    - Do NOT say "the provided JSON" or "this data" — write as if you are the analyst who ran the investigation.
    - If findings and anomalies are empty or contain only system files, say the disk appears clean with no user-level suspicious activity detected.
    - Be direct and specific. Name file paths, timestamps, and severities."""

    def __init__(self):
        self.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    def refine(self, raw_narrative: str, analysis: dict = None) -> str:
        if analysis is None:
            return self._deterministic_format(raw_narrative)

        # 1. Try Ollama first
        if self._ollama_available():
            try:
                print("[*] RefinementEngine: using Ollama local LLM")
                return self._call_ollama(analysis)
            except Exception as e:
                print(f"[!] Ollama call failed: {e} — trying next option")

        # 2. Try Anthropic Claude
        if self.anthropic_api_key:
            try:
                print("[*] RefinementEngine: using Anthropic Claude API")
                return self._call_anthropic(analysis)
            except Exception as e:
                print(f"[!] Anthropic call failed: {e} — using deterministic fallback")

        # 3. Deterministic fallback
        print("[~] RefinementEngine: using deterministic fallback")
        return self._deterministic_format(raw_narrative)

    # =========================================================================
    # Ollama
    # =========================================================================

    def _find_ollama(self) -> str:
        """Find ollama executable — checks PATH then default install locations."""
        import shutil
        path = shutil.which("ollama")
        if path:
            return path

        # Windows default install location
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        candidate = os.path.join(local_app_data, "Programs", "Ollama", "ollama.exe")
        if os.path.exists(candidate):
            return candidate

        # Linux default
        candidate = "/usr/local/bin/ollama"
        if os.path.exists(candidate):
            return candidate

        return None

    def _ollama_available(self) -> bool:
        """Check if Ollama is running and our model is pulled."""
        try:
            req = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                body = json.loads(resp.read().decode())
            models = [m.get("name", "") for m in body.get("models", [])]
            print("[DEBUG] Ollama models found:", models)
            return any(self.OLLAMA_MODEL.split(":")[0] in m for m in models)
        except Exception as e:
            print("[DEBUG] Ollama check failed:", e)
            return False

    def _call_ollama(self, analysis: dict) -> str:
        # If Ollama isn't responding, try to start it
        if not self._ollama_available():
            ollama_exe = self._find_ollama()
            if ollama_exe:
                import subprocess
                subprocess.Popen(
                    [ollama_exe, "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                # Give it a moment to start
                import time
                time.sleep(3)

        prompt = self._build_prompt(analysis)

        payload = json.dumps({
            "model": self.OLLAMA_MODEL,
            "stream": False,
            "messages": [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ]
        }).encode("utf-8")

        req = urllib.request.Request(
            self.OLLAMA_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        # Local inference can be slow on CPU — give it plenty of time
        with urllib.request.urlopen(req, timeout=300) as resp:
            body = json.loads(resp.read().decode())

        text = body.get("message", {}).get("content", "")
        if not text:
            raise ValueError("Ollama returned empty content")
        return text

    # =========================================================================
    # Anthropic Claude (optional upgrade / fallback)
    # =========================================================================

    def _call_anthropic(self, analysis: dict) -> str:
        prompt = self._build_prompt(analysis)

        payload = json.dumps({
            "model": self.ANTHROPIC_MODEL,
            "max_tokens": 2048,
            "system": self.SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}]
        }).encode("utf-8")

        req = urllib.request.Request(
            self.ANTHROPIC_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.anthropic_api_key,
                "anthropic-version": "2023-06-01"
            },
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode())

        texts = [
            b["text"] for b in body.get("content", [])
            if b.get("type") == "text"
        ]
        if not texts:
            raise ValueError("Anthropic returned no text content")
        return "\n".join(texts)

    # =========================================================================
    # Shared prompt builder
    # =========================================================================

    def _build_prompt(self, analysis: dict) -> str:
        summary = analysis.get("summary", {})
        findings = analysis.get("findings", [])
        anomalies = analysis.get("anomalies", [])
        timeline_events = analysis.get("timeline", {}).get("events", [])

        # System file prefixes to filter out of timeline — these are noise
        SYSTEM_PREFIXES = (
            "/$", "//$", "$MFT", "$Bitmap", "$Boot", "$LogFile",
            "$BadClus", "$Secure", "$Extend", "$UpCase", "$AttrDef",
            "$Volume", "$MFTMirr"
        )

        def is_system_file(path: str) -> bool:
            if not path:
                return True
            return any(path.lstrip("/").startswith(p.lstrip("/")) for p in SYSTEM_PREFIXES)

        # Filter timeline to only user-relevant events
        user_events = [
                          e for e in timeline_events
                          if not is_system_file(e.get("path", ""))
                      ][:40]

        # Separate high severity findings for emphasis
        high_findings = [f for f in findings if f.get("severity", 1) >= 3]
        low_findings = [f for f in findings if f.get("severity", 1) < 3]

        def slim(f):
            return {
                "type": f.get("type"),
                "severity": f.get("severity"),
                "path": f.get("path"),
                "reason": f.get("reason"),
                "timestamp": f.get("timestamp"),
            }

        def slim_event(e):
            return {
                "timestamp": e.get("timestamp"),
                "source": e.get("source"),
                "path": e.get("path"),
                "size": e.get("size"),
            }

        context = {
            "summary": summary,
            "high_severity_findings": [slim(f) for f in high_findings],
            "other_findings": [slim(f) for f in low_findings[:20]],
            "total_findings": len(findings),
            "anomalies": [slim(a) for a in anomalies[:30]],
            "total_anomalies": len(anomalies),
            "user_relevant_timeline": [slim_event(e) for e in user_events],
            "total_timeline_events": len(timeline_events),
            "filtered_system_events": len(timeline_events) - len(user_events),
        }

        return (
            "Analyse the following forensic investigation data and write your report.\n"
            "Focus on the findings and anomalies. The timeline has had NTFS system files "
            "pre-filtered — only user-relevant events remain.\n\n"
            f"```json\n{json.dumps(context, indent=2, default=str)}\n```"
        )

    # =========================================================================
    # Deterministic fallback
    # =========================================================================

    def _deterministic_format(self, raw_narrative: str) -> str:
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
                    "An overview of the system's activity reveals several notable forensic signals. " + p
                )
                continue
            refined.append(p)
        return "\n".join(refined)
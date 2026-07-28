"""
ai/refinement_engine.py

LLM integration layer for the forensic narrative engine.

Generates the forensic report one section at a time using few-shot prompting.
Backends in priority order:
  1. Ollama (local) — runs fully offline after first setup
  2. Anthropic Claude API — used when the user sets a key in Settings
  3. Deterministic fallback — used when no LLM is available

The section format (voice, structure, few-shot example) is owned by
formats/report_section.md via ai.format_library, so the report's shape can be
changed without touching this code. The constants below remain as the
fallback when the spec file is absent.
"""

import os
import json
import queue
import socket
import datetime
import threading
import urllib.error
import urllib.request
from collections import Counter

from ai import accounts as accounts_mod
from ai import format_library
from core import ollama_runtime


def _accounts_from_events(events):
    """The account block handed to the section prompts. Derived from the events
    themselves so a section can attribute activity to a real account, and is
    told plainly when none was established."""
    return accounts_mod.brief(accounts_mod.extract(events))


class GenerationCancelled(Exception):
    """Raised out of refine() when cancel() was called mid-draft.

    It signals a deliberate teardown, not a failure: the caller must leave any
    existing narrative untouched rather than write the partial one, so this is
    caught separately from the section-level errors that degrade to rule-based
    text.
    """


# Shared persona prepended to every LLM call
_PERSONA = (
    "You are a digital forensics examiner writing a formal investigation report. "
    "IMPORTANT RULES:\n"
    "- Write ONLY the report text. Do not describe, explain, or comment on the data format.\n"
    "- Begin the FIRST sentence with the forensic content itself. Never open with "
    "meta-commentary about the data or the task — do NOT start with 'The output "
    "appears', 'The data shows', 'Here is', 'This section describes', 'Based on the "
    "data provided', or anything similar. Write the finding, not a description of it.\n"
    "- Do NOT mention JSON, arrays, objects, properties, or data structures.\n"
    "- Do NOT say 'here is a breakdown', 'here are observations', or 'if you would like'.\n"
    "- Do NOT ask questions or offer to help further.\n"
    "- Write in English only. Write as the analyst who ran the investigation.\n"
    "- Be specific, but only from the evidence facts given in this prompt: name the "
    "file paths, timestamps and counts they contain, and no others.\n"
    "- Every sentence must state a forensic conclusion, not describe the data."
)

# Fallback few-shot, used only when formats/report_section.md is missing. Its
# example is shape-only: every specific is a bracketed placeholder, because a
# small local model copies an example's values as readily as its structure.
_FEW_SHOT = """
EXAMPLE OF WRONG OUTPUT (never do this):
"This is a JSON array of objects. Each object has properties: type, severity, reason, timestamp. If you would like me to help process this data, feel free to ask."

EXAMPLE OF WRONG OUTPUT (never do this — this narrates instead of concluding):
"The output appears to describe several deleted directories. Based on the data provided, here is a summary of what the records show."

SHAPE OF CORRECT OUTPUT (structure only — fill each bracketed slot from the evidence facts below, and never write a bracketed placeholder itself):
"[COUNT] deleted directories were identified that still contain active child entries. This pattern is consistent with a deliberate but incomplete deletion attempt, where the parent directory was removed while its contents remained accessible. The absence of timestamps across all entries indicates the MFT metadata was subsequently wiped, a recognised anti-forensic technique."

Now write the section below. Begin writing the report immediately after "REPORT TEXT:" — with the forensic content, not a description of it.
"""


class RefinementEngine:

    OLLAMA_URL   = f"{ollama_runtime.OLLAMA_HOST}/api/generate"

    ANTHROPIC_URL   = "https://api.anthropic.com/v1/messages"
    ANTHROPIC_MODEL = "claude-sonnet-4-5"

    def __init__(self, ai_config: dict | None = None):
        """ai_config: {"provider", "model", "api_key"} from Settings.
        Falls back to Ollama defaults + the ANTHROPIC_API_KEY env var so the
        headless pipeline keeps working without a GUI."""
        config = ai_config or {}
        self.provider = config.get("provider", "ollama")
        self.OLLAMA_MODEL = config.get("model") or ollama_runtime.DEFAULT_MODEL
        self.anthropic_api_key = (config.get("api_key")
                                  or os.environ.get("ANTHROPIC_API_KEY", ""))

        # Records who drafted the report and, when the model did not, why. The
        # deterministic fallback used to announce itself only on the console;
        # this attribute carries the same truth up to the result and the UI.
        # Populated by refine(); this is the honest state until it runs.
        self.ai_status = self._status(False, reason="analysis has not been run")

        # Set by cancel() to unwind an in-flight refine(). Checked between
        # sections so a torn-down UI stops promptly without joining the section
        # workers (which may be mid-request) at interpreter exit.
        self._abort = threading.Event()

    def cancel(self):
        """Ask an in-flight refine() to stop. Safe from any thread and
        idempotent: the section loop checks this between sections and raises
        GenerationCancelled, so no partial report is ever returned."""
        self._abort.set()

    @staticmethod
    def _status(used_llm: bool, provider: str = "", model: str = "",
                reason: str = "", detail: str = "", degraded=None) -> dict:
        """The one shape every layer above reads: did the model draft this, and
        if not, the plain-English reason plus the raw exception text.

        `degraded` lists the section names the model failed or timed out on and
        that fell back to rule-based text — an empty list when the model drafted
        every section cleanly.
        """
        return {
            "used_llm": used_llm,
            "provider": provider,
            "model":    model,
            "reason":   reason,
            "detail":   detail,
            "degraded": list(degraded) if degraded else [],
        }

    # ── Public entry point ────────────────────────────────────────────────────

    def refine(self, raw_narrative: str, analysis: dict = None,
               on_progress=None, section_timeout: int = 180) -> str:
        """Draft the report, section by section, from `analysis`.

        on_progress(section_name, done, total): called on the calling thread as
        each section finishes, so a UI can show "Generating report… 4 of 10"
        instead of a frozen window.

        section_timeout: per-section wall-clock cap. A section that exceeds it
        (or errors) degrades to rule-based text rather than sinking the whole
        report; which sections degraded is recorded in ai_status["degraded"].

        Raises GenerationCancelled if cancel() is called mid-draft, so a caller
        tearing down its UI can discard the run and keep the prior narrative.
        """
        if analysis is None:
            self.ai_status = self._status(
                False, reason="no structured analysis was supplied")
            return self._deterministic_format(raw_narrative)

        if self.provider == "anthropic":
            use_ollama, ollama_reason, ollama_detail = False, "", ""
        else:
            use_ollama, ollama_reason, ollama_detail = self._ollama_status()
        use_anthropic = (not use_ollama) and bool(self.anthropic_api_key)

        if not use_ollama and not use_anthropic:
            if self.provider == "anthropic":
                reason, detail = "no Anthropic API key is set", ""
            else:
                reason = ollama_reason or "no local model is available"
                detail = ollama_detail
            self.ai_status = self._status(
                False, provider=self.provider, model=self.OLLAMA_MODEL,
                reason=reason, detail=detail)
            print(f"[~] No LLM available ({reason}) — using deterministic fallback")
            if detail:
                print(f"    ↳ {detail}")
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

        provider = "anthropic" if use_anthropic else "ollama"
        model    = self.ANTHROPIC_MODEL if use_anthropic else self.OLLAMA_MODEL
        call     = self._call_anthropic if use_anthropic else self._call_ollama
        total    = len(sections)

        # Run the section calls concurrently rather than back-to-back. On a
        # local 3B model the old sequential loop took 5–10 minutes and made the
        # window look frozen.
        #
        # These are raw daemon threads, deliberately NOT a ThreadPoolExecutor:
        # the executor registers its workers for an atexit join, so a worker
        # stuck in a request would block interpreter exit for up to the section
        # timeout when the app is closed mid-draft. Daemon threads simply die
        # with the process. Concurrency is capped by the worker count — enough
        # to overlap the network waits, not so many that we starve the CPU the
        # model needs. Output order is restored by index below; a section that
        # times out or errors degrades to rule-based text so one slow section
        # never sinks the whole report.
        results  = [None] * total
        degraded = []

        def draft(index: int) -> str:
            heading, prompt_fn = sections[index]
            return self._strip_preamble(
                call(prompt_fn(ctx), timeout=section_timeout))

        work_q = queue.Queue()
        for i in range(total):
            work_q.put(i)
        done_q = queue.Queue()   # (index, ok, value_or_exception)

        def worker():
            while not self._abort.is_set():
                try:
                    i = work_q.get_nowait()
                except queue.Empty:
                    return
                try:
                    done_q.put((i, True, draft(i)))
                except Exception as e:                       # noqa: BLE001
                    done_q.put((i, False, e))

        workers = min(3, total)
        for n in range(workers):
            threading.Thread(target=worker, daemon=True,
                             name=f"section-{n}").start()

        # Drain completions on this thread, polling so the abort flag is seen
        # promptly even while every worker is blocked in a request.
        done = 0
        while done < total:
            if self._abort.is_set():
                raise GenerationCancelled()
            try:
                i, ok, payload = done_q.get(timeout=0.3)
            except queue.Empty:
                continue
            name = self._section_name(sections[i][0])
            if ok:
                results[i] = payload
            else:
                print(f"[!] Section '{name}' fell back to rule-based: {payload}")
                results[i] = self._fallback_section(sections[i][0], ctx)
                degraded.append(name)
            done += 1
            if on_progress:
                on_progress(name, done, total)

        parts = [f"{sections[i][0]}\n\n{(results[i] or '').strip()}"
                 for i in range(total)]

        if degraded:
            reason = (f"{len(degraded)} of {total} section(s) timed out and were "
                      f"drafted rule-based")
            detail = ", ".join(degraded)
        else:
            reason, detail = "", ""
        self.ai_status = self._status(
            True, provider=provider, model=model,
            reason=reason, detail=detail, degraded=degraded)
        return "\n\n---\n\n".join(parts)

    # ── LLM callers ───────────────────────────────────────────────────────────

    def _section_format_text(self) -> str:
        """The report-section format from formats/report_section.md, or the
        built-in few-shot text when the spec file is missing."""
        spec = format_library.load(format_library.SURFACE_REPORT_SECTION)
        return spec.prompt_text if spec else _FEW_SHOT

    def _call_ollama(self, prompt: str, timeout: int = 300) -> str:
        full_prompt = (f"{_PERSONA}\n\n{format_library.GROUNDING}\n\n"
                       f"{self._section_format_text()}\n\n"
                       f"{prompt}\n\nREPORT TEXT:")

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

        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode())

        text = body.get("response", "").strip()
        if not text:
            raise ValueError("Ollama returned empty response")
        return text

    def _call_anthropic(self, prompt: str, timeout: int = 60) -> str:
        full_prompt = (f"{format_library.GROUNDING}\n\n"
                       f"{self._section_format_text()}\n\n{prompt}\n\nREPORT TEXT:")

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

        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode())

        texts = [b["text"] for b in body.get("content", []) if b.get("type") == "text"]
        if not texts:
            raise ValueError("Anthropic returned no text")
        return "\n".join(texts)

    # ── Per-section rule-based fallback ─────────────────────────────────────────

    @staticmethod
    def _section_name(heading: str) -> str:
        """'## 3. Critical Findings' -> 'Critical Findings', for progress and
        the degraded-section list."""
        text = heading.lstrip("# ").strip()
        if "." in text.split(" ", 1)[0]:
            text = text.split(".", 1)[1].strip()
        return text or heading.strip()

    def _fallback_section(self, heading: str, ctx: dict) -> str:
        """A rule-based rendering of one section, for when the model times out
        or errors on it.

        It states the same structured facts the prompt would have handed the
        model, so the section stays truthful — just plainer — and is prefixed so
        the reader knows the model did not write it. This is what keeps one slow
        section from taking the whole report down with it.
        """
        s = ctx["summary"]
        b = ctx["browser"]
        marker = "*(Rule-based — the model did not return this section in time.)*"
        name = self._section_name(heading)

        def plural(n, one, many):
            return one if n == 1 else many

        if name.startswith("Executive Summary"):
            body = (f"The examination recovered {s['total_events']} filesystem "
                    f"events and produced {s['critical_count']} critical/high and "
                    f"{s['supporting_count']} lower-severity finding(s), with "
                    f"{s['anomaly_count']} "
                    f"{plural(s['anomaly_count'], 'anomaly', 'anomalies')} detected. "
                    f"{s['wiped_records']} record(s) show wiped MFT metadata.")
        elif name.startswith("Investigative Context"):
            body = (f"A disk image was processed with SleuthKit and merged into a "
                    f"unified timeline of {s['total_events']} events "
                    f"({s['user_events']} user-relevant). Browser data: "
                    f"{b['visit_count']} visit(s), {b['download_count']} download(s).")
        elif name.startswith("Critical Findings"):
            lines = ctx["critical_findings"] or [
                "No critical or high severity findings were identified."]
            body = "\n".join(f"- {x}" for x in lines)
        elif name.startswith("Supporting Findings"):
            lines = ctx["supporting_findings"] or [
                "No medium or low severity findings were identified."]
            body = "\n".join(f"- {x}" for x in lines)
        elif name.startswith("Anomaly Analysis"):
            lines = ctx["anomalies"] or ["No anomalies were detected."]
            body = "\n".join(f"- {x}" for x in lines)
        elif name.startswith("Timeline"):
            lines = ctx["timeline_lines"][:20] or [
                "No user-relevant timeline events with valid timestamps were "
                "recovered — itself consistent with MFT metadata wiping."]
            body = "\n".join(f"- {x}" for x in lines)
        elif name.startswith("Anti-Forensic"):
            body = (f"{s['wiped_records']} record(s) have fully zeroed MFT "
                    f"timestamps and size, consistent with metadata wiping. See "
                    f"the critical findings above for corroborating indicators.")
        elif name.startswith("Browser"):
            body = ((f"{b['visit_count']} visit(s), {b['download_count']} "
                     f"download(s) and {b['cookie_count']} cookie(s) were parsed.")
                    if (b["visit_count"] or b["download_count"])
                    else "No browser artefacts were available for analysis.")
        elif name.startswith("Evidence Preservation"):
            body = ("Preserve the disk image read-only, recover flagged items with "
                    "SleuthKit `icat`, and hash every extracted artefact before "
                    "further analysis.")
        elif name.startswith("Conclusion"):
            body = (f"The evidence yielded {s['critical_count']} critical finding(s) "
                    f"and {s['anomaly_count']} "
                    f"{plural(s['anomaly_count'], 'anomaly', 'anomalies')}; "
                    f"{s['wiped_records']} wiped record(s) were observed. The "
                    f"supporting detail is in the findings above.")
        else:
            body = ("The underlying facts for this section are available in the "
                    "Findings and Timeline tabs.")
        return f"{marker}\n\n{body}"

    def _ollama_status(self) -> tuple[bool, str, str]:
        """(available, reason, detail) for the local backend.

        The availability decision still defers entirely to core.ollama_runtime —
        the single authority — so this does NOT change when the fallback fires.
        It only recovers *why* it fired, in words the examiner can act on, plus
        the underlying exception for the audit trail.

        If the exact model is absent but another tag is present, use what's
        there rather than failing the whole report (behaviour unchanged).
        """
        if not ollama_runtime.server_running():
            reason, detail = self._ollama_probe_failure()
            return False, reason, detail
        if ollama_runtime.model_available(self.OLLAMA_MODEL):
            return True, "", ""

        models = ollama_runtime.installed_models()
        if models:
            self.OLLAMA_MODEL = models[0]
            print(f"[~] Configured model unavailable — using {self.OLLAMA_MODEL}")
            return True, "", ""

        return (False, "no model is installed in Ollama",
                f"the server is running but has no models; expected "
                f"{self.OLLAMA_MODEL}")

    def _ollama_probe_failure(self) -> tuple[str, str]:
        """Name the reason the local server is unreachable.

        server_running() already collapsed the failure to a bool; this repeats
        the probe once so the specific exception can be recovered and the report
        can tell "not running" apart from a timeout or a connection error.
        """
        tags_url = f"{ollama_runtime.OLLAMA_HOST}/api/tags"
        try:
            req = urllib.request.Request(tags_url, method="GET")
            with urllib.request.urlopen(req, timeout=4):
                # It answered on the retry: the first negative was a transient
                # blip, not a down server.
                return "Ollama server is not running", ""
        except urllib.error.URLError as e:
            inner = getattr(e, "reason", e)
            if isinstance(inner, (socket.timeout, TimeoutError)):
                return "the Ollama server did not respond in time (timeout)", str(e)
            if isinstance(inner, ConnectionRefusedError):
                return "Ollama server is not running", str(inner)
            return "cannot reach the Ollama server (connection error)", str(e)
        except (socket.timeout, TimeoutError) as e:
            return "the Ollama server did not respond in time (timeout)", str(e)
        except OSError as e:
            return "cannot reach the Ollama server (connection error)", str(e)

    # ── Preamble stripper ─────────────────────────────────────────────────────

    def _strip_preamble(self, text: str) -> str:
        """Remove any boilerplate the model outputs before the actual report text.

        First drops an echoed "REPORT TEXT:" label, then strips leading
        meta-commentary sentences ("The output appears to list…", "Here is the
        section:") via the shared format_library stripper, which cuts at the
        first sentence boundary rather than dropping the whole line — so a
        preamble glued to the real prose loses only the preamble.
        """
        if "REPORT TEXT:" in text:
            text = text.split("REPORT TEXT:", 1)[-1]
        return format_library.strip_leading_meta(text)

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

        # Which artifact sources actually contributed events. The context
        # prompts used to assert a disk image processed with SleuthKit for every
        # case; on a network- or log-only case that is a fabricated method
        # statement, so the sections are told what was really examined.
        source_counts = Counter(e.get("source") or "Unknown" for e in timeline_events)
        sources_line = ", ".join(f"{name} ({count:,} events)"
                                 for name, count in source_counts.most_common())

        # Account names the evidence itself carries, so a section that needs to
        # attribute activity has real accounts to name — and an explicit "none
        # established" when it does not.
        accounts = _accounts_from_events(timeline_events)

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
            "sources":             sources_line or "no artifact produced events",
            "accounts":            accounts,
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
            f"Sentence 1: What was examined — the artifact sources and event counts\n"
            f"  listed below. Name an account as the subject ONLY if the account\n"
            f"  block below establishes one; otherwise do not refer to a subject.\n"
            f"Sentence 2: The most critical finding identified.\n"
            f"Sentence 3: Whether anti-forensic activity was detected.\n"
            f"Sentence 4: The overall risk level — choose one: Critical / High / Medium / Low / Clean.\n\n"
            f"Evidence facts:\n"
            f"- Artifact sources examined: {ctx['sources']}\n"
            f"- {s['critical_count']} critical/high severity findings\n"
            f"- {s['supporting_count']} medium/low severity findings\n"
            f"- {s['anomaly_count']} anomalies detected\n"
            f"- {s['wiped_records']} files with wiped MFT metadata\n"
            f"- {s['user_events']} user-relevant filesystem events recovered\n\n"
            f"{ctx['accounts']}\n\n"
            f"Critical findings:\n{findings_text}"
        )

    def _prompt_investigative_context(self, ctx: dict) -> str:
        s = ctx["summary"]
        b = ctx["browser"]
        return (
            f"Write the Investigative Context section of a forensic report.\n"
            f"Write 3 short paragraphs. No bullet points.\n"
            f"Paragraph 1: What was examined — name only the artifact sources\n"
            f"  listed below. Do not describe a tool or an artifact type that is\n"
            f"  not among them.\n"
            f"Paragraph 2: What data was available — state the event counts and browser data status.\n"
            f"Paragraph 3: Key limitations — what could not be determined and why.\n\n"
            f"Facts:\n"
            f"- Artifact sources examined: {ctx['sources']}\n"
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
            f"Suspicious Activity, Deletion Phase). Name paths and timestamps only "
            f"as they appear in the event list below, character for character.\n"
            f"Label each conclusion as CONFIRMED or INFERRED. Do not describe data formats.\n\n"
            f"{ctx['accounts']}\n\n"
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

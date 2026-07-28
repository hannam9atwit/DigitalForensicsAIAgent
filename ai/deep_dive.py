"""
ai/deep_dive.py

The background deep dive: digest the case once into the knowledge base so every
AI surface reasons from the digest instead of re-reasoning over raw events.

Three layers, each feeding the next — this layering is what turns fifty
disconnected paragraphs into one case narrative:

  Layer 1 (per artifact)  — a small, forensically-pointed prompt set matched to
                            the artifact's kind, fed only a compact brief of
                            THAT artifact's own records, never the whole case.
  Layer 2 (cross artifact)— using the layer-1 findings, what connects the
                            artifacts: overlapping times, corroboration,
                            sequences that span sources.
  Layer 3 (synthesis)     — using layers 1+2, the case-level narrative and the
                            specific slots the surfaces consume (executive
                            summary, conclusion, findings assessment, overview).

Pure orchestration: no Qt, no network. The LLM call, the cancel check, and the
progress / entry / milestone callbacks are injected, so this unit-tests headless
and the daemon-thread wrapper (gui_v2/deep_dive_worker.py) owns concurrency.
"""

import datetime
from collections import Counter

from ai import format_library
from ai import knowledge_base as kb


_PERSONA = (
    "You are a digital forensics examiner digesting evidence into concise, "
    "reusable analytical findings. Answer only the question asked, using only "
    "the material given. Write plain investigator prose that states a "
    "conclusion and its basis — never a description of the data or the task."
)

# Private-address test, shared with the network brief.
_PRIVATE_PREFIXES = ("10.", "192.168.", "127.")


def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _fmt_ts(value):
    try:
        return datetime.datetime.utcfromtimestamp(int(value)).strftime(
            "%Y-%m-%d %H:%M:%S UTC")
    except (ValueError, OSError, OverflowError, TypeError):
        return str(value)


def _is_private(ip):
    ip = str(ip or "")
    if any(ip.startswith(p) for p in _PRIVATE_PREFIXES):
        return True
    if ip.startswith("172."):
        try:
            return 16 <= int(ip.split(".")[1]) <= 31
        except (ValueError, IndexError):
            return False
    return False


def _top(counter, n=5):
    items = [f"{value} ({count})" for value, count in counter.most_common(n) if value]
    return ", ".join(items) if items else "none"


def _timeframe(events):
    stamps = [e["timestamp"] for e in events
              if isinstance(e.get("timestamp"), int) and e["timestamp"] > 0]
    if not stamps:
        return "no timestamped activity"
    lo, hi = min(stamps), max(stamps)
    return _fmt_ts(lo) if lo == hi else f"{_fmt_ts(lo)} to {_fmt_ts(hi)}"


def _infer_confidence(answer):
    """A coarse confidence read from the model's own calibration language, so
    the stored indicator reflects how the finding was stated rather than a
    blanket default."""
    text = (answer or "").lower()
    if any(w in text for w in ("no evidence", "cannot", "could not", "unclear",
                               "unable to", "not established", "insufficient",
                               "may ", "might ", "possibly", "unknown")):
        return "low"
    if any(w in text for w in ("confirm", "clearly", "direct evidence",
                               "conclusively", "records itself", "definitively")):
        return "high"
    return "medium"


# ── per-artifact briefs (digest, not raw dump) ──────────────────────────────────

def _artifact_events(events, artifact_id):
    return [e for e in events if e.get("artifact") == artifact_id]


def _artifact_findings(case, artifact_id):
    return [f for f in case.get("findings", []) if artifact_id in f.get("ev", [])]


def _findings_brief(findings):
    if not findings:
        return "No findings were attributed to this artifact."
    lines = [f"- {f.get('id', '')} [{f.get('sev', '')}] {f.get('title', '')}: "
             f"{f.get('short', '')}" for f in findings]
    return "Findings attributed to this artifact:\n" + "\n".join(lines)


def _network_brief(ev, events, findings):
    packets = [e for e in events
               if e.get("src_ip") or e.get("dst_ip") or e.get("type") == "packet"]
    src = Counter(e.get("src_ip") for e in packets if e.get("src_ip"))
    dst = Counter(e.get("dst_ip") for e in packets if e.get("dst_ip"))
    proto = Counter(e.get("proto") for e in packets if e.get("proto"))
    ports = Counter(e.get("dport") for e in packets if e.get("dport"))
    external = Counter(e.get("dst_ip") for e in packets
                       if e.get("dst_ip") and not _is_private(e["dst_ip"]))
    return "\n".join([
        f"Artifact {ev.get('id')} ({ev.get('name', '')}) — network capture.",
        f"Timeframe: {_timeframe(events)}.",
        f"Decoded packets on the timeline: {len(packets)}.",
        f"Top source hosts: {_top(src)}.",
        f"Top destination hosts: {_top(dst)}.",
        f"Top external destination hosts: {_top(external)}.",
        f"Protocols: {_top(proto)}.",
        f"Top destination ports: {_top(ports)}.",
        _findings_brief(findings),
    ])


def _disk_brief(ev, events, findings):
    deleted = [e for e in events if "(deleted)" in (e.get("path") or "")]
    user_paths = [e.get("path") for e in events
                  if e.get("path") and not e["path"].lstrip("/").startswith("$")
                  and e.get("rel") != "noise"][:12]
    exts = Counter()
    for e in events:
        path = e.get("path") or ""
        if "." in path and "(deleted)" not in path:
            exts[path.rsplit(".", 1)[-1].lower()[:8]] += 1
    return "\n".join([
        f"Artifact {ev.get('id')} ({ev.get('name', '')}) — disk image.",
        f"Timeframe: {_timeframe(events)}.",
        f"Filesystem events on the timeline: {len(events)} "
        f"({len(deleted)} deleted entries).",
        f"Common file extensions: {_top(exts)}.",
        "Sample user-relevant paths: "
        + ("; ".join(user_paths) if user_paths else "none recorded") + ".",
        _findings_brief(findings),
    ])


def _generic_brief(ev, events, findings):
    labels = [e.get("label") for e in events if e.get("label")][:15]
    return "\n".join([
        f"Artifact {ev.get('id')} ({ev.get('name', '')}) — "
        f"{ev.get('kindLabel', ev.get('kind', 'artifact'))}.",
        f"Timeframe: {_timeframe(events)}.",
        f"Records on the timeline: {len(events)}.",
        "Sample records: " + ("; ".join(labels) if labels else "none recorded") + ".",
        _findings_brief(findings),
    ])


_BRIEF_BUILDERS = {"network": _network_brief, "disk": _disk_brief}


# ── prompt sets ─────────────────────────────────────────────────────────────────
# Lean, high-value sets — a handful of pointed questions beats fifty shallow
# ones, and keeps the dive short. Each is (topic_suffix, title, question); the
# artifact brief is supplied as MATERIAL by the orchestrator.

_LAYER1_SETS = {
    "network": [
        ("dominant_hosts", "Dominant hosts",
         "Which hosts dominate this capture's conversation, and what is the "
         "balance between internal and external endpoints?"),
        ("unusual_destinations", "Unusual destinations",
         "Are any destination hosts, ports, or protocols unusual or suspicious "
         "for an ordinary workstation, and why?"),
        ("timeframe", "Capture timeframe",
         "What period does this capture cover, and is the activity spread evenly "
         "or concentrated into bursts?"),
        ("exfiltration", "Signs of data leaving",
         "Does any traffic suggest data leaving the network — large or "
         "one-directional outbound transfers — and to where?"),
    ],
    "disk": [
        ("user_activity", "User activity",
         "What user activity is evident on this image: files created, opened or "
         "copied, and in whose directories?"),
        ("deletions", "Deletions",
         "What was deleted and when, and does the pattern look routine or "
         "deliberate, such as a burst of deletions?"),
        ("tooling_concealment", "Tooling and concealment",
         "Is there evidence of tooling or concealment — archivers, wiping tools, "
         "alternate data streams, timestamp anomalies, or orphaned entries?"),
        ("timeframe_actors", "Timeframe and account",
         "What timeframe does the significant activity span, and which "
         "account(s) does it attribute to?"),
    ],
    "_generic": [
        ("evidences", "What this evidences",
         "What does this artifact evidence for the investigation — what activity "
         "or facts does it establish?"),
        ("anomalies", "Anything notable",
         "Is there anything anomalous or noteworthy in this artifact's records — "
         "unusual timestamps, actors, or entries?"),
    ],
}

_LAYER2_SET = [
    ("overlapping_timeframes", "Overlapping timeframes",
     "Across the artifacts, do any timeframes overlap or line up into a single "
     "sequence of activity?"),
    ("corroboration", "Corroboration and contradiction",
     "Where do the artifacts corroborate one another, and where do they "
     "contradict?"),
    ("cross_source_sequences", "Cross-source sequences",
     "Is there a sequence of actions that spans more than one artifact, for "
     "example staging on disk followed by transfer over the network?"),
]

# Layer-3 writes the exact topics the consuming surfaces read by name.
_LAYER3_SET = [
    (kb.TOPIC_CASE_NARRATIVE, "What happened",
     "Give the case-level narrative: what happened and in what order, "
     "attributing actions to accounts rather than named people."),
    (kb.TOPIC_FINDINGS_ASSESSMENT, "What the evidence shows",
     "Reason over the findings as a whole: what do they collectively indicate, "
     "how do they relate, and what should the examiner conclude?"),
    (kb.TOPIC_EXECUTIVE_SUMMARY, "Executive summary",
     "Write the report's executive summary: what was examined, what was found, "
     "the single most significant point, and the overall risk level."),
    (kb.TOPIC_CONCLUSION, "Conclusion",
     "Write the report's conclusion: the collective read of the evidence, your "
     "confidence in it and why, what remains unexplained, and the single most "
     "useful next step."),
    (kb.TOPIC_CASE_OVERVIEW, "Case overview",
     "Write a single plain-English paragraph for the case dashboard: the story "
     "of the case as it currently reads."),
]


def _layer1_digest(knowledge):
    lines = [f"- {e.get('title')} ({', '.join(e.get('artifact_ids', [])) or '—'}): "
             f"{e.get('answer')}" for e in knowledge.by_layer(kb.LAYER_PER_ARTIFACT)]
    return ("Per-artifact findings so far:\n" + "\n".join(lines)) if lines else \
        "No per-artifact findings are available yet."


def _layer12_digest(knowledge):
    parts = [_layer1_digest(knowledge)]
    cross = [f"- {e.get('title')}: {e.get('answer')}"
             for e in knowledge.by_layer(kb.LAYER_CROSS_ARTIFACT)]
    if cross:
        parts.append("Cross-artifact findings:\n" + "\n".join(cross))
    return "\n\n".join(parts)


class DeepDive:
    """Runs the three-layer dive, emitting each entry as it is produced.

    call_llm(prompt) -> str | None : None means the model is unreachable.
    is_cancelled()   -> bool       : checked between prompts.
    on_entry(entry, step)          : one finished KB entry (for live UI + save).
    on_progress(done, total)       : after every prompt (for the countdown).
    on_milestone()                 : at a persistence-worthy boundary.
    log(msg)                       : audit / diagnostic line.
    """

    def __init__(self, case, events, call_llm, *, is_cancelled=None,
                 on_entry=None, on_progress=None, on_milestone=None, log=None):
        self.case = case or {}
        self.events = events or []
        self._call_llm = call_llm
        self._is_cancelled = is_cancelled or (lambda: False)
        self._on_entry = on_entry or (lambda entry, step: None)
        self._on_progress = on_progress or (lambda done, total: None)
        self._on_milestone = on_milestone or (lambda: None)
        self._log = log or (lambda msg: None)
        self._spec = format_library.load("kb_entry")

    # ── planning ──────────────────────────────────────────────────────────────

    def plan(self):
        """The ordered list of prompt steps. The COUNT is fixed up front (so the
        countdown can be honest); each step's MATERIAL is built at run time,
        because layers 2 and 3 read the entries the earlier layers produced."""
        steps = []

        for ev in self.case.get("evidence", []):
            kind = ev.get("kind", "unknown")
            prompt_set = _LAYER1_SETS.get(kind, _LAYER1_SETS["_generic"])
            ev_events = _artifact_events(self.events, ev.get("id"))
            findings = _artifact_findings(self.case, ev.get("id"))
            brief = _BRIEF_BUILDERS.get(kind, _generic_brief)(ev, ev_events, findings)
            finding_ids = [f.get("id") for f in findings]
            for index, (suffix, title, question) in enumerate(prompt_set):
                steps.append({
                    "layer":        kb.LAYER_PER_ARTIFACT,
                    "topic":        f"{kind}:{suffix}",
                    "title":        title,
                    "question":     question,
                    "artifact_ids": [ev.get("id")],
                    "finding_ids":  finding_ids,
                    "material":     lambda _k, b=brief: b,
                    "milestone":    index == len(prompt_set) - 1,
                })

        for index, (suffix, title, question) in enumerate(_LAYER2_SET):
            steps.append({
                "layer":        kb.LAYER_CROSS_ARTIFACT,
                "topic":        f"cross:{suffix}",
                "title":        title,
                "question":     question,
                "artifact_ids": [e.get("id") for e in self.case.get("evidence", [])],
                "finding_ids":  [],
                "material":     _layer1_digest,
                "milestone":    index == len(_LAYER2_SET) - 1,
            })

        top_findings = [f.get("id") for f in self.case.get("findings", [])[:10]]
        for index, (topic, title, question) in enumerate(_LAYER3_SET):
            steps.append({
                "layer":        kb.LAYER_SYNTHESIS,
                "topic":        topic,
                "title":        title,
                "question":     question,
                "artifact_ids": [e.get("id") for e in self.case.get("evidence", [])],
                "finding_ids":  top_findings,
                "material":     _layer12_digest,
                "milestone":    index == len(_LAYER3_SET) - 1,
            })

        return steps

    # ── run ─────────────────────────────────────────────────────────────────────

    def run(self, knowledge):
        """Execute the plan against `knowledge` (a KnowledgeBase, possibly with
        entries from a previous, interrupted run — those are skipped). Returns
        one of: "complete", "cancelled", "unavailable"."""
        steps = self.plan()
        total = len(steps)
        done = 0
        self._on_progress(done, total)

        for step in steps:
            if self._is_cancelled():
                self._log("Deep dive cancelled by request.")
                return "cancelled"

            resume_artifact = (step["artifact_ids"][0]
                               if step["layer"] == kb.LAYER_PER_ARTIFACT
                               and step["artifact_ids"] else None)
            if knowledge.has(step["layer"], step["topic"], resume_artifact):
                done += 1
                self._on_progress(done, total)
                continue

            material = step["material"](knowledge)
            answer = self._ask(step["question"], material)
            if answer is None:
                self._log("Model became unavailable — keeping completed insights.")
                return "unavailable"

            if answer.strip():
                entry = kb.make_entry(
                    step["topic"], step["title"], answer, step["layer"],
                    artifact_ids=step["artifact_ids"],
                    finding_ids=step["finding_ids"],
                    confidence=_infer_confidence(answer), generated_at=_now())
                knowledge.add(entry)
                self._on_entry(entry, step)

            done += 1
            self._on_progress(done, total)
            if step["milestone"]:
                self._on_milestone()

        return "complete"

    def _ask(self, question, material):
        """One KB-entry generation with a single validation-guided retry.
        Returns the answer text, or None only when the model is unreachable."""
        base = (f"{_PERSONA}\n\n{self._spec.prompt_text if self._spec else ''}\n\n"
                f"MATERIAL:\n{material}\n\nQUESTION: {question}\n\nANSWER:")
        prompt = base
        text = ""
        for _attempt in range(2):
            raw = self._call_llm(prompt)
            if raw is None:
                return None  # unreachable — degrade honestly
            text = format_library.strip_leading_meta(_strip_label(raw))
            violations = self._spec.validate(text) if self._spec else []
            if not violations:
                return text
            prompt = (f"{base}\n\nYour previous answer violated the format "
                      f"({'; '.join(violations)}). Rewrite it correctly.\nANSWER:")
        return text  # accept the last attempt; a weak digest beats none


def _strip_label(text):
    cleaned = (text or "").strip().strip("`").strip()
    for label in ("ANSWER:", "TEXT:", "OUTPUT:"):
        if cleaned.upper().startswith(label):
            cleaned = cleaned[len(label):].strip()
    return cleaned

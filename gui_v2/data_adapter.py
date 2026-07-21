"""
gui_v2/data_adapter.py

Bridges the forensic pipeline to the shape the screens render.

The screens never branch on "demo vs real": content.demo_case() and this module
produce the same keys, so anything that works against the fixture works against
a live analysis. That contract is the whole point of this file — see
gui_v2/content.py for the reference shape.

The pipeline emits machine facts (a type, a severity number, a rule id). The UI
needs to answer three questions for every finding — what is this, why am I
seeing it, what should I do — so this module is where that translation happens:
severity numbers become words, ATT&CK codes get their plain-English name, and
each finding type carries the follow-up actions an examiner would actually take.
Where the pipeline genuinely cannot know something (the narrative "phase" of an
incident), the key is omitted rather than guessed, and the UI degrades to a flat
list instead of inventing structure.
"""

import datetime

from .content import REPORT_TITLE

# ── severity ──────────────────────────────────────────────────────────────────

SEV_TEXT = {4: "CRITICAL", 3: "HIGH", 2: "MEDIUM", 1: "LOW"}

# Screen-facing titles for the pipeline's finding types.
TITLES = {
    "deleted_user_file": "Deleted user file recovered",
    "wiped_mft_metadata": "MFT metadata deliberately wiped",
    "orphaned_file": "Orphaned MFT entry (unlinked file)",
    "alternate_data_stream": "NTFS alternate data stream detected",
    "timestamp_anomaly": "Timestamp anomaly — possible timestomping",
    "large_badclus_stream": "Abnormal $BadClus stream — hidden data suspected",
    "deleted_directory_with_live_children": "Deleted directory retains live children",
    "activity_burst": "Filesystem activity burst",
    "rare_extension": "Rare file extension observed",
    "large_file": "Unusually large file",
    "service_installed": "Service installed",
    "history_gap": "Log or history gap",
    "exfiltration_removable_media": "Data written to removable media",
}

# What an examiner should do next, per finding type. Without these the rail's
# "WHAT SHOULD I DO?" block would be empty on every real case — which is the
# exact failure the redesign exists to fix.
NEXT_STEPS = {
    "deleted_user_file": [
        "Recover the file from unallocated space and hash it",
        "Establish whether the deletion was routine for this user",
    ],
    "wiped_mft_metadata": [
        "Compare against the $MFTMirr backup for surviving records",
        "Check for wiping tools in installed programs and prefetch",
    ],
    "timestamp_anomaly": [
        "Treat the affected timestamps as untrusted in the timeline",
        "Corroborate the sequence against a second source (registry, event log)",
    ],
    "activity_burst": [
        "Check what the burst touched — user data or system files",
        "Compare the rate against this user's normal baseline",
    ],
    "exfiltration_removable_media": [
        "Identify the device from the registry (USBSTOR serial)",
        "Acquire the physical device if it can be located",
    ],
    "history_gap": [
        "Recover surviving records from backups or unallocated space",
        "Check whether the gap aligns with other activity",
    ],
    "service_installed": [
        "Establish whether the service was sanctioned",
        "Check the binary's path and signature",
    ],
    "alternate_data_stream": [
        "Read the stream's contents in the raw viewer",
        "Check whether the stream hides an executable",
    ],
}

GENERIC_NEXT = ["Open the supporting evidence and confirm the underlying records",
                "Corroborate against a second source before relying on this"]

# ── evidence ──────────────────────────────────────────────────────────────────

# Plain-English descriptions per artifact kind, so the rail can say what an
# artifact *is* rather than repeating its filename.
KIND_PLAIN = {
    "disk": ("A bit-for-bit copy of a drive — the record of what happened on it.",
             "It anchors filesystem findings: what was created, copied and deleted."),
    "browser": ("What the user searched for and visited, with timestamps.",
                "It shows intent and activity around the incident."),
    "registry": ("Windows settings — records devices, recent files and program use.",
                 "It identifies attached devices and when they were connected."),
    "eventlog": ("Windows' own record of sign-ins, services and system events.",
                 "It establishes who was signed in and when."),
    "prefetch": ("Windows' record of which programs ran, and when.",
                 "It shows what was executed on the machine."),
    "network": ("Captured network traffic.",
                "It shows what left or entered the machine over the network."),
    "email": ("Stored mail messages and attachments.",
              "It shows what was communicated and what was attached."),
    "unknown": ("An artifact of an unrecognised type, read as raw bytes.",
                "Its role in the case has not been established."),
}

REL_MAP = {"significant": "sig", "notable": "not", "context": "ctx", "noise": "noise"}

# The parsers are inconsistent about source casing ("disk" vs "Disk"), and the
# timeline's filter pills and source colours both key off the exact string — an
# unnormalised "disk" silently matches no filter and renders in the default
# grey. Canonicalise here, once, rather than making every screen defensive.
SRC_CANON = {
    "disk": "Disk", "browser": "Browser", "browser_visit": "Browser",
    "downloads": "Downloads", "browser_download": "Downloads",
    "cookie": "Browser", "registry": "Registry", "eventlog": "EventLog",
    "event_log": "EventLog", "usb": "USB", "network": "Network",
    "email": "Email", "prefetch": "Disk",
}


def _src(raw):
    if not raw:
        return "Disk"
    return SRC_CANON.get(str(raw).strip().lower(), str(raw).strip().capitalize())


def _fmt(ts):
    try:
        return datetime.datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts) if ts else ""


def _risk(findings):
    w = {4: 25, 3: 12, 2: 5, 1: 1}
    score = min(100, sum(w.get(f.get("severity", 1), 1) for f in findings))
    label = ("CRITICAL" if score >= 90 else "HIGH" if score >= 60
             else "MEDIUM" if score >= 30 else "LOW")
    return score, label


def _first_sentence(text, limit=110):
    """A one-line summary for the finding card, from the rule's reasoning."""
    t = " ".join(str(text or "").split())
    if not t:
        return ""
    for stop in (". ", "; "):
        if stop in t[:limit + 40]:
            return t.split(stop)[0].strip() + "."
    return (t[:limit].rstrip() + "…") if len(t) > limit else t


def _why(f):
    """Assemble "why am I seeing this" from confidence, ATT&CK and the rule.

    The design forbids showing a bare technique code, so the technique is only
    mentioned when its human-readable name is available to go with it.
    """
    parts = []
    conf = f.get("conf") or "Medium"
    parts.append(f"Confidence is {str(conf).lower()} — this was raised by "
                 f"{f.get('rule') or 'the rule and anomaly engines'}.")
    mitre, mname = f.get("mitre"), f.get("mitreName")
    if mitre and mname:
        parts.append(f"Technique {mitre} (“{mname}”): the behaviour this finding "
                     f"matches in the ATT&CK catalogue.")
    return " ".join(parts)


def reshape_case(meta: dict, evidence: list, audit: list, analysis) -> dict:
    """Build the screen-facing case dict from a CaseBuilder's state.

    Works with any number of evidence items and any mix of kinds. `analysis` may
    be None (case created, not yet analyzed).
    """
    analysis = analysis or {}
    raw_findings = analysis.get("findings", [])
    raw_events = analysis.get("events", [])
    ev_ids = [e["id"] for e in evidence]

    # ── findings ──────────────────────────────────────────────────────────────
    sorted_f = sorted(raw_findings, key=lambda f: -f.get("severity", 1))
    findings, fid_by_type = [], {}
    for i, f in enumerate(sorted_f):
        ftype = f.get("type", "finding")
        fid = f"F-{i+1:02d}"
        sev = f.get("severity", 1)

        art = None
        if isinstance(f.get("details"), dict):
            art = f["details"].get("artifact")
        refs = [art] if art in ev_ids else (ev_ids[:1] if ev_ids else [])

        reason = f.get("reason", "")
        findings.append({
            "id": fid,
            "sev": SEV_TEXT.get(sev, "LOW"),
            "conf": f.get("conf", "Medium"),
            "title": TITLES.get(ftype, ftype.replace("_", " ").capitalize()),
            "short": _first_sentence(reason) or "No further detail was recorded.",
            "what": reason or "The engine flagged this without a written reason.",
            "why": _why(f),
            "next": list(NEXT_STEPS.get(ftype, GENERIC_NEXT)),
            "mitre": f.get("mitre") or "—",
            "mitreName": f.get("mitreName"),
            "ev": refs,
            "ts": _fmt(f.get("timestamp")),
            "rule": f.get("rule", ""),
            # No "phase": the pipeline has no notion of an incident narrative,
            # and a guessed phase would be a claim the evidence does not make.
            # Findings without one render as a flat list.
        })
        fid_by_type.setdefault(ftype, fid)

    # ── events ────────────────────────────────────────────────────────────────
    events = []
    for e in raw_events:
        meaning = (e.get("meaning") or e.get("description") or e.get("note") or "")
        events.append({
            "ts": _fmt(e.get("timestamp")),
            "src": _src(e.get("source")),
            "label": (e.get("label") or "")[:160],
            "mean": meaning or "No interpretation was recorded for this record.",
            "rel": REL_MAP.get(e.get("relevance", "context"), "ctx"),
            "fid": fid_by_type.get(e.get("type")),
            "path": (e.get("path") or "")[:160],
            "sev": e.get("sev", 1),
            "artifact": e.get("artifact"),  # enables per-artifact drill-down
        })

    # ── evidence ──────────────────────────────────────────────────────────────
    ev_ui = []
    for e in evidence:
        d = dict(e)                      # keep _path; main_window re-verifies with it
        kind = e.get("kind", "unknown")
        plain, role = KIND_PLAIN.get(kind, KIND_PLAIN["unknown"])
        d["kindLabel"] = e.get("type", "Artifact")
        d["sha"] = e.get("sha256", "")
        d["intake"] = e.get("added", "—")
        d["plain"] = plain
        d["role"] = (f"{role} It contributed {e.get('events', 0):,} events to the "
                     f"timeline." if e.get("events") else role)
        ev_ui.append(d)

    score, risk_label = _risk(raw_findings)
    pipeline = analysis.get("pipeline", {
        "lastRun": "—", "duration": "—", "eventsParsed": 0, "status": "idle"})

    crit = sum(1 for f in findings if f["sev"] == "CRITICAL")
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    return {
        "loaded": True,
        "demo": False,
        "caseMeta": {
            "id": meta["id"], "title": meta["title"],
            "examiner": meta["examiner"], "examinerId": meta["examinerId"],
            "agency": meta.get("agency", ""), "opened": meta["opened"],
            "custodian": meta.get("custodian", meta["examiner"]),
            "riskScore": score, "riskLabel": risk_label,
            "riskCaption": (f"Driven by {crit} critical finding"
                            f"{'s' if crit != 1 else ''}." if crit else
                            f"Based on {len(findings)} finding"
                            f"{'s' if len(findings) != 1 else ''} below critical."
                            if findings else
                            "No findings crossed the reporting threshold."),
            "aiEngine": {"provider": "Ollama (local)", "model": "llama3.2:3b",
                         "status": "online" if analysis else "idle",
                         "fallback": "Local → Cloud key (if set) → Rule-based"},
            "pipeline": pipeline,
        },
        "evidence": ev_ui,
        "events": events,
        "findings": findings,
        "audit": list(audit),
        "paragraph": None,          # CaseScreen writes its own summary instead
        "report": {
            "title": REPORT_TITLE,
            "byline": (f"Examiner {meta['examiner']} ({meta['examinerId']}) · "
                       f"Generated {now} · Drafted by the local model, "
                       f"reviewed by the examiner"),
            "summary": _summary(analysis, findings, evidence, pipeline),
            "footer": (f"The exported PDF embeds the SHA-256 of all "
                       f"{len(evidence)} artifact(s) and the full audit trail.\n"
                       f"Evidence was mounted read-only throughout the examination."),
            "order": [f["id"] for f in findings],
            "include": {f["id"]: True for f in findings},
        },
    }


def _summary(analysis, findings, evidence, pipeline):
    """The report's executive summary: the model's narrative if it wrote one,
    otherwise a factual statement of what was examined and found."""
    md = (analysis.get("narrative") or "").strip()
    if md:
        # First real paragraph of the generated markdown.
        for block in md.split("\n\n"):
            text = " ".join(l.strip() for l in block.splitlines()
                            if l.strip() and not l.strip().startswith(("#", "-", "*")))
            if len(text) > 80:
                # Same sanitizer the PDF uses: the model's markdown must never
                # reach a rendered surface (** and backticks in the preview).
                from .report_pdf import _clean
                return _clean(text)
    crit = sum(1 for f in findings if f["sev"] == "CRITICAL")
    return (f"{len(evidence)} artifact(s) were examined and parsed into "
            f"{pipeline.get('eventsParsed', 0):,} events. The analysis produced "
            f"{len(findings)} finding(s)"
            f"{f', {crit} of them critical' if crit else ''}. "
            f"Each finding below states what was observed and which artifacts "
            f"support it.")

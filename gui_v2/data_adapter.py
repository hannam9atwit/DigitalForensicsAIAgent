"""
gui_v2/data_adapter.py

Bridges the existing forensic pipeline to the GUI's case-dict shape.

build_case_from_analysis() takes the dict returned by
ai.reasoning_engine.ReasoningEngine.analyze() (the same object the old
pipeline produced) plus some intake metadata, and reshapes it into exactly
what screens.py expects — so the native screens render real results with no
code changes.

It also folds in MITRE + confidence via ai.ioc_matcher if that module is
present (added in the integration step); if not, it degrades gracefully.
"""

import datetime
import hashlib
import os

try:
    from ai import ioc_matcher
except Exception:                      # ioc_matcher optional
    ioc_matcher = None

SEV_LABEL = {4: "Critical", 3: "High", 2: "Medium", 1: "Low"}

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
}

SRC_MAP = {"disk": "Disk", "browser_visit": "Browser", "browser_download": "Downloads",
           "cookie": "Browser", "EventLog": "EventLog", "Registry": "Registry",
           "Network": "Network", "Email": "Email", "USB": "USB"}


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


def build_case_from_analysis(analysis: dict, *, artifact_path: str,
                             examiner="Examiner", examiner_id="EX-00",
                             case_id=None, agency="") -> dict:
    raw_findings = analysis.get("findings", [])
    raw_events = analysis.get("timeline", {}).get("events", [])

    # findings: assign F-IDs (critical-first), MITRE, confidence
    sorted_f = sorted(raw_findings, key=lambda f: -f.get("severity", 1))
    findings = []
    fid_by_type = {}
    for i, f in enumerate(sorted_f):
        ftype = f.get("type", "finding")
        fid = f"F-{i+1:02d}"
        mitre, mname = (ioc_matcher.match(ftype) if ioc_matcher else (None, None))
        conf = (ioc_matcher.confidence(f) if ioc_matcher else "Medium")
        findings.append({
            "id": fid, "sev": f.get("severity", 1), "conf": conf,
            "mitre": mitre, "mitreName": mname,
            "title": TITLES.get(ftype, ftype.replace("_", " ").capitalize()),
            "ts": _fmt(f.get("timestamp")),
            "evidence": ["EV-01"],
            "reason": f.get("reason", ""),
            "rule": f.get("rule", "rule engine / anomaly engine"),
        })
        fid_by_type.setdefault(ftype, fid)

    # events: (ts, src, label, path, sev, fid)
    events = []
    for e in raw_events:
        src_raw = e.get("source", "disk")
        src = SRC_MAP.get(src_raw, src_raw.capitalize() if isinstance(src_raw, str) else "Disk")
        label = e.get("label") or ("Filesystem — " + (e.get("path") or "")[-70:])
        events.append((_fmt(e.get("timestamp")), src, label[:120],
                       (e.get("path") or "")[:160], e.get("sev", 1),
                       fid_by_type.get(e.get("type"))))

    # evidence (single artifact intake; real CoC lives in server.case_manager
    # if you adopt it, but the native app can hash here directly)
    digest = ""
    size_s = "—"
    try:
        h = hashlib.sha256()
        with open(artifact_path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        digest = h.hexdigest()
        n = os.path.getsize(artifact_path)
        size_s = (f"{n/1_073_741_824:.1f} GB" if n >= 1_073_741_824
                  else f"{n/1_048_576:.1f} MB" if n >= 1_048_576 else f"{n/1024:.1f} KB")
    except Exception:
        pass

    score, risk_label = _risk(raw_findings)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    evidence = [{
        "id": "EV-01", "name": os.path.basename(artifact_path),
        "type": "Evidence artifact", "kind": "disk", "size": size_s,
        "added": now, "sha256": digest, "verified": bool(digest),
        "lastVerified": now if digest else None,
        "detail": f"{len(raw_events)} events parsed",
        "parser": "pipeline", "events": len(raw_events),
    }]

    # narrative sections from the markdown
    sections = []
    md = analysis.get("narrative", "")
    cur_h, cur_b = None, []
    for line in md.split("\n"):
        s = line.strip()
        if s.startswith("## "):
            if cur_h:
                sections.append((cur_h, "Medium", " ".join(cur_b).strip()))
            cur_h, cur_b = s.lstrip("# ").strip(), []
        elif s and s != "---":
            cur_b.append(s)
    if cur_h:
        sections.append((cur_h, "Medium", " ".join(cur_b).strip()))

    audit = [
        (now, examiner, "CASE_CREATED", f"Case registered for {os.path.basename(artifact_path)}"),
        (now, examiner, "EVIDENCE_ADDED",
         f"{os.path.basename(artifact_path)} · SHA-256 {digest[:8]}…{digest[-6:]} (read-only)" if digest else "artifact added"),
        (now, "system", "ANALYSIS_COMPLETE", f"{len(raw_events)} events · {len(findings)} findings"),
    ]

    return {
        "caseMeta": {
            "id": case_id or f"FA-{datetime.date.today().year}-{abs(hash(artifact_path)) % 10000:04d}",
            "title": "Investigation: " + os.path.basename(artifact_path),
            "examiner": examiner, "examinerId": examiner_id, "agency": agency,
            "opened": now, "custodian": examiner,
            "riskScore": score, "riskLabel": risk_label,
            "aiEngine": {"provider": "OpenClaw → Ollama (local)", "model": "llama3.2:3b",
                         "status": "online", "fallback": "Claude API → Rule-based"},
            "pipeline": {"lastRun": now, "duration": "—",
                         "eventsParsed": len(raw_events), "status": "complete"},
        },
        "evidence": evidence,
        "events": events,
        "findings": findings,
        "narrative": {"generated": now, "engine": "OpenClaw → Ollama · llama3.2:3b (local)",
                      "sections": sections or [("Summary", "Medium", md[:800] or "No narrative generated.")]},
        "audit": audit,
    }


# ── multi-evidence reshape (used by case_model.CaseBuilder) ───────────────────

def reshape_case(meta: dict, evidence: list, audit: list, analysis) -> dict:
    """
    Build the screen-facing case dict from a CaseBuilder's state.
    Works with any number of evidence items and any mix of artifact kinds.
    `analysis` may be None (case created but not yet analyzed).
    """
    analysis = analysis or {}
    raw_findings = analysis.get("findings", [])
    raw_events = analysis.get("events", [])

    # findings → F-IDs (critical first) with MITRE + confidence already attached
    sorted_f = sorted(raw_findings, key=lambda f: -f.get("severity", 1))
    findings, fid_by_type = [], {}
    for i, f in enumerate(sorted_f):
        ftype = f.get("type", "finding")
        fid = f"F-{i+1:02d}"
        art = None
        if isinstance(f.get("details"), dict):
            art = f["details"].get("artifact")
        findings.append({
            "id": fid, "sev": f.get("severity", 1),
            "conf": f.get("conf", "Medium"),
            "mitre": f.get("mitre"), "mitreName": f.get("mitreName"),
            "title": TITLES.get(ftype, ftype.replace("_", " ").capitalize()),
            "ts": _fmt(f.get("timestamp")),
            "evidence": [art] if art else [e["id"] for e in evidence[:1]],
            "reason": f.get("reason", ""),
            "rule": f.get("rule", "rule engine / anomaly engine"),
        })
        fid_by_type.setdefault(ftype, fid)

    # events → dicts carrying interpretation (description, relevance, note)
    events = []
    for e in raw_events:
        events.append({
            "ts": _fmt(e.get("timestamp")),
            "src": e.get("source", "Disk"),
            "label": (e.get("label") or "")[:120],
            "path": (e.get("path") or "")[:160],
            "sev": e.get("sev", 1),
            "fid": fid_by_type.get(e.get("type")),
            "description": e.get("description", ""),
            "relevance": e.get("relevance", "context"),
            "note": e.get("note", ""),
            "meaning": e.get("meaning", ""),
        })

    # evidence → strip private _path into a UI-safe copy (keep _path for re-verify)
    ev_ui = []
    for e in evidence:
        d = dict(e)
        ev_ui.append(d)  # keep _path; screens ignore unknown keys, main_window uses it

    score, risk_label = _risk(raw_findings)
    pipeline = analysis.get("pipeline", {
        "lastRun": "—", "duration": "—", "eventsParsed": 0, "status": "idle"})

    # narrative markdown → sections
    sections = []
    cur_h, cur_b = None, []
    for line in analysis.get("narrative", "").split("\n"):
        s = line.strip()
        if s.startswith("## "):
            if cur_h:
                sections.append((cur_h, "Medium", " ".join(cur_b).strip()))
            cur_h, cur_b = s.lstrip("# ").strip(), []
        elif s and s != "---":
            cur_b.append(s)
    if cur_h:
        sections.append((cur_h, "Medium", " ".join(cur_b).strip()))
    for sec in sections[:2]:
        if sec[1] == "Medium":
            sections[sections.index(sec)] = (sec[0], "High", sec[2])

    return {
        "loaded": True,
        "caseMeta": {
            "id": meta["id"], "title": meta["title"],
            "examiner": meta["examiner"], "examinerId": meta["examinerId"],
            "agency": meta.get("agency", ""), "opened": meta["opened"],
            "custodian": meta.get("custodian", meta["examiner"]),
            "riskScore": score, "riskLabel": risk_label,
            "aiEngine": {"provider": "OpenClaw → Ollama (local)", "model": "llama3.2:3b",
                         "status": "online" if analysis else "idle",
                         "fallback": "Claude API → Rule-based"},
            "pipeline": pipeline,
        },
        "evidence": ev_ui,
        "events": events,
        "findings": findings,
        "narrative": {
            "generated": pipeline.get("lastRun", "—"),
            "engine": "OpenClaw → Ollama · llama3.2:3b (local)",
            "sections": sections,
        },
        "audit": list(audit),
    }

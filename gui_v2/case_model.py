"""
gui_v2/case_model.py

The case the GUI works on. Supports an EMPTY state (no demo data) and building
up a real case from one or more evidence files of any supported kind.

This is the single place that:
  - detects what each evidence file is (disk / browser / eventlog / registry /
    prefetch / network / email)
  - SHA-256 hashes each file on intake (chain of custody)
  - records an append-only audit trail
  - runs every artifact through the right parser and merges one timeline
  - reshapes the result into the dict the screens render

It deliberately does NOT depend on PySide6, so it can be unit-tested headless.
"""

import os
import hashlib
import datetime

# Parsers — existing pipeline pieces plus the new Windows/network/email ones.
# All imports are deferred inside methods so a partial checkout still launches.

SUPPORTED_EXT = {
    ".e01": "disk", ".ex01": "disk", ".s01": "disk", ".img": "disk",
    ".dd": "disk", ".raw": "disk",
    ".evtx": "eventlog",
    ".pf": "prefetch",
    ".pcap": "network", ".pcapng": "network",
    ".mbox": "email", ".eml": "email",
    ".hive": "registry",
}
SUPPORTED_NAMES = {
    "history": "browser", "history.db": "browser", "places.sqlite": "browser",
    "downloads": "browser",
    "ntuser.dat": "registry", "sam": "registry", "system": "registry",
    "software": "registry", "security": "registry",
}

KIND_LABEL = {
    "disk": "Disk Image", "browser": "Browser Artifact (SQLite)",
    "registry": "Registry Hive", "eventlog": "Windows Event Log (EVTX)",
    "prefetch": "Windows Prefetch", "network": "Network Capture (PCAP)",
    "email": "Email Archive", "unknown": "Unknown Artifact",
}

KIND_SRC = {"disk": "Disk", "browser": "Browser", "registry": "Registry",
            "eventlog": "EventLog", "prefetch": "Disk", "network": "Network",
            "email": "Email", "unknown": "Disk"}


def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def detect_kind(path):
    name = os.path.basename(path).lower()
    if name in SUPPORTED_NAMES:
        return SUPPORTED_NAMES[name]
    if "cookies" in name:
        return "browser"
    ext = os.path.splitext(name)[1].lower()
    return SUPPORTED_EXT.get(ext, "unknown")


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(chunk), b""):
            h.update(blk)
    return h.hexdigest()


def _size_str(n):
    if n >= 1_073_741_824:
        return f"{n/1_073_741_824:.1f} GB"
    if n >= 1_048_576:
        return f"{n/1_048_576:.1f} MB"
    if n >= 1024:
        return f"{n/1024:.1f} KB"
    return f"{n} B"


def empty_case():
    """The blank state shown on launch — no demo data."""
    return {
        "loaded": False,
        "caseMeta": {
            "id": "—", "title": "No case loaded", "examiner": "—", "examinerId": "—",
            "agency": "—", "opened": "—", "custodian": "—",
            "riskScore": 0, "riskLabel": "—",
            "aiEngine": {"provider": "Ollama (local)", "model": "llama3.2:3b",
                         "status": "idle", "fallback": "Claude API → Rule-based"},
            "pipeline": {"lastRun": "—", "duration": "—", "eventsParsed": 0, "status": "idle"},
        },
        "evidence": [], "events": [], "findings": [],
        "narrative": {"generated": "—", "engine": "—", "sections": []},
        "audit": [],
    }


class CaseBuilder:
    """Owns case metadata, evidence intake, analysis, and reshaping."""

    def __init__(self, examiner="Examiner", examiner_id="EX-00", agency="",
                 case_id=None, title=None):
        self.meta = {
            "id": case_id or f"FA-{datetime.date.today().year}-{abs(hash(_now())) % 10000:04d}",
            "title": title or "Untitled investigation",
            "examiner": examiner, "examinerId": examiner_id, "agency": agency,
            "opened": _now(), "custodian": examiner,
        }
        self.evidence = []     # list of dicts incl. private "_path"
        self.audit = []
        self.analysis = None
        self._log("CASE_CREATED", f"Case {self.meta['id']} registered · intake completed")

    def _log(self, act, detail, who=None):
        self.audit.append((_now(), who or self.meta["examiner"], act, detail))

    # ── intake ────────────────────────────────────────────────────────────────

    def add_evidence(self, path):
        path = os.path.abspath(path)
        kind = detect_kind(path)
        digest = sha256_file(path)
        ev = {
            "id": f"EV-{len(self.evidence)+1:02d}",
            "name": os.path.basename(path),
            "type": KIND_LABEL[kind], "kind": kind,
            "size": _size_str(os.path.getsize(path)),
            "added": _now(), "sha256": digest,
            "verified": True, "lastVerified": _now(),
            "detail": "Pending analysis", "parser": "—", "events": 0,
            "_path": path,
        }
        self.evidence.append(ev)
        self._log("EVIDENCE_ADDED",
                  f"{ev['name']} ({KIND_LABEL[kind]}) · SHA-256 "
                  f"{digest[:8]}…{digest[-6:]} computed (read-only)")
        return ev

    def reverify(self):
        results = {}
        for e in self.evidence:
            try:
                results[e["id"]] = (sha256_file(e["_path"]) == e["sha256"])
            except OSError:
                results[e["id"]] = False
            e["verified"] = results[e["id"]]
            e["lastVerified"] = _now()
        ok = sum(results.values())
        self._log("HASH_VERIFIED", f"{ok}/{len(self.evidence)} artifacts re-verified OK",
                  who="system")
        return results

    # ── analysis ──────────────────────────────────────────────────────────────

    def analyze(self, log=print, ai_config=None):
        """Run every evidence item through its parser, merge, reason, narrate."""
        from .pipeline_router import run_analysis
        self._log("ANALYSIS_STARTED",
                  f"Full pipeline · {len(self.evidence)} artifacts queued", who="system")
        self.analysis = run_analysis(self.evidence, log=log, ai_config=ai_config)
        self._log("ANALYSIS_COMPLETE",
                  f"{len(self.analysis['events'])} events · "
                  f"{len(self.analysis['findings'])} findings", who="system")
        return self.analysis

    # ── reshape to screen dict ─────────────────────────────────────────────────

    def to_case(self):
        from .data_adapter import reshape_case
        return reshape_case(self.meta, self.evidence, self.audit, self.analysis)

"""
gui_v2/case_store.py

Local case persistence + history. Cases are saved as ".forensic" files (a zip
containing case.json + audit.jsonl) under a per-user app-data directory, so an
examiner can close the app and reopen any previous case.

No network, no database — just files on disk, which suits an offline tool and
keeps the evidence-handling auditable.
"""

import os
import json
import zipfile
import datetime
import platform


def app_data_dir() -> str:
    """Per-OS writable folder for saved cases."""
    if platform.system() == "Windows":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    elif platform.system() == "Darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    path = os.path.join(base, "AIRforensics", "cases")
    os.makedirs(path, exist_ok=True)
    return path


def _safe_name(case_id: str) -> str:
    keep = "-_."
    return "".join(c if (c.isalnum() or c in keep) else "_" for c in case_id)


def save_case(builder, directory=None) -> str:
    """
    Serialize a CaseBuilder to <dir>/<case_id>.forensic.
    Stores metadata, evidence records (incl. hash + original path), the audit
    trail, and the last analysis result so the case reopens fully populated.
    """
    directory = directory or app_data_dir()
    os.makedirs(directory, exist_ok=True)
    out = os.path.join(directory, _safe_name(builder.meta["id"]) + ".forensic")

    blob = {
        "meta": builder.meta,
        "evidence": builder.evidence,          # includes "_path" + hashes
        "analysis": builder.analysis,          # may be None if not analyzed yet
        "saved": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "schema": 1,
    }
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("case.json", json.dumps(blob, indent=2, default=str))
        z.writestr("audit.jsonl", "\n".join(json.dumps(list(a)) for a in builder.audit))

    builder._log("CASE_SAVED", f"Case written to {os.path.basename(out)}", who="system")
    return out


def load_case(path):
    """Rebuild a CaseBuilder from a .forensic file."""
    from .case_model import CaseBuilder
    with zipfile.ZipFile(path) as z:
        blob = json.loads(z.read("case.json"))
        audit = [tuple(json.loads(l)) for l in z.read("audit.jsonl").decode().splitlines() if l]

    m = blob["meta"]
    cb = CaseBuilder(examiner=m.get("examiner", "Examiner"),
                     examiner_id=m.get("examinerId", "EX-00"),
                     agency=m.get("agency", ""),
                     case_id=m.get("id"), title=m.get("title"))
    cb.meta = m                              # restore exact metadata (opened date etc.)
    cb.evidence = blob.get("evidence", [])
    cb.analysis = blob.get("analysis")
    cb.audit = audit or cb.audit
    cb._log("CASE_REOPENED", f"Loaded from {os.path.basename(path)}", who="system")
    return cb


def list_cases(directory=None):
    """Return saved-case summaries, newest first, for the history view."""
    directory = directory or app_data_dir()
    rows = []
    if not os.path.isdir(directory):
        return rows
    for fn in os.listdir(directory):
        if not fn.endswith(".forensic"):
            continue
        full = os.path.join(directory, fn)
        try:
            with zipfile.ZipFile(full) as z:
                blob = json.loads(z.read("case.json"))
            m = blob.get("meta", {})
            analysis = blob.get("analysis") or {}
            rows.append({
                "path": full,
                "id": m.get("id", fn),
                "title": m.get("title", "—"),
                "examiner": m.get("examiner", "—"),
                "opened": m.get("opened", "—"),
                "saved": blob.get("saved", "—"),
                "evidence": len(blob.get("evidence", [])),
                "findings": len(analysis.get("findings", [])),
                "analyzed": bool(blob.get("analysis")),
            })
        except Exception:
            continue
    rows.sort(key=lambda r: r.get("saved", ""), reverse=True)
    return rows


def delete_case(path) -> bool:
    try:
        os.remove(path)
        return True
    except OSError:
        return False

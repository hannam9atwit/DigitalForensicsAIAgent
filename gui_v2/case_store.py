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


def _snapshot(builder, directory=None):
    """A consistent, serialization-ready snapshot of the builder's state plus
    the output path. Taken on the caller's thread so an off-thread writer sees
    a stable picture: the small mutable lists (audit, knowledge base) are copied
    now; the large, post-analysis-immutable events/findings are referenced.
    """
    directory = directory or app_data_dir()
    os.makedirs(directory, exist_ok=True)
    out = os.path.join(directory, _safe_name(builder.meta["id"]) + ".forensic")

    analysis = builder.analysis
    if isinstance(analysis, dict):
        analysis = dict(analysis)
        analysis["knowledge_base"] = list(analysis.get("knowledge_base", []))

    blob = {
        "meta": dict(builder.meta),
        "evidence": builder.evidence,          # includes "_path" + hashes
        "analysis": analysis,                  # may be None if not analyzed yet
        "saved": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "schema": 1,
    }
    audit_lines = [list(a) for a in builder.audit]
    return out, blob, audit_lines


def _write_forensic(out, blob, audit_lines):
    """Write the zip atomically: build a temp then replace, so a crash or a
    concurrent milestone write can never leave a half-written case file."""
    tmp = f"{out}.{os.getpid()}.{id(blob)}.tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("case.json", json.dumps(blob, indent=2, default=str))
        z.writestr("audit.jsonl",
                   "\n".join(json.dumps(a) for a in audit_lines))
    os.replace(tmp, out)   # atomic on the same filesystem
    return out


def save_case(builder, directory=None) -> str:
    """
    Serialize a CaseBuilder to <dir>/<case_id>.forensic.
    Stores metadata, evidence records (incl. hash + original path), the audit
    trail, and the last analysis result (including the knowledge base) so the
    case reopens fully populated.
    """
    out, blob, audit_lines = _snapshot(builder, directory)
    _write_forensic(out, blob, audit_lines)
    builder._log("CASE_SAVED", f"Case written to {os.path.basename(out)}", who="system")
    return out


def save_case_async(builder, task_set, directory=None):
    """Persist off the UI thread. The snapshot is taken here (UI thread) so it
    is consistent; the json serialization and zip write — the parts that scale
    with the event count — run on a background task, so a milestone save during
    the deep dive never hitches the interface. `task_set` keeps the task alive
    until it finishes (see MainWindow._bg_tasks)."""
    out, blob, audit_lines = _snapshot(builder, directory)

    def work(_progress):
        return _write_forensic(out, blob, audit_lines)

    from .task_worker import BackgroundTask
    task = BackgroundTask(work)
    task_set.add(task)
    task.finished.connect(lambda t=task: task_set.discard(t))
    task.start()
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

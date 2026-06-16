"""
gui_v2/evidence_export.py

Export selected evidence artifacts out of a case. Copies the ORIGINAL files
byte-for-byte to a chosen folder (never modifies them), writes a manifest, and
re-hashes each copy to prove the export is identical to the intake hash.

This keeps the export defensible: the manifest records intake hash, export
hash, and whether they matched.
"""

import os
import json
import shutil
import datetime

from .case_model import sha256_file


def export_evidence(evidence_items, dest_dir, case_meta, log=print):
    """
    evidence_items: list of evidence dicts (each with "_path", "sha256", …)
    dest_dir: target folder (created if needed)
    Returns a result dict with per-item status and the manifest path.
    """
    os.makedirs(dest_dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    results = []

    for ev in evidence_items:
        src = ev.get("_path")
        entry = {"id": ev["id"], "name": ev["name"], "intake_sha256": ev.get("sha256", "")}
        if not src or not os.path.exists(src):
            entry["status"] = "missing_source"
            entry["verified"] = False
            log(f"[!] {ev['id']} {ev['name']}: source file not found")
            results.append(entry)
            continue

        # avoid name collisions: prefix with evidence id
        out_name = f"{ev['id']}_{ev['name']}"
        out_path = os.path.join(dest_dir, out_name)
        try:
            shutil.copy2(src, out_path)
            export_hash = sha256_file(out_path)
            ok = (export_hash == ev.get("sha256"))
            entry.update({
                "exported_as": out_name,
                "export_sha256": export_hash,
                "verified": ok,
                "status": "ok" if ok else "hash_mismatch",
            })
            log(f"[+] {ev['id']} exported -> {out_name} "
                f"({'verified' if ok else 'HASH MISMATCH'})")
        except Exception as e:
            entry["status"] = f"error: {e}"
            entry["verified"] = False
            log(f"[!] {ev['id']} export failed: {e}")
        results.append(entry)

    manifest = {
        "case_id": case_meta.get("id", "—"),
        "case_title": case_meta.get("title", "—"),
        "examiner": case_meta.get("examiner", "—"),
        "exported_at": stamp,
        "destination": os.path.abspath(dest_dir),
        "artifacts": results,
    }
    manifest_path = os.path.join(dest_dir, "EXPORT_MANIFEST.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    # also write a human-readable manifest
    txt_path = os.path.join(dest_dir, "EXPORT_MANIFEST.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"EVIDENCE EXPORT MANIFEST\n")
        f.write(f"Case:       {manifest['case_id']} — {manifest['case_title']}\n")
        f.write(f"Examiner:   {manifest['examiner']}\n")
        f.write(f"Exported:   {stamp}\n")
        f.write(f"Destination:{manifest['destination']}\n")
        f.write("=" * 64 + "\n\n")
        for r in results:
            f.write(f"[{r['id']}] {r['name']}\n")
            f.write(f"   status        : {r.get('status')}\n")
            f.write(f"   intake SHA-256: {r.get('intake_sha256','')}\n")
            if r.get("export_sha256"):
                f.write(f"   export SHA-256: {r['export_sha256']}\n")
                f.write(f"   integrity     : {'VERIFIED (match)' if r['verified'] else 'MISMATCH'}\n")
            f.write("\n")

    ok_count = sum(1 for r in results if r.get("verified"))
    return {"results": results, "manifest": manifest_path, "text": txt_path,
            "ok": ok_count, "total": len(results)}

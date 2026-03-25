"""
ai/rule_engine.py

Deterministic DFIR rule engine.

Key change: records with metadata_wiped=True (all timestamps and size = 0)
are treated as a distinct HIGH-severity finding — wiped MFT metadata is
itself a strong anti-forensic indicator, not just missing data.
"""


class RuleEngine:

    def run(self, disk_data, browser_data, unified_timeline):
        print("[DEBUG] RuleEngine disk_data type:", type(disk_data))
        print("[DEBUG] RuleEngine disk events sample:", disk_data.get("events", [])[:3])

        findings = []
        disk_events = disk_data.get("events", [])

        # ── RULE 1 — Deleted user files ───────────────────────────────────────
        for e in disk_events:
            path = e.get("path", "")
            if "(deleted)" in path and not path.startswith("/$"):
                self._safe_append(findings, {
                    "type":      "deleted_user_file",
                    "severity":  2,
                    "path":      path,
                    "timestamp": e.get("timestamp"),
                    "reason":    "File was deleted from a user-accessible directory.",
                    "details":   e,
                })

        # ── RULE 2 — Wiped MFT metadata ──────────────────────────────────────
        # Zero timestamps + zero size on a deleted file = metadata was wiped,
        # not just that the file was deleted normally.
        wiped = [
            e for e in disk_events
            if e.get("metadata_wiped")
            and not e.get("path", "").startswith("/$")
        ]
        if wiped:
            # Report as a single grouped finding to avoid flooding
            self._safe_append(findings, {
                "type":      "wiped_mft_metadata",
                "severity":  3,
                "path":      f"{len(wiped)} files affected",
                "timestamp": None,
                "reason": (
                    f"{len(wiped)} deleted files have fully zeroed MFT metadata "
                    f"(timestamps and size all 0). This indicates deliberate metadata "
                    f"wiping, not normal deletion. Example paths: "
                    + "; ".join(e.get("path", "") for e in wiped[:5])
                ),
                "details": {"wiped_files": [e.get("path") for e in wiped[:20]]},
            })

        # ── RULE 3 — Orphaned files ───────────────────────────────────────────
        for e in disk_events:
            if "/$OrphanFiles" in e.get("path", ""):
                self._safe_append(findings, {
                    "type":      "orphaned_file",
                    "severity":  3,
                    "path":      e.get("path"),
                    "timestamp": e.get("timestamp"),
                    "reason":    "File exists in $OrphanFiles — unlinked MFT entry.",
                    "details":   e,
                })

        # ── RULE 4 — Alternate data streams ──────────────────────────────────
        for e in disk_events:
            path = e.get("path", "")
            if ":" in path and not path.startswith("/$"):
                self._safe_append(findings, {
                    "type":      "alternate_data_stream",
                    "severity":  3,
                    "path":      path,
                    "timestamp": e.get("timestamp"),
                    "reason":    "NTFS alternate data stream detected — common hiding technique.",
                    "details":   e,
                })

        # ── RULE 5 — Timestamp anomalies (mtime < crtime) ────────────────────
        for e in disk_events:
            m = e.get("mtime")
            c = e.get("crtime")
            # Only flag if both are non-zero (zero = wiped, handled above)
            if isinstance(m, int) and isinstance(c, int) and m > 0 and c > 0 and m < c:
                self._safe_append(findings, {
                    "type":      "timestamp_anomaly",
                    "severity":  2,
                    "path":      e.get("path"),
                    "timestamp": m,
                    "reason": (
                        f"mtime ({m}) is earlier than crtime ({c}) — "
                        f"possible timestomping."
                    ),
                    "details": e,
                })

        # ── RULE 6 — Large $BadClus:$Bad ─────────────────────────────────────
        for e in disk_events:
            path = e.get("path", "")
            size = e.get("size", 0)
            if "$BadClus:$Bad" in path and size and size > 10_000_000:
                self._safe_append(findings, {
                    "type":      "large_badclus_stream",
                    "severity":  4,
                    "path":      path,
                    "size":      size,
                    "timestamp": e.get("timestamp"),
                    "reason": (
                        f"$BadClus:$Bad stream is {size:,} bytes — possible "
                        f"anti-forensic bad cluster manipulation."
                    ),
                    "details": e,
                })

        # ── RULE 7 — Deleted directory with live children ─────────────────────
        deleted_dirs = [
            e for e in disk_events
            if "(deleted)" in e.get("path", "")
            and str(e.get("mode", "")).startswith("d/")
        ]
        for d in deleted_dirs:
            live_base = d["path"].replace(" (deleted)", "")
            for e in disk_events:
                child = e.get("path", "")
                if child.startswith(live_base + "/") and "(deleted)" not in child:
                    self._safe_append(findings, {
                        "type":      "deleted_directory_with_live_children",
                        "severity":  3,
                        "directory": d["path"],
                        "child":     child,
                        "timestamp": d.get("timestamp"),
                        "reason": (
                            "Deleted directory still has active child entries — "
                            "possible incomplete deletion or anti-forensic activity."
                        ),
                        "details": {"directory": d, "child": e},
                    })

        return findings

    def _safe_append(self, lst, item):
        if isinstance(item, dict):
            lst.append(item)
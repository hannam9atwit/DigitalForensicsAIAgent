class RuleEngine:
    """
    Deterministic DFIR rule-based engine.
    Produces structured forensic findings from disk and browser artifacts.
    """

    def __init__(self):
        pass

    def run(self, disk_data, browser_data, unified_timeline):
        print("[DEBUG] RuleEngine disk_data type:", type(disk_data))
        print("[DEBUG] RuleEngine disk events sample:", disk_data.get("events", [])[:3])

        findings = []

        disk_events = disk_data.get("events", [])
        deleted_files = disk_data.get("deleted", [])
        mft_entries = disk_data.get("entries", [])

        # ---------------------------------------------------------
        # RULE 1 — Deleted user files (non-system paths)
        # ---------------------------------------------------------
        for e in disk_events:
            path = e.get("path", "")
            if "(deleted)" in path and not path.startswith("/$"):
                self._safe_append(findings, {
                    "type": "deleted_user_file",
                    "severity": 2,
                    "path": path,
                    "timestamp": e.get("timestamp"),
                    "reason": "File was deleted from a user-accessible directory.",
                    "details": e
                })

        # ---------------------------------------------------------
        # RULE 2 — Orphaned files
        # ---------------------------------------------------------
        for e in disk_events:
            if "/$OrphanFiles" in e.get("path", ""):
                self._safe_append(findings,{
                    "type": "orphaned_file",
                    "severity": 3,
                    "path": e.get("path"),
                    "timestamp": e.get("timestamp"),
                    "reason": "File exists in $OrphanFiles, indicating lost or unlinked MFT entries.",
                    "details": e
                })

        # ---------------------------------------------------------
        # RULE 3 — Suspicious alternate data streams (ADS)
        # ---------------------------------------------------------
        for e in disk_events:
            path = e.get("path", "")
            if ":" in path and not path.startswith("/$"):
                self._safe_append(findings,{
                    "type": "alternate_data_stream",
                    "severity": 3,
                    "path": path,
                    "timestamp": e.get("timestamp"),
                    "reason": "File contains an NTFS alternate data stream (ADS), often used for hiding data.",
                    "details": e
                })

        # ---------------------------------------------------------
        # RULE 4 — Timestamp anomalies (mtime < crtime)
        # ---------------------------------------------------------
        for e in disk_events:
            m = e.get("mtime")
            c = e.get("crtime")
            if isinstance(m, int) and isinstance(c, int) and m < c:
                self._safe_append(findings,{
                    "type": "timestamp_anomaly",
                    "severity": 2,
                    "path": e["path"],
                    "timestamp": m,
                    "reason": "File timestamps are inconsistent (mtime < crtime), suggesting possible timestomping.",
                    "details": e
                })

        # ---------------------------------------------------------
        # RULE 5 — Large $BadClus:$Bad streams (possible anti-forensics)
        # ---------------------------------------------------------
        for e in disk_events:
            path = e.get("path", "")
            size = e.get("size", 0)
            if "$BadClus:$Bad" in path and size and size > 10_000_000:
                self._safe_append(findings,{
                    "type": "large_badclus_stream",
                    "severity": 4,
                    "path": e["path"],
                    "size": e["size"],
                    "timestamp": e["timestamp"],
                    "reason": "Unusually large $BadClus:$Bad stream — may indicate anti-forensic manipulation of bad clusters.",
                    "details": e
                })

        # ---------------------------------------------------------
        # RULE 6 — Deleted directories with live children
        # ---------------------------------------------------------
        deleted_dirs = [
            e for e in disk_events
            if "(deleted)" in e.get("path", "") and str(e.get("mode", "")).startswith("d/")
        ]

        for d in deleted_dirs:
            dpath_live = d["path"].replace(" (deleted)", "")
            for e in disk_events:
                child_path = e.get("path", "")
                if child_path.startswith(dpath_live + "/") and "(deleted)" not in child_path:
                    self._safe_append(findings,{
                        "type": "deleted_directory_with_live_children",
                        "severity": 3,
                        "directory": d["path"],
                        "child": e["path"],
                        "timestamp": d["timestamp"],
                        "reason": "Directory was deleted but contains active child entries — possible incomplete deletion or anti-forensics.",
                        "details": {"directory": d, "child": e}
                    })

        return findings
    def _safe_append(self, lst, item):
        if isinstance(item, dict):
            lst.append(item)

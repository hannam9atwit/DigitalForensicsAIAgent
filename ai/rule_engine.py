"""
ai/rule_engine.py

Deterministic DFIR rule engine. Evaluates disk and browser artifacts against
a fixed set of forensic rules and returns a list of severity-tagged findings.

Records with metadata_wiped=True (all timestamps and size zeroed) are treated
as a distinct HIGH-severity finding, since wiped MFT metadata is a strong
anti-forensic indicator in its own right.
"""


class RuleEngine:

    # Hard ceiling on findings from a single run. A pathological image (tens of
    # thousands of deleted entries) could otherwise generate findings without
    # bound, exploding both the report and memory. When the ceiling is reached
    # we stop appending and add one honest note, so the cap is never silent.
    MAX_FINDINGS = 500

    def run(self, disk_data, browser_data, unified_timeline):

        findings    = []
        self._cap_noted = False
        disk_events = disk_data.get("events", [])

        # RULE 1 — Deleted user files
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

        # RULE 2 — Wiped MFT metadata
        # Zero timestamps + zero size on a deleted file means the metadata was
        # actively wiped, not just that the file was normally deleted.
        wiped = [
            e for e in disk_events
            if e.get("metadata_wiped")
            and not e.get("path", "").startswith("/$")
        ]
        if wiped:
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

        # RULE 3 — Orphaned files
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

        # RULE 4 — Alternate data streams
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

        # RULE 5 — Timestamp anomalies (mtime earlier than crtime)
        for e in disk_events:
            m = e.get("mtime")
            c = e.get("crtime")
            if isinstance(m, int) and isinstance(c, int) and m > 0 and c > 0 and m < c:
                self._safe_append(findings, {
                    "type":      "timestamp_anomaly",
                    "severity":  2,
                    "path":      e.get("path"),
                    "timestamp": m,
                    "reason":    f"mtime ({m}) is earlier than crtime ({c}) — possible timestomping.",
                    "details":   e,
                })

        # RULE 6 — Abnormally large $BadClus:$Bad stream
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
                    "reason":    f"$BadClus:$Bad stream is {size:,} bytes — possible anti-forensic bad cluster manipulation.",
                    "details":   e,
                })

        # RULE 7 — Deleted directory with live child entries
        #
        # Build a one-pass index of live (non-deleted) entries grouped by their
        # immediate parent directory, then look up each deleted directory's
        # children in O(1). The previous version scanned every event inside a
        # loop over every deleted directory — O(n^2) — which hung on large
        # images (50k events × thousands of deleted dirs = hundreds of millions
        # of iterations). One finding is emitted per deleted directory, with a
        # child count and a capped sample of paths, rather than one finding per
        # child; details store paths only, never whole event dicts.
        SAMPLE = 5
        deleted_dirs = [
            e for e in disk_events
            if "(deleted)" in e.get("path", "")
            and str(e.get("mode", "")).startswith("d/")
        ]

        children_by_parent = {}
        for e in disk_events:
            path = e.get("path", "")
            if not path or "(deleted)" in path:
                continue
            parent = path.rsplit("/", 1)[0] if "/" in path else ""
            children_by_parent.setdefault(parent, []).append(path)

        for d in deleted_dirs:
            live_base = d.get("path", "").replace(" (deleted)", "")
            children = children_by_parent.get(live_base)
            if not children:
                continue
            self._safe_append(findings, {
                "type":        "deleted_directory_with_live_children",
                "severity":    3,
                "directory":   d.get("path"),
                "timestamp":   d.get("timestamp"),
                "child_count": len(children),
                "reason": (
                    f"Deleted directory still has {len(children)} active child "
                    f"entr{'y' if len(children) == 1 else 'ies'} — possible "
                    f"incomplete deletion or anti-forensic activity."
                ),
                "details": {
                    "directory":    d.get("path"),
                    "artifact":     d.get("artifact"),
                    "child_count":  len(children),
                    "child_sample": children[:SAMPLE],
                },
            })

        return findings

    def _safe_append(self, lst, item):
        """Append a finding, but never past MAX_FINDINGS. On reaching the cap,
        add a single honest note and drop the rest, so a runaway image cannot
        explode the findings list."""
        if not isinstance(item, dict):
            return
        if len(lst) < self.MAX_FINDINGS:
            lst.append(item)
            return
        if not self._cap_noted:
            self._cap_noted = True
            lst.append({
                "type":     "findings_capped",
                "severity": 2,
                "reason": (
                    f"The {self.MAX_FINDINGS}-finding limit was reached; further "
                    f"matches were suppressed so the report and memory stay "
                    f"bounded on very large images. Review the timeline for the "
                    f"remaining activity."
                ),
                "details": {"limit": self.MAX_FINDINGS},
            })

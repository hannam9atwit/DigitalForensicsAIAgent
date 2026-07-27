"""
ai/rule_engine.py

Deterministic DFIR rule engine. Evaluates disk and browser artifacts against
a fixed set of forensic rules and returns a list of severity-tagged findings.

Each rule emits ONE aggregated finding per pattern, never one per matching
file. A volume that recovers 1,847 orphaned entries is a single MEDIUM
observation about the volume — "1,847 orphaned files recovered from
$OrphanFiles" — carrying a count, the time range they span, and a small sample
of representative paths, not 1,847 identical HIGH findings that bury the report
and flatten the narrative. The target shape is the demo case in
gui_v2/content.py: a handful of findings that each tell a story.
"""

import datetime


class RuleEngine:

    # Backstop ceiling on findings. With per-pattern aggregation a run yields a
    # handful of findings, so this should never bind — it only guards against a
    # future rule regressing to per-instance output. When hit, one honest note
    # is added so the cap is never silent.
    MAX_FINDINGS = 50

    # How many representative paths to keep on an aggregated finding.
    SAMPLE = 8

    def run(self, disk_data, browser_data, unified_timeline):

        findings    = []
        self._cap_noted = False
        disk_events = disk_data.get("events", [])

        # RULE 1 — Deleted entries in user-accessible directories
        matches = [
            e for e in disk_events
            if "(deleted)" in e.get("path", "")
            and not e.get("path", "").startswith("/$")
        ]
        if matches:
            paths, span = self._summarize(matches)
            self._safe_append(findings, self._finding(
                "deleted_user_file", 2, matches, paths, span,   # MEDIUM
                f"{len(matches):,} deleted entr"
                f"{'y was' if len(matches) == 1 else 'ies were'} found in "
                f"user-accessible directories{self._span(span)}. Deletion is "
                f"routine on any active volume; the set is worth reviewing for "
                f"files relevant to the case. Examples: {self._examples(paths)}."))

        # RULE 2 — Wiped MFT metadata
        # Zero timestamps + zero size on a deleted file means the metadata was
        # actively wiped, not just that the file was normally deleted.
        matches = [
            e for e in disk_events
            if e.get("metadata_wiped")
            and not e.get("path", "").startswith("/$")
        ]
        if matches:
            paths, span = self._summarize(matches)
            self._safe_append(findings, self._finding(
                "wiped_mft_metadata", 3, matches, paths, span,   # HIGH
                f"{len(matches):,} deleted file"
                f"{'' if len(matches) == 1 else 's'} have fully zeroed MFT "
                f"metadata (timestamps and size all 0){self._span(span)}. This "
                f"indicates deliberate metadata wiping, not normal deletion, and "
                f"is a strong anti-forensic indicator. Examples: "
                f"{self._examples(paths)}."))

        # RULE 3 — Orphaned files (unlinked MFT entries)
        matches = [e for e in disk_events if "/$OrphanFiles" in e.get("path", "")]
        if matches:
            paths, span = self._summarize(matches)
            self._safe_append(findings, self._finding(
                "orphaned_file", 2, matches, paths, span,   # MEDIUM — volume note
                f"{len(matches):,} orphaned file"
                f"{'' if len(matches) == 1 else 's'} recovered from $OrphanFiles "
                f"(unlinked MFT entries){self._span(span)}. A high count is "
                f"common on a heavily-used volume and is usually benign, but the "
                f"set is worth scanning for recoverable user data. Examples: "
                f"{self._examples(paths)}."))

        # RULE 4 — Alternate data streams
        matches = [
            e for e in disk_events
            if ":" in e.get("path", "") and not e.get("path", "").startswith("/$")
        ]
        if matches:
            paths, span = self._summarize(matches)
            self._safe_append(findings, self._finding(
                "alternate_data_stream", 2, matches, paths, span,   # MEDIUM
                f"{len(matches):,} NTFS alternate data stream"
                f"{'' if len(matches) == 1 else 's'} detected{self._span(span)}. "
                f"Most ADS on Windows are benign Zone.Identifier markers; inspect "
                f"the set for streams that hide executable content. Examples: "
                f"{self._examples(paths)}."))

        # RULE 5 — Timestamp anomalies (mtime earlier than crtime)
        matches = [
            e for e in disk_events
            if isinstance(e.get("mtime"), int) and isinstance(e.get("crtime"), int)
            and e["mtime"] > 0 and e["crtime"] > 0 and e["mtime"] < e["crtime"]
        ]
        if matches:
            paths, span = self._summarize(matches)
            self._safe_append(findings, self._finding(
                "timestamp_anomaly", 2, matches, paths, span,   # MEDIUM
                f"{len(matches):,} file"
                f"{'' if len(matches) == 1 else 's'} have a modified time earlier "
                f"than their creation time{self._span(span)} — a signature of "
                f"timestomping. Treat the affected timestamps as untrusted and "
                f"corroborate against a second source. Examples: "
                f"{self._examples(paths)}."))

        # RULE 6 — Abnormally large $BadClus:$Bad stream
        matches = [
            e for e in disk_events
            if "$BadClus:$Bad" in e.get("path", "")
            and isinstance(e.get("size"), int) and e["size"] > 10_000_000
        ]
        if matches:
            paths, span = self._summarize(matches)
            biggest = max(m.get("size", 0) for m in matches)
            self._safe_append(findings, self._finding(
                "large_badclus_stream", 4, matches, paths, span,   # CRITICAL
                f"The $BadClus:$Bad stream holds {biggest:,} bytes of data "
                f"{self._span(span)}. Bad-cluster space is not normally used to "
                f"store data; a large stream here is a classic anti-forensic "
                f"hiding place and should be carved and examined."))

        # RULE 7 — Deleted directories that still hold live child entries
        #
        # Index live entries by immediate parent in one pass, then look up each
        # deleted directory's children in O(1) (the previous nested scan was
        # O(n^2) and hung on large images). The whole pattern collapses to a
        # single finding — "N deleted directories retain live children" — with a
        # sample of the directories, not one finding per directory.
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

        retaining = []
        total_children = 0
        for d in deleted_dirs:
            live_base = d.get("path", "").replace(" (deleted)", "")
            children = children_by_parent.get(live_base)
            if children:
                retaining.append(d)
                total_children += len(children)
        if retaining:
            paths, span = self._summarize(retaining)
            self._safe_append(findings, self._finding(
                "deleted_directory_with_live_children", 3, retaining, paths, span,
                f"{len(retaining):,} deleted director"
                f"{'y' if len(retaining) == 1 else 'ies'} still hold "
                f"{total_children:,} active child entr"
                f"{'y' if total_children == 1 else 'ies'}{self._span(span)} — a "
                f"sign of incomplete deletion or anti-forensic activity. "
                f"Examples: {self._examples(paths)}.",
                extra={"child_total": total_children}))   # HIGH

        return findings

    # ── aggregation helpers ─────────────────────────────────────────────────────

    def _summarize(self, matches):
        """(sample_paths, (earliest, latest)) for a set of matching events.

        Paths are capped at SAMPLE; the span is the min/max of the real
        timestamps, or None when none of the matches carry one.
        """
        paths = [m.get("path", "") for m in matches if m.get("path")][:self.SAMPLE]
        times = [m.get("timestamp") for m in matches
                 if isinstance(m.get("timestamp"), int) and m.get("timestamp") > 0]
        span = (min(times), max(times)) if times else None
        return paths, span

    def _finding(self, ftype, severity, matches, sample_paths, span, reason,
                 extra=None):
        """One aggregated finding for a pattern. `reason` leads with the count
        (its first sentence becomes the finding's one-line summary); details
        carry the count, sample and span — never whole event dicts."""
        count = len(matches)
        finding = {
            "type":      ftype,
            "severity":  severity,
            "count":     count,
            "path":      (sample_paths[0] if count == 1 and sample_paths
                          else f"{count:,} files"),
            "timestamp": (span[0] if span else None),
            "reason":    reason,
            "details": {
                "count":      count,
                "sample":     sample_paths,
                "time_range": span,
                "artifact":   matches[0].get("artifact"),
            },
        }
        if extra:
            finding.update(extra)
        return finding

    def _span(self, span):
        """A human phrase for a (start, end) timestamp range, or '' if unknown."""
        if not span:
            return ""
        start, end = span
        if start == end:
            return f" on {self._fmt(start)}"
        return f", spanning {self._fmt(start)} to {self._fmt(end)}"

    def _examples(self, paths):
        return "; ".join(paths) if paths else "none recorded"

    @staticmethod
    def _fmt(ts):
        try:
            return datetime.datetime.utcfromtimestamp(int(ts)).strftime(
                "%Y-%m-%d %H:%M:%S UTC")
        except (ValueError, OSError, OverflowError, TypeError):
            return str(ts)

    def _safe_append(self, lst, item):
        """Append a finding, but never past MAX_FINDINGS. On reaching the cap,
        add a single honest note and drop the rest. With per-pattern aggregation
        this is a backstop, not the normal path."""
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
                    f"patterns were suppressed so the report stays readable. "
                    f"Review the timeline for the remaining activity."
                ),
                "details": {"limit": self.MAX_FINDINGS},
            })

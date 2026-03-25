class TimelineCorrelationEngine:
    """
    Merges disk and browser events into a unified chronological timeline.
    Accepts raw mactime pipe-delimited strings or pre-parsed dicts.
    """

    def correlate(self, disk_events, browser_visits, browser_downloads, cookies):
        unified = []

        for e in disk_events:
            parsed = self._parse_disk_event(e)
            if isinstance(parsed, dict):
                parsed["source"] = "disk"
                unified.append(parsed)

        for v in browser_visits:
            unified.append({
                "timestamp": v.get("visit_time"),
                "source":    "browser_visit",
                "details":   v,
            })

        for d in browser_downloads:
            unified.append({
                "timestamp": d.get("start_time"),
                "source":    "browser_download",
                "details":   d,
            })

        for c in cookies:
            unified.append({
                "timestamp": c.get("expires_utc"),
                "source":    "cookie",
                "details":   c,
            })

        unified = [e for e in unified if e["timestamp"] is not None]
        unified.sort(key=lambda x: x["timestamp"])

        return {"count": len(unified), "events": unified}

    def _parse_disk_event(self, raw):
        """
        Parse a raw mactime line into a structured dict.
        Format: 0|path|inode|mode|uid|gid|size|mtime|atime|ctime|crtime
        Returns None for unrecognised input; passes through existing dicts unchanged.
        """
        if isinstance(raw, dict):
            return raw
        if not isinstance(raw, str):
            return None

        parts = raw.split("|")
        if len(parts) < 11:
            return None

        try:
            return {
                "raw":       raw,
                "path":      parts[1],
                "inode":     parts[2],
                "mode":      parts[3],
                "size":      int(parts[6]),
                "mtime":     int(parts[7]),
                "atime":     int(parts[8]),
                "ctime":     int(parts[9]),
                "crtime":    int(parts[10]),
                "timestamp": int(parts[7]),  # mtime as primary timestamp
            }
        except (ValueError, IndexError):
            return None

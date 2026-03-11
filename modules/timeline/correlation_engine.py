import time

class TimelineCorrelationEngine:
    """
    Merges disk and browser events into a unified chronological timeline.
    Accepts raw mactime strings OR structured dicts.
    """

    def __init__(self):
        pass

    def correlate(self, disk_events, browser_visits, browser_downloads, cookies):
        unified = []

        # -----------------------------
        # Add disk timeline events
        # -----------------------------
        for e in disk_events:
            parsed = self._parse_disk_event(e)
            if parsed:
                unified.append({
                    "timestamp": parsed["timestamp"],
                    "source": "disk",
                    "details": parsed
                })

        # -----------------------------
        # Add browser visit events
        # -----------------------------
        for v in browser_visits:
            unified.append({
                "timestamp": v.get("visit_time"),
                "source": "browser_visit",
                "details": v
            })

        # -----------------------------
        # Add browser download events
        # -----------------------------
        for d in browser_downloads:
            unified.append({
                "timestamp": d.get("start_time"),
                "source": "browser_download",
                "details": d
            })

        # -----------------------------
        # Add cookie expiration events
        # -----------------------------
        for c in cookies:
            unified.append({
                "timestamp": c.get("expires_utc"),
                "source": "cookie",
                "details": c
            })

        # -----------------------------
        # Sort chronologically
        # -----------------------------
        unified = [e for e in unified if e["timestamp"] is not None]
        unified.sort(key=lambda x: x["timestamp"])

        return {
            "count": len(unified),
            "events": unified
        }

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------

    def _parse_disk_event(self, raw):
        """
        Parse a raw mactime line into a structured dict.
        Example mactime line:
        0|/path|inode|mode|uid|gid|size|mtime|atime|ctime|crtime
        """

        # If it's already a dict, return it
        if isinstance(raw, dict):
            return raw

        # If it's not a string, skip it
        if not isinstance(raw, str):
            return None

        parts = raw.split("|")
        if len(parts) < 11:
            return None

        try:
            return {
                "raw": raw,
                "path": parts[1],
                "inode": parts[2],
                "mode": parts[3],
                "size": int(parts[6]),
                "mtime": int(parts[7]),
                "atime": int(parts[8]),
                "ctime": int(parts[9]),
                "crtime": int(parts[10]),
                "timestamp": int(parts[7])  # use mtime as primary timestamp
            }
        except:
            return None

    def _parse_time(self, date_str):
        """
        Convert mactime date string to Unix timestamp.
        Example: '2023-01-01 12:34:56'
        """
        try:
            return int(time.mktime(time.strptime(date_str, "%Y-%m-%d %H:%M:%S")))
        except:
            return None

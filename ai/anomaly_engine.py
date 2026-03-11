from collections import Counter

class AnomalyEngine:
    """
    Heuristic/statistical anomaly detection over disk and browser artifacts.
    Produces 'anomalies' (weird, not necessarily malicious).
    """

    def __init__(self):
        pass

    def run(self, disk_data, browser_data, unified_timeline):
        print("[DEBUG] AnomalyEngine disk_data type:", type(disk_data))
        print("[DEBUG] AnomalyEngine disk events sample:", disk_data.get("events", [])[:3])

        anomalies = []

        disk_events = disk_data.get("events", [])
        browser_visits = browser_data.get("visits", [])
        browser_downloads = browser_data.get("downloads", [])

        # ---------------------------------------------------------
        # ANOMALY 1 — Very large files
        # ---------------------------------------------------------
        for e in disk_events:
            size = e.get("size")
            if isinstance(size, int) and size > 100_000_000:  # > ~100MB
                self._safe_append(anomalies, {
                    "type": "large_file",
                    "severity": 1,
                    "path": e.get("path"),
                    "size": size,
                    "timestamp": e.get("timestamp"),
                    "details": e
                })

        # ---------------------------------------------------------
        # ANOMALY 2 — Rare extensions
        # ---------------------------------------------------------
        ext_counter = Counter()
        for e in disk_events:
            path = e.get("path", "")
            if "." in path and not path.startswith("/$"):
                ext = path.rsplit(".", 1)[-1].lower()
                ext_counter[ext] += 1

        rare_exts = {ext for ext, count in ext_counter.items() if count == 1}

        for e in disk_events:
            path = e.get("path", "")
            if "." in path and not path.startswith("/$"):
                ext = path.rsplit(".", 1)[-1].lower()
                if ext in rare_exts:
                    self._safe_append(anomalies,{
                        "type": "rare_extension",
                        "severity": 1,
                        "path": path,
                        "extension": ext,
                        "timestamp": e.get("timestamp"),
                        "details": e
                    })

        # ---------------------------------------------------------
        # ANOMALY 3 — Activity bursts (many events in short time)
        # ---------------------------------------------------------
        timestamps = sorted(
            [e.get("timestamp") for e in disk_events if isinstance(e.get("timestamp"), int)]
        )

        window = 60  # seconds
        threshold = 20  # events per window

        i = 0
        n = len(timestamps)
        while i < n:
            start = timestamps[i]
            j = i
            while j < n and timestamps[j] <= start + window:
                j += 1
            count = j - i
            if count >= threshold:
                self._safe_append(anomalies,{
                    "type": "activity_burst",
                    "severity": 2,
                    "start": start,
                    "end": start + window,
                    "event_count": count,
                    "details": {"timestamps": timestamps[i:j]}
                })
            i += 1

        # ---------------------------------------------------------
        # ANOMALY 4 — Downloads with no obvious disk counterpart (placeholder)
        # ---------------------------------------------------------
        # Later you can correlate browser_downloads with disk paths.
        # For now, we just flag presence of downloads when disk is quiet.
        if browser_downloads and not disk_events:
            self._safe_append(anomalies,{
                "type": "downloads_without_disk_activity",
                "severity": 1,
                "details": {"downloads": browser_downloads}
            })

        return anomalies

    def _safe_append(self, lst, item):
        if isinstance(item, dict):
            lst.append(item)
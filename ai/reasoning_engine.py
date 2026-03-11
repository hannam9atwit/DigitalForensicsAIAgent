class ReasoningEngine:
    """
    Performs AI-style reasoning over correlated forensic data.
    This is rule-based for now, but structured so an LLM can be plugged in later.
    """

    def analyze(self, disk_data, browser_data, timeline):
        findings = []
        anomalies = []

        # ---------------------------------------
        # 1. Detect suspicious downloads
        # ---------------------------------------
        for d in browser_data.get("downloads", []):
            if d.get("danger_type", 0) not in (0, None):
                findings.append({
                    "type": "suspicious_download",
                    "details": d,
                    "reason": f"Danger type {d.get('danger_type')}"
                })

        # ---------------------------------------
        # 2. Detect deleted files shortly after downloads
        # ---------------------------------------
        for event in timeline.get("events", []):
            if event["source"] == "browser_download":
                download_time = event["timestamp"]

                # Look for disk events within 5 minutes
                for e2 in timeline["events"]:
                    if e2["source"] == "disk":
                        if abs(e2["timestamp"] - download_time) < 300:
                            anomalies.append({
                                "type": "download_then_disk_activity",
                                "download": event,
                                "disk_event": e2,
                                "reason": "Disk activity shortly after download"
                            })

        # ---------------------------------------
        # 3. Detect expired cookies (possible account logout)
        # ---------------------------------------
        for c in browser_data.get("cookies", []):
            if c.get("expires_utc") and c["expires_utc"] < 0:
                findings.append({
                    "type": "expired_cookie",
                    "details": c,
                    "reason": "Cookie expiration timestamp invalid or expired"
                })

        # ---------------------------------------
        # 4. Build summary
        # ---------------------------------------
        summary = f"""
Forensic Analysis Summary
-------------------------
Disk events: {len(disk_data.get('events', []))}
Browser visits: {len(browser_data.get('visits', []))}
Browser downloads: {len(browser_data.get('downloads', []))}
Cookies: {len(browser_data.get('cookies', []))}

Findings: {len(findings)}
Anomalies: {len(anomalies)}
"""

        return {
            "summary": summary.strip(),
            "findings": findings,
            "anomalies": anomalies,
            "timeline": timeline
        }

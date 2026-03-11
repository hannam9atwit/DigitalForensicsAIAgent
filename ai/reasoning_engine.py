from ai.rule_engine import RuleEngine
from ai.anomaly_engine import AnomalyEngine

class ReasoningEngine:
    """
    Combines rule-based findings and anomaly detection
    with disk/browser artifacts and unified timeline.
    """

    def __init__(self):
        self.rules = RuleEngine()
        self.anomalies_engine = AnomalyEngine()

    def analyze(self, disk_data, browser_data, unified_timeline):
        disk_events = unified_timeline.get("events", [])
        browser_visits = browser_data.get("visits", [])
        browser_downloads = browser_data.get("downloads", [])
        cookies = browser_data.get("cookies", [])

        findings = self.rules.run(
            {"events": disk_events},  # parsed events
            browser_data,
            unified_timeline
        )

        anomalies = self.anomalies_engine.run(
            {"events": disk_events},  # parsed events
            browser_data,
            unified_timeline
        )

        print("[DEBUG] findings type:", type(findings), findings[:3] if isinstance(findings, list) else findings)
        print("[DEBUG] anomalies type:", type(anomalies), anomalies[:3] if isinstance(anomalies, list) else anomalies)

        return {
            "disk": disk_data,
            "browser": browser_data,
            "timeline": unified_timeline,
            "findings": findings,
            "anomalies": anomalies,
            "summary": {
                "finding_count": len(findings),
                "anomaly_count": len(anomalies)
            }
        }

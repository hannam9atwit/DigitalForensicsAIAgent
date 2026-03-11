from ai.rule_engine import RuleEngine
from ai.anomaly_engine import AnomalyEngine
from ai.narrative_engine import NarrativeEngine

class ReasoningEngine:
    """
    Combines rule-based findings and anomaly detection
    with disk/browser artifacts and unified timeline.
    """

    def __init__(self):
        self.rules = RuleEngine()
        self.anomalies_engine = AnomalyEngine()
        self.narrative_engine = NarrativeEngine()

    def analyze(self, disk_data, browser_data, unified_timeline):
        disk_events = unified_timeline.get("events", [])
        browser_visits = browser_data.get("visits", [])
        browser_downloads = browser_data.get("downloads", [])
        cookies = browser_data.get("cookies", [])

        # Run rule engine + anomaly engine
        findings = self.rules.run(
            {"events": disk_events},
            browser_data,
            unified_timeline
        )

        anomalies = self.anomalies_engine.run(
            {"events": disk_events},
            browser_data,
            unified_timeline
        )

        # Build the result dictionary FIRST
        result_dict = {
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

        # Now generate the narrative using the full result
        narrative_text = self.narrative_engine.generate(result_dict)
        result_dict["narrative"] = narrative_text

        # Debug prints
        print("[DEBUG] findings type:", type(findings), findings[:3] if isinstance(findings, list) else findings)
        print("[DEBUG] anomalies type:", type(anomalies), anomalies[:3] if isinstance(anomalies, list) else anomalies)

        return result_dict

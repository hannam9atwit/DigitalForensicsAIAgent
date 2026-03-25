from core.artifact_router import ArtifactRouter
from modules.disk.mft_parser import MFTParser
from modules.disk.deleted_recovery import DeletedRecovery
from modules.disk.timeline_builder import DiskTimelineBuilder
from modules.browser.history_parser import HistoryParser
from modules.browser.downloads_parser import DownloadsParser
from modules.browser.cookies_parser import CookiesParser
from modules.timeline.correlation_engine import TimelineCorrelationEngine
from ai.reasoning_engine import ReasoningEngine
from ai.report_generator import ReportGenerator


def main():
    print("[*] Forensic AI Agent starting...")

    # Route artifact
    path = "data/sample_disk.img"
    router = ArtifactRouter()
    route = router.route(path)
    print("[*] Routing result:", route)

    artifact_type = route["artifact_type"]

    # Disk Forensics
    disk_data = {"events": []}

    if artifact_type == "disk_image":
        print("\n[*] Running Disk Forensics...")
        MFTParser().parse(path)
        DeletedRecovery().recover(path)
        timeline = DiskTimelineBuilder().build_timeline(path)
        disk_data = timeline

    # Browser Forensics
    browser_data = {"visits": [], "downloads": [], "cookies": []}

    if artifact_type.startswith("browser"):
        print("\n[*] Running Browser Forensics...")
        hp = HistoryParser().parse(path)
        dp = DownloadsParser().parse(path)
        cp = CookiesParser().parse(path)
        browser_data = {
            "visits":    hp.get("visits", []),
            "downloads": dp.get("downloads", []),
            "cookies":   cp.get("cookies", []),
        }

    # Unified Timeline
    print("\n[*] Building Unified Timeline...")
    tce = TimelineCorrelationEngine()
    unified_timeline = tce.correlate(
        disk_data.get("events", []),
        browser_data.get("visits", []),
        browser_data.get("downloads", []),
        browser_data.get("cookies", []),
    )

    # Reasoning Engine
    print("\n[*] Running Reasoning Engine...")
    reasoning = ReasoningEngine()
    analysis = reasoning.analyze(disk_data, browser_data, unified_timeline)

    # Report Generation
    print("\n[*] Generating Final Report...")
    rg = ReportGenerator()
    report_path = rg.generate(analysis)
    print("[*] Report generated at:", report_path)


if __name__ == "__main__":
    main()

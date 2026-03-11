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


def run_pipeline(path, log):
    """
    Runs the full forensic pipeline.
    'log' is a callback function that receives log messages.
    """

    log("[*] Routing artifact...")
    router = ArtifactRouter()
    route = router.route(path)
    log(f"[+] Artifact type: {route['artifact_type']}")

    artifact_type = route["artifact_type"]

    # ---------------------------------------------------------
    # Disk Forensics
    # ---------------------------------------------------------
    disk_data = {"events": []}

    if artifact_type == "disk_image":
        log("[*] Running Disk Forensics...")

        mft = MFTParser().parse(path)
        log("[+] MFT parsed")

        deleted = DeletedRecovery().recover(path)
        log("[+] Deleted files processed")

        timeline = DiskTimelineBuilder().build_timeline(path)
        log("[+] Disk timeline built")

        disk_data = timeline

    # ---------------------------------------------------------
    # Browser Forensics
    # ---------------------------------------------------------
    browser_data = {
        "visits": [],
        "downloads": [],
        "cookies": []
    }

    if artifact_type.startswith("browser"):
        log("[*] Running Browser Forensics...")

        hp = HistoryParser().parse(path)
        dp = DownloadsParser().parse(path)
        cp = CookiesParser().parse(path)

        browser_data = {
            "visits": hp.get("visits", []),
            "downloads": dp.get("downloads", []),
            "cookies": cp.get("cookies", [])
        }

        log("[+] Browser artifacts parsed")
    # # ---------------------------------------------------------
    # # Unified Timeline
    # # ---------------------------------------------------------
    # log(f"[DEBUG] disk_data type: {type(disk_data)} value: {disk_data}")
    # log(f"[DEBUG] browser_data type: {type(browser_data)} value: {browser_data}")
    #
    # log("[*] Building Unified Timeline...")
    # tce = TimelineCorrelationEngine()
    # unified_timeline = tce.correlate(
    #     disk_data.get("events", []),
    #     browser_data.get("visits", []),
    #     browser_data.get("downloads", []),
    #     browser_data.get("cookies", [])
    # )

    # ---------------------------------------------------------
    # Unified Timeline
    # ---------------------------------------------------------
    log("[*] Building Unified Timeline...")
    tce = TimelineCorrelationEngine()
    unified_timeline = tce.correlate(
        disk_data.get("events", []),
        browser_data.get("visits", []),
        browser_data.get("downloads", []),
        browser_data.get("cookies", [])
    )
    log("[+] Timeline built")

    # ---------------------------------------------------------
    # Reasoning Engine
    # ---------------------------------------------------------
    log("[*] Running Reasoning Engine...")
    re = ReasoningEngine()
    analysis = re.analyze(disk_data, browser_data, unified_timeline)
    log("[+] Reasoning complete")

    # ---------------------------------------------------------
    # Report Generation
    # ---------------------------------------------------------
    log("[*] Generating Report...")
    rg = ReportGenerator()
    report_path = rg.generate(analysis)
    log(f"[+] Report generated at: {report_path}")

    return analysis, report_path

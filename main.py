from core.artifact_router import ArtifactRouter
from core.tool_runner import ToolRunner
from core.output_normalizer import OutputNormalizer
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
    # Tests for everything
    # print("[*] Forensic AI Agent starting...")
    #
    # # Artifact routing test
    # sample_path = "data/sample_disk.img"
    # router = ArtifactRouter()
    # result = router.route(sample_path)
    # print("[*] Routing result:", result)
    #
    # # Tool runner test
    # print("\n[*] Testing Tool Runner...")
    # runner = ToolRunner()
    #
    # # Test: run 'fls -V' (version check)
    # test_cmd = ["fls", "-V"]
    # output = runner.run_tsk(test_cmd)
    #
    # print("[*] fls output:")
    # print(output)
    #
    # print("\n[*] Testing Output Normalizer...")
    #
    # normalizer = OutputNormalizer()
    #
    # # Fake fls output for testing
    # fake_fls = """
    # r/r 128-128-3: $MFT
    # d/d 256-256-5: Users
    # r/r 512-512-1: secret.docx (deleted)
    # """
    #
    # parsed = normalizer.normalize_fls(fake_fls)
    # print("[*] Parsed fls:")
    # print(parsed)
    #
    # print("\n[*] Testing MFT Parser...")
    #
    # mft = MFTParser()
    # mft_result = mft.parse("data/sample_disk.img")
    #
    # print("[*] MFT Parser result:")
    # print(mft_result)
    #
    # print("\n[*] Testing Deleted File Recovery...")
    #
    # dr = DeletedRecovery()
    # recovery_result = dr.recover("data/sample_disk.img")
    #
    # print("[*] Deleted Recovery result:")
    # print(recovery_result)
    #
    # print("\n[*] Testing Disk Timeline Builder...")
    #
    # tl = DiskTimelineBuilder()
    # timeline_result = tl.build_timeline("data/sample_disk.img")
    #
    # print("[*] Timeline result:")
    # print(timeline_result)
    #
    # print("\n[*] Testing Browser History Parser...")
    #
    # hp = HistoryParser()
    # history_result = hp.parse("data/sample_browser/History")
    #
    # print("[*] History Parser result:")
    # print(history_result)
    #
    # print("\n[*] Testing Downloads Parser...")
    #
    # dp = DownloadsParser()
    # downloads_result = dp.parse("data/sample_browser/History")
    #
    # print("[*] Downloads Parser result:")
    # print(downloads_result)
    #
    # print("\n[*] Testing Cookies Parser...")
    #
    # cp = CookiesParser()
    # cookies_result = cp.parse("data/sample_browser/Cookies")
    #
    # print("[*] Cookies Parser result:")
    # print(cookies_result)
    #
    # print("\n[*] Testing Timeline Correlation Engine...")
    #
    # tce = TimelineCorrelationEngine()
    #
    # # Fake test data
    # fake_disk = [{"date": "2023-01-01 12:00:00"}]
    # fake_visits = [{"visit_time": 1672574400}]  # Unix timestamp
    # fake_downloads = [{"start_time": 1672578000}]
    # fake_cookies = [{"expires_utc": 1672581600}]
    #
    # timeline = tce.correlate(fake_disk, fake_visits, fake_downloads, fake_cookies)
    #
    # print("[*] Unified Timeline:")
    # print(timeline)
    #
    # re = ReasoningEngine()
    #
    # fake_disk = {"events": [{"date": "2023-01-01 12:00:00"}]}
    # fake_browser = {
    #     "visits": [],
    #     "downloads": [{"start_time": 1672578000, "danger_type": 1}],
    #     "cookies": [{"expires_utc": -1}]
    # }
    # fake_timeline = timeline  # from previous test
    #
    # analysis = re.analyze(fake_disk, fake_browser, fake_timeline)
    #
    # print("[*] Reasoning Engine Output:")
    # print(analysis)
    #
    # print("\n[*] Testing Report Generator...")
    #
    # rg = ReportGenerator()
    # report_path = rg.generate(analysis)
    #
    # print("[*] Report generated at:", report_path)

    print("[*] Forensic AI Agent starting...")

    # ---------------------------------------------------------
    # 1. Route artifact
    # ---------------------------------------------------------
    path = "data/sample_disk.img"  # You can change this later
    router = ArtifactRouter()
    route = router.route(path)
    print("[*] Routing result:", route)

    artifact_type = route["artifact_type"]

    # ---------------------------------------------------------
    # 2. Disk Forensics
    # ---------------------------------------------------------
    disk_data = {"events": []}

    if artifact_type == "disk_image":
        print("\n[*] Running Disk Forensics...")

        mft = MFTParser().parse(path)
        deleted = DeletedRecovery().recover(path)
        timeline = DiskTimelineBuilder().build_timeline(path)

        disk_data = timeline  # timeline contains events

    # ---------------------------------------------------------
    # 3. Browser Forensics
    # ---------------------------------------------------------
    browser_data = {
        "visits": [],
        "downloads": [],
        "cookies": []
    }

    if artifact_type.startswith("browser"):
        print("\n[*] Running Browser Forensics...")

        hp = HistoryParser().parse(path)
        dp = DownloadsParser().parse(path)
        cp = CookiesParser().parse(path)

        browser_data = {
            "visits": hp.get("visits", []),
            "downloads": dp.get("downloads", []),
            "cookies": cp.get("cookies", [])
        }

    # ---------------------------------------------------------
    # 4. Unified Timeline
    # ---------------------------------------------------------
    print("\n[*] Building Unified Timeline...")

    tce = TimelineCorrelationEngine()
    unified_timeline = tce.correlate(
        disk_data.get("events", []),
        browser_data.get("visits", []),
        browser_data.get("downloads", []),
        browser_data.get("cookies", [])
    )

    # ---------------------------------------------------------
    # 5. Reasoning Engine
    # ---------------------------------------------------------
    print("\n[*] Running Reasoning Engine...")

    re = ReasoningEngine()
    analysis = re.analyze(disk_data, browser_data, unified_timeline)

    # ---------------------------------------------------------
    # 6. Report Generation
    # ---------------------------------------------------------
    print("\n[*] Generating Final Report...")

    rg = ReportGenerator()
    report_path = rg.generate(analysis)

    print("[*] Report generated at:", report_path)

if __name__ == "__main__":
    main()

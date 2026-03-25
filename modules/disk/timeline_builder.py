"""
modules/disk/timeline_builder.py
"""
from core.tool_runner import ToolRunner
from core.partition_detector import detect_ntfs_offset


class DiskTimelineBuilder:

    def __init__(self):
        self.runner = ToolRunner()

    def build_timeline(self, image_path: str) -> dict:
        print("[*] Building disk timeline...")
        offset = detect_ntfs_offset(image_path)
        cmd    = ["fls", "-o", str(offset), "-m", "/", "-r", image_path]
        result = self.runner.run_tsk(cmd, image_path=image_path)

        if not isinstance(result, dict):
            return {"error": "Invalid result from ToolRunner", "events": []}
        if result.get("returncode") != 0:
            print("[!] fls failed:", result.get("stderr"))
            return {"error": result.get("stderr"), "events": []}

        events = result.get("stdout", "").splitlines()
        return {"offset": offset, "events": events, "count": len(events)}
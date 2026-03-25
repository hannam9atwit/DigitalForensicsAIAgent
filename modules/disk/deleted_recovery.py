"""
modules/disk/deleted_recovery.py
"""
from core.tool_runner import ToolRunner
from core.partition_detector import detect_ntfs_offset


class DeletedRecovery:

    def __init__(self):
        self.runner = ToolRunner()

    def recover(self, image_path: str) -> dict:
        print("[*] Searching for deleted files...")
        offset = detect_ntfs_offset(image_path)
        cmd    = ["fls", "-o", str(offset), "-d", "-r", image_path]
        result = self.runner.run_tsk(cmd, image_path=image_path)

        if not isinstance(result, dict):
            return {"error": "Invalid result from ToolRunner", "deleted": []}
        if result.get("returncode") != 0:
            print("[!] fls failed:", result.get("stderr"))
            return {"error": result.get("stderr"), "deleted": []}

        deleted = result.get("stdout", "").splitlines()
        return {"offset": offset, "deleted": deleted, "count": len(deleted)}
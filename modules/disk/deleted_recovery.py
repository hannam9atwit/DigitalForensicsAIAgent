from core.tool_runner import ToolRunner
from core.partition_detector import detect_ntfs_offset

class DeletedRecovery:
    def __init__(self):
        self.runner = ToolRunner()

    def recover(self, image_path: str):
        print("[*] Searching for deleted files...")

        offset = detect_ntfs_offset(image_path)

        cmd = ["fls", "-o", str(offset), "-d", "-r", image_path]
        result = self.runner.run_tsk(cmd)

        if not isinstance(result, dict):
            return {"error": "Invalid result from ToolRunner", "deleted": []}

        if result.get("returncode") != 0:
            print("[!] fls failed:", result.get("stderr"))
            return {"error": result.get("stderr"), "deleted": []}

        deleted_entries = result.get("stdout", "").splitlines()

        return {
            "offset": offset,
            "deleted": deleted_entries,
            "count": len(deleted_entries)
        }

from core.output_normalizer import OutputNormalizer
from core.tool_runner import ToolRunner
from core.partition_detector import detect_ntfs_offset

class MFTParser:
    def __init__(self):
        self.normalizer = OutputNormalizer()
        self.runner = ToolRunner()

    def parse(self, image_path: str):
        print("[*] Running fls to extract MFT entries...")

        offset = detect_ntfs_offset(image_path)

        cmd = ["fls", "-o", str(offset), "-r", image_path]
        result = self.runner.run_tsk(cmd)

        if not isinstance(result, dict):
            return {"error": "Invalid result from ToolRunner", "entries": []}

        if result.get("returncode") != 0:
            print("[!] fls failed:", result.get("stderr"))
            return {"error": result.get("stderr"), "entries": []}

        entries = self.normalizer.normalize_fls(result.get("stdout", ""))

        return {
            "image_path": image_path,
            "entries": entries,
            "count": len(entries),
            "offset": offset
        }

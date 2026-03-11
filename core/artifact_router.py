import os
from typing import Dict

class ArtifactRouter:
    """
    Determines artifact type (disk image vs browser DB) and returns routing info.
    """

    def route(self, path: str) -> Dict:
        artifact_type = self._detect_type(path)
        return {
            "path": path,
            "artifact_type": artifact_type,
        }

    def _detect_type(self, path: str) -> str:
        if not os.path.exists(path):
            return "unknown"

        filename = os.path.basename(path).lower()

        # Correct disk image detection
        if filename.endswith((".img", ".dd", ".raw", ".e01")):
            return "disk_image"

        # Browser artifacts
        if filename in ("history", "history.db", "places.sqlite"):
            return "browser_history"

        if "cookies" in filename:
            return "browser_cookies"

        if "downloads" in filename:
            return "browser_downloads"

        return "unknown"

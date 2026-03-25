"""
core/artifact_router.py
"""
import os
from typing import Dict


class ArtifactRouter:

    DISK_EXTENSIONS = {".img", ".dd", ".raw", ".e01", ".ex01", ".s01"}
    BROWSER_NAMES   = {"history", "history.db", "places.sqlite"}

    def route(self, path: str) -> Dict:
        return {
            "path":          path,
            "artifact_type": self._detect_type(path),
        }

    def _detect_type(self, path: str) -> str:
        if not os.path.exists(path):
            return "unknown"

        filename = os.path.basename(path).lower()
        ext      = os.path.splitext(filename)[1].lower()

        if ext in self.DISK_EXTENSIONS:
            return "disk_image"
        if filename in self.BROWSER_NAMES:
            return "browser_history"
        if "cookies" in filename:
            return "browser_cookies"
        if "downloads" in filename:
            return "browser_downloads"
        return "unknown"
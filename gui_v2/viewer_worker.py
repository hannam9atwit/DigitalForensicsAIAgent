"""
gui_v2/viewer_worker.py

Runs the artifact-viewer parsers off the UI thread, mirroring ai_worker.py.

The freeze this prevents: rendered_records() on a large pcap and file_tree()'s
SleuthKit fls call can block for seconds. Run inline they stall the Qt event
loop and Windows paints "not responding". Here the blocking parse happens on a
daemon threading.Thread and the result crosses back to the UI thread via a
queued Qt signal — same reasoning as ai_worker.py's docstring: daemon threads
die silently with the process, so a parse in flight at app close can't abort
the shutdown the way a stuck QThread would.

Each job carries a token (artifact id + tier). The screen compares the token
against its current selection before rendering, which makes stale results
harmless when the user clicks between artifacts faster than files parse.
"""

import threading

from PySide6.QtCore import QObject, Signal

from . import artifact_viewer


class ViewerJob(QObject):
    """One parse on a background daemon thread, one signal back."""

    result_ready = Signal(str, object)   # (token, result_dict)
    progress = Signal(str, int, object)  # (token, done, total_or_None)

    def run(self, kind: str, token: str, path: str, artifact_kind: str):
        """Start a parse. kind ∈ {raw, records, tree}."""
        worker = threading.Thread(
            target=self._parse,
            args=(kind, token, path, artifact_kind),
            daemon=True,
            name=f"viewer-{kind}-{token}",
        )
        worker.start()

    def _parse(self, kind, token, path, artifact_kind):
        try:
            if kind == "raw":
                result = artifact_viewer.raw_preview(path)
            elif kind == "records":
                result = artifact_viewer.rendered_records(path, artifact_kind)
            elif kind == "tree":
                result = artifact_viewer.file_tree(path, artifact_kind)
            else:
                result = {"error": f"unknown viewer job kind: {kind}"}
        except Exception as error:  # a bad file must never crash the app
            result = {"error": f"couldn't read this artifact: {error}"}

        # Cross-thread emit: Qt queues this onto the UI thread.
        self.result_ready.emit(token, result)

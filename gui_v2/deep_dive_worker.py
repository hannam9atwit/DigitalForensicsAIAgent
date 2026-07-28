"""
gui_v2/deep_dive_worker.py

Runs the background deep dive off the UI thread, mirroring ai_worker.py.

A daemon threading.Thread, not a QThread: each layer is a blocking HTTP
generation that cannot be interrupted mid-flight, and a daemon thread simply
dies with the process at close rather than aborting shutdown the way a stuck
QThread would. Cancellation is a flag checked between prompts (never mid-prompt,
so a case is never left half-written). Results cross back to the UI thread on
queued Qt signals; MainWindow is the only writer to the case and the only caller
of persistence, which keeps the knowledge base race-free.

The elapsed/remaining estimate is measured from the per-prompt durations
actually observed in THIS run — a skipped (already-done) step is near-instant
and excluded — so the countdown tracks reality rather than a fixed constant.
"""

import time
import threading

from PySide6.QtCore import QObject, Signal

from ai import knowledge_base as kb_mod
from ai.deep_dive import DeepDive


class DeepDiveWorker(QObject):
    """One deep dive on a background daemon thread, results by signal."""

    entry_ready = Signal(object)          # a finished KB entry dict
    progress = Signal(int, int, object)   # done, total, eta_seconds | None
    milestone = Signal()                  # persist-worthy boundary reached
    log = Signal(str)                     # audit / diagnostic line
    finished = Signal(str)                # "complete" | "cancelled" | "unavailable"

    def __init__(self, case, events, ai_config, existing_entries=None, parent=None):
        super().__init__(parent)
        self._case = case
        self._events = events
        self._ai_config = ai_config or {}
        self._existing = list(existing_entries or [])
        self._cancel = threading.Event()
        self._durations = []       # observed seconds per executed prompt
        self._last_tick = None

    def cancel(self):
        """Ask the dive to stop. Safe from the UI thread; the run loop checks
        this between prompts and returns 'cancelled' with completed work kept."""
        self._cancel.set()

    def start(self):
        threading.Thread(target=self._run, daemon=True, name="deep-dive").start()

    def _run(self):
        from ai.surface_engine import SurfaceEngine
        engine = SurfaceEngine(self._ai_config)
        knowledge = kb_mod.KnowledgeBase(self._existing)

        dive = DeepDive(
            self._case, self._events, engine.complete,
            is_cancelled=self._cancel.is_set,
            on_entry=lambda entry, step: self.entry_ready.emit(entry),
            on_progress=self._on_progress,
            on_milestone=self.milestone.emit,
            log=self.log.emit,
        )
        try:
            result = dive.run(knowledge)
        except Exception as error:                      # noqa: BLE001
            self.log.emit(f"deep dive error: {error}")
            result = "unavailable"
        self.finished.emit(result)

    def _on_progress(self, done, total):
        now = time.monotonic()
        if self._last_tick is not None:
            delta = now - self._last_tick
            # A real generation takes seconds; a skipped/resumed step is
            # near-instant. Only real ones inform the estimate.
            if delta >= 1.0:
                self._durations.append(delta)
        self._last_tick = now

        eta = None
        if self._durations and done < total:
            mean = sum(self._durations) / len(self._durations)
            eta = int(mean * (total - done))
        self.progress.emit(done, total, eta)

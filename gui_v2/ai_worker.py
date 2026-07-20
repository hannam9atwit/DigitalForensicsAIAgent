"""
gui_v2/ai_worker.py

Runs surface_engine generations off the UI thread.

The UX contract every screen follows: show the deterministic text instantly,
kick a SurfaceJob, and when result_ready fires — if the user's selection
hasn't moved on — swap the richer LLM text in. A 3B model on CPU can take
tens of seconds; the app must never look frozen while it thinks.

Implementation note: this uses a daemon threading.Thread rather than QThread
on purpose. The generation is one blocking HTTP call that cannot be
interrupted mid-flight; a QThread stuck in that call at app close aborts the
whole process ("QThread: Destroyed while thread is still running"). A daemon
thread simply dies with the process. The result crosses back to the UI thread
via a queued Qt signal, which is thread-safe by design.

Each job carries a `token` (whatever the screen uses to identify the request,
typically an artifact id). The screen compares the token against its current
selection before applying the result, which makes stale responses harmless
without any cancellation machinery.
"""

import threading

from PySide6.QtCore import QObject, Signal

from ai.surface_engine import SurfaceEngine


class SurfaceJob(QObject):
    """One generation on a background daemon thread, one signal back."""

    result_ready = Signal(str, str)     # (token, generated_text)
    answer_ready = Signal(str, object)  # (token, answer_dict | None) — ask only

    def __init__(self, ai_config: dict, parent=None):
        super().__init__(parent)
        self._engine = SurfaceEngine(ai_config)

    def run(self, kind: str, token: str, fallback: str, **kwargs):
        """Start a generation. kind ∈ {overview, plain_terms, what_it_means, ask}."""
        worker = threading.Thread(
            target=self._generate,
            args=(kind, token, fallback, kwargs),
            daemon=True,
            name=f"surface-{kind}-{token}",
        )
        worker.start()

    def _generate(self, kind, token, fallback, kwargs):
        if kind == "ask":
            try:
                answer = self._engine.ask(kwargs["question"], kwargs["case"])
            except Exception:
                answer = None
            self.answer_ready.emit(token, answer)
            return

        try:
            if kind == "overview":
                text = self._engine.case_overview(kwargs["case"], fallback)
            elif kind == "plain_terms":
                text = self._engine.plain_terms(
                    kwargs["subject"], kwargs["detail"], kwargs["case"], fallback)
            elif kind == "what_it_means":
                text = self._engine.what_it_means(
                    kwargs["artifact"], kwargs["case"], fallback)
            else:
                text = fallback
        except Exception:
            text = fallback

        # Cross-thread emit: Qt queues this onto the receiver's (UI) thread.
        self.result_ready.emit(token, text)

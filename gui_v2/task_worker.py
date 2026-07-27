"""
gui_v2/task_worker.py

Runs one blocking callable off the UI thread and reports back with queued Qt
signals — the same rationale as gui_v2/ai_worker.py.

Hashing a multi-GB disk image, copying evidence, building a PDF, or opening a
saved case is seconds-to-minutes of file and CPU work. Run inline in a slot it
freezes the whole window — the progress dialog included, because the event loop
never gets a turn. Run here it leaves the loop free to paint and animate while
the work proceeds.

A daemon threading.Thread is used rather than a QThread on purpose: the work is
uninterruptible file/subprocess I/O, and a daemon thread simply dies with the
process at close instead of aborting it mid-flight. The return value crosses
back on the done signal, which Qt delivers on the UI thread; progress lines
cross back the same way.
"""

import threading

from PySide6.QtCore import QObject, Signal


class BackgroundTask(QObject):
    """One blocking callable on a background daemon thread, results by signal.

    `fn` receives a single argument — a progress(str) callback for status
    lines — and returns any value. The value is delivered on `done`; an
    exception is delivered on `failed`.
    """

    progress = Signal(str)      # human-readable status line
    done = Signal(object)       # the callable's return value
    failed = Signal(str)        # exception text
    finished = Signal()         # always last — the thread has returned

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def start(self):
        threading.Thread(target=self._run, daemon=True, name="bg-task").start()

    def _run(self):
        try:
            result = self._fn(self.progress.emit)
        except Exception as e:                                   # noqa: BLE001
            self.failed.emit(str(e))
        else:
            # Cross-thread emit: Qt queues this onto the receiver's (UI) thread.
            self.done.emit(result)
        # Fires after done/failed so an owner can release its reference only
        # once the worker has truly stopped, never on the result alone.
        self.finished.emit()

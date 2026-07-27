"""
gui_v2/thread_registry.py

Keeps QThread-based workers alive until their thread has *genuinely* finished.

The trap this closes: a QThread (and the worker moved onto it) held only in a
single instance attribute — on a screen, say — is freed the moment that owner
is garbage-collected or the attribute is reassigned. If the thread is still
running when that happens, Qt aborts the whole process with
"QThread: Destroyed while thread is still running". The reported crash was
exactly this: the Settings screen starts a readiness-probe QThread in its
constructor, and the very next step (entering analysis) clears the screen
stack, freeing that screen — and its still-running thread — mid-probe.

So every live thread is retained here, in a process-lifetime set, and released
ONLY on the thread's finished() signal — never on the worker's result signal,
which fires while the thread is still winding down. Screens and re-runs drop
their own references freely; the registry outlives them.
"""

_live = set()   # {(thread, worker_or_None)} — retained until thread.finished


def track(thread, worker=None):
    """Retain `thread` (and its `worker`) until the thread finishes.

    Call right after moveToThread and before thread.start(). Both objects must
    stay alive for the whole run: the worker so it can still emit its result and
    quit signals, the thread so Qt can finish and delete it cleanly. On
    finished() the pair is released and the thread is scheduled for deletion;
    the worker is then collected once the finished thread is gone.

    Returns `thread` for convenient chaining.
    """
    entry = (thread, worker)
    _live.add(entry)

    def _release(*_):
        _live.discard(entry)
        # deleteLater on a QThread has UI-thread affinity and runs after the
        # thread has stopped, so Qt owns the teardown; the worker is freed with
        # the closure once this connection (and the thread) is gone.
        thread.deleteLater()

    thread.finished.connect(_release)
    return thread


def shutdown(wait_ms=3000):
    """Stop and join every live thread so interpreter exit never collects a
    still-running QThread. Called from the window's close path.

    A thread stuck in a blocking call it can't be told to abandon (a network
    probe, a long parse) is waited on up to wait_ms and then left to the exiting
    process — the mid-session crash this module prevents cannot happen at that
    point because nothing will try to touch it again.
    """
    for thread, _worker in list(_live):
        try:
            if thread.isRunning():
                thread.quit()
                thread.wait(wait_ms)
        except RuntimeError:
            pass  # C++ object already deleted — nothing to wait on

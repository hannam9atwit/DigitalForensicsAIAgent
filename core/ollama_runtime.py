"""
core/ollama_runtime.py

The single authority for everything Ollama: where the executable lives, whether
the server is up, which models are present, and starting the server when it
isn't running.

Every other module (entry point, settings screen, refinement engine, surface
engine) asks this module instead of probing localhost:11434 itself, so the
"is local AI available?" question has exactly one answer at any moment.

Pure stdlib — no Qt, no third-party deps — so it works identically from the
GUI, the headless pipeline, and build tooling.
"""

import json
import os
import platform
import shutil
import subprocess
import time
import urllib.error
import urllib.request

OLLAMA_HOST = "http://localhost:11434"
DEFAULT_MODEL = "llama3.2:3b"

_SERVER_START_TIMEOUT_S = 20
_HTTP_TIMEOUT_S = 4


def find_executable() -> str | None:
    """Return the path to the ollama executable, or None if not installed.

    Checks PATH first, then the per-user Windows install location (the Ollama
    installer is per-user and does not always update PATH for the current
    process), then common Linux locations.
    """
    on_path = shutil.which("ollama")
    if on_path:
        return on_path

    if platform.system() == "Windows":
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        candidate = os.path.join(local_app_data, "Programs", "Ollama", "ollama.exe")
        if os.path.isfile(candidate):
            return candidate
        return None

    for candidate in ("/usr/local/bin/ollama", "/usr/bin/ollama"):
        if os.path.isfile(candidate):
            return candidate
    return None


def is_installed() -> bool:
    return find_executable() is not None


def server_running() -> bool:
    """True if an Ollama server answers on the local API port."""
    try:
        request = urllib.request.Request(f"{OLLAMA_HOST}/api/tags", method="GET")
        with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT_S):
            return True
    except (urllib.error.URLError, OSError):
        return False


def installed_models() -> list[str]:
    """Names of models the local server has available. Empty if server down."""
    try:
        request = urllib.request.Request(f"{OLLAMA_HOST}/api/tags", method="GET")
        with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT_S) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return []
    return [m.get("name", "") for m in body.get("models", []) if m.get("name")]


def model_available(model: str = DEFAULT_MODEL) -> bool:
    """True if `model` (or any tag of its base name) is present locally."""
    base_name = model.split(":")[0]
    return any(base_name == name.split(":")[0] for name in installed_models())


def start_server() -> bool:
    """Start `ollama serve` detached and wait until it answers.

    Returns True once the API responds, False if Ollama is not installed or
    the server did not come up within the timeout. Safe to call when a server
    is already running.
    """
    if server_running():
        return True

    executable = find_executable()
    if not executable:
        return False

    creation_flags = 0
    if platform.system() == "Windows":
        creation_flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS

    try:
        subprocess.Popen(
            [executable, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=creation_flags,
        )
    except OSError:
        return False

    deadline = time.monotonic() + _SERVER_START_TIMEOUT_S
    while time.monotonic() < deadline:
        if server_running():
            return True
        time.sleep(0.5)
    return False


def pull_model(model: str = DEFAULT_MODEL, on_progress=None) -> bool:
    """Pull `model` via the local API, streaming progress.

    `on_progress` receives human-readable status strings. Returns True on
    success. Requires the server to be running and internet access.
    """
    payload = json.dumps({"name": model, "stream": True}).encode("utf-8")
    request = urllib.request.Request(
        f"{OLLAMA_HOST}/api/pull",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=None) as response:
            for raw_line in response:
                if not on_progress:
                    continue
                try:
                    update = json.loads(raw_line.decode("utf-8"))
                except ValueError:
                    continue
                status = update.get("status", "")
                total = update.get("total")
                completed = update.get("completed")
                if total and completed:
                    percent = completed * 100 // total
                    on_progress(f"{status} — {percent}%")
                elif status:
                    on_progress(status)
    except (urllib.error.URLError, OSError) as error:
        if on_progress:
            on_progress(f"pull failed: {error}")
        return False

    return model_available(model)


def model_loaded(model: str = DEFAULT_MODEL) -> bool:
    """True if the model is loaded in memory right now (not just on disk).

    Ollama reports running models at /api/ps. A model present on disk but not
    loaded still costs a multi-second load on the first real request, so the
    GUI distinguishes "present" from "warm".
    """
    try:
        request = urllib.request.Request(f"{OLLAMA_HOST}/api/ps", method="GET")
        with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT_S) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return False
    base = model.split(":")[0]
    return any(base == m.get("name", "").split(":")[0]
               for m in body.get("models", []))


def warm_model(model: str = DEFAULT_MODEL) -> bool:
    """Load the model into memory with one tiny request, so the user's first
    real question doesn't eat the load time.

    Warming only loads a model that is already present; it never downloads
    (that needs consent). keep_alive asks Ollama to hold the model resident.
    Returns True if the model is warm afterward.
    """
    if not server_running() or not model_available(model):
        return False
    payload = json.dumps({
        "model": model,
        "prompt": "ok",
        "stream": False,
        "keep_alive": "30m",
        "options": {"num_predict": 1},
    }).encode("utf-8")
    request = urllib.request.Request(
        f"{OLLAMA_HOST}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120):
            return True
    except (urllib.error.URLError, OSError):
        return False


def readiness(model: str = DEFAULT_MODEL) -> dict:
    """One-call health summary the GUI can render directly.

    Returns {"installed", "running", "model_ready", "model_loaded"} — each a
    bool, evaluated in dependency order (a stopped server can't report
    models). model_loaded distinguishes a warm model from one merely present.
    """
    installed = is_installed()
    running = server_running()
    ready = model_available(model) if running else False
    loaded = model_loaded(model) if ready else False
    return {"installed": installed, "running": running,
            "model_ready": ready, "model_loaded": loaded}


def ensure_ready(model: str = DEFAULT_MODEL) -> dict:
    """Best-effort silent bring-up: start the server if installed but stopped.

    Never pulls a model (that needs user consent for a 2 GB download) — it
    only starts what is already on the machine. Returns the same shape as
    readiness().
    """
    if is_installed() and not server_running():
        start_server()
    return readiness(model)

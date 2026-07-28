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
# Faster probe for interactive status checks: the UI asks for readiness on
# every screen show, and a full 4s-per-call wait when Ollama is absent makes
# the whole app feel frozen. Status probes use this shorter timeout; the real
# work calls (pull, warm, generate) keep the longer ones.
_STATUS_TIMEOUT_S = 1.5

# readiness() is called from UI render paths (chat pill, settings). Each call
# otherwise makes up to three blocking HTTP requests, so opening a screen could
# stall for seconds. A short cache means repeated calls within the window reuse
# the last probe instead of re-hitting the network every render.
_READINESS_CACHE = {"value": None, "at": 0.0, "model": None}
_READINESS_TTL_S = 3.0


def find_executable() -> str | None:
    """Return the path to the ollama executable, or None if not found.

    Checks PATH first, then every known Windows install location across Ollama
    versions (the install path has moved between releases and differs for
    per-user vs all-users installs), then common Unix locations.
    """
    on_path = shutil.which("ollama")
    if on_path:
        return on_path

    if platform.system() == "Windows":
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        program_files_x86 = os.environ.get(
            "ProgramFiles(x86)", r"C:\Program Files (x86)")
        candidates = [
            os.path.join(local_app_data, "Programs", "Ollama", "ollama.exe"),
            os.path.join(local_app_data, "Ollama", "ollama.exe"),
            os.path.join(program_files, "Ollama", "ollama.exe"),
            os.path.join(program_files_x86, "Ollama", "ollama.exe"),
        ]
        for candidate in candidates:
            if candidate and os.path.isfile(candidate):
                return candidate
        return None

    for candidate in ("/usr/local/bin/ollama", "/usr/bin/ollama",
                      os.path.expanduser("~/.ollama/bin/ollama")):
        if os.path.isfile(candidate):
            return candidate
    return None


def is_installed() -> bool:
    """True if Ollama is present. A server already answering on the API port
    is itself proof Ollama is installed, even when the executable sits in a
    location we don't recognize — so that counts too."""
    return find_executable() is not None or server_running()


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
            invalidate_readiness_cache()
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

    A model that is already loaded needs no warm-up: on a local CPU model the
    warm request is itself a full 30-90s generation, so double-warming would
    double the latency the user feels. When model_loaded() is already True this
    returns immediately, making the call safe to issue from any path — the app
    warms once at startup (see gui_v2/startup.py) and this guard keeps every
    later call a no-op rather than a second generation.
    """
    if not server_running() or not model_available(model):
        return False
    if model_loaded(model):
        return True
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
        with urllib.request.urlopen(request, timeout=60):
            invalidate_readiness_cache()
            return True
    except (urllib.error.URLError, OSError):
        return False


def readiness(model: str = DEFAULT_MODEL, use_cache: bool = True) -> dict:
    """One-call health summary the GUI can render directly.

    Returns {"installed", "running", "model_ready", "model_loaded"} — each a
    bool, evaluated in dependency order (a stopped server can't report
    models). model_loaded distinguishes a warm model from one merely present.

    Cached for a few seconds because the UI calls this on every screen show;
    without the cache, each call makes up to three blocking HTTP requests and
    the app hitches. Pass use_cache=False to force a fresh probe (e.g. after a
    manual re-check).
    """
    now = time.monotonic()
    if (use_cache and _READINESS_CACHE["value"] is not None
            and _READINESS_CACHE["model"] == model
            and now - _READINESS_CACHE["at"] < _READINESS_TTL_S):
        return dict(_READINESS_CACHE["value"])

    installed = is_installed()
    running = _server_running_fast()
    ready = _model_available_fast(model) if running else False
    loaded = model_loaded(model) if ready else False
    value = {"installed": installed, "running": running,
             "model_ready": ready, "model_loaded": loaded}

    _READINESS_CACHE["value"] = value
    _READINESS_CACHE["at"] = now
    _READINESS_CACHE["model"] = model
    return dict(value)


def invalidate_readiness_cache():
    """Force the next readiness() call to re-probe (after start/stop/pull)."""
    _READINESS_CACHE["value"] = None


def _server_running_fast() -> bool:
    """server_running() with the short status timeout."""
    try:
        request = urllib.request.Request(f"{OLLAMA_HOST}/api/tags", method="GET")
        with urllib.request.urlopen(request, timeout=_STATUS_TIMEOUT_S):
            return True
    except (urllib.error.URLError, OSError):
        return False


def _model_available_fast(model: str = DEFAULT_MODEL) -> bool:
    try:
        request = urllib.request.Request(f"{OLLAMA_HOST}/api/tags", method="GET")
        with urllib.request.urlopen(request, timeout=_STATUS_TIMEOUT_S) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return False
    base = model.split(":")[0]
    return any(base == m.get("name", "").split(":")[0]
               for m in body.get("models", []))


def ensure_ready(model: str = DEFAULT_MODEL) -> dict:
    """Best-effort silent bring-up: start the server if installed but stopped.

    Never pulls a model (that needs user consent for a 2 GB download) — it
    only starts what is already on the machine. Returns the same shape as
    readiness().
    """
    if is_installed() and not server_running():
        start_server()
    return readiness(model, use_cache=False)


# Embedding models are named by convention; use whichever is installed.
_EMBED_HINTS = ("embed", "minilm", "bge", "gte")


def embedding_model() -> str | None:
    """The name of an installed embedding model, or None if none is present.

    Semantic retrieval is optional: when this returns None the knowledge base
    falls back to lexical search, so nothing depends on an embedding model
    having been pulled.
    """
    for name in installed_models():
        if any(hint in name.lower() for hint in _EMBED_HINTS):
            return name
    return None


def embed(texts) -> list | None:
    """Embed a list of strings via the local embeddings endpoint.

    Returns a list of vectors aligned with `texts`, or None when no embedding
    model is available or any request fails — the signal to use lexical search.
    """
    model = embedding_model()
    if not model:
        return None
    vectors = []
    for text in texts:
        payload = json.dumps({"model": model, "prompt": text}).encode("utf-8")
        request = urllib.request.Request(
            f"{OLLAMA_HOST}/api/embeddings", data=payload,
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError):
            return None
        vector = body.get("embedding")
        if not vector:
            return None
        vectors.append(vector)
    return vectors

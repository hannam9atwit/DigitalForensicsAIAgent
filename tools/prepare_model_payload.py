"""
tools/prepare_model_payload.py

Build-machine tool: stage the Ollama model files the Full installer bundles.

Ollama stores models as a manifest (a JSON file naming content-addressed
blobs) plus the blobs themselves. Copying the whole ~/.ollama/models folder
would drag along every model on the build machine, so this reads the target
model's manifest and copies only the blobs it references, preserving the
directory layout Ollama expects:

    redist/ollama-models/
    ├── manifests/registry.ollama.ai/library/<model>/<tag>
    └── blobs/sha256-<digest>...

The installer then lays this tree into the end user's %USERPROFILE%/.ollama/
models, and Ollama picks the model up with no pull and no internet.

Usage (after `ollama pull llama3.2:3b` on the build machine):

    python tools/prepare_model_payload.py [model:tag]
"""

import json
import os
import shutil
import sys

DEFAULT_MODEL = "llama3.2:3b"
REGISTRY = "registry.ollama.ai"
LIBRARY = "library"


def ollama_models_dir() -> str:
    override = os.environ.get("OLLAMA_MODELS")
    if override:
        return override
    return os.path.join(os.path.expanduser("~"), ".ollama", "models")


def output_dir() -> str:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(project_root, "redist", "ollama-models")


def stage_model(model_spec: str) -> int:
    name, _, tag = model_spec.partition(":")
    tag = tag or "latest"

    source_root = ollama_models_dir()
    manifest_path = os.path.join(
        source_root, "manifests", REGISTRY, LIBRARY, name, tag)

    if not os.path.isfile(manifest_path):
        print(f"[!] Manifest not found: {manifest_path}")
        print(f"    Run `ollama pull {model_spec}` on this machine first.")
        return 1

    with open(manifest_path, "r", encoding="utf-8") as manifest_file:
        manifest = json.load(manifest_file)

    digests = [layer["digest"] for layer in manifest.get("layers", [])]
    config_digest = manifest.get("config", {}).get("digest")
    if config_digest:
        digests.append(config_digest)

    destination_root = output_dir()
    if os.path.isdir(destination_root):
        shutil.rmtree(destination_root)

    manifest_destination = os.path.join(
        destination_root, "manifests", REGISTRY, LIBRARY, name)
    os.makedirs(manifest_destination, exist_ok=True)
    shutil.copy2(manifest_path, os.path.join(manifest_destination, tag))

    blob_destination = os.path.join(destination_root, "blobs")
    os.makedirs(blob_destination, exist_ok=True)

    total_bytes = 0
    for digest in digests:
        blob_name = digest.replace(":", "-")
        source_blob = os.path.join(source_root, "blobs", blob_name)
        if not os.path.isfile(source_blob):
            print(f"[!] Missing blob: {source_blob}")
            return 1
        print(f"[*] Copying {blob_name} "
              f"({os.path.getsize(source_blob) / 1_048_576:.0f} MB)")
        shutil.copy2(source_blob, os.path.join(blob_destination, blob_name))
        total_bytes += os.path.getsize(source_blob)

    print(f"[+] Staged {model_spec}: {len(digests)} blobs, "
          f"{total_bytes / 1_073_741_824:.2f} GB → {destination_root}")
    return 0


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL
    sys.exit(stage_model(target))

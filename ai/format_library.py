"""
ai/format_library.py

The format skill system. Every LLM-generated surface in the app (report
sections, case overview, plain-terms rail text, evidence "what it means") has
a spec file in formats/ that defines its structure, tone rules, and few-shot
examples. This module loads those specs and validates model output against
them.

The contract: to change how the AI writes a surface, edit its spec file —
no code changes. When a spec's constraints tighten, validation tightens with
it automatically because the limits live in the spec's front matter.

Spec file anatomy (markdown with a small key: value header block):

    ---
    max_sentences: 3
    max_chars: 420
    forbid: json, array, "as an ai"
    ---
    <the prompt-facing spec text: structure rules + few-shot examples>

Everything after the closing --- is injected verbatim into the prompt.
"""

import os
import re
import sys

SURFACE_CASE_OVERVIEW = "case_overview"
SURFACE_PLAIN_TERMS = "plain_terms"
SURFACE_WHAT_IT_MEANS = "what_it_means"
SURFACE_REPORT_SECTION = "report_section"

_HEADER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# Phrases that mean the model narrated the data instead of writing the surface.
# Applied to every surface on top of each spec's own forbid list.
_ALWAYS_FORBIDDEN = [
    "json", "array of", "objects with", "here is a breakdown",
    "here are the", "if you would like", "feel free to", "as an ai",
    "i cannot", "i can't", "sure!", "certainly!",
]


def _formats_dir() -> str:
    """Locate formats/ both in source checkouts and PyInstaller bundles."""
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "formats")
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(project_root, "formats")


class FormatSpec:
    """One loaded spec: the prompt text plus its validation limits."""

    def __init__(self, surface: str, prompt_text: str, limits: dict):
        self.surface = surface
        self.prompt_text = prompt_text
        self.max_sentences = limits.get("max_sentences")
        self.max_chars = limits.get("max_chars")
        self.min_chars = limits.get("min_chars", 20)
        self.forbidden = _ALWAYS_FORBIDDEN + limits.get("forbid", [])

    def validate(self, text: str) -> list[str]:
        """Return a list of violations; empty means the output conforms."""
        violations = []
        stripped = text.strip()

        if len(stripped) < self.min_chars:
            violations.append(f"too short ({len(stripped)} chars)")
        if self.max_chars and len(stripped) > self.max_chars:
            violations.append(f"too long ({len(stripped)} > {self.max_chars} chars)")

        if self.max_sentences:
            sentence_count = len(re.findall(r"[.!?](?:\s|$)", stripped))
            if sentence_count > self.max_sentences:
                violations.append(
                    f"too many sentences ({sentence_count} > {self.max_sentences})")

        lowered = stripped.lower()
        for phrase in self.forbidden:
            if phrase in lowered:
                violations.append(f"forbidden phrase: {phrase!r}")

        return violations


def load(surface: str) -> FormatSpec | None:
    """Load the spec for a surface, or None if its file is missing."""
    path = os.path.join(_formats_dir(), f"{surface}.md")
    if not os.path.isfile(path):
        return None

    with open(path, "r", encoding="utf-8") as spec_file:
        raw = spec_file.read()

    limits = {}
    prompt_text = raw
    header_match = _HEADER_PATTERN.match(raw)
    if header_match:
        prompt_text = raw[header_match.end():]
        limits = _parse_header(header_match.group(1))

    return FormatSpec(surface, prompt_text.strip(), limits)


def _parse_header(header: str) -> dict:
    limits = {}
    for line in header.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key in ("max_sentences", "max_chars", "min_chars"):
            try:
                limits[key] = int(value)
            except ValueError:
                pass
        elif key == "forbid":
            limits["forbid"] = [
                phrase.strip().strip('"').lower()
                for phrase in value.split(",")
                if phrase.strip()
            ]
    return limits

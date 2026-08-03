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
    <the prompt-facing spec text: structure rules + shape-only examples>

Everything after the closing --- is injected verbatim into the prompt.

The spec examples teach SHAPE ONLY. Every specific value in them is a bracketed
placeholder ([ACCOUNT], [FILE], …) rather than a name, filename, device or time,
because a small local model copies an example's specifics as readily as its
structure — which is how a demo scenario's fictional user ended up being reported
as the subject of a real disk image. GROUNDING is prepended to every prompt by
every engine to close the same hole from the other side, and PLACEHOLDER_TOKENS
are rejected by validate() so a model that echoes a placeholder is retried rather
than published.
"""

import os
import re
import sys

SURFACE_CASE_OVERVIEW = "case_overview"
SURFACE_PLAIN_TERMS = "plain_terms"
SURFACE_WHAT_IT_MEANS = "what_it_means"
SURFACE_REPORT_SECTION = "report_section"

# The placeholders the spec examples use in place of real values. They are
# forbidden in output: a model that emits one has copied the example's shape
# without substituting evidence, which validate() catches and retries.
PLACEHOLDER_TOKENS = [
    "[account]", "[file]", "[path]", "[device]", "[host]", "[address]",
    "[time]", "[date]", "[count]", "[size]", "[hash]", "[id]", "[tool]",
    "[artifact]", "[finding]", "[topic]", "[level]", "[protocol]",
]

# Prepended to EVERY prompt in every engine (report sections, the short
# surfaces, the deep dive). It lives in code rather than in a spec file because
# it is a correctness invariant, not a style choice: it must hold even if a spec
# file is edited, replaced, or missing entirely.
GROUNDING = (
    "GROUNDING — these override every other instruction:\n"
    "- Every account name, user name, file name, path, device, host, IP address, "
    "hash and timestamp you write MUST appear verbatim in the CASE DATA supplied "
    "below in this prompt. Copy it from there; do not reconstruct it from memory.\n"
    "- If the supplied case data does not establish one, say so plainly — for "
    "example \"the evidence does not establish which account performed this\" — "
    "and carry on with what it does establish. Never supply a plausible value, a "
    "typical value, a placeholder, or a value carried over from an example.\n"
    "- The examples in the format spec below demonstrate SHAPE ONLY. Their "
    "bracketed placeholders are not data. Never emit a bracketed placeholder, and "
    "never reuse any specific value that appeared in an example.\n"
    "- A fabricated identifier is a false statement in an evidence record. When "
    "you are unsure, name the gap instead of filling it."
)

_HEADER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# Phrases that mean the model narrated the data instead of writing the surface.
# Matched anywhere in the output. Applied to every surface on top of each spec's
# own forbid list.
_ALWAYS_FORBIDDEN = [
    "json", "array of", "objects with", "here is a breakdown",
    "here are the", "if you would like", "feel free to", "as an ai",
    "i cannot", "i can't", "sure!", "certainly!",
] + PLACEHOLDER_TOKENS

# Meta-commentary the model uses to *open* — describing the data or the task
# instead of writing the content ("The output appears to list…", "Here is the
# section:", "Based on the data provided…"). These are matched only against the
# START of the output, so a legitimate mid-sentence "…the value here is 482 MB"
# is never rejected. Applied to every surface; specs may add their own via a
# `forbid_opening:` header. Also drives strip_leading_meta().
FORBIDDEN_OPENINGS = [
    "the output appears", "the output shows", "the output is",
    "the output contains", "the data appears", "the data shows",
    "the data provided", "the provided data", "this data",
    "this section describes", "this section will", "this section provides",
    "this section covers", "in this section", "based on the data",
    "based on the provided", "based on the information", "based on the analysis",
    "here is", "here's", "here are", "below is", "below are", "the following",
    "i have", "i will", "let me", "as requested", "as an ai", "as an assistant",
    "it appears that", "the analysis appears", "sure,", "certainly", "of course",
]

_SENTENCE_BOUNDARY = re.compile(r"[.!?:\n]")


def strip_leading_meta(text: str) -> str:
    """Remove meta-commentary sentences a model prepends before the real
    content — "The output appears to list…", "Here is the section:" — and
    return the content that follows.

    A FORBIDDEN_OPENINGS phrase is matched only at the very start, then the text
    is cut at the first sentence or label boundary; this repeats so a stacked
    preamble ("Here is the report. The output shows…") is fully removed while
    the forensic prose is kept. Idempotent.
    """
    cleaned = (text or "").strip()
    for _ in range(6):
        lowered = cleaned.lower()
        if not any(lowered.startswith(opening) for opening in FORBIDDEN_OPENINGS):
            break
        boundary = _SENTENCE_BOUNDARY.search(cleaned)
        cleaned = cleaned[boundary.end():].strip() if boundary else ""
    return cleaned


# Identifiers a model must have copied from the case data rather than composed.
# Deliberately narrow: only shapes that are unambiguously an identifier, so a
# grounding check never fires on ordinary prose and forces a pointless retry.
_ACCOUNT_MENTION = re.compile(
    r"\bthe\s+([A-Za-z][A-Za-z0-9._\-]{1,30})\s+account\b", re.IGNORECASE)
_FILENAME = re.compile(
    r"\b([A-Za-z0-9][A-Za-z0-9 _\-]{0,40}\.(?:7z|zip|rar|gz|tar|docx?|xlsx?|pptx?|"
    r"pdf|exe|dll|sys|bat|ps1|vbs|db|sqlite|pcapng?|evtx|dat|hive|log|txt|csv|"
    r"jpe?g|png|eml|mbox|e01|raw|img|dd))\b", re.IGNORECASE)
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

# Words that legitimately follow "the ... account" without naming one.
_ACCOUNT_NON_NAMES = {
    "user", "same", "affected", "local", "domain", "built", "service", "system",
    "administrator", "guest", "relevant", "subject", "above", "only", "single",
    "signed", "one", "other", "another", "responsible",
}


def ungrounded_identifiers(text: str, source: str) -> list[str]:
    """Identifiers in `text` that do not appear in `source`.

    `source` is the case data the model was given. Anything an answer names that
    is not in there was composed rather than read, which in an evidence record is
    a fabrication — so callers feed the result back as a format violation and
    make the model rewrite the answer.

    Only account mentions, filenames and IPv4 addresses are checked: they are
    unambiguous, they are what the reported failure invented, and a narrow check
    that never false-fires is worth more than a broad one that makes every answer
    retry.
    """
    haystack = (source or "").lower()
    flagged, seen = [], set()

    def note(value, label):
        value = value.strip()
        if not value or value.lower() in seen:
            return
        if value.lower() in haystack:
            return
        seen.add(value.lower())
        flagged.append(f"{label} {value!r} does not appear in the case data")

    for match in _ACCOUNT_MENTION.finditer(text or ""):
        name = match.group(1)
        if name.lower() not in _ACCOUNT_NON_NAMES:
            note(name, "account")
    for match in _FILENAME.finditer(text or ""):
        note(match.group(1), "filename")
    for match in _IPV4.finditer(text or ""):
        note(match.group(0), "address")
    return flagged


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
        # Openings are matched against the start of the output only.
        self.forbidden_openings = FORBIDDEN_OPENINGS + limits.get(
            "forbid_opening", [])

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

        # Meta-commentary openings — checked at the start, so real prose that
        # merely contains one of these words mid-sentence is not penalised.
        for opening in self.forbidden_openings:
            if lowered.startswith(opening):
                violations.append(f"meta-commentary opening: {opening!r}")
                break

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
        elif key in ("forbid", "forbid_opening"):
            limits[key] = [
                phrase.strip().strip('"').lower()
                for phrase in value.split(",")
                if phrase.strip()
            ]
    return limits

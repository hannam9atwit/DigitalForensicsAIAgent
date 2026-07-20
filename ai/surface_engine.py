"""
ai/surface_engine.py

Generates the app's short LLM surfaces: the case overview paragraph, the
"in plain terms" rail text, and the per-artifact / per-event "what it means"
note. (The long-form report lives in refinement_engine.py.)

Every surface follows the same contract:

    deterministic text  →  shown instantly by the UI
    LLM generation      →  format spec loaded from formats/, output validated,
                           one retry with the violations fed back
    fallback            →  the deterministic text, when no LLM or both
                           attempts fail validation

So the UI never blocks and never shows an unformatted or empty surface. The
spec files in formats/ own the output shape — swap a file, the AI conforms.
"""

import json
import urllib.error
import urllib.request

from ai import format_library
from core import ollama_runtime

_GENERATE_TIMEOUT_S = 90
_RETRY_LIMIT = 1

_PERSONA = (
    "You are a digital forensics examiner writing product copy inside an "
    "investigation console. Write ONLY the requested text — no preamble, no "
    "markdown headings, no commentary about the task or the data format."
)


class SurfaceEngine:
    """Stateless generator for the short LLM surfaces.

    `ai_config` carries the user's engine choice:
        provider  — "ollama" | "anthropic" | "none"
        model     — ollama model name (default llama3.2:3b)
        api_key   — anthropic key, held in memory only
    """

    def __init__(self, ai_config: dict | None = None):
        config = ai_config or {}
        self.provider = config.get("provider", "ollama")
        self.model = config.get("model", ollama_runtime.DEFAULT_MODEL)
        self.api_key = config.get("api_key", "")

    # ── Public surfaces ──────────────────────────────────────────────────────

    def case_overview(self, case: dict, fallback: str) -> str:
        context = self._case_context(case)
        prompt = (
            "Write the case overview paragraph for this investigation.\n\n"
            f"CASE DATA:\n{context}"
        )
        return self._generate(format_library.SURFACE_CASE_OVERVIEW, prompt, fallback)

    def plain_terms(self, subject: str, detail: str, case: dict, fallback: str) -> str:
        prompt = (
            f"Explain this for a non-technical reader: {subject}\n\n"
            f"KNOWN FACTS:\n{detail}\n\n"
            f"CASE CONTEXT:\n{self._case_context(case, brief=True)}"
        )
        return self._generate(format_library.SURFACE_PLAIN_TERMS, prompt, fallback)

    def what_it_means(self, artifact: dict, case: dict, fallback: str) -> str:
        facts = json.dumps(
            {key: artifact.get(key) for key in
             ("name", "kindLabel", "size", "plain", "role", "intake")
             if artifact.get(key)},
            ensure_ascii=False)
        prompt = (
            "State what this artifact tells the investigation.\n\n"
            f"ARTIFACT:\n{facts}\n\n"
            f"CASE CONTEXT:\n{self._case_context(case, brief=True)}"
        )
        return self._generate(format_library.SURFACE_WHAT_IT_MEANS, prompt, fallback)

    # ── Generation core ──────────────────────────────────────────────────────

    def available(self) -> bool:
        if self.provider == "anthropic":
            return bool(self.api_key)
        if self.provider == "ollama":
            return ollama_runtime.server_running()
        return False

    def _generate(self, surface: str, prompt: str, fallback: str) -> str:
        spec = format_library.load(surface)
        if spec is None or not self.available():
            return fallback

        full_prompt = f"{_PERSONA}\n\n{spec.prompt_text}\n\nTASK:\n{prompt}\n\nTEXT:"

        attempt_prompt = full_prompt
        for _ in range(1 + _RETRY_LIMIT):
            text = self._call_llm(attempt_prompt)
            if text is None:
                return fallback

            text = _strip_wrapping(text)
            violations = spec.validate(text)
            if not violations:
                return text

            attempt_prompt = (
                f"{full_prompt}\n\nYour previous attempt violated the format: "
                f"{'; '.join(violations)}. Rewrite it correctly. TEXT:"
            )

        return fallback

    def _call_llm(self, prompt: str) -> str | None:
        try:
            if self.provider == "anthropic" and self.api_key:
                return self._call_anthropic(prompt)
            return self._call_ollama(prompt)
        except (urllib.error.URLError, OSError, ValueError, KeyError):
            return None

    def _call_ollama(self, prompt: str) -> str:
        payload = json.dumps({
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.15, "num_predict": 300},
        }).encode("utf-8")
        request = urllib.request.Request(
            f"{ollama_runtime.OLLAMA_HOST}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=_GENERATE_TIMEOUT_S) as response:
            body = json.loads(response.read().decode("utf-8"))
        return body.get("response", "")

    def _call_anthropic(self, prompt: str) -> str:
        payload = json.dumps({
            "model": "claude-sonnet-4-5",
            "max_tokens": 400,
            "messages": [{"role": "user", "content": prompt}],
        }).encode("utf-8")
        request = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=_GENERATE_TIMEOUT_S) as response:
            body = json.loads(response.read().decode("utf-8"))
        parts = body.get("content", [])
        return "".join(p.get("text", "") for p in parts if p.get("type") == "text")

    # ── Context building ─────────────────────────────────────────────────────

    def _case_context(self, case: dict, brief: bool = False) -> str:
        meta = case.get("caseMeta", {})
        lines = [
            f"Case: {meta.get('title', 'Untitled')} ({meta.get('id', '—')})",
            f"Risk: {meta.get('riskLabel', '—')} ({meta.get('riskScore', '—')})",
        ]

        findings = case.get("findings", [])
        if findings:
            lines.append("Findings:")
            for finding in findings if not brief else findings[:4]:
                lines.append(
                    f"  - [{finding.get('sev', '?')}] {finding.get('title', '')}: "
                    f"{finding.get('short', '')}")

        if not brief:
            evidence = case.get("evidence", [])
            if evidence:
                lines.append("Evidence:")
                for artifact in evidence:
                    lines.append(
                        f"  - {artifact.get('name', '')} "
                        f"({artifact.get('kindLabel', '')}, {artifact.get('size', '')})")

        return "\n".join(lines)


def _strip_wrapping(text: str) -> str:
    """Remove quote marks, code fences, and leading labels models add."""
    cleaned = text.strip().strip("`").strip()
    if cleaned.startswith('"') and cleaned.endswith('"'):
        cleaned = cleaned[1:-1].strip()
    for label in ("TEXT:", "OUTPUT:", "PARAGRAPH:"):
        if cleaned.upper().startswith(label):
            cleaned = cleaned[len(label):].strip()
    return cleaned

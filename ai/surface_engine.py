"""
ai/surface_engine.py

Generates the app's interactive LLM surfaces: the case overview paragraph,
the "in plain terms" rail text, the per-artifact "what it means" note, and
the "Ask the AI" case-scoped answers. (The long-form report lives in
refinement_engine.py.)

Providers: Ollama (local, default), Anthropic, OpenAI, and Gemini — all
through the same stdlib-urllib path so no SDK dependencies are dragged in.
Cloud keys are held in memory only.

Every surface follows the same contract:

    deterministic text  →  shown instantly by the UI
    LLM generation      →  format spec loaded from formats/, output validated,
                           one retry with the violations fed back
    fallback            →  the deterministic text, when no LLM or both
                           attempts fail validation

So the UI never blocks and never shows an unformatted or empty surface. The
spec files in formats/ own the output shape — swap a file, the AI conforms.
"""

import re
import json
import urllib.error
import urllib.request

from ai import format_library
from core import ollama_runtime

_CLOUD_DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-5",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.0-flash",
}

_GENERATE_TIMEOUT_S = 90
_RETRY_LIMIT = 1

_PERSONA = (
    "You are a digital forensics examiner writing product copy inside an "
    "investigation console. Write ONLY the requested text — no preamble, no "
    "markdown headings, no commentary about the task or the data format. Begin "
    "with the content itself; never open with meta-commentary such as 'The "
    "output appears', 'The data shows', 'Here is', 'This section describes', or "
    "'Based on the data provided'. State the substance, not a description of it."
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
        self.cloud_model = _CLOUD_DEFAULT_MODELS.get(self.provider, "")

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

    def ask(self, question: str, case: dict) -> dict | None:
        """Answer an examiner's question from the case knowledge base.

        Retrieves the digested entries most relevant to the question and answers
        from those plus the findings index — never by re-reasoning over raw
        events — and cites the source artifacts/findings. When the deep dive is
        still incomplete, it answers from what exists and says what has not been
        analysed yet.

        Returns {"paras", "uncertain", "chips"} for the chat bubble, or None
        only when no engine is reachable or the model genuinely returns nothing.
        Interactive chat stays lenient: the answer is cleaned rather than
        rejected on a format slip, and SOURCES are seeded from the retrieved
        entries when the model omits them.
        """
        if not self.available():
            return None

        from ai import knowledge_base as kb_mod
        knowledge = kb_mod.KnowledgeBase.from_list(case.get("knowledge_base", []))
        entries = (knowledge.retrieve(question, k=6, embed_fn=self.embed)
                   if len(knowledge) else [])
        incomplete = self._dive_incomplete(case, knowledge)

        spec = format_library.load("ask_answer")
        spec_text = spec.prompt_text if spec else _ASK_FALLBACK_GUIDE

        context = [f"CASE: {case.get('caseMeta', {}).get('title', '')}"]
        if entries:
            context.append("ANALYSED FINDINGS — reason from these and cite their "
                           "IDs:\n" + _format_kb_entries(entries))
        context.append("FINDINGS INDEX:\n" + self._findings_index(case))
        if incomplete:
            context.append("NOTE: the deep analysis is still in progress; some "
                           "artifacts may not be digested yet. Answer from what "
                           "is available and state plainly what has not been "
                           "analysed.")
        prompt = (f"QUESTION: {question}\n\n" + "\n\n".join(context))
        full_prompt = f"{_PERSONA}\n\n{spec_text}\n\nTASK:\n{prompt}\n\nTEXT:"

        text = self._call_llm(full_prompt)
        if text is None:
            return None
        text = _strip_wrapping(text)
        self._last_entries = entries        # so _parse_answer can seed sources
        self._last_incomplete = incomplete
        if len(text.strip()) < 15:
            return None  # genuinely empty / broken response

        return self._parse_answer(text, case)

    def _parse_answer(self, text: str, case: dict) -> dict:
        """Split the model's answer into paragraphs, an optional UNCERTAIN
        note, and validated SOURCES chips.

        Formatting the model added (markdown bold, bullets, dashes) is cleaned
        here rather than rejected upstream, so a real answer always reaches the
        user. SOURCES and UNCERTAIN are honored if present but not required.
        """
        uncertain = ""
        source_ids = []
        body_lines = []

        for line in text.splitlines():
            stripped = line.strip()
            upper = stripped.upper()
            if upper.startswith("UNCERTAIN:"):
                uncertain = _clean_line(stripped[len("UNCERTAIN:"):].strip())
            elif upper.startswith("SOURCES:"):
                source_ids = [s.strip().upper()
                              for s in stripped[len("SOURCES:"):].split(",")
                              if s.strip()]
            else:
                body_lines.append(line)

        paras = [_clean_line(p.strip())
                 for p in "\n".join(body_lines).split("\n\n") if p.strip()]

        known_evidence = {e.get("id"): e for e in case.get("evidence", [])}
        known_findings = {f.get("id") for f in case.get("findings", [])}

        # Seed the cited sources from the retrieved knowledge-base entries when
        # the model named none, so an answer built from digested evidence always
        # points back to the artifacts it rests on.
        if not source_ids:
            for entry in getattr(self, "_last_entries", []) or []:
                source_ids.extend(entry.get("artifact_ids", []))
                source_ids.extend(entry.get("finding_ids", []))

        chips, seen = [], set()
        for source_id in [s.upper() for s in source_ids]:
            if source_id in seen:
                continue
            seen.add(source_id)
            if source_id in known_evidence:
                name = known_evidence[source_id].get("name", source_id)
                chips.append((f"{source_id} · {name}", source_id))
            elif source_id in known_findings:
                chips.append((source_id, source_id))

        # When the dive is still running, name that honestly rather than letting
        # a partial answer read as complete.
        if getattr(self, "_last_incomplete", False) and not uncertain:
            uncertain = ("The deep analysis is still running, so some artifacts "
                         "may not be reflected in this answer yet.")

        return {"paras": paras, "uncertain": uncertain, "chips": chips[:6]}

    # ── knowledge-base helpers ─────────────────────────────────────────────────

    def _findings_index(self, case):
        findings = case.get("findings", [])
        if not findings:
            return "No findings were recorded."
        return "\n".join(
            f"- {f.get('id', '')} [{f.get('sev', '')}] {f.get('title', '')}: "
            f"{f.get('short', '')}" for f in findings[:40])

    def _dive_incomplete(self, case, knowledge):
        """True while the knowledge base is still being built — used to answer
        honestly on partial results. Complete once the case-level synthesis has
        landed (the last thing the dive writes)."""
        from ai import knowledge_base as kb_mod
        if len(knowledge) == 0:
            return True
        return knowledge.slot(kb_mod.TOPIC_CONCLUSION) is None

    # ── Generation core ──────────────────────────────────────────────────────

    def available(self) -> bool:
        if self.provider == "ollama":
            return ollama_runtime.server_running()
        if self.provider in _CLOUD_DEFAULT_MODELS:
            return bool(self.api_key)
        return False

    def complete(self, prompt: str):
        """Raw completion for callers that build their own prompt and validate
        their own output (the deep dive). Returns the model's text, or None when
        no engine is reachable — the signal the dive uses to degrade honestly."""
        if not self.available():
            return None
        return self._call_llm(prompt)

    def embed(self, texts):
        """Embed a list of strings via the local Ollama embeddings endpoint, for
        semantic retrieval. Returns a list of vectors, or None when no embedding
        model is available — callers fall back to lexical retrieval. Ollama
        only; cloud embedding is out of scope for the offline-first path."""
        if self.provider != "ollama":
            return None
        return ollama_runtime.embed(texts)

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
        callers = {
            "anthropic": self._call_anthropic,
            "openai": self._call_openai,
            "gemini": self._call_gemini,
        }
        try:
            if self.provider in callers and self.api_key:
                return callers[self.provider](prompt)
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
            "model": self.cloud_model,
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

    def _call_openai(self, prompt: str) -> str:
        payload = json.dumps({
            "model": self.cloud_model,
            "max_tokens": 700,
            "messages": [{"role": "user", "content": prompt}],
        }).encode("utf-8")
        request = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=_GENERATE_TIMEOUT_S) as response:
            body = json.loads(response.read().decode("utf-8"))
        choices = body.get("choices", [])
        if not choices:
            raise ValueError("OpenAI returned no choices")
        return choices[0].get("message", {}).get("content", "")

    def _call_gemini(self, prompt: str) -> str:
        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 700, "temperature": 0.15},
        }).encode("utf-8")
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{self.cloud_model}:generateContent")
        request = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=_GENERATE_TIMEOUT_S) as response:
            body = json.loads(response.read().decode("utf-8"))
        candidates = body.get("candidates", [])
        if not candidates:
            raise ValueError("Gemini returned no candidates")
        parts = candidates[0].get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in parts)

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
    """Remove quote marks, code fences, leading labels, and any leading
    meta-commentary the model adds before the content."""
    cleaned = text.strip().strip("`").strip()
    if cleaned.startswith('"') and cleaned.endswith('"'):
        cleaned = cleaned[1:-1].strip()
    for label in ("TEXT:", "OUTPUT:", "PARAGRAPH:"):
        if cleaned.upper().startswith(label):
            cleaned = cleaned[len(label):].strip()
    # Drop meta-commentary openings ("The output appears…", "Here is…") so the
    # surface leads with the content, and a merely-preambled answer is cleaned
    # rather than rejected. Same stripper the report path uses.
    return format_library.strip_leading_meta(cleaned)


def _format_kb_entries(entries):
    """Render retrieved knowledge-base entries as compact, citable context —
    each carries the artifact/finding IDs it derives from, so the model can
    cite them and the answer stays grounded."""
    lines = []
    for entry in entries:
        ids = entry.get("artifact_ids", []) + entry.get("finding_ids", [])
        tag = f"[{', '.join(ids)}] " if ids else ""
        lines.append(f"- {tag}{entry.get('title', '')}: {entry.get('answer', '')}")
    return "\n".join(lines)


_ASK_FALLBACK_GUIDE = (
    "Answer the examiner's question using only the case data provided, in one "
    "to three short plain-language paragraphs. If the data can't answer it, say "
    "so and name what evidence would. You may end with a line 'SOURCES: <ids>' "
    "listing the artifact or finding IDs your answer used."
)

_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")
_MD_BULLET = re.compile(r"^\s*[-*•]\s+", re.MULTILINE)


def _clean_line(text: str) -> str:
    """Normalize model formatting for display: unwrap bold, drop bullet marks,
    replace dashes with plain punctuation. Keeps the words, loses the markup —
    so a well-meaning but markdown-happy local model still reads cleanly."""
    cleaned = _MD_BOLD.sub(r"\1", text)
    cleaned = _MD_BULLET.sub("", cleaned)
    cleaned = cleaned.replace(" — ", ", ").replace("—", ", ")
    cleaned = cleaned.replace("`", "").replace("#", "")
    return cleaned.strip()

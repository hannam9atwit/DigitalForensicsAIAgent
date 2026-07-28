"""
ai/knowledge_base.py

The case knowledge base: structured, digested facts the AI reasons FROM, instead
of re-reasoning over tens of thousands of raw events at question time.

Each entry is a small structured record — never a prose blob — so it can be
searched, cited, and rendered partially:

    {
      "topic":        stable id, e.g. "network:dominant_hosts",
      "title":        human label, e.g. "Dominant hosts",
      "answer":       the model's digested finding (validated, cleaned),
      "artifact_ids": ["EV-01"],   the evidence it derives from,
      "finding_ids":  ["F-03"],    the findings it derives from,
      "confidence":   "high" | "medium" | "low",
      "layer":        1 | 2 | 3,   which pass produced it,
      "generated_at": timestamp,
    }

Retrieval is offline-first and dependency-free: lexical token overlap between a
question and each entry, boosted when the question names an artifact or finding
id. An optional embedding hook (Ollama /api/embeddings, when a model is present)
blends semantic similarity on top; without it, lexical stands alone — so answers
never depend on a model that may not be installed.

Pure data + text: no Qt, no network, so it unit-tests headless and the network
call lives in the caller that owns the embedding hook.
"""

import re
import math

# Confidence + layer are small closed vocabularies; keep them here so callers
# and the format spec agree on the words.
CONFIDENCE_LEVELS = ("high", "medium", "low")
LAYER_PER_ARTIFACT = 1
LAYER_CROSS_ARTIFACT = 2
LAYER_SYNTHESIS = 3

# Synthesis topics the consuming surfaces read by name (see ai/deep_dive.py).
TOPIC_EXECUTIVE_SUMMARY = "synthesis:executive_summary"
TOPIC_CONCLUSION = "synthesis:conclusion"
TOPIC_FINDINGS_ASSESSMENT = "synthesis:findings_assessment"
TOPIC_CASE_NARRATIVE = "synthesis:case_narrative"
TOPIC_CASE_OVERVIEW = "synthesis:case_overview"

_TOKEN = re.compile(r"[a-z0-9]+(?:[-_.][a-z0-9]+)*")
_ID = re.compile(r"\b(?:EV|F)-\d+\b", re.IGNORECASE)

# Small closed stopword set — enough to stop "the/what/was" dominating overlap
# without a linguistics dependency.
_STOPWORDS = {
    "the", "and", "for", "was", "were", "are", "any", "did", "does", "what",
    "when", "where", "which", "who", "why", "how", "this", "that", "these",
    "those", "from", "into", "with", "have", "has", "had", "been", "being",
    "you", "your", "our", "its", "his", "her", "their", "them", "they",
    "there", "here", "about", "over", "under", "than", "then", "some", "all",
    "can", "could", "would", "should", "may", "might", "will", "shall",
    "not", "but", "out", "off", "per", "via", "get", "got",
}


def make_entry(topic, title, answer, layer, artifact_ids=None, finding_ids=None,
               confidence="medium", generated_at=""):
    """Build a validated knowledge-base entry dict."""
    conf = str(confidence).lower().strip()
    if conf not in CONFIDENCE_LEVELS:
        conf = "medium"
    return {
        "topic":        topic,
        "title":        title,
        "answer":       (answer or "").strip(),
        "artifact_ids": list(artifact_ids or []),
        "finding_ids":  list(finding_ids or []),
        "confidence":   conf,
        "layer":        int(layer),
        "generated_at": generated_at,
    }


def _tokens(text):
    return [t for t in _TOKEN.findall((text or "").lower())
            if len(t) >= 3 and t not in _STOPWORDS]


def _cosine(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class KnowledgeBase:
    """Ordered collection of digested entries with search and slot lookup.

    Persistence is trivial: entries are plain JSON-native dicts, so the whole
    KB round-trips through the case file with to_list()/from_list().
    """

    def __init__(self, entries=None):
        self.entries = [dict(e) for e in (entries or [])]

    # ── persistence ─────────────────────────────────────────────────────────

    @classmethod
    def from_list(cls, data):
        return cls(data if isinstance(data, list) else [])

    def to_list(self):
        return [dict(e) for e in self.entries]

    # ── population ──────────────────────────────────────────────────────────

    def add(self, entry):
        if isinstance(entry, dict) and entry.get("answer"):
            self.entries.append(entry)

    def has(self, layer, topic, artifact_id=None):
        """True if an entry for this (layer, topic[, artifact]) already exists —
        the resume check that lets a re-started dive skip finished prompts."""
        for e in self.entries:
            if e.get("layer") == layer and e.get("topic") == topic and (
                    artifact_id is None or artifact_id in e.get("artifact_ids", [])):
                return True
        return False

    # ── access ──────────────────────────────────────────────────────────────

    def by_layer(self, layer):
        return [e for e in self.entries if e.get("layer") == layer]

    def slot(self, topic):
        """The most recent entry for a synthesis topic, or None. Layer-3 writes
        one entry per slot; the last wins so a re-synthesis supersedes."""
        for e in reversed(self.entries):
            if e.get("topic") == topic:
                return e
        return None

    def slot_text(self, topic):
        entry = self.slot(topic)
        return entry.get("answer", "") if entry else ""

    def __len__(self):
        return len(self.entries)

    # ── retrieval ─────────────────────────────────────────────────────────────

    def retrieve(self, question, k=6, embed_fn=None):
        """Return the up-to-k entries most relevant to `question`.

        Lexical overlap (question tokens vs. each entry's title+topic+answer),
        with a strong boost when the question names an artifact/finding id and a
        small nudge toward layer-3 synthesis for broad questions. When embed_fn
        is supplied it blends cosine similarity on top; any embedding failure
        silently leaves lexical in charge. With no lexical hit at all, the
        case-level synthesis is returned as general context rather than nothing.
        """
        if not self.entries:
            return []

        q_tokens = set(_tokens(question))
        q_ids = {m.upper() for m in _ID.findall(question or "")}

        scored = []
        for entry in self.entries:
            text = f"{entry.get('title', '')} {entry.get('topic', '')} " \
                   f"{entry.get('answer', '')}"
            e_tokens = set(_tokens(text))
            overlap = len(q_tokens & e_tokens)
            score = overlap / (1.0 + math.log(1 + len(e_tokens)))
            entry_ids = {i.upper() for i in
                         entry.get("artifact_ids", []) + entry.get("finding_ids", [])}
            if q_ids & entry_ids:
                score += 3.0
            if entry.get("layer") == LAYER_SYNTHESIS:
                score += 0.25
            scored.append([score, entry])

        if embed_fn is not None:
            self._blend_embeddings(question, scored, embed_fn)

        scored.sort(key=lambda s: s[0], reverse=True)
        hits = [entry for score, entry in scored if score > 0][:k]
        if hits:
            return hits
        # Nothing matched — hand back the case narrative as general grounding.
        synthesis = self.by_layer(LAYER_SYNTHESIS)
        return synthesis[:k] if synthesis else [e for _s, e in scored[:k]]

    def _blend_embeddings(self, question, scored, embed_fn):
        """Add cosine similarity to each score. embed_fn(list[str]) -> list[vec];
        the first vector is the question's. Best-effort: on any shape mismatch or
        error, scores are left untouched and lexical alone decides."""
        try:
            texts = [f"{entry.get('title', '')}. {entry.get('answer', '')}"
                     for _score, entry in scored]
            vectors = embed_fn([question] + texts)
            if not vectors or len(vectors) != len(texts) + 1:
                return
            question_vec = vectors[0]
            for index, (score, entry) in enumerate(scored):
                scored[index][0] = score + 2.0 * _cosine(question_vec,
                                                         vectors[index + 1])
        except Exception:  # noqa: BLE001 — retrieval must never raise
            return

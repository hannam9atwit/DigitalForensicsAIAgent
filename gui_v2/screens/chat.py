"""
gui_v2/screens/chat.py

Ask the AI — an assistant scoped to the current case.

Three design rules do the real work here, and all three are about trust:

  * Every answer cites the artifacts it came from, and the citations are
    clickable through to the evidence. An uncited answer is an opinion.
  * Uncertainty is shown, not hidden. The uncertainty callout is part of the
    answer shape, so a model that is unsure looks unsure.
  * It is obvious this runs locally. Offline operation is a hard product
    requirement, so the header states the engine rather than implying it.

The canned demo answers remain as the quality bar and the offline fallback:
when an AI engine is configured and reachable the question goes to it (scoped
to this case's data); when none is, suggested demo questions still answer from
the fixtures so the screen demonstrates itself.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QWidget, QFrame, QLineEdit, QSizePolicy,
)

from .. import theme, widgets as w
from ..content import SUGGESTED, ANSWERS, FALLBACK_ANSWER, RAIL_STATIC
from ..rail import RailPayload
from .base import Screen

P = theme.GUIDED


def _text_width(text, size):
    """Pixel width of `text` at the body face, for sizing bubbles to content."""
    from PySide6.QtGui import QFont, QFontMetricsF
    f = QFont()
    f.setFamilies([theme.SANS, "Segoe UI"])
    f.setPixelSize(int(round(size)))
    return int(QFontMetricsF(f).horizontalAdvance(str(text)))


class ChatScreen(Screen):
    id = "chat"

    asked = Signal(str)   # so the window can log the question to the audit trail

    def __init__(self, case, parent=None):
        super().__init__(case, parent)
        self.msgs = []
        self.thinking = False
        self._ai_job = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        host, lay = w.page(max_width=760)
        root.addWidget(w.scroll_area(host))
        self._page_lay = lay

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(10)
        head.addWidget(w.label("Ask the AI", size=19, weight=theme.W_SEMIBOLD))
        self._engine_pill = w.Pill("LOCAL MODEL · OFFLINE")
        head.addWidget(self._engine_pill)
        head.addStretch(1)
        lay.addLayout(head)

        lay.addWidget(w.body(
            "Scoped to this case only. Every answer cites the artifacts it came "
            "from — click a citation to see the evidence yourself.",
            size=13, color=P["text2"]))

        self._thread_host = QWidget()
        self._thread = QVBoxLayout(self._thread_host)
        self._thread.setContentsMargins(0, 0, 0, 0)
        self._thread.setSpacing(12)
        lay.addWidget(self._thread_host)

        lay.addStretch(1)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Ask about this case…")
        self._input.returnPressed.connect(self._send)
        row.addWidget(self._input, 1)
        row.addWidget(w.primary_button("Ask", self._send))
        lay.addLayout(row)

        lay.addWidget(w.body(
            "Answers are drafted by the local model from this case's evidence only. "
            "Nothing is sent to the cloud. Questions and answers are recorded in the "
            "audit trail.",
            size=11, color=P["text3"], lh=1.45))

        self._render()

    # ── thread ────────────────────────────────────────────────────────────────

    def on_show(self, arg=None):
        super().on_show(arg)
        self._engine_pill.setText(self._engine_label())

    def _engine_label(self):
        config = self.ai_config or {}
        provider = config.get("provider", "ollama")
        if provider == "ollama":
            return f"LOCAL MODEL · {config.get('model', 'llama3.2')} · OFFLINE"
        if provider == "none":
            return "RULE-BASED · NO AI"
        return f"CLOUD · {provider.upper()} · KEY IN MEMORY"

    def _render(self):
        w.clear_layout(self._thread)
        if not self.msgs and not self.thinking:
            self._thread.addWidget(self._suggestions())
            return

        for m in self.msgs:
            self._thread.addWidget(
                self._user_bubble(m["text"]) if m["user"] else self._ai_bubble(m))

        if self.thinking:
            self._thread.addWidget(self._ghost())

    def _suggestions(self):
        box = w.Card(pad=16, spacing=8)
        box.head("NOT SURE WHAT TO ASK?")
        for i, q in enumerate(SUGGESTED):
            b = w.link_button(f"→  {q}", lambda idx=i: self.ask(SUGGESTED[idx], idx))
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            box.add(b)
        return box

    def _user_bubble(self, text):
        wrap = QWidget()
        h = QHBoxLayout(wrap)
        h.setContentsMargins(0, 0, 0, 0)
        h.addStretch(1)
        bub = QFrame()
        bub.setObjectName("bubbleUser")
        bub.setMaximumWidth(480)
        # A word-wrapped rich-text label reports a narrow preferred width, so a
        # one-line question would otherwise be squeezed into a tall column.
        # Size the bubble to the text, capped at the design's max.
        bub.setMinimumWidth(min(480, _text_width(text, 12.5) + 34))
        v = QVBoxLayout(bub)
        v.setContentsMargins(14, 10, 14, 10)
        v.addWidget(w.body(text, size=12.5, weight=theme.W_REGULAR,
                           color="#FFFFFF", lh=1.45))
        h.addWidget(bub)
        return wrap

    def _ai_bubble(self, m):
        wrap = QWidget()
        h = QHBoxLayout(wrap)
        h.setContentsMargins(0, 0, 0, 0)
        bub = QFrame()
        bub.setObjectName("bubbleAi")
        bub.setMaximumWidth(620)
        # Multi-paragraph answers need room; without a floor the wrapped labels
        # collapse the card into a narrow column.
        bub.setMinimumWidth(560)
        v = QVBoxLayout(bub)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(10)

        for para in m["paras"]:
            v.addWidget(w.body(para, size=13, lh=1.6))

        if m.get("uncertain"):
            v.addWidget(w.Callout(
                f"<b>Where I'm uncertain:</b> {m['uncertain']}"))

        if m.get("chips"):
            v.addWidget(w.micro_label("SOURCES"))
            row = QWidget()
            rh = QHBoxLayout(row)
            rh.setContentsMargins(0, 0, 0, 0)
            rh.setSpacing(6)
            for label_text, ref in m["chips"]:
                rh.addWidget(w.chip_button(
                    label_text, lambda r=ref: self._goto(r)))
            rh.addStretch(1)
            v.addWidget(row)

        h.addWidget(bub)
        h.addStretch(1)
        return wrap

    def _ghost(self):
        wrap = QWidget()
        h = QHBoxLayout(wrap)
        h.setContentsMargins(0, 0, 0, 0)
        bub = QFrame()
        bub.setObjectName("bubbleAi")
        v = QVBoxLayout(bub)
        v.setContentsMargins(16, 12, 16, 12)
        v.addWidget(w.label("Reading the case evidence…", size=12.5,
                            color=P["text3"]))
        h.addWidget(bub)
        h.addStretch(1)
        return wrap

    # ── behaviour ─────────────────────────────────────────────────────────────

    def _send(self):
        text = self._input.text().strip()
        if not text or self.thinking:
            return
        idx = next((i for i, s in enumerate(SUGGESTED)
                    if s.lower() == text.lower()), -1)
        self.ask(text, idx)

    def ask(self, text, idx=-1):
        self.msgs.append({"user": True, "text": text})
        self._input.clear()
        self.thinking = True
        self._render()
        self.asked.emit(text)

        from ..ai_worker import SurfaceJob
        job = SurfaceJob(self.ai_config or {})
        job.answer_ready.connect(
            lambda _token, answer, i=idx: self._answer(answer, i))
        self._ai_job = job
        job.run("ask", token="ask", fallback="",
                question=text, case=self.case)

    def _answer(self, ai_answer, idx):
        """Prefer the model's answer; fall back to the demo fixtures for
        suggested questions, and to an honest capability note otherwise."""
        if ai_answer and ai_answer.get("paras"):
            answer = ai_answer
        elif 0 <= idx < len(ANSWERS):
            answer = ANSWERS[idx]
        else:
            answer = FALLBACK_ANSWER
        self.msgs.append({
            "user": False, "paras": list(answer["paras"]),
            "uncertain": answer.get("uncertain", ""),
            "chips": list(answer.get("chips", [])),
        })
        self.thinking = False
        self._render()

    def _goto(self, ref):
        if ref == "TL":
            self.navigate.emit("timeline", "Jun 3 19:18:47")
        elif ref.startswith("F-"):
            self.navigate.emit("findings", ref)
        else:
            self.navigate.emit("evidence", ref)

    def rail(self) -> RailPayload:
        title, blocks, steps = RAIL_STATIC["chat"]
        return RailPayload(title, list(blocks), list(steps))

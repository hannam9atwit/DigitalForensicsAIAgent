"""
gui_v2/rail.py

The explainer rail: a persistent 292px panel on the right that always answers
the product's three questions — what is this, why am I seeing it, what should I
do about it.

It is the signature feature of the design, so it is deliberately dumb: it holds
no state and knows nothing about screens. Whichever screen owns the current
selection pushes a RailPayload at it, and it re-renders. That keeps "the rail
updates on every selection change anywhere in the app" a property of one code
path instead of a rule every screen has to remember.
"""

from dataclasses import dataclass, field
from typing import Callable, List, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QWidget, QLabel

from . import theme, widgets as w
from .content import RAIL_FOOTER

P = theme.GUIDED

RAIL_WIDTH = 292


@dataclass
class RailPayload:
    """Everything the rail can show.

    blocks : [(HEADING, text)] — the what/why explanation
    steps  : ["do this", …]    — the "WHAT SHOULD I DO?" checklist
    chips  : [(label, ref)]    — navigation chips; `ref` is resolved by the
                                 window, so the rail never imports a screen
    """
    title: str = ""
    blocks: List[Tuple[str, str]] = field(default_factory=list)
    steps: List[str] = field(default_factory=list)
    chips: List[Tuple[str, str]] = field(default_factory=list)
    chip_head: str = "SEE THE EVIDENCE"


class ExplainerRail(QFrame):
    """Right-hand rail. Emits chip_clicked(ref) when a chip is pressed, and
    ask_submitted(question) when the user uses the inline mini-chat."""

    chip_clicked = Signal(str)
    ask_submitted = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("rail")
        self.setFixedWidth(RAIL_WIDTH)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # header — rounded "?" mark plus the payload title
        header = QWidget()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 14, 16, 12)
        hl.setSpacing(9)
        mark = QLabel("?")
        mark.setFixedSize(22, 22)
        mark.setAlignment(Qt.AlignCenter)
        mark.setStyleSheet(
            f"background: {P['accentTint']}; color: {P['accent']}; "
            f"border-radius: 6px; font-weight: 700; font-size: 12px;")
        self._title = w.label("", size=13, weight=theme.W_SEMIBOLD, wrap=True)
        hl.addWidget(mark)
        hl.addWidget(self._title, 1)
        root.addWidget(header)
        root.addWidget(w.hline(P["line"]))

        # body — rebuilt on every payload
        self._body_host = QWidget()
        self._body_host.setObjectName("railBody")
        self._body = QVBoxLayout(self._body_host)
        self._body.setContentsMargins(16, 14, 16, 14)
        self._body.setSpacing(14)
        root.addWidget(w.scroll_area(self._body_host), 1)

        # footer — states the rail's contract, always visible
        root.addWidget(w.hline(P["line"]))
        foot = QWidget()
        fl = QVBoxLayout(foot)
        fl.setContentsMargins(16, 10, 16, 12)
        fl.addWidget(w.body(RAIL_FOOTER, size=11, color=P["text3"], lh=1.45))
        root.addWidget(foot)

        self.set_payload(RailPayload())

    # ── rendering ─────────────────────────────────────────────────────────────

    def set_payload(self, payload: RailPayload):
        self._title.setText(payload.title or "")
        w.clear_layout(self._body)

        for head, text in payload.blocks:
            self._body.addWidget(self._block(head, text))

        if payload.steps:
            self._body.addWidget(self._checklist(payload.steps))

        if payload.chips:
            self._body.addWidget(self._chip_row(payload.chip_head, payload.chips))

        self._body.addWidget(self._mini_chat())
        self._body.addStretch(1)

    def _mini_chat(self):
        """A compact 'ask the model about this' box, present on every screen
        that shows the rail. Answers appear inline; the heavy lifting is the
        same async ask path the full chat screen uses."""
        from PySide6.QtWidgets import QLineEdit, QPushButton
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 8, 0, 0)
        v.setSpacing(6)
        v.addWidget(w.micro_label("ASK ABOUT THIS", color=P["accent"]))

        self._mini_answer = w.body("", size=12, color=P["text2"], lh=1.5)
        self._mini_answer.setVisible(False)
        v.addWidget(self._mini_answer)

        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        self._mini_input = QLineEdit()
        self._mini_input.setPlaceholderText("Ask the model…")
        self._mini_input.returnPressed.connect(self._mini_send)
        h.addWidget(self._mini_input, 1)
        send = QPushButton("Ask")
        send.setObjectName("primary")
        send.clicked.connect(self._mini_send)
        h.addWidget(send)
        v.addWidget(row)
        return box

    def _mini_send(self):
        question = self._mini_input.text().strip()
        if not question:
            return
        self._mini_input.clear()
        self._mini_answer.setVisible(True)
        self._mini_answer.setText("Thinking…")
        self.ask_submitted.emit(question)

    def show_mini_answer(self, text: str):
        """Called by the window when the async answer returns."""
        if hasattr(self, "_mini_answer") and self._mini_answer is not None:
            self._mini_answer.setVisible(True)
            self._mini_answer.setText(text)

    def _block(self, head, text):
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        # Micro-label headings are accent-colored in the rail, unlike elsewhere.
        v.addWidget(w.micro_label(head, color=P["accent"]))
        v.addWidget(w.body(text, size=12.5, color=P["text2"], lh=1.5))
        return box

    def _checklist(self, steps):
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(7)
        v.addWidget(w.micro_label("WHAT SHOULD I DO?", color=P["accent"]))
        for s in steps:
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 3, 0, 0)
            h.setSpacing(8)
            # An empty bordered square rather than the ▢ character: the bundled
            # fonts have no such glyph, and the fallback faces draw it at an
            # inconsistent size.
            box_glyph = QLabel()
            box_glyph.setFixedSize(11, 11)
            box_glyph.setStyleSheet(
                f"border: 1.4px solid {P['sevHigh']}; border-radius: 3px; "
                f"background: transparent;")
            h.addWidget(box_glyph, 0, Qt.AlignTop)
            h.addWidget(w.body(s, size=12, color=P["text2"], lh=1.45), 1)
            v.addWidget(row)
        return box

    def _chip_row(self, head, chips):
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(7)
        v.addWidget(w.micro_label(head, color=P["accent"]))
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        for label_text, ref in chips:
            h.addWidget(w.chip_button(
                label_text, lambda r=ref: self.chip_clicked.emit(r)))
        h.addStretch(1)
        v.addWidget(row)
        return box

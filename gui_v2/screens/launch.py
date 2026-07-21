"""
gui_v2/screens/launch.py

Launch (no case open) and the analysis-progress screen.

The brief is explicit that the app must not look broken when it is empty, so the
launch screen is a real screen: it states what the app does, what it accepts,
and offers the previous cases — rather than an empty frame with a disabled nav.

Neither screen shows the sidebar or the rail: with no case there is nothing for
them to explain, and a rail full of dashes would be worse than no rail.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QWidget, QFrame

from .. import theme, widgets as w
from ..content import SUPPORTED_FORMATS, ANALYSIS_STAGES, ANALYSIS_LOGS

P = theme.GUIDED


class LaunchScreen(QWidget):
    """Empty state. Emits new_case() and open_case(path_or_none)."""

    new_case = Signal()
    open_case = Signal(object)

    def __init__(self, recent=None, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self._recent = recent or []

        root = QHBoxLayout(self)
        root.setContentsMargins(60, 40, 60, 40)
        root.setSpacing(60)
        root.addStretch(1)
        root.addWidget(self._left(), 0, Qt.AlignVCenter)
        root.addWidget(self._history(), 0, Qt.AlignVCenter)
        root.addStretch(1)

    def _left(self):
        col = QWidget()
        col.setMaximumWidth(400)
        v = QVBoxLayout(col)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        v.addWidget(LogoMark(), 0, Qt.AlignLeft)
        v.addWidget(w.spacer(h=20))

        v.addWidget(w.label("No case open", size=22, weight=theme.W_SEMIBOLD))
        v.addWidget(w.spacer(h=8))
        sub = w.body(
            "Create a case and add evidence to begin an investigation. Every file is "
            "hashed on intake and opened read-only.",
            size=13, color=P["text2"], lh=1.55)
        sub.setMaximumWidth(380)
        v.addWidget(sub)
        v.addWidget(w.spacer(h=20))

        btn = w.primary_button("+  New case", self.new_case.emit)
        v.addWidget(btn, 0, Qt.AlignLeft)
        v.addWidget(w.spacer(h=26))

        v.addWidget(w.micro_label("SUPPORTED EVIDENCE"))
        v.addWidget(w.spacer(h=6))
        fmt = w.body(SUPPORTED_FORMATS, size=9.5, color=P["text3"], lh=1.7, mono=True)
        fmt.setMaximumWidth(380)
        v.addWidget(fmt)
        return col

    def _history(self):
        card = w.Card(pad=16, spacing=2)
        card.setFixedWidth(360)
        card.head("CASE HISTORY")
        card.add(w.spacer(h=6))

        if not self._recent:
            card.add(w.body(
                "No previous cases on this machine yet. The cases you create will "
                "appear here.", size=12, color=P["text3"], lh=1.5))
        for c in self._recent:
            card.add(self._row(c))

        card.add(w.spacer(h=8))
        card.add(w.hline())
        card.add(w.body(
            "Cases are stored locally, with their audit trails. Opening one is logged.",
            size=11, color=P["text3"], lh=1.45))
        return card

    def _row(self, c):
        row = QWidget()
        row.setObjectName("hoverRow")
        row.setAttribute(Qt.WA_StyledBackground, True)
        row.setCursor(Qt.PointingHandCursor)
        h = QHBoxLayout(row)
        h.setContentsMargins(8, 9, 8, 9)
        h.setSpacing(10)

        col = QWidget()
        v = QVBoxLayout(col)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        v.addWidget(w.label(c["id"], size=11.5, weight=theme.W_SEMIBOLD,
                            color=P["accent"], mono=True))
        v.addWidget(w.label(c["title"], size=12, weight=theme.W_REGULAR, wrap=True))
        v.addWidget(w.label(c["meta"], size=10.5, color=P["text3"]))
        h.addWidget(col, 1)

        hot = c.get("hot")
        tag = w.label(c.get("risk", ""), size=9, weight=theme.W_SEMIBOLD, mono=True,
                      color=P["sevCritical"] if hot else P["text3"])
        tag.setStyleSheet(
            f"color: {P['sevCritical'] if hot else P['text3']}; "
            f"background: {theme.tint(P['sevCritical'], '10') if hot else P['lineSoft']}; "
            f"border-radius: 4px; padding: 3px 8px;")
        h.addWidget(tag, 0, Qt.AlignTop)

        row.mouseReleaseEvent = lambda e, cc=c: self.open_case.emit(cc.get("path"))
        return row


class LogoMark(QFrame):
    """The AIRforensics logo, scaled smoothly to the requested size.

    Falls back to the original abstract mark (accent rounded square with a
    white inner square) only if the bundled logo image cannot be loaded."""

    def __init__(self, size=52, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)

        from .. import theme
        from PySide6.QtGui import QPixmap
        from PySide6.QtWidgets import QLabel
        pixmap = QPixmap(theme.assets_path("logo.png"))
        if not pixmap.isNull():
            label = QLabel()
            label.setPixmap(pixmap.scaled(
                size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            v.addWidget(label, 0, Qt.AlignCenter)
            return

        self.setObjectName("logoMark")
        inner = QFrame()
        inner.setObjectName("logoInner")
        inner.setFixedSize(20, 20)
        v.addWidget(inner, 0, Qt.AlignCenter)


class AnalyzingScreen(QWidget):
    """Pipeline progress. Driven by the worker thread's stage signals."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self._step = 0
        self._rows = []

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 40, 40, 40)
        root.setAlignment(Qt.AlignCenter)

        card = w.Card(pad=24, spacing=0)
        card.setFixedWidth(520)
        card.add(w.label("Analyzing evidence", size=17, weight=theme.W_SEMIBOLD))
        card.add(w.spacer(h=4))
        card.add(w.body(
            "Everything runs on this machine. You can watch each stage complete.",
            size=12.5, color=P["text2"], lh=1.5))
        card.add(w.spacer(h=16))

        self._bar = w.ProgressBar(0, color=P["accent"], height=6,
                                  track=P["lineSoft"])
        card.add(self._bar)
        card.add(w.spacer(h=18))

        for label_text, note in ANALYSIS_STAGES:
            row = _StageRow(label_text, note)
            self._rows.append(row)
            card.add(row)

        card.add(w.spacer(h=14))
        card.add(w.hline())
        card.add(w.spacer(h=10))
        self._log = w.label(ANALYSIS_LOGS[0], size=10.5, mono=True, color=P["text3"])
        card.add(self._log)

        root.addWidget(card)
        self.set_step(0)

    def set_step(self, n):
        """0..5 — n is the number of completed stages."""
        self._step = max(0, min(len(self._rows), n))
        for i, row in enumerate(self._rows):
            row.set_state("done" if self._step > i else
                          "active" if self._step == i else "pending")
        self._bar.set_pct(int(self._step / len(self._rows) * 100))
        self._log.setText(ANALYSIS_LOGS[min(self._step, len(ANALYSIS_LOGS) - 1)])

    def set_log(self, text):
        self._log.setText(text)


class _StageRow(QWidget):
    """One pipeline stage: a state dot, the stage name, and its result.

    The dot is a QLabel carrying its own glyph rather than a frame wrapping one,
    so styling it cannot leak onto a child.
    """

    def __init__(self, text, note, parent=None):
        super().__init__(parent)
        self._note_text = note
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 5, 0, 5)
        h.setSpacing(10)

        self._dot = w.label("", size=10, weight=theme.W_BOLD)
        self._dot.setFixedSize(20, 20)
        self._dot.setAlignment(Qt.AlignCenter)
        h.addWidget(self._dot)

        self._label = w.label(text, size=13)
        h.addWidget(self._label, 1)
        self._note = w.label("", size=10.5, mono=True, color=P["text3"])
        h.addWidget(self._note)

    def set_state(self, state):
        if state == "done":
            self._dot.setText("✓")
            self._dot.setStyleSheet(
                f"background: {P['good']}; color: #FFFFFF; border-radius: 10px;")
            self._label.setStyleSheet(f"color: {P['text']};")
            self._note.setText(self._note_text)
        elif state == "active":
            self._dot.setText("●")
            self._dot.setStyleSheet(
                f"background: {P['accentTint']}; color: {P['accent']}; "
                f"border-radius: 10px;")
            self._label.setStyleSheet(f"color: {P['text']};")
            self._note.setText("…")
        else:
            self._dot.setText("")
            self._dot.setStyleSheet(
                f"background: {P['lineSoft']}; border-radius: 10px;")
            self._label.setStyleSheet(f"color: {P['text3']};")
            self._note.setText("")

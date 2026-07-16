"""
gui_v2/sidebar.py

The left navigation: five investigation steps plus three "anytime" tools, and
the case-risk card pinned to the bottom.

The nav rows are not QPushButtons. The design's active marker is a 3px rust bar
flush to the item's left edge with the row background rounded on the right side
only — a button's border-radius applies to the whole widget, so each row is a
composed widget (marker + label + sub-line) instead.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QWidget, QLabel

from . import theme, widgets as w

P = theme.GUIDED

SIDEBAR_WIDTH = 216


class NavRow(QWidget):
    """One nav item: 3px marker, label, and an optional live sub-line."""

    clicked = Signal()

    def __init__(self, text, sub=None, parent=None):
        super().__init__(parent)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setAttribute(Qt.WA_StyledBackground, True)

        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 10, 0)
        h.setSpacing(10)

        self._mark = QFrame()
        self._mark.setFixedSize(3, 26)
        h.addWidget(self._mark)

        col = QWidget()
        v = QVBoxLayout(col)
        v.setContentsMargins(0, 8, 0, 8)
        v.setSpacing(1)
        self._label = w.label(text, size=13, weight=theme.W_MEDIUM)
        v.addWidget(self._label)
        self._sub = None
        if sub is not None:
            self._sub = w.label(sub, size=10.5, color=P["text3"])
            v.addWidget(self._sub)
        h.addWidget(col, 1)

        self._active = False
        self._apply()

    def set_sub(self, text):
        if self._sub is not None:
            self._sub.setText(str(text))

    def set_active(self, on: bool):
        self._active = bool(on)
        self._apply()

    def _apply(self):
        if self._active:
            self._mark.setStyleSheet(
                f"background: {P['accent']}; border: none; "
                f"border-radius: 0px 2px 2px 0px;")
            # Rounded on the right only, so the marker stays flush to the edge.
            self.setStyleSheet(
                f"NavRow {{ background: {P['accentTint']}; "
                f"border-radius: 0px 9px 9px 0px; }}")
            self._label.setStyleSheet(f"color: {P['text']}; background: transparent;")
        else:
            self._mark.setStyleSheet("background: transparent; border: none;")
            self.setStyleSheet(
                "NavRow { background: transparent; border-radius: 0px 9px 9px 0px; }"
                f"NavRow:hover {{ background: {P['lineSoft']}; }}")
            self._label.setStyleSheet(f"color: {P['text2']}; background: transparent;")

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(e)


class RiskCard(QFrame):
    """Bottom-of-sidebar risk summary: score, a filled bar, and why."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("callout")
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 10, 12, 11)
        v.setSpacing(7)

        self._head = w.micro_label("CASE RISK · —", color=P["accent"])
        v.addWidget(self._head)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(9)
        self._bar = w.ProgressBar(0, color=P["sevCritical"], height=6,
                                  track=P["panel"])
        row.addWidget(self._bar, 1)
        self._score = w.label("—", size=15, weight=theme.W_SEMIBOLD,
                              color=P["sevCritical"], mono=True)
        row.addWidget(self._score)
        v.addLayout(row)

        self._caption = w.body("", size=10.5, color=P["text3"], lh=1.4)
        v.addWidget(self._caption)

    def set_risk(self, score, label_text, caption):
        self._head.setText(f"CASE RISK · {str(label_text).upper()}")
        self._score.setText(str(score))
        self._bar.set_pct(score)
        self._caption.setText(
            f'<div style="line-height:140%; font-size:10.5px; '
            f'color:{P["text3"]};">{caption}</div>')


class Sidebar(QFrame):
    """Left rail. Emits navigate(screen_id)."""

    navigate = Signal(str)

    def __init__(self, steps, extras, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(SIDEBAR_WIDTH)

        self.rows = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._section("INVESTIGATION"))
        for sid, text, sub in steps:
            row = NavRow(text, sub)
            row.clicked.connect(lambda s=sid: self.navigate.emit(s))
            self.rows[sid] = row
            root.addWidget(row)

        root.addWidget(w.spacer(h=14))
        root.addWidget(self._section("ANYTIME"))
        for sid, text in extras:
            row = NavRow(text)
            row.clicked.connect(lambda s=sid: self.navigate.emit(s))
            self.rows[sid] = row
            root.addWidget(row)

        root.addStretch(1)

        self.risk = RiskCard()
        foot = QWidget()
        fl = QVBoxLayout(foot)
        fl.setContentsMargins(12, 0, 12, 12)
        fl.addWidget(self.risk)
        root.addWidget(foot)

    def _section(self, title):
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(15, 14, 12, 6)
        v.addWidget(w.micro_label(title))
        return box

    def set_active(self, sid):
        for k, row in self.rows.items():
            row.set_active(k == sid)

    def set_sub(self, sid, text):
        if sid in self.rows:
            self.rows[sid].set_sub(text)

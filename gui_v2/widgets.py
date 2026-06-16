"""
gui_v2/widgets.py

Small reusable widgets that mirror the web prototype's components:
Panel, SeverityBadge, ConfidenceBadge, MitreTag, HashChip, SourceTag,
MicroLabel, and a painted RiskDial.
"""

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QFont
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QWidget, QSizePolicy,
    QPushButton, QApplication,
)

from . import theme


def _c(pal, key):
    return pal[key]


class MicroLabel(QLabel):
    def __init__(self, text=""):
        super().__init__(text.upper())
        self.setObjectName("microLabel")


class Panel(QFrame):
    """Titled card with an optional header-right widget and a body layout."""

    def __init__(self, title=None, right=None, pad=12):
        super().__init__()
        self.setObjectName("panel")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        if title is not None:
            header = QFrame()
            header.setObjectName("panelHeader")
            hl = QHBoxLayout(header)
            hl.setContentsMargins(12, 8, 12, 8)
            hl.addWidget(MicroLabel(title))
            hl.addStretch(1)
            if right is not None:
                hl.addWidget(right)
            outer.addWidget(header)

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(pad, pad, pad, pad)
        self.body_layout.setSpacing(8)
        outer.addWidget(self.body, 1)

    def add(self, w):
        self.body_layout.addWidget(w)
        return w

    def add_layout(self, l):
        self.body_layout.addLayout(l)
        return l


class Badge(QLabel):
    """Generic pill badge."""

    def __init__(self, text, color_hex, mono=True, filled=False):
        super().__init__(text)
        fam = theme.MONO if mono else theme.SANS
        if filled:
            self.setStyleSheet(
                f"background:{color_hex}22; color:{color_hex}; "
                f"border:1px solid {color_hex}55; border-radius:7px; "
                f"padding:2px 7px; font-family:{fam}; font-size:10px; font-weight:600;")
        else:
            self.setStyleSheet(
                f"color:{color_hex}; font-family:{fam}; font-size:10px; font-weight:600;")
        self.setAlignment(Qt.AlignCenter)


class SeverityBadge(QWidget):
    def __init__(self, sev, pal):
        super().__init__()
        label, key = theme.SEV.get(sev, ("Low", "good"))
        color = pal[key]
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(5)
        dot = QLabel("●")
        dot.setStyleSheet(f"color:{color}; font-size:9px;")
        txt = QLabel(label.upper())
        txt.setStyleSheet(
            f"color:{color}; font-family:{theme.MONO}; font-size:10px; font-weight:600;")
        lay.addWidget(dot)
        lay.addWidget(txt)
        lay.addStretch(1)


class ConfidenceBadge(Badge):
    def __init__(self, conf, pal):
        cmap = {"High": pal["good"], "Medium": pal["med"], "Low": pal["text3"]}
        super().__init__(f"CONF {conf.upper()}", cmap.get(conf, pal["text2"]), filled=True)


class MitreTag(Badge):
    def __init__(self, mid, pal, name=""):
        super().__init__(f"ATT&CK {mid}", pal["accent"], filled=True)
        if name:
            self.setToolTip(f"{mid} — {name}")


class SourceTag(Badge):
    def __init__(self, src, pal):
        key = theme.SRC_COLORS.get(src, "text2")
        super().__init__(src.upper(), pal.get(key, pal["text2"]), filled=False)


class HashChip(QPushButton):
    """Click-to-copy SHA-256 chip with verified dot."""

    def __init__(self, full_hash, verified, pal):
        short = (full_hash[:8] + "…" + full_hash[-6:]) if full_hash else "—"
        super().__init__(("● " if verified else "○ ") + short)
        self._full = full_hash
        dot = pal["good"] if verified else pal["med"]
        self.setStyleSheet(
            f"QPushButton {{ background:transparent; border:1px solid {pal['line2']}; "
            f"color:{pal['text2']}; font-family:{theme.MONO}; font-size:11px; "
            f"border-radius:7px; padding:3px 8px; text-align:left; }}"
            f"QPushButton:hover {{ border-color:{pal['accent']}; }}")
        self.setToolTip(full_hash + "\n(click to copy)")
        self.clicked.connect(self._copy)

    def _copy(self):
        QApplication.clipboard().setText(self._full)
        old = self.text()
        self.setText("COPIED")
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1000, lambda: self.setText(old))


class RiskDial(QWidget):
    """Painted circular risk gauge 0-100."""

    def __init__(self, score, label, pal):
        super().__init__()
        self.score = score
        self.label = label
        self.pal = pal
        self.setFixedSize(132, 132)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(12, 12, 108, 108)
        # track
        pen = QPen(QColor(self.pal["line2"]), 9)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(rect, 0, 360 * 16)
        # value
        color = self.pal["crit"] if self.score >= 60 else self.pal["med"]
        pen2 = QPen(QColor(color), 9)
        pen2.setCapStyle(Qt.RoundCap)
        p.setPen(pen2)
        span = int(-360 * 16 * (self.score / 100.0))
        p.drawArc(rect, 90 * 16, span)
        # number
        p.setPen(QColor(color))
        f = QFont(theme.MONO.split(",")[0], 26, QFont.Bold)
        p.setFont(f)
        p.drawText(rect, Qt.AlignCenter, str(self.score))
        # label
        p.setPen(QColor(self.pal["text3"]))
        f2 = QFont(theme.MONO.split(",")[0], 7)
        p.setFont(f2)
        p.drawText(QRectF(12, 78, 108, 20), Qt.AlignCenter, f"RISK · {self.label}")


def hline(pal):
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet(f"color:{pal['line']}; background:{pal['line']}; max-height:1px;")
    return f

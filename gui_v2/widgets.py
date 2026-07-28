"""
gui_v2/widgets.py

The small reusable pieces the Guided Lab screens are built from.

Three of the design's properties have no Qt stylesheet equivalent, so they are
handled here once rather than at every call site:

  * letter-spacing — micro_label() sets it on the QFont.
  * line-height    — body() renders rich text with a line-height rule, because
                     QLabel's plain-text path has no line spacing control.
  * box-shadow     — SelectableCard swaps a 1px border for a 2px accent border
                     and drops one pixel of padding to keep its geometry fixed,
                     which is the closest Qt gets to the design's selection ring.
"""

import time

from PySide6.QtCore import Qt, Signal, QSize, QTimer
from PySide6.QtGui import QFont, QCursor, QFontMetricsF
from PySide6.QtWidgets import (
    QFrame, QLabel, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QSizePolicy, QApplication, QScrollArea,
)

from . import theme

P = theme.GUIDED


# ── text ──────────────────────────────────────────────────────────────────────

# Lexend and IBM Plex Mono are Latin faces: they have no σ, ✓, ●, ▸ or ▢. A
# QFont with a single family renders those as tofu, so every font carries an
# explicit fallback chain and Qt walks it per-glyph.
_SANS_FALLBACK = ["Segoe UI", "Segoe UI Symbol", "Arial Unicode MS", "Arial"]
_MONO_FALLBACK = ["Consolas", "Segoe UI Symbol", "Courier New"]


def _font(size, weight, mono=False):
    f = QFont()
    primary = theme.MONO if mono else theme.SANS
    f.setFamilies([primary] + (_MONO_FALLBACK if mono else _SANS_FALLBACK))
    f.setPixelSize(int(round(size)))
    f.setWeight(QFont.Weight(weight))
    return f


def label(text="", size=13, weight=theme.W_LIGHT, color=None, mono=False,
          wrap=False, parent=None):
    """A plain QLabel with the type scale applied."""
    lb = QLabel(str(text), parent)
    lb.setFont(_font(size, weight, mono))
    lb.setStyleSheet(f"color: {color or P['text']}; background: transparent;")
    if wrap:
        lb.setWordWrap(True)
    return lb


def elided_label(text, width, size=12, weight=theme.W_LIGHT, color=None, mono=False):
    """A label that ellipsizes at `width`.

    QLabel clips rather than elides, which reads as a rendering bug — the text
    just stops. Artifact names are long and the columns holding them are narrow,
    so they get a real ellipsis and the full value in a tooltip.
    """
    lb = label("", size=size, weight=weight, color=color, mono=mono)
    fm = QFontMetricsF(lb.font())
    lb.setText(fm.elidedText(str(text), Qt.ElideMiddle, width))
    lb.setFixedWidth(width)
    if lb.text() != str(text):
        lb.setToolTip(str(text))
    return lb


def micro_label(text="", color=None, size=9):
    """UPPERCASE mono micro-heading with the design's 1.2px tracking.

    Qt has no letter-spacing stylesheet property, so it is set on the font.
    """
    lb = QLabel(str(text).upper())
    f = _font(size, theme.W_SEMIBOLD, mono=True)
    f.setLetterSpacing(QFont.AbsoluteSpacing, 1.2)
    lb.setFont(f)
    lb.setStyleSheet(f"color: {color or P['text3']}; background: transparent;")
    return lb


def _esc(t):
    return (str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def body(text="", size=13, weight=theme.W_LIGHT, color=None, lh=1.55, wrap=True,
         rich=False, mono=False):
    """A paragraph with real line spacing.

    QLabel's plain-text rendering ignores line-height, so anything that needs
    the design's 1.55 leading goes through the rich-text path. Pass rich=True if
    `text` already contains markup that should be honoured rather than escaped.

    The face is baked into the markup: inline CSS wins over any stylesheet set
    on the widget, so a caller cannot switch this to mono from the outside.
    """
    lb = QLabel()
    content = str(text) if rich else _esc(text)
    lb.setText(
        f'<div style="line-height:{int(lh * 100)}%; '
        f'font-family:{theme.MONO_STACK if mono else theme.SANS_STACK}; '
        f'font-size:{size}px; '
        f'font-weight:{weight}; color:{color or P["text"]};">{content}</div>')
    lb.setTextFormat(Qt.RichText)
    lb.setWordWrap(wrap)
    return lb


def mono(text="", size=11, weight=theme.W_REGULAR, color=None, wrap=False):
    return label(text, size=size, weight=weight, color=color or P["text2"],
                 mono=True, wrap=wrap)


class ThinkingLabel(QLabel):
    """A label that counts elapsed seconds while an AI generation runs, so a
    slow local model reads as work — "Thinking… 12s" — rather than a hang.

    start() begins counting from now; stop() freezes it. The one-second tick is
    a QTimer owned by the label, so it is torn down with the widget. Elapsed
    time is read from a monotonic clock rather than counted in ticks, so a busy
    event loop never makes the number drift.
    """

    def __init__(self, prefix="Thinking", size=12.5, color=None, parent=None):
        super().__init__(parent)
        self._prefix = prefix
        self._start = None
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._refresh)
        self.setFont(_font(size, theme.W_LIGHT))
        self.setStyleSheet(f"color: {color or P['text3']}; background: transparent;")
        self._refresh()

    def start(self):
        self._start = time.monotonic()
        self._refresh()
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def _refresh(self):
        if self._start is None:
            self.setText(f"{self._prefix}…")
            return
        seconds = int(time.monotonic() - self._start)
        self.setText(f"{self._prefix}… {seconds}s")


# ── surfaces ──────────────────────────────────────────────────────────────────

class Card(QFrame):
    """White panel, 1px hairline, 12px radius — the design's default surface."""

    def __init__(self, pad=16, spacing=8, alt=False, parent=None):
        super().__init__(parent)
        self.setObjectName("cardAlt" if alt else "card")
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(pad, pad, pad, pad)
        self.v.setSpacing(spacing)

    def add(self, w, *a, **kw):
        self.v.addWidget(w, *a, **kw)
        return w

    def add_layout(self, l):
        self.v.addLayout(l)
        return l

    def head(self, title, right=None):
        """A micro-label heading, optionally with a right-aligned widget."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(micro_label(title))
        row.addStretch(1)
        if right is not None:
            row.addWidget(right)
        self.v.addLayout(row)
        return row


class Callout(QFrame):
    """Tinted accent panel used for the sealed-viewer note and AI uncertainty."""

    def __init__(self, text, rich=True, pad=12, parent=None):
        super().__init__(parent)
        self.setObjectName("callout")
        v = QVBoxLayout(self)
        v.setContentsMargins(pad, pad, pad, pad)
        v.addWidget(body(text, size=12, color=P["text2"], lh=1.5, rich=rich))


class SelectableCard(QFrame):
    """A card that reports clicks and shows the accent selection ring."""

    clicked = Signal()

    def __init__(self, pad=12, spacing=6, parent=None):
        super().__init__(parent)
        self.setObjectName("selCard")
        self.setProperty("sel", "false")
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(pad, pad, pad, pad)
        self.v.setSpacing(spacing)

    def set_selected(self, on: bool):
        self.setProperty("sel", "true" if on else "false")
        # Qt only re-evaluates property-based selectors after a style refresh.
        self.style().unpolish(self)
        self.style().polish(self)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(e)


def clear_layout(layout):
    """Empty a layout, immediately.

    deleteLater() on its own schedules destruction for the next event-loop pass,
    so a widget rebuilt in response to a click would paint on top of the one it
    replaces. setParent(None) unparents it now; deleteLater then frees it once
    Qt is done with any in-flight events referencing it.
    """
    while layout.count():
        item = layout.takeAt(0)
        wdg = item.widget()
        if wdg is not None:
            wdg.setParent(None)
            wdg.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())
            item.layout().deleteLater()


def hline(color=None):
    f = QFrame()
    f.setFixedHeight(1)
    f.setStyleSheet(f"background: {color or P['lineSoft']}; border: none;")
    return f


def vline(color=None, height=18):
    f = QFrame()
    f.setFixedWidth(1)
    f.setFixedHeight(height)
    f.setStyleSheet(f"background: {color or P['line']}; border: none;")
    return f


def spacer(h=0, w=0):
    s = QWidget()
    s.setFixedSize(QSize(w, h))
    return s


# ── chips, pills, tags ────────────────────────────────────────────────────────

class Tag(QLabel):
    """Small tinted mono tag — severity chips, meaning tags, integrity marks.

    `fill` renders the design's ~7%-alpha tinted background; without it the tag
    is bare colored text.
    """

    def __init__(self, text, color, fill=True, size=8.5, parent=None):
        super().__init__(str(text).upper(), parent)
        f = _font(size, theme.W_BOLD, mono=True)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 0.6)
        self.setFont(f)
        if fill:
            self.setStyleSheet(
                f"color: {color}; background: {theme.tint(color, '12')}; "
                f"border-radius: 4px; padding: 3px 7px;")
        else:
            self.setStyleSheet(f"color: {color}; background: transparent;")
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)


def sev_tag(sev: str):
    """Severity chip from the demo content's text severity ("CRITICAL")."""
    return Tag(sev, P[theme.SEV_KEY.get(str(sev).upper(), "good")])


class Pill(QLabel):
    """Rounded status pill — READ-ONLY, LOCAL MODEL, OFFLINE."""

    def __init__(self, text, color=None, dot=True, parent=None):
        color = color or P["good"]
        super().__init__(("● " if dot else "") + str(text).upper(), parent)
        f = _font(9, theme.W_SEMIBOLD, mono=True)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 0.8)
        self.setFont(f)
        self.setStyleSheet(
            f"color: {color}; background: {theme.tint(color, '12')}; "
            f"border-radius: 9px; padding: 4px 9px;")
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)


def chip_button(text, on_click=None, arrow=True):
    """Mono outline chip that navigates somewhere ("EV-01 ↗")."""
    b = QPushButton(f"{text} ↗" if arrow else str(text))
    b.setObjectName("chip")
    b.setCursor(QCursor(Qt.PointingHandCursor))
    b.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    if on_click:
        b.clicked.connect(lambda: on_click())
    return b


def primary_button(text, on_click=None):
    b = QPushButton(str(text))
    b.setObjectName("primary")
    b.setCursor(QCursor(Qt.PointingHandCursor))
    b.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    if on_click:
        b.clicked.connect(lambda: on_click())
    return b


def link_button(text, on_click=None):
    b = QPushButton(str(text))
    b.setObjectName("link")
    b.setCursor(QCursor(Qt.PointingHandCursor))
    b.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    if on_click:
        b.clicked.connect(lambda: on_click())
    return b


class CheckRow(QWidget):
    """Checkbox + label. Painted as a rounded square so it matches the design
    rather than the platform's native check."""

    toggled = Signal(bool)

    def __init__(self, text, checked=False, size=15, color=None, text_size=12.5,
                 wrap=False, parent=None):
        super().__init__(parent)
        self._on = checked
        self._color = color or P["accent"]
        self._size = size
        self.setCursor(QCursor(Qt.PointingHandCursor))
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        self.box = QLabel("")
        self.box.setFixedSize(size, size)
        self.box.setAlignment(Qt.AlignCenter)
        self.box.setFont(_font(size * 0.66, theme.W_BOLD))
        self.lbl = label(text, size=text_size, weight=theme.W_LIGHT, color=P["text2"],
                         wrap=wrap)
        h.addWidget(self.box, 0, Qt.AlignTop if wrap else Qt.AlignVCenter)
        h.addWidget(self.lbl, 1)
        self._paint()

    def _paint(self):
        if self._on:
            self.box.setText("✓")
            self.box.setStyleSheet(
                f"color: #FFFFFF; background: {self._color}; "
                f"border: 1px solid {self._color}; border-radius: 4px;")
        else:
            self.box.setText("")
            self.box.setStyleSheet(
                f"background: {P['panel']}; border: 1px solid {P['lineInput']}; "
                f"border-radius: 4px;")

    def is_checked(self):
        return self._on

    def set_checked(self, on):
        self._on = bool(on)
        self._paint()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._on = not self._on
            self._paint()
            self.toggled.emit(self._on)
        super().mouseReleaseEvent(e)


# ── data display ──────────────────────────────────────────────────────────────

def kv_row(k, v, mono_value=True, value_color=None):
    """Label/value row with the design's hairline separator handled by callers."""
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 5, 0, 5)
    h.setSpacing(10)
    h.addWidget(label(k, size=12, color=P["text3"]))
    h.addStretch(1)
    h.addWidget(label(v, size=11.5, weight=theme.W_REGULAR,
                      color=value_color or P["text"], mono=mono_value))
    return w


class HashLabel(QPushButton):
    """Click-to-copy SHA-256. Long hashes have to be present for chain of
    custody but must not dominate, so only the head is shown."""

    def __init__(self, full_hash, chars=8, size=9.5, color=None, parent=None):
        short = (full_hash[:chars] + "…") if full_hash else "—"
        super().__init__(short, parent)
        self._full = full_hash or ""
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setFlat(True)
        self.setFont(_font(size, theme.W_REGULAR, mono=True))
        self.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; "
            f"color: {color or P['text3']}; padding: 0; text-align: left; }}"
            f"QPushButton:hover {{ color: {P['accent']}; }}")
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setToolTip(f"{self._full}\n(click to copy)")
        self.clicked.connect(self._copy)

    def _copy(self):
        if not self._full:
            return
        QApplication.clipboard().setText(self._full)
        old = self.text()
        self.setText("copied")
        from PySide6.QtCore import QTimer
        QTimer.singleShot(900, lambda: self.setText(old))


class ProgressBar(QFrame):
    """Flat progress bar. QProgressBar carries platform chrome the design does
    not want, so this is two nested frames."""

    def __init__(self, pct=0, color=None, height=6, track=None, parent=None):
        super().__init__(parent)
        self.setFixedHeight(height)
        self._color = color or P["accent"]
        self._h = height
        self.setStyleSheet(
            f"background: {track or P['panel']}; border-radius: {height // 2}px; "
            f"border: none;")
        self._fill = QFrame(self)
        self._fill.setStyleSheet(
            f"background: {self._color}; border-radius: {height // 2}px; border: none;")
        self._pct = 0
        self.set_pct(pct)

    def set_pct(self, pct):
        self._pct = max(0, min(100, pct))
        self._resize_fill()

    def _resize_fill(self):
        self._fill.setGeometry(0, 0, int(self.width() * self._pct / 100.0), self._h)

    def resizeEvent(self, e):
        self._resize_fill()
        super().resizeEvent(e)


def scroll_area(inner: QWidget) -> QScrollArea:
    """Scroll host with the frame suppressed.

    Horizontal scrolling is left on-demand rather than disabled: the layouts are
    sized for the design's 1440 window, and near the 1100 minimum the widest
    screen (Evidence) would otherwise clip its right-hand column silently. A
    scrollbar that appears only when needed is preferable to content that is
    quietly cut off.
    """
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.NoFrame)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    sa.setWidget(inner)
    return sa


def page(pad_h=24, pad_v=20, spacing=14, max_width=None):
    """A content page: returns (widget, layout). `max_width` keeps the column
    stable when the window is wider than the design's 1440."""
    w = QWidget()
    w.setObjectName("page")
    outer = QVBoxLayout(w)
    outer.setContentsMargins(pad_h, pad_v, pad_h, pad_v)
    outer.setSpacing(0)

    inner = QWidget()
    if max_width:
        inner.setMaximumWidth(max_width)
    lay = QVBoxLayout(inner)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(spacing)
    outer.addWidget(inner)
    return w, lay


def screen_title(title, meta=None):
    """19/600 screen title with an optional mono meta line under it."""
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(4)
    v.addWidget(label(title, size=19, weight=theme.W_SEMIBOLD))
    if meta:
        v.addWidget(label(meta, size=10.5, color=P["text3"], mono=True))
    return w

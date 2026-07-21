"""
gui_v2/theme.py

Design tokens + Qt stylesheet for the "Guided Lab" interface.

The palette, type scale and spacing come from the design handoff. Everything
here was chosen to be renderable by Qt: flat fills, 1px hairlines, radii,
spacing and typography. No blur, no shadows (except the report paper), no
web-only effects.

Three Qt stylesheet gaps are worth knowing about, because the rest of the code
works around them rather than fighting them:

  * letter-spacing      — not a QSS property; set on the QFont instead
                          (see widgets.micro_label).
  * line-height         — not a QSS property; paragraphs that need it are
                          rendered as rich text (see widgets.body).
  * box-shadow          — unsupported; the design's 1px selection ring is done
                          with a 2px border plus padding compensation so the
                          widget's geometry does not shift when it is selected.
"""

import os
import sys

# ── Palette ───────────────────────────────────────────────────────────────────

GUIDED = {
    "bg":        "#F5F5F7",   # window / content background
    "panel":     "#FFFFFF",   # cards, sidebar, rail, menu bar, status bar
    "panelAlt":  "#F8F8FA",   # table headers, code/hex blocks, inputs
    "line":      "#E4E4EA",   # hairline borders
    "lineSoft":  "#EFEFF3",   # inner dividers
    "lineInput": "#CFCFD8",   # input borders, unselected checkboxes
    "text":      "#1B1B1F",
    "text2":     "#55555E",
    "text3":     "#8B8B96",
    "accent":      "#B3572D",  # rust
    "accentHover": "#8C4222",
    "accentTint":  "#F5EAE3",
    # The design specifies callout borders as accent at ~18% alpha. Qt honours
    # rgba() in stylesheets, so this stays a real alpha rather than a blend
    # against an assumed backdrop. Stylesheet-only — not a valid QColor string.
    "accentBorder": "rgba(179, 87, 45, 0.18)",
    "sevCritical": "#C24B51",
    "sevHigh":     "#C0763A",
    "sevMedium":   "#A88A3A",
    "good":        "#3D8B63",
}

# Back-compat alias: older code imported theme.LIGHT / theme.DARK.
LIGHT = GUIDED
DARK = GUIDED

# ── Fonts ─────────────────────────────────────────────────────────────────────

_FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "assets", "fonts")

# The symbol faces are fallbacks for glyphs the bundled Latin fonts lack
# (σ, ✓, ●, ▸, ▢ — all of which the design's copy and chrome use).
SANS_STACK = "'Lexend', 'Segoe UI', 'Segoe UI Symbol', -apple-system, sans-serif"
MONO_STACK = "'IBM Plex Mono', Consolas, 'Segoe UI Symbol', Menlo, monospace"

# Resolved at runtime by load_fonts(); fall back to system faces if the bundled
# TTFs are missing so a partial checkout still launches.
SANS = "Segoe UI"
MONO = "Consolas"

_loaded = False


def assets_path(*parts) -> str:
    """Absolute path into the bundled assets directory, source or frozen."""
    if getattr(sys, "frozen", False):
        root = os.path.join(sys._MEIPASS, "assets")
    else:
        root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "assets")
    return os.path.join(root, *parts)


def load_fonts():
    """Register the bundled OFL fonts. Safe to call more than once.

    Returns a (sans_family, mono_family) tuple of whatever actually resolved,
    so callers can log a fallback rather than silently rendering wrong.
    """
    global SANS, MONO, SANS_STACK, MONO_STACK, _loaded
    if _loaded:
        return SANS, MONO

    from PySide6.QtGui import QFontDatabase

    families = set()
    if os.path.isdir(_FONT_DIR):
        for fn in sorted(os.listdir(_FONT_DIR)):
            if not fn.lower().endswith((".ttf", ".otf")):
                continue
            fid = QFontDatabase.addApplicationFont(os.path.join(_FONT_DIR, fn))
            if fid != -1:
                families.update(QFontDatabase.applicationFontFamilies(fid))

    if "Lexend" in families:
        SANS = "Lexend"
    if "IBM Plex Mono" in families:
        MONO = "IBM Plex Mono"

    SANS_STACK = f"'{SANS}', 'Segoe UI', 'Segoe UI Symbol', -apple-system, sans-serif"
    MONO_STACK = f"'{MONO}', Consolas, 'Segoe UI Symbol', Menlo, monospace"
    _loaded = True

    # The inherited default for widgets that never call setFont(). Applied to
    # the application rather than declared in the stylesheet, so that individual
    # widgets can still set their own size, weight and face.
    from PySide6.QtWidgets import QApplication
    app_ = QApplication.instance()
    if app_ is not None:
        app_.setFont(base_font())

    return SANS, MONO


def base_font():
    """Body text: 13px Lexend Light, with the symbol fallbacks."""
    from PySide6.QtGui import QFont
    f = QFont()
    f.setFamilies([SANS, "Segoe UI", "Segoe UI Symbol", "Arial"])
    f.setPixelSize(13)
    f.setWeight(QFont.Weight(W_LIGHT))
    return f


# ── Weights ───────────────────────────────────────────────────────────────────
# Named so call sites read like the design spec ("body 13/300").

W_LIGHT, W_REGULAR, W_MEDIUM, W_SEMIBOLD, W_BOLD = 300, 400, 500, 600, 700

# ── Severity / source mappings ────────────────────────────────────────────────

# Numeric severity (used by the pipeline) -> (label, palette key)
SEV = {
    4: ("Critical", "sevCritical"),
    3: ("High", "sevHigh"),
    2: ("Medium", "sevMedium"),
    1: ("Low", "good"),
}

# Text severity (used by the demo content) -> palette key
SEV_KEY = {
    "CRITICAL": "sevCritical",
    "HIGH": "sevHigh",
    "MEDIUM": "sevMedium",
    "LOW": "good",
}

SRC_COLORS = {
    "Disk": "accent",
    "Browser": "good",
    "Downloads": "good",
    "Registry": "sevHigh",
    "EventLog": "text2",
    "USB": "sevCritical",
    "Network": "accent",
    "Email": "sevMedium",
}


def tint(hex_color: str, alpha_hex: str = "12") -> str:
    """Design tokens express chip fills as the base color at ~7% alpha.

    Qt honours #AARRGGBB in stylesheets, so translate #RRGGBB + a two-digit
    alpha suffix into the ARGB form Qt expects.
    """
    h = hex_color.lstrip("#")
    return f"#{alpha_hex}{h}"


# ── Stylesheet ────────────────────────────────────────────────────────────────

def stylesheet(p: dict = None) -> str:
    """Build the application stylesheet from a palette dict."""
    p = p or GUIDED
    return f"""
    /* This rule sets colour only, on purpose.

       background: a `QWidget {{ background: … }}` rule paints every widget in
       the tree, including the children of white cards, which then have to be
       papered over with per-widget `background: transparent` — and those leak
       onto THEIR children. Only surfaces meant to be painted get a background.

       font: a font declared here would override every widget's setFont(),
       because a Qt stylesheet beats a programmatically-set font. That would
       flatten the entire type scale to one size and face. The base font is set
       on the QApplication instead (see base_font), which acts as an inherited
       default that setFont() is free to override. */
    QWidget {{ color: {p['text']}; }}
    QMainWindow, QDialog, QWidget#page {{ background: {p['bg']}; }}

    /* ── surfaces ─────────────────────────────────────────────────────── */
    QFrame#card {{
        background: {p['panel']};
        border: 1px solid {p['line']};
        border-radius: 12px;
    }}
    QFrame#cardAlt {{
        background: {p['panelAlt']};
        border: 1px solid {p['line']};
        border-radius: 10px;
    }}
    QFrame#callout {{
        background: {p['accentTint']};
        border: 1px solid {p['accentBorder']};
        border-radius: 9px;
    }}
    QFrame#sidebar, QFrame#rail {{
        background: {p['panel']};
        border: none;
    }}
    QFrame#sidebar {{ border-right: 1px solid {p['line']}; }}
    QFrame#rail    {{ border-left: 1px solid {p['line']}; }}
    /* The rail's scrolling body is the widget inside a QScrollArea, so it does
       not inherit the rail's fill and must state its own. */
    QWidget#railBody {{ background: {p['panel']}; }}

    /* Report paper. The only shadow in the design; Qt has no box-shadow, so
       the sheet reads as paper through its border and radius alone. */
    QFrame#paper {{
        background: {p['panel']};
        border: 1px solid {p['line']};
        border-radius: 4px;
    }}

    /* Table headers and rows that need their own hairline. */
    QWidget#thead {{
        background: {p['panelAlt']};
        border-bottom: 1px solid {p['line']};
    }}
    QWidget#trow {{
        background: transparent;
        border-bottom: 1px solid {p['lineSoft']};
    }}

    /* Rows that highlight on hover (start-here, case history). */
    QWidget#hoverRow {{ background: transparent; border-radius: 8px; }}
    QWidget#hoverRow:hover {{ background: {p['panelAlt']}; }}

    /* Chat bubbles. */
    QFrame#bubbleUser {{
        background: {p['accent']};
        border: none;
        border-radius: 12px 12px 3px 12px;
    }}
    QFrame#bubbleAi {{
        background: {p['panel']};
        border: 1px solid {p['line']};
        border-radius: 12px 12px 12px 3px;
    }}

    /* Notices. */
    QFrame#noticeBad {{
        background: rgba(194, 75, 81, 0.06);
        border: 1px solid rgba(194, 75, 81, 0.20);
        border-radius: 9px;
    }}
    QFrame#noticeGood {{
        background: rgba(61, 139, 99, 0.07);
        border: 1px solid rgba(61, 139, 99, 0.25);
        border-radius: 8px;
    }}
    QFrame#dashed {{
        background: transparent;
        border: 1px dashed {p['lineInput']};
        border-radius: 10px;
    }}

    /* App mark on the launch screen. */
    QFrame#logoMark  {{ background: {p['accent']}; border-radius: 14px; }}
    QFrame#logoInner {{
        background: transparent;
        border: 2px solid #FFFFFF;
        border-radius: 6px;
    }}

    /* Selectable cards. The unselected state carries an extra 1px of padding
       so switching to the 2px selected border does not move the contents. */
    QFrame#selCard {{
        background: {p['panel']};
        border: 1px solid {p['line']};
        border-radius: 10px;
        padding: 1px;
    }}
    QFrame#selCard[sel="true"] {{
        border: 2px solid {p['accent']};
        padding: 0px;
    }}
    QFrame#selCard:hover {{ border-color: {p['accentBorder']}; }}
    QFrame#selCard[sel="true"]:hover {{ border-color: {p['accent']}; }}

    /* ── buttons ──────────────────────────────────────────────────────── */
    QPushButton {{
        background: {p['panel']};
        color: {p['text2']};
        border: 1px solid {p['lineInput']};
        border-radius: 8px;
        padding: 7px 14px;
        font-size: 12.5px;
        font-weight: {W_MEDIUM};
    }}
    QPushButton:hover {{ background: {p['panelAlt']}; }}
    QPushButton:disabled {{ color: {p['text3']}; border-color: {p['line']}; }}

    QPushButton#primary {{
        background: {p['accent']};
        color: #FFFFFF;
        border: 1px solid {p['accent']};
        border-radius: 8px;
        padding: 8px 16px;
        font-size: 12.5px;
        font-weight: {W_SEMIBOLD};
    }}
    QPushButton#primary:hover {{
        background: {p['accentHover']};
        border-color: {p['accentHover']};
    }}
    QPushButton#primary:disabled {{
        background: {p['lineInput']};
        border-color: {p['lineInput']};
        color: {p['panel']};
    }}

    /* Text-only button (e.g. "+ Add more files…") */
    QPushButton#link {{
        background: transparent;
        border: none;
        color: {p['accent']};
        padding: 4px 2px;
        font-size: 12px;
        font-weight: {W_MEDIUM};
        text-align: left;
    }}
    QPushButton#link:hover {{ color: {p['accentHover']}; }}

    /* Mono outline chip — the rail's "EV-01 ↗" navigation chips */
    QPushButton#chip {{
        background: {p['panel']};
        border: 1px solid {p['lineInput']};
        border-radius: 5px;
        padding: 3px 8px;
        color: {p['text2']};
        font-family: {MONO_STACK};
        font-size: 10px;
        font-weight: {W_SEMIBOLD};
    }}
    QPushButton#chip:hover {{
        border-color: {p['accent']};
        background: {p['accentTint']};
        color: {p['accent']};
    }}

    /* Timeline source filter pills */
    QPushButton#pill {{
        background: {p['panel']};
        border: 1px solid {p['lineInput']};
        border-radius: 16px;
        padding: 5px 12px;
        color: {p['text2']};
        font-size: 11.5px;
        font-weight: {W_MEDIUM};
    }}
    QPushButton#pill:hover {{ background: {p['panelAlt']}; }}
    QPushButton#pill[on="true"] {{
        background: {p['accent']};
        border-color: {p['accent']};
        color: #FFFFFF;
    }}

    /* Sidebar / list rows that highlight on hover */
    QPushButton#row {{
        background: transparent;
        border: none;
        border-radius: 8px;
        padding: 8px;
        text-align: left;
        color: {p['text']};
        font-weight: {W_LIGHT};
    }}
    QPushButton#row:hover {{ background: {p['panelAlt']}; }}

    /* ── inputs ───────────────────────────────────────────────────────── */
    QLineEdit, QPlainTextEdit, QTextEdit {{
        background: {p['panelAlt']};
        border: 1px solid {p['lineInput']};
        border-radius: 7px;
        padding: 8px 10px;
        color: {p['text']};
        font-size: 12.5px;
        font-weight: {W_REGULAR};
        selection-background-color: {p['accentTint']};
        selection-color: {p['text']};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
        border-color: {p['accent']};
    }}
    QLineEdit#mono {{ font-family: {MONO_STACK}; }}

    /* ── tables ───────────────────────────────────────────────────────── */
    QTableWidget, QTreeWidget {{
        background: {p['panel']};
        border: none;
        gridline-color: transparent;
        font-size: 12.5px;
        outline: none;
    }}
    QHeaderView::section {{
        background: {p['panelAlt']};
        color: {p['text3']};
        padding: 8px 10px;
        border: none;
        border-bottom: 1px solid {p['line']};
        font-family: {MONO_STACK};
        font-size: 9px;
        font-weight: {W_SEMIBOLD};
    }}
    QTableWidget::item {{
        padding: 8px 10px;
        border-bottom: 1px solid {p['lineSoft']};
        color: {p['text']};
    }}
    QTableWidget::item:hover {{ background: {p['panelAlt']}; }}
    QTableWidget::item:selected {{
        background: {p['accentTint']};
        color: {p['text']};
    }}

    /* ── scrollbars ───────────────────────────────────────────────────── */
    QScrollArea {{ border: none; background: transparent; }}
    QScrollBar:vertical {{
        background: transparent; width: 10px; margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {p['lineInput']}; border-radius: 5px; min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {p['text3']}; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; }}
    QScrollBar::handle:horizontal {{
        background: {p['lineInput']}; border-radius: 5px; min-width: 30px;
    }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    /* ── menu bar / status bar ────────────────────────────────────────── */
    QMenuBar {{
        background: {p['panel']};
        color: {p['text2']};
        border-bottom: 1px solid {p['line']};
        font-size: 12px;
        font-weight: {W_REGULAR};
    }}
    QMenuBar::item {{ padding: 6px 10px; background: transparent; }}
    QMenuBar::item:selected {{ background: {p['lineSoft']}; }}
    QMenu {{
        background: {p['panel']};
        color: {p['text']};
        border: 1px solid {p['line']};
        padding: 4px;
        font-size: 12.5px;
    }}
    QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 5px; }}
    QMenu::item:selected {{ background: {p['accentTint']}; color: {p['accent']}; }}
    QMenu::separator {{ height: 1px; background: {p['line']}; margin: 4px 8px; }}

    QStatusBar {{
        background: {p['panel']};
        border-top: 1px solid {p['line']};
        color: {p['text3']};
        font-family: {MONO_STACK};
        font-size: 10px;
    }}
    QStatusBar::item {{ border: none; }}

    /* ── dialogs ──────────────────────────────────────────────────────── */
    QDialog {{ background: {p['bg']}; }}
    QToolTip {{
        background: {p['text']};
        color: {p['panel']};
        border: none;
        padding: 5px 8px;
        font-size: 11px;
    }}
    """

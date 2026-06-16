"""
gui_v2/theme.py

Design tokens + Qt stylesheet for the Forensic AI Agent native console.
Mirrors the CSS-variable system from the web prototype so the look stays
consistent. Two palettes (dark default, light) are provided.

Qt has no real backdrop-blur, so "glass" panels are approximated with
semi-transparent fills + subtle borders. Everything else (colors, radii,
spacing, accent system, severity colors) maps 1:1.
"""

# ── Palettes ──────────────────────────────────────────────────────────────────

DARK = {
    "bg0":   "#0A0D14",   # window background
    "bg1":   "#141925",   # panels (approx of translucent white 0.05 over bg0)
    "bg2":   "#1B2230",   # hover / raised
    "line":  "#222a3a",   # hairline borders
    "line2": "#2d3750",   # stronger borders
    "text":  "#ECF1F8",
    "text2": "#A2AEC0",
    "text3": "#6B7689",
    "accent":     "#5E8BFF",
    "accent_dim": "#1b2740",
    "crit":  "#FF5C61",
    "high":  "#E08A4A",
    "med":   "#E0B84A",
    "good":  "#4FC487",
    "th_bg": "#11161f",
    "sel":   "#16233f",
}

LIGHT = {
    "bg0":   "#F3F5FA",
    "bg1":   "#FFFFFF",
    "bg2":   "#ECEFF6",
    "line":  "#dfe3ec",
    "line2": "#c5ccda",
    "text":  "#16202E",
    "text2": "#4C586C",
    "text3": "#8B96A8",
    "accent":     "#3A63D8",
    "accent_dim": "#e4ebfb",
    "crit":  "#D03238",
    "high":  "#C2590F",
    "med":   "#96781A",
    "good":  "#1F8A5B",
    "th_bg": "#eef1f7",
    "sel":   "#e4ebfb",
}

MONO = "IBM Plex Mono, Consolas, Menlo, monospace"
SANS = "Segoe UI, -apple-system, Helvetica Neue, sans-serif"

# severity -> (label, color key)
SEV = {
    4: ("Critical", "crit"),
    3: ("High", "high"),
    2: ("Medium", "med"),
    1: ("Low", "good"),
}

# source tag -> color key
SRC_COLORS = {
    "Disk": "accent", "Browser": "good", "Downloads": "good",
    "Registry": "high", "EventLog": "good", "USB": "crit", "Network": "accent",
    "Email": "med",
}


def stylesheet(p: dict) -> str:
    """Build the full application stylesheet from a palette dict."""
    return f"""
    QWidget {{
        background: {p['bg0']};
        color: {p['text']};
        font-family: {SANS};
        font-size: 13px;
    }}
    /* panels */
    QFrame#panel {{
        background: {p['bg1']};
        border: 1px solid {p['line']};
        border-radius: 14px;
    }}
    QFrame#panelHeader {{
        background: transparent;
        border: none;
        border-bottom: 1px solid {p['line']};
    }}
    QLabel#microLabel {{
        color: {p['text3']};
        font-family: {MONO};
        font-size: 10px;
        font-weight: 600;
        letter-spacing: 1px;
    }}
    QLabel#h1 {{ font-size: 19px; font-weight: 700; }}
    QLabel#sub {{ color: {p['text3']}; font-family: {MONO}; font-size: 11px; }}
    QLabel#mono {{ font-family: {MONO}; font-size: 11px; color: {p['text2']}; }}
    QLabel#dim  {{ color: {p['text3']}; }}

    /* sidebar */
    QFrame#sidebar {{
        background: {p['bg1']};
        border: none;
        border-right: 1px solid {p['line']};
    }}
    QPushButton#navItem {{
        text-align: left;
        padding: 9px 14px;
        border: none;
        border-left: 2px solid transparent;
        border-radius: 0px;
        background: transparent;
        color: {p['text2']};
        font-size: 13px;
    }}
    QPushButton#navItem:hover {{ background: {p['bg2']}; color: {p['text']}; }}
    QPushButton#navItemActive {{
        text-align: left;
        padding: 9px 14px;
        border: none;
        border-left: 2px solid {p['accent']};
        background: {p['accent_dim']};
        color: {p['text']};
        font-size: 13px;
        font-weight: 600;
    }}

    /* buttons */
    QPushButton {{
        background: {p['bg2']};
        color: {p['text']};
        border: 1px solid {p['line2']};
        border-radius: 8px;
        padding: 7px 14px;
        font-family: {MONO};
        font-size: 11px;
    }}
    QPushButton:hover {{ background: {p['line']}; }}
    QPushButton#primary {{
        background: {p['accent']};
        color: #ffffff;
        border: 1px solid {p['accent']};
        font-weight: 700;
    }}
    QPushButton#primary:hover {{ background: {p['accent']}; }}

    /* tables */
    QTableWidget {{
        background: transparent;
        border: none;
        gridline-color: {p['line']};
        font-size: 12px;
    }}
    QHeaderView::section {{
        background: {p['th_bg']};
        color: {p['text3']};
        padding: 7px 10px;
        border: none;
        border-bottom: 1px solid {p['line2']};
        font-family: {MONO};
        font-size: 10px;
        font-weight: 600;
    }}
    QTableWidget::item {{ padding: 6px 10px; border-bottom: 1px solid {p['line']}; }}
    QTableWidget::item:selected {{ background: {p['sel']}; color: {p['text']}; }}

    /* inputs */
    QLineEdit, QPlainTextEdit, QTextEdit, QComboBox {{
        background: {p['bg0']};
        border: 1px solid {p['line2']};
        border-radius: 8px;
        padding: 6px 9px;
        color: {p['text']};
        selection-background-color: {p['accent']};
    }}
    QComboBox::drop-down {{ border: none; width: 22px; }}
    QComboBox QAbstractItemView {{
        background: {p['bg1']};
        border: 1px solid {p['line2']};
        selection-background-color: {p['accent_dim']};
        color: {p['text']};
    }}

    /* scrollbars */
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {p['line2']}; border-radius: 5px; min-height: 30px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; }}
    QScrollBar::handle:horizontal {{ background: {p['line2']}; border-radius: 5px; min-width: 30px; }}

    /* status bar */
    QStatusBar {{
        background: {p['bg1']};
        color: {p['text3']};
        font-family: {MONO};
        font-size: 10px;
        border-top: 1px solid {p['line']};
    }}
    QStatusBar::item {{ border: none; }}

    /* menus */
    QMenuBar {{ background: {p['bg1']}; color: {p['text2']}; border-bottom: 1px solid {p['line']}; }}
    QMenuBar::item:selected {{ background: {p['bg2']}; }}
    QMenu {{ background: {p['bg1']}; color: {p['text']}; border: 1px solid {p['line2']}; }}
    QMenu::item:selected {{ background: {p['accent_dim']}; }}

    QToolTip {{
        background: {p['bg2']}; color: {p['text']};
        border: 1px solid {p['line2']}; padding: 4px 6px;
    }}
    """

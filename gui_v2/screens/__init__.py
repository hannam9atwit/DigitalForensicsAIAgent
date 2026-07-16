"""
gui_v2/screens

One module per screen. Every case screen subclasses base.Screen and talks to the
window through two signals (rail_changed, navigate) rather than to each other.
"""

from .base import Screen
from .case import CaseScreen
from .findings import FindingsScreen
from .evidence import EvidenceScreen
from .timeline import TimelineScreen
from .report import ReportScreen
from .chat import ChatScreen
from .audit import AuditScreen
from .settings import SettingsScreen
from .launch import LaunchScreen, AnalyzingScreen

__all__ = [
    "Screen", "CaseScreen", "FindingsScreen", "EvidenceScreen", "TimelineScreen",
    "ReportScreen", "ChatScreen", "AuditScreen", "SettingsScreen",
    "LaunchScreen", "AnalyzingScreen",
]

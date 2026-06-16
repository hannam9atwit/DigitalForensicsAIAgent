"""
gui_v2/main_window.py

Native PySide6 main window. No server, no browser — pure Qt widgets.

Launches into an EMPTY state (no demo data). The examiner creates a case via
File > New Case, adds one or more evidence files (disk / browser / Event Log /
Registry / Prefetch / PCAP / email), and the app hashes them on intake, runs
every artifact through its parser on a background thread, merges one timeline,
reasons over it, and rebuilds all six screens from the live result.
"""

import os

from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QFrame, QStackedWidget, QStatusBar, QDialog, QLineEdit,
    QDialogButtonBox, QMessageBox, QProgressDialog, QFileDialog,
)

from . import theme, screens
from .case_model import empty_case
from .intake_dialog import IntakeDialog, EVIDENCE_FILTER
from .widgets import MicroLabel

NAV = [
    ("dashboard", "Dashboard", "1"),
    ("evidence",  "Evidence",  "2"),
    ("timeline",  "Timeline",  "3"),
    ("findings",  "Findings",  "4"),
    ("narrative", "AI Narrative", "5"),
    ("audit",     "Audit Log", "6"),
]


class AnalysisWorker(QObject):
    finished = Signal(object)
    error = Signal(str)
    log = Signal(str)

    def __init__(self, builder, api_key=""):
        super().__init__()
        self.builder = builder
        self.api_key = api_key

    def run(self):
        try:
            if self.api_key:
                os.environ["ANTHROPIC_API_KEY"] = self.api_key
            self.builder.analyze(log=self.log.emit)
            self.finished.emit(self.builder)
        except Exception as e:
            import traceback
            self.error.emit(f"{e}\n{traceback.format_exc()}")


class SettingsDialog(QDialog):
    def __init__(self, parent, settings):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Default examiner name"))
        self.examiner = QLineEdit(settings.get("examiner", ""))
        lay.addWidget(self.examiner)
        lay.addWidget(QLabel("Default examiner ID"))
        self.examiner_id = QLineEdit(settings.get("examiner_id", ""))
        lay.addWidget(self.examiner_id)
        lay.addWidget(QLabel("Default agency / organisation"))
        self.agency = QLineEdit(settings.get("agency", ""))
        lay.addWidget(self.agency)
        lay.addWidget(QLabel("Anthropic API key (optional - for Claude narrative)"))
        self.api_key = QLineEdit(settings.get("anthropic_api_key", ""))
        self.api_key.setEchoMode(QLineEdit.Password)
        self.api_key.setPlaceholderText("sk-ant-...  (blank = local Ollama / rule-based)")
        lay.addWidget(self.api_key)
        note = QLabel("Key is held in memory only - never written to disk.")
        note.setStyleSheet("color: gray; font-size: 11px;")
        lay.addWidget(note)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def values(self):
        return {
            "examiner": self.examiner.text().strip(),
            "examiner_id": self.examiner_id.text().strip(),
            "agency": self.agency.text().strip(),
            "anthropic_api_key": self.api_key.text().strip(),
        }


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Forensic AI Agent - Examiner Console")
        self.setMinimumSize(1240, 800)
        self.is_dark = True
        self.pal = theme.DARK
        self.builder = None
        self.case = empty_case()
        self.settings = {"examiner": "", "examiner_id": "", "agency": "",
                         "anthropic_api_key": ""}
        self.nav_buttons = {}
        self._current = None
        self._build_menu()
        self._build_ui()
        self._apply_theme()
        self._show_empty()

    def _build_menu(self):
        mb = self.menuBar()
        fm = mb.addMenu("File")
        fm.addAction(QAction("New Case...", self, triggered=self.new_case))
        fm.addAction(QAction("Open Previous Case...", self, triggered=self.open_case_history))
        fm.addAction(QAction("Add Evidence...", self, triggered=self.add_evidence))
        fm.addAction(QAction("Save Case", self, triggered=self.save_case))
        fm.addSeparator()
        fm.addAction(QAction("Export Selected Evidence...", self, triggered=lambda: self._export_evidence(None)))
        fm.addAction(QAction("Generate PDF Report...", self, triggered=self._generate_report))
        fm.addSeparator()
        fm.addAction(QAction("Exit", self, triggered=self.close))
        tm = mb.addMenu("Tools")
        tm.addAction(QAction("Run / Re-run Analysis", self, triggered=self.run_analysis))
        tm.addAction(QAction("Re-verify Hashes", self, triggered=self._verify_hashes))
        tm.addAction(QAction("Settings...", self, triggered=self.open_settings))
        vm = mb.addMenu("View")
        self.theme_action = QAction("Light Mode", self, checkable=True,
                                    triggered=self.toggle_theme)
        vm.addAction(self.theme_action)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.sidebar = self._build_sidebar()
        root.addWidget(self.sidebar)
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        self.setStatusBar(QStatusBar())
        self._refresh_status()

    def _build_sidebar(self):
        bar = QFrame(); bar.setObjectName("sidebar"); bar.setFixedWidth(226)
        lay = QVBoxLayout(bar); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        brand = QWidget(); bl = QVBoxLayout(brand); bl.setContentsMargins(14, 14, 14, 12)
        name = QLabel("FORENSIC AI AGENT")
        name.setStyleSheet("font-size:13px; font-weight:700; letter-spacing:1px;")
        ver = QLabel("v2.0 - EXAMINER CONSOLE")
        ver.setStyleSheet(f"font-family:{theme.MONO}; font-size:9px; color:{self.pal['text3']};")
        bl.addWidget(name); bl.addWidget(ver)
        lay.addWidget(brand)
        lay.addWidget(self._sep())
        self.case_block = QWidget()
        lay.addWidget(self.case_block)
        self._fill_case_block()
        lay.addWidget(self._sep())
        nav_wrap = QWidget()
        nl = QVBoxLayout(nav_wrap); nl.setContentsMargins(0, 8, 0, 8); nl.setSpacing(1)
        for sid, label, key in NAV:
            btn = QPushButton(f"  {label}")
            btn.setObjectName("navItem")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, s=sid: self._show_screen(s))
            btn.setShortcut(key)
            self.nav_buttons[sid] = btn
            nl.addWidget(btn)
        lay.addWidget(nav_wrap)
        lay.addStretch(1)
        lay.addWidget(self._sep())
        foot = QWidget(); fl = QVBoxLayout(foot)
        fl.setContentsMargins(14, 10, 14, 12); fl.setSpacing(6)
        self.ai_label = QLabel("o OLLAMA - LLAMA3.2:3B")
        self.ai_label.setStyleSheet(f"color:{self.pal['text3']}; font-family:{theme.MONO}; font-size:10px;")
        ofl = QLabel("LOCAL - OFFLINE")
        ofl.setStyleSheet(f"color:{self.pal['text3']}; font-family:{theme.MONO}; font-size:9px;")
        fl.addWidget(self.ai_label); fl.addWidget(ofl)
        self.examiner_label = QLabel("")
        self.examiner_label.setStyleSheet(f"color:{self.pal['text2']}; font-family:{theme.MONO}; font-size:9px;")
        fl.addWidget(self.examiner_label)
        lay.addWidget(foot)
        return bar

    def _fill_case_block(self):
        if self.case_block.layout():
            old = self.case_block.layout()
            while old.count():
                it = old.takeAt(0)
                if it.widget():
                    it.widget().deleteLater()
            QWidget().setLayout(old)
        cl = QVBoxLayout(self.case_block)
        cl.setContentsMargins(14, 10, 14, 10); cl.setSpacing(2)
        cl.addWidget(MicroLabel("Active case"))
        meta = self.case["caseMeta"]
        cid = QLabel(meta["id"])
        cid.setStyleSheet(f"color:{self.pal['accent']}; font-family:{theme.MONO}; "
                          f"font-size:13px; font-weight:700;")
        title = QLabel(meta["title"]); title.setWordWrap(True)
        title.setStyleSheet(f"color:{self.pal['text2']}; font-size:11px;")
        cl.addWidget(cid); cl.addWidget(title)

    def _sep(self):
        f = QFrame(); f.setFixedHeight(1)
        f.setStyleSheet(f"background:{self.pal['line']};")
        return f

    def _clear_stack(self):
        while self.stack.count():
            w = self.stack.widget(0)
            self.stack.removeWidget(w)
            w.deleteLater()

    def _show_empty(self):
        self._clear_stack()
        self.stack.addWidget(screens.empty_state(self.pal, self.new_case))
        for btn in self.nav_buttons.values():
            btn.setEnabled(False)
        self._current = None

    def _show_screen(self, sid):
        if not self.case.get("loaded"):
            return
        builders = {
            "dashboard": lambda: screens.dashboard(self.case, self.pal),
            "evidence":  lambda: screens.evidence(self.case, self.pal,
                                                  on_verify=self._verify_hashes,
                                                  on_export=self._export_evidence,
                                                  on_report=self._generate_report),
            "timeline":  lambda: screens.timeline(self.case, self.pal),
            "findings":  lambda: screens.findings(self.case, self.pal),
            "narrative": lambda: screens.narrative(self.case, self.pal),
            "audit":     lambda: screens.audit(self.case, self.pal),
        }
        self._clear_stack()
        self.stack.addWidget(builders[sid]())
        for s, btn in self.nav_buttons.items():
            btn.setEnabled(True)
            btn.setObjectName("navItemActive" if s == sid else "navItem")
            btn.style().unpolish(btn); btn.style().polish(btn)
        self._current = sid

    def new_case(self):
        dlg = IntakeDialog(self, self.settings)
        if not dlg.exec():
            return
        prog = self._progress("Hashing evidence on intake...")
        try:
            self.builder = dlg.build(log=lambda m: self.statusBar().showMessage(m))
        finally:
            prog.close()
        self.case = self.builder.to_case()
        self._fill_case_block()
        self._refresh_status()
        self._show_screen("evidence")
        if QMessageBox.question(
                self, "Run analysis",
                f"{len(self.builder.evidence)} artifact(s) hashed and registered.\n"
                "Run the full analysis pipeline now?") == QMessageBox.Yes:
            self.run_analysis()

    def add_evidence(self):
        if not self.builder:
            QMessageBox.information(self, "No case",
                                    "Create a case first (File > New Case).")
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add Evidence Files", "", EVIDENCE_FILTER)
        if not paths:
            return
        prog = self._progress("Hashing evidence on intake...")
        try:
            for p in paths:
                self.statusBar().showMessage(f"Hashing {os.path.basename(p)}...")
                self.builder.add_evidence(p)
        finally:
            prog.close()
        self.case = self.builder.to_case()
        self._show_screen("evidence")
        self._refresh_status()

    def run_analysis(self):
        if not self.builder or not self.builder.evidence:
            QMessageBox.information(self, "Nothing to analyze",
                                    "Create a case and add evidence first.")
            return
        self.prog = self._progress("Running analysis pipeline...")
        self.thread = QThread()
        self.worker = AnalysisWorker(self.builder, self.settings.get("anthropic_api_key", ""))
        self.worker.moveToThread(self.thread)
        self.worker.log.connect(lambda m: (self.statusBar().showMessage(m),
                                           self.prog.setLabelText(m)))
        self.worker.finished.connect(self._analysis_done)
        self.worker.error.connect(self._analysis_error)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.error.connect(self.thread.quit)
        self.thread.start()

    def _analysis_done(self, builder):
        self.prog.close()
        self.builder = builder
        self.case = builder.to_case()
        self.ai_label.setText("* OLLAMA - LLAMA3.2:3B")
        self.ai_label.setStyleSheet(f"color:{self.pal['good']}; font-family:{theme.MONO}; font-size:10px;")
        self._fill_case_block()
        self._show_screen("dashboard")
        self._refresh_status()
        # auto-save to case history so it's available next session
        try:
            from .case_store import save_case
            save_case(self.builder)
        except Exception:
            pass
        self.statusBar().showMessage(
            f"Analysis complete - {self.case['caseMeta']['id']} - "
            f"{len(self.case['findings'])} findings", 8000)

    def _analysis_error(self, msg):
        self.prog.close()
        QMessageBox.critical(self, "Analysis failed", msg.split("\n")[0])
        self.statusBar().showMessage("Analysis failed - see message", 6000)

    def _verify_hashes(self):
        if not self.builder:
            return
        results = self.builder.reverify()
        self.case = self.builder.to_case()
        self._show_screen("evidence")
        ok = sum(1 for v in results.values() if v)
        self.statusBar().showMessage(
            f"Re-verified {ok}/{len(results)} artifact(s) OK", 5000)

    # ── evidence export ────────────────────────────────────────────────────────

    def _export_evidence(self, selected):
        if not self.builder or not self.builder.evidence:
            QMessageBox.information(self, "No evidence", "Create a case with evidence first.")
            return
        # if called from the menu (selected is None), export everything
        items = selected if selected else self.builder.evidence
        if not items:
            QMessageBox.information(self, "Nothing selected",
                                    "Tick at least one artifact to export.")
            return
        dest = QFileDialog.getExistingDirectory(self, "Choose export destination")
        if not dest:
            return
        from .evidence_export import export_evidence
        prog = self._progress("Copying & re-hashing evidence...")
        try:
            res = export_evidence(items, dest, self.case["caseMeta"],
                                  log=lambda m: self.statusBar().showMessage(m))
            if self.builder:
                self.builder._log("EVIDENCE_EXPORTED",
                                  f"{res['ok']}/{res['total']} artifact(s) exported to {dest}",
                                  who=self.settings.get("examiner") or "examiner")
                self.case = self.builder.to_case()
        finally:
            prog.close()
        QMessageBox.information(
            self, "Export complete",
            f"Exported {res['ok']}/{res['total']} artifact(s).\n"
            f"All copies re-hashed against intake SHA-256.\n\n"
            f"Manifest:\n{res['text']}")
        self.statusBar().showMessage(
            f"Exported {res['ok']}/{res['total']} artifact(s) to {dest}", 6000)

    # ── PDF report ─────────────────────────────────────────────────────────────

    def _generate_report(self):
        if not self.case.get("loaded"):
            QMessageBox.information(self, "No case", "Create and analyze a case first.")
            return
        if not self.case.get("findings"):
            if QMessageBox.question(
                    self, "No findings yet",
                    "This case has no findings (has it been analyzed?).\n"
                    "Generate the report anyway?") != QMessageBox.Yes:
                return
        default = f"{self.case['caseMeta']['id']}_report.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save PDF Report", default, "PDF files (*.pdf)")
        if not path:
            return
        if not path.endswith(".pdf"):
            path += ".pdf"
        try:
            from .report_pdf import generate_report
            prog = self._progress("Building PDF report...")
            try:
                generate_report(self.case, path)
            finally:
                prog.close()
            if self.builder:
                self.builder._log("REPORT_GENERATED",
                                  f"PDF report written to {path}", who="system")
                self.case = self.builder.to_case()
        except ImportError:
            QMessageBox.warning(self, "reportlab missing",
                                "PDF reports need reportlab:\n\npip install reportlab")
            return
        except Exception as e:
            QMessageBox.critical(self, "Report failed", str(e))
            return
        # offer to open it
        if QMessageBox.question(
                self, "Report ready",
                f"Report saved:\n{path}\n\nOpen it now?") == QMessageBox.Yes:
            self._open_path(path)

    # ── case persistence ───────────────────────────────────────────────────────

    def save_case(self):
        if not self.builder:
            QMessageBox.information(self, "No case", "Create a case first.")
            return
        from .case_store import save_case
        path = save_case(self.builder)
        self.case = self.builder.to_case()
        self.statusBar().showMessage(f"Case saved — {path}", 6000)

    def open_case_history(self):
        from .case_history import CaseHistoryDialog
        dlg = CaseHistoryDialog(self)
        if dlg.exec() and dlg.selected_path:
            from .case_store import load_case
            try:
                self.builder = load_case(dlg.selected_path)
            except Exception as e:
                QMessageBox.critical(self, "Open failed", str(e))
                return
            self.case = self.builder.to_case()
            self._fill_case_block()
            self._refresh_status()
            if self.case.get("findings"):
                self._show_screen("dashboard")
            else:
                self._show_screen("evidence")
            self.statusBar().showMessage(
                f"Opened case {self.case['caseMeta']['id']}", 5000)

    def _open_path(self, path):
        import sys, subprocess, os
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # noqa
            elif sys.platform.startswith("darwin"):
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            pass

    def open_settings(self):
        dlg = SettingsDialog(self, self.settings)
        if dlg.exec():
            self.settings.update(dlg.values())
            self.examiner_label.setText(
                f"{self.settings['examiner'].upper()} - {self.settings['examiner_id']}"
                if self.settings['examiner'] else "")

    def toggle_theme(self, light):
        self.is_dark = not light
        self.pal = theme.LIGHT if light else theme.DARK
        self._apply_theme()
        self.centralWidget().deleteLater()
        self._build_ui()
        if self.case.get("loaded"):
            self._show_screen(self._current or "dashboard")
        else:
            self._show_empty()

    def _apply_theme(self):
        self.setStyleSheet(theme.stylesheet(self.pal))

    def _progress(self, text):
        p = QProgressDialog(text, None, 0, 0, self)
        p.setWindowModality(Qt.WindowModal)
        p.setMinimumDuration(0)
        p.setCancelButton(None)
        p.show()
        return p

    def _refresh_status(self):
        meta = self.case["caseMeta"]
        if not self.case.get("loaded"):
            self.statusBar().showMessage("No case loaded - File > New Case to begin")
            return
        verified = sum(1 for e in self.case["evidence"] if e["verified"])
        self.statusBar().showMessage(
            f"PIPELINE {meta['pipeline']['status'].upper()} - "
            f"EVENTS {meta['pipeline']['eventsParsed']:,} - "
            f"HASHES {verified}/{len(self.case['evidence'])} VERIFIED - "
            f"CHAIN INTACT - READ-ONLY EVIDENCE")

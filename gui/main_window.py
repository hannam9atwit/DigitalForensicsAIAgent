"""
gui/main_window.py
"""
import sys
import os
import subprocess
import datetime

from PySide6.QtCore  import QThread, Signal, QObject, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QFileDialog, QProgressBar, QTabWidget,
    QTableWidget, QTableWidgetItem, QTextBrowser, QMenuBar,
    QMessageBox, QDialog, QLabel, QLineEdit, QCheckBox,
    QDialogButtonBox, QSplashScreen, QFrame, QStatusBar,
)
from PySide6.QtGui import QAction, QPixmap, QColor, QFont, QDragEnterEvent, QDropEvent

from pipeline.run_pipeline import run_pipeline


# ── Pipeline worker ───────────────────────────────────────────────────────────

class PipelineWorker(QObject):
    finished = Signal(object, str)
    error    = Signal(str)
    log      = Signal(str)

    def __init__(self, path):
        super().__init__()
        self.path = path

    def run(self):
        try:
            analysis, report_path = run_pipeline(self.path, self.log.emit)
            self.finished.emit(analysis, report_path)
        except Exception as e:
            import traceback
            self.error.emit(f"{e}\n{traceback.format_exc()}")


# ── Settings dialog ───────────────────────────────────────────────────────────

class SettingsDialog(QDialog):
    def __init__(self, parent, settings):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(480)
        self.settings = settings
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        layout.addWidget(QLabel("Anthropic API Key (optional — for Claude narrative):"))
        key_row = QHBoxLayout()
        self.api_key_edit = QLineEdit(settings.get("anthropic_api_key", ""))
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.api_key_edit.setPlaceholderText("sk-ant-…  (leave blank to use local Ollama)")
        key_row.addWidget(self.api_key_edit)
        self.show_key_btn = QPushButton("Show")
        self.show_key_btn.setFixedWidth(56)
        self.show_key_btn.setCheckable(True)
        self.show_key_btn.toggled.connect(
            lambda v: (self.api_key_edit.setEchoMode(QLineEdit.Normal if v else QLineEdit.Password),
                       self.show_key_btn.setText("Hide" if v else "Show")))
        key_row.addWidget(self.show_key_btn)
        layout.addLayout(key_row)

        note = QLabel("Key is stored in memory only — never written to disk.")
        note.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(note)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine); sep.setFrameShadow(QFrame.Sunken)
        layout.addWidget(sep)

        layout.addWidget(QLabel("Default Output Folder:"))
        self.output_edit = QLineEdit(settings.get("default_output_folder", ""))
        layout.addWidget(self.output_edit)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        layout.addWidget(browse)

        self.auto_open = QCheckBox("Automatically open report folder after analysis")
        self.auto_open.setChecked(settings.get("auto_open_report", False))
        layout.addWidget(self.auto_open)

        self.light_mode = QCheckBox("Use Light Mode")
        self.light_mode.setChecked(settings.get("light_mode", False))
        layout.addWidget(self.light_mode)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self.output_edit.setText(folder)

    def get_settings(self):
        return {
            "anthropic_api_key":     self.api_key_edit.text().strip(),
            "default_output_folder": self.output_edit.text(),
            "auto_open_report":      self.auto_open.isChecked(),
            "light_mode":            self.light_mode.isChecked(),
        }


# ── Main window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):

    SUPPORTED_FILTERS = (
        "Forensic Images (*.e01 *.ex01 *.s01 *.img *.dd *.raw);;"
        "EnCase E01 (*.e01 *.ex01);;"
        "Raw Images (*.img *.dd *.raw);;"
        "Browser Artifacts (History Cookies Downloads);;"
        "All Files (*.*)"
    )

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Forensic AI Agent")
        self.setMinimumSize(1100, 720)
        self.setAcceptDrops(True)

        self.artifact_path    = None
        self.last_report_path = None
        self.settings = {
            "anthropic_api_key": "", "default_output_folder": "",
            "auto_open_report": False, "light_mode": False,
        }

        self._build_menu()
        self._build_ui()
        self._apply_dark_theme()

    # ── Menu ──────────────────────────────────────────────────────────────────

    def _build_menu(self):
        mb = self.menuBar()

        fm = mb.addMenu("File")
        fm.addAction("Open Artifact…", self.select_artifact)
        fm.addSeparator()
        fm.addAction("Exit", self.close)

        tm = mb.addMenu("Tools")
        tm.addAction("Settings",       self.open_settings_dialog)
        tm.addAction("Re-run Analysis",self.run_analysis)
        tm.addAction("Clear Logs",     lambda: self.log.clear())

        vm = mb.addMenu("View")
        self.light_action = QAction("Light Mode", self, checkable=True)
        self.light_action.triggered.connect(self.toggle_light_mode)
        vm.addAction(self.light_action)

        hm = mb.addMenu("Help")
        hm.addAction("About", self.show_about)
        hm.addAction("SleuthKit / E01 Setup Guide", self.show_e01_guide)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # ── Top bar ───────────────────────────────────────────────────────────
        top = QHBoxLayout()

        self.select_btn = QPushButton("📂  Open Artifact")
        self.select_btn.setFixedHeight(36)
        self.select_btn.clicked.connect(self.select_artifact)
        top.addWidget(self.select_btn)

        self.artifact_label = QLabel("No artifact selected — drag & drop or click Open Artifact")
        self.artifact_label.setStyleSheet("color: #888; font-style: italic;")
        top.addWidget(self.artifact_label, stretch=1)

        self.run_btn = QPushButton("▶  Run Analysis")
        self.run_btn.setFixedHeight(36)
        self.run_btn.setEnabled(False)
        self.run_btn.clicked.connect(self.run_analysis)
        top.addWidget(self.run_btn)

        root.addLayout(top)

        # ── Progress bar ──────────────────────────────────────────────────────
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        self.progress.setFixedHeight(4)
        root.addWidget(self.progress)

        # ── Tabs ──────────────────────────────────────────────────────────────
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)

        # Timeline
        self.timeline_table = QTableWidget()
        self.timeline_table.setColumnCount(3)
        self.timeline_table.setHorizontalHeaderLabels(["Timestamp", "Source", "Details"])
        self.timeline_table.setAlternatingRowColors(True)
        self.timeline_table.setSortingEnabled(True)
        self.timeline_table.horizontalHeader().setStretchLastSection(True)
        self.timeline_table.horizontalHeader().setDefaultSectionSize(200)
        self.timeline_table.verticalHeader().setVisible(False)
        self.tabs.addTab(self.timeline_table, "Timeline")

        # Findings
        self.findings_view = QTextBrowser()
        self.tabs.addTab(self.findings_view, "Findings")

        # AI Narrative
        self.narrative_view = QTextBrowser()
        self.tabs.addTab(self.narrative_view, "AI Narrative")

        # Report
        report_widget = QWidget()
        rl = QVBoxLayout(report_widget)
        self.report_view = QTextBrowser()
        rl.addWidget(self.report_view)

        btn_row = QHBoxLayout()
        self.open_report_btn = QPushButton("Open Report Folder")
        self.open_report_btn.clicked.connect(self.open_report_location)
        self.open_report_btn.setEnabled(False)
        btn_row.addWidget(self.open_report_btn)

        self.open_pdf_btn = QPushButton("Open PDF Report")
        self.open_pdf_btn.clicked.connect(self.open_pdf_report)
        self.open_pdf_btn.setEnabled(False)
        btn_row.addWidget(self.open_pdf_btn)

        rl.addLayout(btn_row)
        self.tabs.addTab(report_widget, "Report")

        # Logs
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Courier New", 10))
        self.tabs.addTab(self.log, "Logs")

        # Status bar
        self.status = self.statusBar()
        self.status.showMessage("Ready — open a disk image or browser artifact to begin")

    # ── Artifact selection ────────────────────────────────────────────────────

    def select_artifact(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Forensic Artifact", "", self.SUPPORTED_FILTERS)
        if path:
            self._set_artifact(path)

    def _set_artifact(self, path: str):
        self.artifact_path = path
        size_mb = os.path.getsize(path) / 1_048_576 if os.path.exists(path) else 0
        ext     = os.path.splitext(path)[1].upper() or "Unknown"
        name    = os.path.basename(path)
        self.artifact_label.setText(
            f"{name}  |  {ext}  |  {size_mb:,.1f} MB"
        )
        self.artifact_label.setStyleSheet("color: #4fc3f7; font-style: normal; font-weight: bold;")
        self.run_btn.setEnabled(True)
        self.log.append(f"[+] Artifact: {path}")
        self.log.append(f"    Type: {ext}  |  Size: {size_mb:,.1f} MB")
        if ext == ".E01":
            self.log.append(
                "[i] E01 image detected. SleuthKit will use the -i ewf driver.\n"
                "    Make sure your fls/mmls binaries were compiled with libewf support."
            )

    # ── Analysis ──────────────────────────────────────────────────────────────

    def run_analysis(self):
        if not self.artifact_path:
            self.log.append("[!] No artifact selected.")
            return

        api_key = self.settings.get("anthropic_api_key", "").strip()
        if api_key:
            os.environ["ANTHROPIC_API_KEY"] = api_key
            self.log.append("[+] Using Anthropic API key from settings.")
        elif os.environ.get("ANTHROPIC_API_KEY"):
            self.log.append("[+] Using Anthropic API key from environment.")
        else:
            self.log.append("[~] No API key — will use Ollama (local) or deterministic fallback.")

        self.log.append(f"[*] Starting analysis: {self.artifact_path}")
        self.status.showMessage("Running analysis…")

        self.select_btn.setEnabled(False)
        self.run_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.tabs.setCurrentIndex(4)   # jump to Logs tab

        self.thread = QThread()
        self.worker = PipelineWorker(self.artifact_path)
        self.worker.moveToThread(self.thread)
        self.worker.log.connect(self.log.append)
        self.worker.log.connect(self.status.showMessage)
        self.worker.finished.connect(self.analysis_complete)
        self.worker.error.connect(self.analysis_error)
        self.thread.started.connect(self.worker.run)
        self.thread.start()

    # ── Results ───────────────────────────────────────────────────────────────

    def analysis_complete(self, analysis, report_path):
        self.log.append(f"[✓] Done — report: {report_path}")

        # Timeline tab
        events = analysis.get("timeline", {}).get("events", [])
        self.timeline_table.setRowCount(len(events))
        for row, event in enumerate(events):
            raw_ts = event.get("timestamp")
            try:
                ts = datetime.datetime.fromtimestamp(raw_ts).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                ts = str(raw_ts)
            details = (
                f"path: {event.get('path','')}\n"
                f"inode: {event.get('inode','')}\n"
                f"mode: {event.get('mode','')}\n"
                f"size: {event.get('size','')}"
            )
            self.timeline_table.setItem(row, 0, QTableWidgetItem(ts))
            self.timeline_table.setItem(row, 1, QTableWidgetItem(str(event.get("source", ""))))
            self.timeline_table.setItem(row, 2, QTableWidgetItem(details))
        self.timeline_table.resizeRowsToContents()

        # Findings tab
        severity_labels = {4: "Critical", 3: "High", 2: "Medium", 1: "Low"}
        groups = {4: [], 3: [], 2: [], 1: []}
        for f in analysis.get("findings", []):
            groups.setdefault(f.get("severity", 1), []).append(f)

        html = "<h2>Findings by Severity</h2>"
        for sev in [4, 3, 2, 1]:
            color = self._severity_color(sev)
            label = severity_labels[sev]
            html += (
                f"<details style='margin-bottom:10px;'>"
                f"<summary style='font-size:15px;font-weight:bold;"
                f"background:{color};padding:6px;border-radius:4px;'>"
                f"{label} ({len(groups[sev])})</summary>"
            )
            if not groups[sev]:
                html += "<p style='margin-left:16px;color:#888'>No findings.</p>"
            else:
                for f in groups[sev]:
                    reason = f.get("reason") or f.get("path") or "(no details)"
                    html += f"<p style='margin-left:16px'><b>{f['type']}</b>: {reason}</p>"
            html += "</details>"
        self.findings_view.setHtml(html)

        # AI Narrative
        narrative     = analysis.get("narrative", "No narrative available.")
        narrative_html = self._md_to_html(narrative)
        self.narrative_view.setHtml(narrative_html)

        # Report tab
        try:
            with open(report_path, "r", encoding="utf-8") as fh:
                self.report_view.setPlainText(fh.read())
            self.last_report_path = report_path
            self.open_report_btn.setEnabled(True)
            pdf_path = report_path.replace(".md", ".pdf")
            if os.path.exists(pdf_path):
                self.open_pdf_btn.setEnabled(True)
            else:
                self.open_pdf_btn.setToolTip("PDF not generated — run: pip install reportlab")
        except Exception:
            self.report_view.setPlainText("Could not load report file.")

        self._cleanup_thread()
        self.status.showMessage(f"Analysis complete — {report_path}")
        self.tabs.setCurrentIndex(2)   # jump to AI Narrative

        if self.settings.get("auto_open_report"):
            self.open_report_location()

    def analysis_error(self, message):
        self.log.append(f"[!] Error: {message}")
        self._cleanup_thread()
        self.status.showMessage("Error during analysis — see Logs tab")

    def _cleanup_thread(self):
        self.thread.quit()
        self.thread.wait()
        self.select_btn.setEnabled(True)
        self.run_btn.setEnabled(True)
        self.progress.setVisible(False)

    # ── Drag & Drop ───────────────────────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            self._set_artifact(urls[0].toLocalFile())

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _md_to_html(self, text: str) -> str:
        import re
        lines = text.split("\n")
        out   = []
        for line in lines:
            if   line.startswith("### "): out.append(f"<h3>{line[4:]}</h3>")
            elif line.startswith("## "):  out.append(f"<h2>{line[3:]}</h2>")
            elif line.startswith("# "):   out.append(f"<h1>{line[2:]}</h1>")
            elif line.startswith(("• ", "- ", "* ")):
                c = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line[2:])
                c = re.sub(r"`(.+?)`",        r"<code>\1</code>", c)
                out.append(f"<li>{c}</li>")
            elif not line.strip():
                out.append("<br>")
            else:
                line = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line)
                line = re.sub(r"`(.+?)`",        r"<code>\1</code>", line)
                out.append(f"<p>{line}</p>")
        return ("<html><body style='font-family:sans-serif;padding:14px;'>"
                + "\n".join(out) + "</body></html>")

    @staticmethod
    def _severity_color(sev: int) -> str:
        return {4: "#c0392b", 3: "#e67e22", 2: "#f1c40f", 1: "#27ae60"}.get(sev, "#555")

    def open_report_location(self):
        if not self.last_report_path:
            return
        folder = os.path.dirname(os.path.abspath(self.last_report_path))
        if   sys.platform.startswith("win"):    subprocess.Popen(f'explorer "{folder}"')
        elif sys.platform.startswith("darwin"): subprocess.Popen(["open", folder])
        else:                                   subprocess.Popen(["xdg-open", folder])

    def open_pdf_report(self):
        if not self.last_report_path:
            return
        pdf_path = os.path.abspath(self.last_report_path.replace(".md", ".pdf"))
        if not os.path.exists(pdf_path):
            QMessageBox.warning(self, "PDF not found",
                "PDF was not generated.\nRun:  pip install reportlab\nthen re-run the analysis.")
            return
        if   sys.platform.startswith("win"):    os.startfile(pdf_path)
        elif sys.platform.startswith("darwin"): subprocess.Popen(["open", pdf_path])
        else:                                   subprocess.Popen(["xdg-open", pdf_path])

    def open_settings_dialog(self):
        dlg = SettingsDialog(self, self.settings)
        if dlg.exec():
            self.settings = dlg.get_settings()
            self.light_action.setChecked(self.settings["light_mode"])
            self.toggle_light_mode(self.settings["light_mode"])

    def toggle_light_mode(self, enabled: bool):
        if enabled:
            self.setStyleSheet("""
                QMainWindow,QWidget{background:#f5f5f5;color:#111}
                QTextEdit,QTextBrowser{background:#fff;color:#111;border:1px solid #ccc}
                QTableWidget{background:#fff;color:#111;gridline-color:#ddd}
                QHeaderView::section{background:#e8e8e8;color:#111;padding:4px;border:1px solid #ccc}
                QPushButton{background:#e0e0e0;color:#111;border:1px solid #bbb;padding:5px;border-radius:4px}
                QPushButton:hover{background:#d0d0d0}
                QTabBar::tab{background:#ddd;color:#111;padding:6px 12px;border-radius:4px 4px 0 0}
                QTabBar::tab:selected{background:#fff;color:#000}
            """)
        else:
            self._apply_dark_theme()

    def _apply_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow,QWidget{background:#1e1e2e;color:#cdd6f4}
            QTextEdit,QTextBrowser{background:#181825;color:#cdd6f4;border:1px solid #45475a;font-size:13px}
            QTableWidget{background:#181825;color:#cdd6f4;gridline-color:#313244}
            QHeaderView::section{background:#313244;color:#cdd6f4;padding:5px;border:1px solid #45475a}
            QPushButton{background:#313244;color:#cdd6f4;border:1px solid #45475a;
                        padding:6px 14px;border-radius:5px;font-size:13px}
            QPushButton:hover{background:#45475a}
            QPushButton:disabled{background:#1e1e2e;color:#585b70}
            QTabWidget::pane{border:1px solid #45475a}
            QTabBar::tab{background:#313244;color:#cdd6f4;padding:7px 14px;
                         border-radius:5px 5px 0 0;margin-right:2px}
            QTabBar::tab:selected{background:#89b4fa;color:#1e1e2e;font-weight:bold}
            QMenuBar{background:#181825;color:#cdd6f4}
            QMenuBar::item:selected{background:#313244}
            QMenu{background:#1e1e2e;color:#cdd6f4;border:1px solid #45475a}
            QMenu::item:selected{background:#313244}
            QProgressBar{background:#313244;border:none;border-radius:2px}
            QProgressBar::chunk{background:#89b4fa}
            QStatusBar{background:#181825;color:#6c7086}
            QLabel{color:#cdd6f4}
            QLineEdit{background:#181825;color:#cdd6f4;border:1px solid #45475a;
                      padding:4px;border-radius:4px}
            QDialog{background:#1e1e2e}
        """)

    def show_about(self):
        QMessageBox.information(self, "About Forensic AI Agent",
            "Forensic AI Agent  v1.1\n\n"
            "Supports: E01, EX01, IMG, DD, RAW + Chrome browser artefacts\n"
            "AI: Ollama (local) → Claude API → deterministic fallback\n\n"
            "Built with Python · PySide6 · SleuthKit · Ollama")

    def show_e01_guide(self):
        QMessageBox.information(self, "E01 / SleuthKit Setup Guide",
            "To analyse E01 images you need SleuthKit compiled with libewf.\n\n"
            "WINDOWS:\n"
            "  Download the pre-built TSK + libewf binaries from:\n"
            "  https://github.com/msuhanov/TSK-win-libewf/releases\n"
            "  Place fls.exe, mmls.exe, icat.exe, ils.exe into bin\\sleuthkit\\\n\n"
            "LINUX:\n"
            "  sudo apt install sleuthkit libewf-dev ewf-tools\n"
            "  (or build TSK from source with --with-libewf)\n\n"
            "VERIFY:\n"
            "  Run:  fls -i ewf your_image.e01\n"
            "  If it lists files — you're good to go.")
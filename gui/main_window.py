import sys
import os
import subprocess
import datetime

from PySide6.QtCore import (
    QThread,
    Signal,
    QObject,
    Qt,
    QTimer
)
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QPushButton,
    QTextEdit,
    QFileDialog,
    QProgressBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QMenuBar,
    QMessageBox,
    QDialog,
    QLabel,
    QLineEdit,
    QCheckBox,
    QDialogButtonBox,
    QSplashScreen
)
from PySide6.QtGui import (
    QAction,
    QPixmap
)
from pipeline.run_pipeline import run_pipeline

class PipelineWorker(QObject):
    finished = Signal(object, str)   # analysis, report_path
    error = Signal(str)
    log = Signal(str)

    def __init__(self, path):
        super().__init__()
        self.path = path


    def run(self):
        from pipeline.run_pipeline import run_pipeline
        try:
            analysis, report_path = run_pipeline(self.path, self.log.emit)
            self.finished.emit(analysis, report_path)
        except Exception as e:
            self.error.emit(str(e))

class SettingsDialog(QDialog):
    def __init__(self, parent, settings):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.settings = settings

        layout = QVBoxLayout(self)

        # Default output folder
        layout.addWidget(QLabel("Default Output Folder:"))
        self.output_edit = QLineEdit(settings["default_output_folder"])
        layout.addWidget(self.output_edit)

        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self.browse_folder)
        layout.addWidget(browse_btn)

        # Auto-open report
        self.auto_open_checkbox = QCheckBox("Automatically open report after analysis")
        self.auto_open_checkbox.setChecked(settings["auto_open_report"])
        layout.addWidget(self.auto_open_checkbox)

        # Light mode preference
        self.light_mode_checkbox = QCheckBox("Use Light Mode")
        self.light_mode_checkbox.setChecked(settings["light_mode"])
        layout.addWidget(self.light_mode_checkbox)

        # OK / Cancel buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            self.output_edit.setText(folder)

    def get_settings(self):
        return {
            "default_output_folder": self.output_edit.text(),
            "auto_open_report": self.auto_open_checkbox.isChecked(),
            "light_mode": self.light_mode_checkbox.isChecked()
        }


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Forensic AI Agent")
        self.artifact_label = QLabel("No artifact selected.")
        self.setAcceptDrops(True)

        # Status Bar
        self.status = self.statusBar()
        self.status.showMessage("Ready")

        # Menu Bar
        menu_bar = self.menuBar()

        # -------------------------
        # File Menu
        # -------------------------
        file_menu = menu_bar.addMenu("File")

        open_action = file_menu.addAction("Open Artifact")
        open_action.triggered.connect(self.select_artifact)

        exit_action = file_menu.addAction("Exit")
        exit_action.triggered.connect(self.close)

        # -------------------------
        # Tools Menu
        # -------------------------
        tools_menu = menu_bar.addMenu("Tools")

        settings_action = tools_menu.addAction("Settings")
        settings_action.triggered.connect(self.open_settings_dialog)
        rerun_action = tools_menu.addAction("Re-run Analysis")
        rerun_action.triggered.connect(self.run_analysis)

        clear_logs_action = tools_menu.addAction("Clear Logs")
        clear_logs_action.triggered.connect(lambda: self.log.clear())

        # -------------------------
        # View Menu
        # -------------------------
        view_menu = menu_bar.addMenu("View")

        self.light_mode_action = QAction("Light Mode", self, checkable=True)
        self.light_mode_action.triggered.connect(self.toggle_light_mode)
        view_menu.addAction(self.light_mode_action)

        # -------------------------
        # Help Menu
        # -------------------------
        help_menu = menu_bar.addMenu("Help")

        about_action = help_menu.addAction("About")
        about_action.triggered.connect(self.show_about_dialog)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout()
        central.setLayout(layout)

        # Buttons
        self.select_button = QPushButton("Select Artifact")
        self.run_button = QPushButton("Run Analysis")

        # Log output
        self.log = QTextEdit()
        self.log.setReadOnly(True)

        # Add widgets to layout
        layout.addWidget(self.select_button)
        layout.addWidget(self.run_button)
        layout.addWidget(self.log)

        # Progress bar
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # Indeterminate mode
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # Connect signals
        self.select_button.clicked.connect(self.select_artifact)
        self.run_button.clicked.connect(self.run_analysis)

        # Tabs
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Timeline tab
        self.timeline_table = QTableWidget()
        self.timeline_table.setColumnCount(3)
        self.timeline_table.setHorizontalHeaderLabels(["Timestamp", "Source", "Details"])

        self.timeline_table.setAlternatingRowColors(True)
        self.timeline_table.setSortingEnabled(True)
        self.timeline_table.horizontalHeader().setStretchLastSection(True)
        self.timeline_table.horizontalHeader().setDefaultSectionSize(200)
        self.timeline_table.verticalHeader().setVisible(False)
        self.timeline_table.setWordWrap(True)

        self.tabs.addTab(self.timeline_table, "Timeline")

        # Findings tab
        self.findings_view = QTextBrowser()
        self.tabs.addTab(self.findings_view, "Findings")

        # Report tab
        # Report tab layout
        self.report_container = QWidget()
        report_layout = QVBoxLayout(self.report_container)

        self.report_view = QTextBrowser()
        report_layout.addWidget(self.report_view)

        # AI Narrative tab
        self.narrative_view = QTextBrowser()
        self.tabs.addTab(self.narrative_view, "AI Narrative")

        # Open Report button
        self.open_report_button = QPushButton("Open Report in Folder")
        self.open_report_button.clicked.connect(self.open_report_location)
        self.open_report_button.setEnabled(False)  # Disabled until a report exists
        report_layout.addWidget(self.open_report_button)

        self.tabs.addTab(self.report_container, "Report")

        # Logs tab (move your existing log panel here)
        self.tabs.addTab(self.log, "Logs")

        # State
        self.artifact_path = None

        # Default settings
        self.settings = {
            "default_output_folder": "",
            "auto_open_report": False,
            "light_mode": False
        }

    def select_artifact(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Artifact",
            "",
            "All Files (*.*)"
        )
        if path:
            self.artifact_path = path
            self.log.append(f"[+] Selected artifact: {path}")

    def run_analysis(self):
        if not self.artifact_path:
            self.log.append("[!] No artifact selected.")
            return

        self.log.append(f"[*] Running analysis on: {self.artifact_path}")
        self.status.showMessage("Running analysis…")

        # Disable buttons
        self.select_button.setEnabled(False)
        self.run_button.setEnabled(False)

        # Show progress bar
        self.progress.setVisible(True)

        # Create worker + thread
        self.thread = QThread()
        self.worker = PipelineWorker(self.artifact_path)
        self.worker.moveToThread(self.thread)

        # Connect signals
        self.worker.log.connect(self.log.append)
        self.worker.log.connect(self.status.showMessage)
        self.worker.finished.connect(self.analysis_complete)
        self.worker.error.connect(self.analysis_error)
        self.thread.started.connect(self.worker.run)

        # Start thread
        self.thread.start()

    def analysis_complete(self, analysis, report_path):
        self.log.append(f"[✓] Analysis complete. Report saved to: {report_path}")

        # -----------------------------
        # Populate Timeline Tab
        # -----------------------------
        events = analysis["timeline"]["events"]
        self.timeline_table.setRowCount(len(events))

        for row, event in enumerate(events):
            raw_ts = event["timestamp"]
            # If it's a Unix timestamp, convert; otherwise just str()
            try:
                ts = datetime.datetime.fromtimestamp(raw_ts).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                ts = str(raw_ts)

            src = event["source"]
            details = (
                f"path: {event.get('path', '')}\n"
                f"inode: {event.get('inode', '')}\n"
                f"mode: {event.get('mode', '')}\n"
                f"size: {event.get('size', '')}\n"
            )

            self.timeline_table.setItem(row, 0, QTableWidgetItem(ts))
            self.timeline_table.setItem(row, 1, QTableWidgetItem(src))
            self.timeline_table.setItem(row, 2, QTableWidgetItem(details))

        # -----------------------------
        # Populate Findings Tab
        # -----------------------------
        groups = {4: [], 3: [], 2: [], 1: []}
        for f in analysis["findings"]:
            sev = f.get("severity", 1)
            groups.setdefault(sev, []).append(f)

        html = "<h2>Findings by Severity</h2>"

        severity_labels = {
            4: "Critical",
            3: "High",
            2: "Medium",
            1: "Low"
        }

        for sev in [4, 3, 2, 1]:
            color = self.severity_color(sev)
            label = severity_labels[sev]

            html += (
                f"<details style='margin-bottom:10px;'>"
                f"<summary style='font-size:16px; font-weight:bold; "
                f"background-color:{color}; padding:6px; border-radius:4px;'>"
                f"{label} Severity ({len(groups[sev])})"
                f"</summary>"
            )

            if not groups[sev]:
                html += "<p style='margin-left:20px;'>No findings in this category.</p>"
            else:
                for f in groups[sev]:
                    reason = f.get('reason') or f.get('path') or "(no details)"
                    html += (
                        f"<p style='margin-left:20px;'>"
                        f"<b>{f['type']}</b>: {reason}"
                        f"</p>"
                    )

            html += "</details>"

        self.findings_view.setHtml(html)

        # -----------------------------
        # Populate AI Narrative Tab
        # -----------------------------
        narrative = analysis.get("narrative", "No narrative available.")

        # Convert newlines to HTML line breaks for readability
        narrative_html = narrative.replace("\n", "<br>")

        self.narrative_view.setHtml(narrative_html)

        # -----------------------------
        # Populate Report Tab
        # -----------------------------
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                report_text = f.read()
            self.report_view.setText(report_text)
            # Save report path for the button
            self.last_report_path = report_path
            self.open_report_button.setEnabled(True)

        except:
            self.report_view.setText("Could not load report file.")

        # -----------------------------
        # Cleanup Thread + UI
        # -----------------------------
        self.thread.quit()
        self.thread.wait()

        self.select_button.setEnabled(True)
        self.run_button.setEnabled(True)
        self.progress.setVisible(False)

        self.status.showMessage(f"Analysis complete — report saved")

    def analysis_error(self, message):
        self.log.append(f"[!] Error during analysis: {message}")

        # Cleanup
        self.thread.quit()
        self.thread.wait()

        # Re-enable buttons
        self.select_button.setEnabled(True)
        self.run_button.setEnabled(True)

        # Hide progress bar
        self.progress.setVisible(False)

        self.status.showMessage("Error during analysis")

    def show_about_dialog(self):
        QMessageBox.information(
            self,
            "About Forensic AI Agent",
            "Forensic AI Agent\nVersion 1.0\n\nDeveloped by Michael, Aiden, and Ellie.\nPowered by Python + PySide6."
        )

    def toggle_light_mode(self, enabled):
        if enabled:
            # Apply light theme
            light_stylesheet = """
                QMainWindow {
                    background-color: #f2f2f2;
                    color: #000000;
                }
                QWidget {
                    background-color: #ffffff;
                    color: #000000;
                }
                QTextEdit, QTextBrowser {
                    background-color: #ffffff;
                    color: #000000;
                    border: 1px solid #cccccc;
                }
                QTableWidget {
                    background-color: #ffffff;
                    color: #000000;
                    gridline-color: #cccccc;
                }
                QHeaderView::section {
                    background-color: #e6e6e6;
                    color: #000000;
                    padding: 4px;
                    border: 1px solid #cccccc;
                }
                QPushButton {
                    background-color: #e6e6e6;
                    color: #000000;
                    border: 1px solid #bbbbbb;
                    padding: 5px;
                }
                QPushButton:hover {
                    background-color: #dcdcdc;
                }
                QMenuBar {
                    background-color: #f2f2f2;
                    color: #000000;
                }
                QMenuBar::item:selected {
                    background-color: #e6e6e6;
                }
                QMenu {
                    background-color: #ffffff;
                    color: #000000;
                }
                QMenu::item:selected {
                    background-color: #e6e6e6;
                }
            """
            self.setStyleSheet(light_stylesheet)
        else:
            # Reset to system theme (dark on your machine)
            self.setStyleSheet("""
                QTextBrowser {
                    padding: 8px;
                    font-size: 14px;
                }
                QTableWidget {
                    font-size: 13px;
                }
                QTableWidget::item {
                    padding: 4px;
                }
            """)

    def open_report_location(self):
        if not hasattr(self, "last_report_path"):
            return

        path = os.path.abspath(self.last_report_path)
        folder = os.path.dirname(path)

        if sys.platform.startswith("win"):
            subprocess.Popen(f'explorer "{folder}"')
        elif sys.platform.startswith("darwin"):
            subprocess.Popen(["open", folder])
        else:
            subprocess.Popen(["xdg-open", folder])

    def open_settings_dialog(self):
        dialog = SettingsDialog(self, self.settings)
        if dialog.exec():
            self.settings = dialog.get_settings()

            # Apply light mode immediately
            if self.settings["light_mode"]:
                self.light_mode_action.setChecked(True)
                self.toggle_light_mode(True)
            else:
                self.light_mode_action.setChecked(False)
                self.toggle_light_mode(False)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if not urls:
            return

        file_path = urls[0].toLocalFile()

        # Update stored path
        self.artifact_path = file_path

        # Update the label (THIS is the correct widget)
        self.artifact_label.setText(f"Selected: {file_path}")

        # Log it
        self.log.append(f"[+] Dropped artifact: {file_path}")

        # Enable Run button
        self.run_button.setEnabled(True)

    def severity_color(self, sev):
        return {
            4: "#ff4d4d",  # Critical - red
            3: "#ff944d",  # High - orange
            2: "#ffd24d",  # Medium - yellow
            1: "#b3ff66"  # Low - green
        }.get(sev, "#ffffff")

    def launch_main_window(app, splash):
        from gui.main_window import MainWindow
        window = MainWindow()
        window.show()
        splash.finish(window)



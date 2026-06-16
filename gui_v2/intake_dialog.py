"""
gui_v2/intake_dialog.py

New-case intake. Collects case metadata and a list of evidence files (any
supported kind), shows the auto-detected type for each, then hands back a
CaseBuilder with everything hashed on intake.
"""

import os
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QComboBox,
    QPlainTextEdit, QPushButton, QListWidget, QListWidgetItem, QLabel,
    QFileDialog, QDialogButtonBox, QWidget,
)

from . import theme
from .case_model import CaseBuilder, detect_kind, KIND_LABEL

EVIDENCE_FILTER = (
    "All supported (*.e01 *.ex01 *.s01 *.img *.dd *.raw *.evtx *.pf *.pcap "
    "*.pcapng *.mbox *.eml *.hive History Downloads NTUSER.DAT SYSTEM SOFTWARE);;"
    "Disk images (*.e01 *.ex01 *.s01 *.img *.dd *.raw);;"
    "Event logs (*.evtx);;Prefetch (*.pf);;"
    "Network captures (*.pcap *.pcapng);;Email (*.mbox *.eml);;"
    "All files (*.*)")


class IntakeDialog(QDialog):
    def __init__(self, parent, defaults):
        super().__init__(parent)
        self.setWindowTitle("New Case — Evidence Intake")
        self.setMinimumWidth(620)
        self._files = []

        root = QVBoxLayout(self)

        # ── case metadata ──────────────────────────────────────────────────────
        form = QFormLayout()
        self.case_num = QLineEdit()
        self.case_num.setPlaceholderText("auto-generated if blank (e.g. FA-2026-0001)")
        self.title = QLineEdit()
        self.title.setPlaceholderText("e.g. Suspected data exfiltration")
        self.examiner = QLineEdit(defaults.get("examiner", ""))
        self.examiner_id = QLineEdit(defaults.get("examiner_id", ""))
        self.agency = QLineEdit(defaults.get("agency", ""))
        self.method = QComboBox()
        self.method.addItems(["Disk image", "Logical extraction",
                              "Live acquisition", "Cloud pull"])
        self.notes = QPlainTextEdit()
        self.notes.setFixedHeight(60)
        form.addRow("Case number", self.case_num)
        form.addRow("Title", self.title)
        form.addRow("Examiner", self.examiner)
        form.addRow("Examiner ID", self.examiner_id)
        form.addRow("Agency", self.agency)
        form.addRow("Acquisition", self.method)
        form.addRow("Notes", self.notes)
        root.addLayout(form)

        # ── evidence list ──────────────────────────────────────────────────────
        ev_head = QHBoxLayout()
        lbl = QLabel("EVIDENCE")
        lbl.setStyleSheet(f"font-family:{theme.MONO}; font-size:10px; color:#8B96A8;")
        add_btn = QPushButton("+ Add files")
        add_btn.clicked.connect(self._add_files)
        ev_head.addWidget(lbl); ev_head.addStretch(1); ev_head.addWidget(add_btn)
        root.addLayout(ev_head)

        self.list = QListWidget()
        self.list.setMinimumHeight(120)
        root.addWidget(self.list)

        hint = QLabel("Supported: disk images · EVTX event logs · registry hives · "
                      "Prefetch · PCAP · mbox/eml · Chrome SQLite")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#6B7689; font-size:11px;")
        root.addWidget(hint)

        # ── buttons ────────────────────────────────────────────────────────────
        self.btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.btns.button(QDialogButtonBox.Ok).setText("Create Case && Hash Evidence")
        self.btns.accepted.connect(self.accept)
        self.btns.rejected.connect(self.reject)
        root.addWidget(self.btns)
        self._refresh_ok()

    def _add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add Evidence Files", "", EVIDENCE_FILTER)
        for p in paths:
            if p in self._files:
                continue
            self._files.append(p)
            kind = detect_kind(p)
            item = QListWidgetItem(f"{os.path.basename(p)}   —   {KIND_LABEL[kind]}")
            if kind == "unknown":
                item.setForeground(Qt.gray)
                item.setText(item.text() + "  (will be treated as raw disk)")
            self.list.addItem(item)
        self._refresh_ok()

    def _refresh_ok(self):
        self.btns.button(QDialogButtonBox.Ok).setEnabled(bool(self._files))

    # ── result ─────────────────────────────────────────────────────────────────

    def build(self, log=print):
        """Create the CaseBuilder, hash every file on intake, return it."""
        cb = CaseBuilder(
            examiner=self.examiner.text().strip() or "Examiner",
            examiner_id=self.examiner_id.text().strip() or "EX-00",
            agency=self.agency.text().strip(),
            case_id=self.case_num.text().strip() or None,
            title=self.title.text().strip() or "Untitled investigation",
        )
        for p in self._files:
            log(f"[*] Hashing {os.path.basename(p)} …")
            cb.add_evidence(p)
        return cb

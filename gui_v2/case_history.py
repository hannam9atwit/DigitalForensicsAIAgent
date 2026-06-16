"""
gui_v2/case_history.py

Dialog listing previously saved cases (from the app-data folder) so an examiner
can reopen one. Reads summaries via case_store.list_cases().
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView, QAbstractItemView, QMessageBox,
)

from . import case_store


class CaseHistoryDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Case History")
        self.setMinimumSize(720, 420)
        self.selected_path = None

        lay = QVBoxLayout(self)
        head = QLabel("Previous cases")
        head.setStyleSheet("font-size:16px; font-weight:700;")
        lay.addWidget(head)
        loc = QLabel(case_store.app_data_dir())
        loc.setStyleSheet("color:gray; font-size:10px;")
        lay.addWidget(loc)

        self.rows = case_store.list_cases()
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["Case", "Title", "Examiner", "Evidence", "Findings", "Analyzed", "Saved"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setRowCount(len(self.rows))
        for r, c in enumerate(self.rows):
            self.table.setItem(r, 0, QTableWidgetItem(c["id"]))
            self.table.setItem(r, 1, QTableWidgetItem(c["title"]))
            self.table.setItem(r, 2, QTableWidgetItem(c["examiner"]))
            self.table.setItem(r, 3, QTableWidgetItem(str(c["evidence"])))
            self.table.setItem(r, 4, QTableWidgetItem(str(c["findings"])))
            self.table.setItem(r, 5, QTableWidgetItem("yes" if c["analyzed"] else "no"))
            self.table.setItem(r, 6, QTableWidgetItem(c["saved"]))
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.doubleClicked.connect(self._open)
        lay.addWidget(self.table)

        if not self.rows:
            empty = QLabel("No saved cases yet. Cases are saved automatically "
                           "after analysis, or via File ▸ Save Case.")
            empty.setStyleSheet("color:gray;")
            empty.setWordWrap(True)
            lay.addWidget(empty)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.del_btn = QPushButton("Delete")
        self.del_btn.clicked.connect(self._delete)
        open_btn = QPushButton("Open")
        open_btn.setObjectName("primary")
        open_btn.clicked.connect(self._open)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btns.addWidget(self.del_btn)
        btns.addWidget(cancel)
        btns.addWidget(open_btn)
        lay.addLayout(btns)

    def _current(self):
        r = self.table.currentRow()
        if r < 0 or r >= len(self.rows):
            return None
        return self.rows[r]

    def _open(self):
        c = self._current()
        if not c:
            QMessageBox.information(self, "Select a case", "Pick a case to open.")
            return
        self.selected_path = c["path"]
        self.accept()

    def _delete(self):
        c = self._current()
        if not c:
            return
        if QMessageBox.question(
                self, "Delete case",
                f"Delete saved case {c['id']}?\nThis removes the .forensic file "
                "(evidence files on disk are untouched).") == QMessageBox.Yes:
            case_store.delete_case(c["path"])
            r = self.table.currentRow()
            self.table.removeRow(r)
            del self.rows[r]

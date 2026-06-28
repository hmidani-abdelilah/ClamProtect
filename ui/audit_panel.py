from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QLabel, QMessageBox, QTextEdit,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush

from core.security_audit import run_audit
from core.logger import get_logger

log = get_logger()

_COLORS = {
    "ok": QColor("#27ae60"),
    "info": QColor("#2980b9"),
    "warning": QColor("#e67e22"),
    "error": QColor("#e74c3c"),
}


class AuditPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout()

        header = QLabel("Security Audit")
        header.setStyleSheet("font-size: 18px; font-weight: bold; padding: 8px 0;")

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Category", "Status", "Detail"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        btn_layout = QHBoxLayout()
        self.run_btn = QPushButton("Run Security Audit")
        self.run_btn.clicked.connect(self._run)
        btn_layout.addWidget(self.run_btn)
        btn_layout.addStretch()

        self.status_label = QLabel("")

        layout.addWidget(header)
        layout.addWidget(self.table, 1)
        layout.addLayout(btn_layout)
        layout.addWidget(self.status_label)
        self.setLayout(layout)

    def _run(self):
        self.run_btn.setEnabled(False)
        self.run_btn.setText("Running…")
        self.status_label.setText("Audit in progress…")
        try:
            results = run_audit()
            self._display(results)
        except Exception as e:
            log.error("Audit failed: %s", e)
            QMessageBox.critical(self, "Audit Failed", str(e))
        finally:
            self.run_btn.setEnabled(True)
            self.run_btn.setText("Run Security Audit")

    def _display(self, results):
        self.table.setRowCount(len(results))
        summary = {"ok": 0, "info": 0, "warning": 0, "error": 0}

        for row, r in enumerate(results):
            name_item = QTableWidgetItem(r["name"])
            name_item.setFont(name_item.font())
            self.table.setItem(row, 0, name_item)

            status_item = QTableWidgetItem(r["status"].upper())
            color = _COLORS.get(r["status"], QColor("#7f8c8d"))
            status_item.setForeground(QBrush(color))
            self.table.setItem(row, 1, status_item)

            detail = r.get("detail", "")
            detail_item = QTableWidgetItem(detail)
            self.table.setItem(row, 2, detail_item)

            summary[r["status"]] = summary.get(r["status"], 0) + 1

        self.table.resizeColumnsToContents()
        self.status_label.setText(
            f"Audit complete — "
            f'{"✅" if summary.get("ok") else ""}{summary.get("ok",0)} ok | '
            f'ℹ️{summary.get("info",0)} | '
            f'⚠️{summary.get("warning",0)} | '
            f'❌{summary.get("error",0)}'
        )

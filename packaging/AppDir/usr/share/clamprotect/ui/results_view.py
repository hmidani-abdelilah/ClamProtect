import csv
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QLabel,
    QDialog, QTextEdit, QGroupBox, QFileDialog, QMessageBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush


class ScanDetailDialog(QDialog):
    def __init__(self, scan, results, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Scan Details — {scan['path']}")
        self.setMinimumSize(600, 400)

        layout = QVBoxLayout()

        info = (
            f"<b>Path:</b> {scan['path']}<br>"
            f"<b>Type:</b> {scan['scan_type']}<br>"
            f"<b>Status:</b> {scan['status']}<br>"
            f"<b>Started:</b> {scan['started_at']}<br>"
            f"<b>Completed:</b> {scan['completed_at']}<br>"
            f"<b>Files:</b> {scan['total_files']} | "
            f"<b>Infected:</b> {scan['infected_files']}"
        )
        layout.addWidget(QLabel(info))

        text = QTextEdit()
        text.setReadOnly(True)
        lines = []
        for r in results:
            icon = "✓" if r["status"] == "clean" else "✗" if r["status"] == "infected" else "?"
            threat = r["virus_name"] or "-"
            lines.append(f"{icon} {r['file_path']}  [{r['status']}]  {threat}")
        text.setText("\n".join(lines))
        layout.addWidget(text, 1)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        self.setLayout(layout)


class ResultsView(QWidget):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout()

        header = QLabel("Scan History")
        header.setStyleSheet("font-size: 18px; font-weight: bold; padding: 8px 0;")

        stats_row = QHBoxLayout()
        self._stats_cards = {}
        for label, key in [("Today", "today"), ("This Month", "monthly"), ("This Year", "yearly")]:
            card = QGroupBox(label)
            card.setObjectName("statsCard")
            card.setFixedHeight(80)
            inner = QVBoxLayout()
            inner.setContentsMargins(8, 4, 8, 4)
            val = QLabel("0 scans / 0 threats")
            val.setProperty("statValue", True)
            inner.addWidget(val)
            card.setLayout(inner)
            stats_row.addWidget(card)
            self._stats_cards[key] = val
        stats_row.addStretch()

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Date", "Path", "Type", "Status", "Threats"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self._show_details)

        btn_layout = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        clear_btn = QPushButton("Clear Selection")
        clear_btn.clicked.connect(lambda: self.table.clearSelection())
        export_btn = QPushButton("Export CSV")
        export_btn.clicked.connect(self._export_csv)
        btn_layout.addWidget(refresh_btn)
        btn_layout.addWidget(clear_btn)
        btn_layout.addWidget(export_btn)
        btn_layout.addStretch()

        self.status_label = QLabel("")

        layout.addWidget(header)
        layout.addLayout(stats_row)
        layout.addWidget(self.table, 1)
        layout.addLayout(btn_layout)
        layout.addWidget(self.status_label)
        self.setLayout(layout)

        self.refresh()

    def refresh(self):
        history = self.db.get_history()
        self.table.setRowCount(len(history))

        for row, item in enumerate(history):
            date_item = QTableWidgetItem(str(item["started_at"])[:19])
            self.table.setItem(row, 0, date_item)
            self.table.setItem(row, 1, QTableWidgetItem(item["path"]))
            self.table.setItem(row, 2, QTableWidgetItem(item["scan_type"]))

            status_item = QTableWidgetItem(item["status"])
            if item["status"] == "infected":
                status_item.setForeground(QBrush(QColor("#e74c3c")))
                status_item.setBackground(QBrush(QColor("#2c0b0b")))
            elif item["status"] == "clean":
                status_item.setForeground(QBrush(QColor("#2ecc71")))
                status_item.setBackground(QBrush(QColor("#0b2c1a")))
            self.table.setItem(row, 3, status_item)
            self.table.setItem(row, 4, QTableWidgetItem(str(item["infected_files"])))

            self.table.setRowHeight(row, 28)

        self.status_label.setText(f"{len(history)} scan records")
        self._update_stats()

    def _update_stats(self):
        stats = self.db.get_stats()
        for key, val in self._stats_cards.items():
            s = stats.get(key, {"total": 0, "infected": 0})
            val.setText(f"{s['total']} scans / {s['infected']} threats")

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Scan History", str(Path.home() / "clamprotect_history.csv"),
            "CSV Files (*.csv)")
        if not path:
            return
        try:
            history = self.db.get_history(limit=10000)
            with open(path, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["Date", "Path", "Type", "Status", "Total Files", "Infected", "Errors"])
                for h in history:
                    w.writerow([
                        h.get("started_at", ""),
                        h.get("path", ""),
                        h.get("scan_type", ""),
                        h.get("status", ""),
                        h.get("total_files", 0),
                        h.get("infected_files", 0),
                        h.get("errors", 0),
                    ])
            self.status_label.setText(f"Exported {len(history)} records to {path}")
            QMessageBox.information(self, "Exported", f"Exported {len(history)} records.")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

    def _show_details(self, row, _):
        history = self.db.get_history()
        if row < 0 or row >= len(history):
            return
        scan = history[row]
        results = self.db.get_scan_results(scan["id"])
        dlg = ScanDetailDialog(scan, results, self)
        dlg.exec()

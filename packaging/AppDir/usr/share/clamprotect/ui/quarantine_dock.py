from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QLabel, QMessageBox, QDialog, QTextEdit,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush

from core.logger import get_logger

log = get_logger()


def _has_suid_sgid(mode):
    return bool(mode & 0o4000) or bool(mode & 0o2000)


class QuarantineDock(QWidget):
    def __init__(self, quarantine, db, parent=None):
        super().__init__(parent)
        self.quarantine = quarantine
        self.db = db
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout()

        header = QLabel("Quarantine")
        header.setStyleSheet("font-size: 18px; font-weight: bold; padding: 8px 0;")

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["File", "Original Path", "Virus", "Size", "Date", "Integrity", "Mode"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        btn_layout = QHBoxLayout()
        self.verify_btn = QPushButton("Verify Integrity")
        self.verify_btn.clicked.connect(self._verify)
        self.restore_btn = QPushButton("Restore Selected")
        self.restore_btn.clicked.connect(self._restore)
        self.delete_btn = QPushButton("Delete Selected")
        self.delete_btn.clicked.connect(self._delete)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        btn_layout.addWidget(self.verify_btn)
        btn_layout.addWidget(self.restore_btn)
        btn_layout.addWidget(self.delete_btn)
        btn_layout.addWidget(refresh_btn)
        btn_layout.addStretch()

        self.status_label = QLabel("")

        layout.addWidget(header)
        layout.addWidget(self.table, 1)
        layout.addLayout(btn_layout)
        layout.addWidget(self.status_label)
        self.setLayout(layout)

        self.refresh()

    def refresh(self):
        items = self.quarantine.list()
        self.table.setRowCount(len(items))

        for row, item in enumerate(items):
            name = Path(item["original_path"]).name
            self.table.setItem(row, 0, QTableWidgetItem(name))
            self.table.setItem(row, 1, QTableWidgetItem(item["original_path"]))
            virus_item = QTableWidgetItem(item["virus_name"] or "Unknown")
            virus_item.setForeground(QBrush(QColor("#e74c3c")))
            self.table.setItem(row, 2, virus_item)
            self.table.setItem(row, 3, QTableWidgetItem(self._format_size(item["file_size"])))
            self.table.setItem(row, 4, QTableWidgetItem(str(item["quarantined_at"])[:19]))
            self.table.setItem(row, 5, QTableWidgetItem("—"))
            mode = item.get("original_permissions", 0)
            mode_str = f"SUID/SGID" if _has_suid_sgid(mode) else oct(mode) if mode else "—"
            mode_item = QTableWidgetItem(mode_str)
            if _has_suid_sgid(mode):
                mode_item.setForeground(QBrush(QColor("#e67e22")))
            self.table.setItem(row, 6, mode_item)

        self.status_label.setText(f"{len(items)} quarantined items")

    def _verify(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "No Selection", "Select an item to verify.")
            return
        items = self.quarantine.list()
        if row >= len(items):
            return

        item = items[row]
        try:
            ok = self.quarantine.verify(item["id"])
            icon = QMessageBox.Icon.Information if ok else QMessageBox.Icon.Warning
            msg = "Integrity OK — file unchanged." if ok else "INTEGRITY FAILED — file has been modified!"
            self.table.item(row, 5).setText("✅" if ok else "❌")
            if not ok:
                self.table.item(row, 5).setForeground(QBrush(QColor("#e74c3c")))
            mbox = QMessageBox(
                QMessageBox.Icon.Information if ok else QMessageBox.Icon.Warning,
                "Verify Integrity", msg, QMessageBox.StandardButton.Ok, self,
            )
            mbox.exec()
        except Exception as e:
            log.error("Verify failed: %s", e)
            QMessageBox.critical(self, "Verify Failed", str(e))

    def _restore(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "No Selection", "Select an item to restore.")
            return
        items = self.quarantine.list()
        if row >= len(items):
            return

        item = items[row]
        mode = item.get("original_permissions", 0)
        if _has_suid_sgid(mode):
            reply = QMessageBox.warning(
                self, "Dangerous Permissions",
                f"{Path(item['original_path']).name} had SUID/SGID set "
                f"(mode {oct(mode)}). These will be stripped for safety.\n\n"
                f"Continue with restore?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        reply = QMessageBox.question(
            self, "Restore File",
            f"Restore {Path(item['original_path']).name} to its original location?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.quarantine.restore(item["id"])
                self.refresh()
            except Exception as e:
                QMessageBox.critical(self, "Restore Failed", str(e))

    def _delete(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "No Selection", "Select an item to delete.")
            return
        items = self.quarantine.list()
        if row >= len(items):
            return

        item = items[row]
        reply = QMessageBox.warning(
            self, "Permanently Delete",
            f"Permanently delete {Path(item['original_path']).name}? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.quarantine.delete(item["id"])
                self.refresh()
            except Exception as e:
                QMessageBox.critical(self, "Delete Failed", str(e))

    @staticmethod
    def _format_size(size):
        if not size:
            return "0 B"
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

import subprocess
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QLabel, QDialog, QComboBox, QTimeEdit, QFileDialog,
    QLineEdit, QFormLayout, QMessageBox,
)
from PyQt6.QtCore import QTime

from core.logger import get_logger

log = get_logger()

CRON_MAP = {
    "Daily": "0 {hour} * * *",
    "Weekly (Mon)": "0 {hour} * * 1",
    "Weekly (Fri)": "0 {hour} * * 5",
    "Monthly (1st)": "0 {hour} 1 * *",
}


class ScheduleEditDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Scheduled Scan")
        self.setMinimumWidth(400)
        self._setup_ui()

    def _setup_ui(self):
        form = QFormLayout()

        self.freq_cb = QComboBox()
        self.freq_cb.addItems(list(CRON_MAP.keys()))
        form.addRow("Frequency:", self.freq_cb)

        self.time_edit = QTimeEdit()
        self.time_edit.setTime(QTime(2, 0))
        form.addRow("Time:", self.time_edit)

        path_layout = QHBoxLayout()
        self.path_edit = QLineEdit(str(Path.home()))
        browse_btn = QPushButton("...")
        browse_btn.setFixedWidth(40)
        browse_btn.clicked.connect(self._browse)
        path_layout.addWidget(self.path_edit, 1)
        path_layout.addWidget(browse_btn)
        form.addRow("Directory:", path_layout)

        self.script = f"python3 {Path(__file__).resolve().parent.parent / 'main.py'}"
        form.addRow("Command:", QLabel(f"{self.script} --scan <path> --silent"))

        btn_layout = QHBoxLayout()
        self.ok_btn = QPushButton("Add Schedule")
        self.ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(self.ok_btn)
        btn_layout.addWidget(cancel_btn)

        main_layout = QVBoxLayout()
        main_layout.addLayout(form)
        main_layout.addLayout(btn_layout)
        self.setLayout(main_layout)

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, "Select Directory")
        if path:
            self.path_edit.setText(path)

    def get_schedule(self):
        freq = self.freq_cb.currentText()
        hour = self.time_edit.time().hour()
        cron_expr = CRON_MAP[freq].format(hour=hour)
        path = self.path_edit.text()
        return {
            "cron": cron_expr,
            "command": f"{self.script} --scan {path} --silent",
            "label": f"{freq} @ {hour:02d}:00 — {Path(path).name}",
        }


class SchedulerDialog(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout()

        header = QLabel("Scheduled Scans")
        header.setStyleSheet("font-size: 18px; font-weight: bold; padding: 8px 0;")

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Schedule", "Path", "Command"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Add Schedule")
        add_btn.clicked.connect(self._add)
        remove_btn = QPushButton("Remove Selected")
        remove_btn.clicked.connect(self._remove)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(remove_btn)
        btn_layout.addWidget(refresh_btn)
        btn_layout.addStretch()

        self.status_label = QLabel("")

        layout.addWidget(header)
        layout.addWidget(self.table, 1)
        layout.addLayout(btn_layout)
        layout.addWidget(self.status_label)
        self.setLayout(layout)

        self.refresh()

    def _list_cron(self):
        try:
            result = subprocess.run(
                ["crontab", "-l"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                lines = [
                    l.strip() for l in result.stdout.split("\n")
                    if l.strip() and not l.strip().startswith("#")
                ]
                return lines
            return []
        except FileNotFoundError:
            return []

    def refresh(self):
        jobs = self._list_cron()
        aegis_jobs = [j for j in jobs if "--scan" in j]
        self.table.setRowCount(len(aegis_jobs))

        for row, job in enumerate(aegis_jobs):
            parts = job.split(" ", 4)
            schedule = " ".join(parts[:5]) if len(parts) >= 5 else job
            cmd = parts[4] if len(parts) >= 5 else ""
            path_part = ""
            if "--scan" in cmd:
                idx = cmd.index("--scan")
                rest = cmd[idx + 6:].strip().split()[0] if len(cmd[idx:].split()) > 1 else ""
                path_part = rest.split()[0] if rest else ""

            self.table.setItem(row, 0, QTableWidgetItem(schedule))
            self.table.setItem(row, 1, QTableWidgetItem(path_part))
            self.table.setItem(row, 2, QTableWidgetItem(cmd[:60] + "..." if len(cmd) > 60 else cmd))

        self.status_label.setText(f"{len(aegis_jobs)} scheduled scans")

    def _add(self):
        dlg = ScheduleEditDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            sched = dlg.get_schedule()
            jobs = self._list_cron()
            new_job = f"{sched['cron']} {sched['command']}"
            if new_job in jobs:
                QMessageBox.information(self, "Duplicate", "This schedule already exists.")
                return
            jobs.append(new_job)
            self._write_cron(jobs)
            self.refresh()

    def _remove(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "No Selection", "Select a schedule to remove.")
            return

        jobs = self._list_cron()
        aegis_jobs = [j for j in jobs if "--scan" in j]
        if row >= len(aegis_jobs):
            return

        target = aegis_jobs[row]

        reply = QMessageBox.question(
            self, "Remove Schedule",
            "Remove this scheduled scan?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            remaining = [j for j in jobs if j != target]
            self._write_cron(remaining)
            self.refresh()

    def _write_cron(self, jobs):
        try:
            content = "\n".join(jobs) + "\n" if jobs else ""
            proc = subprocess.run(
                ["crontab"],
                input=content, text=True, capture_output=True, timeout=10,
            )
            if proc.returncode != 0:
                QMessageBox.critical(self, "Error", f"Failed to update crontab: {proc.stderr}")
        except FileNotFoundError:
            QMessageBox.critical(self, "Error", "crontab command not found")

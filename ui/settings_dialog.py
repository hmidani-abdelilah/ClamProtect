from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QCheckBox, QComboBox,
    QGroupBox, QFormLayout, QListWidget, QFileDialog,
    QMessageBox, QTabWidget,
)
from PyQt6.QtCore import Qt, pyqtSignal

from core.logger import get_logger
from core.definitions import DefinitionsManager
from core.quarantine import QUARANTINE_DIR
from core.virustotal import VirusTotalChecker

log = get_logger()


class SettingsDialog(QWidget):
    settings_changed = pyqtSignal()

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.defs = DefinitionsManager()
        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):
        main_layout = QVBoxLayout()

        header = QLabel("Settings")
        header.setStyleSheet("font-size: 18px; font-weight: bold; padding: 8px 0;")

        tabs = QTabWidget()

        # General tab
        general = QWidget()
        general_layout = QFormLayout()
        self.clamd_socket_edit = QLineEdit()
        general_layout.addRow("Clamd Socket:", self.clamd_socket_edit)
        self.fallback_cb = QCheckBox("Fall back to clamscan")
        general_layout.addRow("", self.fallback_cb)
        self.notify_cb = QCheckBox("Show notifications")
        general_layout.addRow("", self.notify_cb)
        self.autoupdate_cb = QCheckBox("Auto-update definitions")
        general_layout.addRow("", self.autoupdate_cb)
        general.setLayout(general_layout)
        tabs.addTab(general, "General")

        # Appearance tab
        appearance = QWidget()
        appearance_layout = QFormLayout()
        self.theme_cb = QComboBox()
        self.theme_cb.addItems(["system", "light", "dark"])
        appearance_layout.addRow("Theme:", self.theme_cb)
        appearance.setLayout(appearance_layout)
        tabs.addTab(appearance, "Appearance")

        # Monitoring tab
        monitoring = QWidget()
        monitor_layout = QVBoxLayout()
        monitor_label = QLabel("Watched directories (one per line):")
        self.watch_edit = QLineEdit()
        self.watch_edit.setPlaceholderText("/path/to/watch")
        add_watch_btn = QPushButton("Add Directory")
        add_watch_btn.clicked.connect(self._add_watch)
        self.watch_list = QListWidget()
        monitor_layout.addWidget(monitor_label)
        monitor_layout.addWidget(QLabel("Path to watch:"))
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(self.watch_edit, 1)
        dir_layout.addWidget(add_watch_btn)
        monitor_layout.addLayout(dir_layout)
        monitor_layout.addWidget(QLabel("Currently watched:"))
        monitor_layout.addWidget(self.watch_list, 1)
        remove_watch_btn = QPushButton("Remove Selected")
        remove_watch_btn.clicked.connect(self._remove_watch)
        monitor_layout.addWidget(remove_watch_btn)
        monitoring.setLayout(monitor_layout)
        tabs.addTab(monitoring, "Monitoring")

        # VirusTotal tab
        vt_tab = QWidget()
        vt_layout = QFormLayout()
        self.vt_enabled_cb = QCheckBox("Enable VirusTotal hash lookup")
        vt_layout.addRow("", self.vt_enabled_cb)
        self.vt_key_edit = QLineEdit()
        self.vt_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.vt_key_edit.setPlaceholderText("VirusTotal API key")
        vt_layout.addRow("API Key:", self.vt_key_edit)
        self.vt_status = QLabel("")
        vt_layout.addRow("", self.vt_status)
        vt_test_btn = QPushButton("Test API Key")
        vt_test_btn.clicked.connect(self._test_vt_key)
        vt_layout.addRow("", vt_test_btn)
        vt_tab.setLayout(vt_layout)
        tabs.addTab(vt_tab, "VirusTotal")

        # On-Access tab
        oa_tab = QWidget()
        oa_layout = QFormLayout()
        self.onaccess_cb = QCheckBox("Enable on-access scanning (clamonacc)")
        oa_layout.addRow("", self.onaccess_cb)
        oa_tab.setLayout(oa_layout)
        tabs.addTab(oa_tab, "On-Access")

        # USB tab
        usb_tab = QWidget()
        usb_layout = QFormLayout()
        self.usb_cb = QCheckBox("Auto-scan USB drives when connected")
        usb_layout.addRow("", self.usb_cb)
        self.usb_network_cb = QCheckBox("Also scan network mounts")
        usb_layout.addRow("", self.usb_network_cb)
        usb_tab.setLayout(usb_layout)
        tabs.addTab(usb_tab, "USB Scanning")

        # About tab
        about = QWidget()
        about_layout = QVBoxLayout()
        db_status = self.defs.get_status()
        about_layout.addWidget(QLabel(f"<b>ClamProtect</b> — Modern ClamAV GUI"))
        about_layout.addWidget(QLabel(f"Database: {db_status.get('status', 'unknown')}"))
        about_layout.addWidget(QLabel(f"Version: {db_status.get('version', 'unknown')}"))
        about_layout.addWidget(QLabel(f"Last Updated: {db_status.get('last_updated', 'never')}"))
        about_layout.addWidget(QLabel(f"Quarantine: {QUARANTINE_DIR}"))
        update_btn = QPushButton("Update Definitions Now")
        update_btn.clicked.connect(self._update_defs)
        about_layout.addWidget(update_btn)
        self.update_status = QLabel("")
        about_layout.addWidget(self.update_status)
        about_layout.addStretch()
        about.setLayout(about_layout)
        tabs.addTab(about, "About")

        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save Settings")
        save_btn.clicked.connect(self._save_settings)
        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)

        main_layout.addWidget(header)
        main_layout.addWidget(tabs, 1)
        main_layout.addLayout(btn_layout)
        self.setLayout(main_layout)

    def _load_settings(self):
        self.clamd_socket_edit.setText(
            self.db.get_setting("clamd_socket") or "/var/run/clamav/clamd.ctl"
        )
        self.fallback_cb.setChecked(
            self.db.get_setting("use_clamscan_fallback") == "true"
        )
        self.notify_cb.setChecked(
            self.db.get_setting("notifications") == "true"
        )
        self.autoupdate_cb.setChecked(
            self.db.get_setting("auto_update") == "true"
        )
        self.theme_cb.setCurrentText(
            self.db.get_setting("theme") or "system"
        )

        self.vt_enabled_cb.setChecked(
            self.db.get_setting("vt_enabled") == "true"
        )
        self.vt_key_edit.setText(
            self.db.get_setting("vt_api_key") or ""
        )

        self.onaccess_cb.setChecked(
            self.db.get_setting("onaccess_enabled") == "true"
        )

        self.usb_cb.setChecked(
            self.db.get_setting("usb_scan_enabled") == "true"
        )
        self.usb_network_cb.setChecked(
            self.db.get_setting("usb_scan_network") == "true"
        )

        watch = self.db.get_setting("watch_directories") or ""
        self.watch_list.clear()
        for w in watch.split("\n"):
            w = w.strip()
            if w:
                self.watch_list.addItem(w)

    def _save_settings(self):
        self.db.set_setting("clamd_socket", self.clamd_socket_edit.text().strip())
        self.db.set_setting("use_clamscan_fallback",
                           "true" if self.fallback_cb.isChecked() else "false")
        self.db.set_setting("notifications",
                           "true" if self.notify_cb.isChecked() else "false")
        self.db.set_setting("auto_update",
                           "true" if self.autoupdate_cb.isChecked() else "false")
        self.db.set_setting("theme", self.theme_cb.currentText())

        self.db.set_setting("vt_enabled",
                           "true" if self.vt_enabled_cb.isChecked() else "false")
        self.db.set_setting("vt_api_key", self.vt_key_edit.text().strip())
        self.db.set_setting("onaccess_enabled",
                           "true" if self.onaccess_cb.isChecked() else "false")
        self.db.set_setting("usb_scan_enabled",
                           "true" if self.usb_cb.isChecked() else "false")
        self.db.set_setting("usb_scan_network",
                           "true" if self.usb_network_cb.isChecked() else "false")

        watches = "\n".join(
            self.watch_list.item(i).text()
            for i in range(self.watch_list.count())
        )
        self.db.set_setting("watch_directories", watches)
        QMessageBox.information(self, "Settings", "Settings saved.")
        self.settings_changed.emit()

    def _test_vt_key(self):
        key = self.vt_key_edit.text().strip()
        if not key:
            self.vt_status.setText("No API key entered")
            return
        checker = VirusTotalChecker(key)
        result = checker.check_hash("d41d8cd98f00b204e9800998ecf8427e")
        self.vt_status.setText(f"Test result: {result['status']} — {result['message']}")

    def _add_watch(self):
        path = self.watch_edit.text().strip()
        if not path:
            path = QFileDialog.getExistingDirectory(self, "Select Directory")
            if not path:
                return
        if Path(path).exists():
            existing = [
                self.watch_list.item(i).text()
                for i in range(self.watch_list.count())
            ]
            if path not in existing:
                self.watch_list.addItem(path)
                self.watch_edit.clear()
            else:
                QMessageBox.information(self, "Duplicate", "Directory already in watch list.")
        else:
            QMessageBox.warning(self, "Invalid", "Directory does not exist.")

    def _remove_watch(self):
        row = self.watch_list.currentRow()
        if row >= 0:
            self.watch_list.takeItem(row)

    def _update_defs(self):
        self.update_status.setText("Updating...")
        result = self.defs.update()
        self.update_status.setText(result.get("message", result.get("status", "done")))

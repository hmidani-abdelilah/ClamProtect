from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QMessageBox, QApplication,
    QSystemTrayIcon,
)
from PyQt6.QtCore import Qt, QTimer

from core.scanner import Scanner
from core.database import Database
from core.quarantine import Quarantine
from core.definitions import DefinitionsManager
from core.onaccess import OnAccessScanner
from core.usb_monitor import USBMonitor
from core.logger import get_logger
from ui.theme import apply_theme
from ui.tray import TrayIcon
from ui.scan_panel import ScanPanel
from ui.results_view import ResultsView
from ui.quarantine_dock import QuarantineDock
from ui.scheduler_dialog import SchedulerDialog
from ui.settings_dialog import SettingsDialog
from ui.audit_panel import AuditPanel

from watcher.monitor import FileMonitor

log = get_logger()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ClamProtect — Antivirus Scanner")
        self.setMinimumSize(950, 650)
        self.resize(1100, 750)

        self.db = Database()
        self.scanner = Scanner(
            socket_path=self.db.get_setting("clamd_socket")
            or "/var/run/clamav/clamd.ctl"
        )
        self.quarantine = Quarantine(self.db)
        self.defs = DefinitionsManager()
        self.onaccess = OnAccessScanner()
        self.usb_monitor = USBMonitor(self.scanner, self._on_usb_threat)

        self._setup_ui()
        self._setup_tray()
        self._setup_watcher()
        self._setup_onaccess()
        self._setup_usb_monitor()

        theme = self.db.get_setting("theme") or "system"
        apply_theme(QApplication.instance(), theme)

    def _setup_ui(self):
        self.tabs = QTabWidget()

        self.scan_panel = ScanPanel(self.scanner, self.db, self.quarantine, self)
        self.scan_panel.scan_completed.connect(self._on_scan_completed)
        self.scan_panel.scan_started.connect(self._on_scan_started)
        self.tabs.addTab(self.scan_panel, "Scan")

        self.results_view = ResultsView(self.db, self)
        self.tabs.addTab(self.results_view, "History")

        self.quarantine_dock = QuarantineDock(self.quarantine, self.db, self)
        self.tabs.addTab(self.quarantine_dock, "Quarantine")

        self.scheduler_dialog = SchedulerDialog(self)
        self.tabs.addTab(self.scheduler_dialog, "Scheduler")

        self.audit_panel = AuditPanel(self)
        self.tabs.addTab(self.audit_panel, "Security Audit")

        self.settings_dialog = SettingsDialog(self.db, self)
        self.settings_dialog.settings_changed.connect(self._on_settings_changed)
        self.tabs.addTab(self.settings_dialog, "Settings")

        self.setCentralWidget(self.tabs)

    def _setup_tray(self):
        self.tray = TrayIcon(self)
        self.tray.show_action.triggered.connect(self.show)
        self.tray.scan_action.triggered.connect(self.scan_panel.quick_scan)
        self.tray.update_requested.connect(self._tray_update_defs)
        self.tray.cancel_scan_requested.connect(self.scan_panel._cancel_scan)
        self.tray.quit_action.triggered.connect(self._quit_app)
        self.tray.show()

    def _setup_watcher(self):
        self.monitor = FileMonitor(self)
        self.monitor.scan_requested.connect(self._on_watch_event)
        watch = self.db.get_setting("watch_directories") or ""
        paths = [p.strip() for p in watch.split("\n") if p.strip()]
        if paths:
            self.monitor.start(paths)

    def _on_scan_started(self, path, scan_type):
        self.tray.set_scanning(True)
        if self.db.get_setting("notifications") == "true":
            self.tray.notify(
                "Scan Started",
                f"{scan_type.title()} scan — {path}",
                QSystemTrayIcon.MessageIcon.Information,
            )

    def _on_scan_completed(self, path, scan_type, results):
        self.tray.set_scanning(False)
        try:
            self.db.save_scan(path, scan_type, results)
            self.results_view.refresh()
            infected = [r for r in results if r["status"] == "infected"]
            if infected and self.db.get_setting("notifications") == "true":
                self.tray.notify(
                    "Scan Complete",
                    f"{len(infected)} threats found in {path}",
                    QSystemTrayIcon.MessageIcon.Warning,
                )
        except Exception as e:
            log.error("Failed to save scan results: %s", e)

    def _on_watch_event(self, path):
        log.info("Watch event: %s", path)
        if self.db.is_whitelisted(path):
            return
        try:
            results = self.scanner.scan(path)
            infected = [r for r in results if r.get("status") == "infected"]
            if infected:
                for r in infected:
                    self.quarantine.add(r["path"], r["virus"])
                if self.db.get_setting("notifications") == "true":
                    name = Path(path).name
                    virus = infected[0]["virus"]
                    self.tray.notify(
                        "Threat Blocked",
                        f"{virus} in {name} — Quarantined",
                        QSystemTrayIcon.MessageIcon.Critical,
                    )
            self.db.save_scan(path, "realtime", results)
        except Exception as e:
            log.error("Watch scan failed for %s: %s", path, e)

    def _setup_onaccess(self):
        if self.db.get_setting("onaccess_enabled") == "true":
            self.onaccess.start()

    def _setup_usb_monitor(self):
        self._usb_timer = QTimer(self)
        self._usb_timer.timeout.connect(lambda: self.usb_monitor.poll())
        if self.db.get_setting("usb_scan_enabled") == "true":
            scan_network = self.db.get_setting("usb_scan_network") == "true"
            self.usb_monitor.start(scan_network=scan_network)
        self._usb_timer.start(5000)

    def _on_usb_threat(self, mount_path, infected):
        for r in infected:
            try:
                self.quarantine.add(r["path"], r["virus"])
            except Exception as e:
                log.error("USB quarantine failed: %s", e)
        if self.db.get_setting("notifications") == "true":
            self.tray.notify(
                "USB Threat",
                f"{len(infected)} threats on {mount_path} — Quarantined",
                QSystemTrayIcon.MessageIcon.Warning,
            )

    def _on_settings_changed(self):
        theme = self.db.get_setting("theme") or "system"
        apply_theme(QApplication.instance(), theme)
        watch = self.db.get_setting("watch_directories") or ""
        paths = [p.strip() for p in watch.split("\n") if p.strip()]
        self.monitor.start(paths)

        socket_path = self.db.get_setting("clamd_socket") or "/var/run/clamav/clamd.ctl"
        self.scanner.socket_path = socket_path

        if self.db.get_setting("onaccess_enabled") == "true":
            self.onaccess.start()
        else:
            self.onaccess.stop()

        if self.db.get_setting("usb_scan_enabled") == "true":
            scan_network = self.db.get_setting("usb_scan_network") == "true"
            self.usb_monitor.start(scan_network=scan_network)
        else:
            self.usb_monitor.stop()
        self.usb_monitor.poll()

    def _tray_update_defs(self):
        log.info("Tray update definitions triggered")
        result = self.defs.update()
        msg = result.get("message", result.get("status", "done"))
        self.tray.notify("Definitions Update", msg,
                         QSystemTrayIcon.MessageIcon.Information)

    def _quit_app(self):
        self.monitor.stop()
        self.onaccess.stop()
        self.usb_monitor.stop()
        log.info("ClamProtect shutting down")
        QApplication.instance().quit()

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.tray.notify(
            "ClamProtect Running",
            "Application minimized to tray",
            QSystemTrayIcon.MessageIcon.Information,
        )

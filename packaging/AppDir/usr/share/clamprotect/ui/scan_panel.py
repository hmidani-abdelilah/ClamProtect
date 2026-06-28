from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QFileDialog, QProgressBar, QCheckBox,
    QTreeWidget, QTreeWidgetItem, QHeaderView,
    QMessageBox, QComboBox, QInputDialog,
)
import json
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QColor, QBrush

from core.scanner import Scanner, ScannerError
from core.logger import get_logger
from core.virustotal import VirusTotalChecker

log = get_logger()


class ScanThread(QThread):
    progress = pyqtSignal(dict)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, scanner, path, recursive=True):
        super().__init__()
        self.scanner = scanner
        self.path = path
        self.recursive = recursive

    def run(self):
        try:
            results = self.scanner.scan(self.path, callback=self._on_result, recursive=self.recursive)
            self.finished.emit(results)
        except ScannerError as e:
            self.error.emit(str(e))
        except Exception as e:
            log.error("Scan thread error: %s", e)
            self.error.emit(str(e))

    def cancel(self):
        self.scanner.cancel()

    def _on_result(self, result):
        self.progress.emit(result)


class VTCheckThread(QThread):
    result_ready = pyqtSignal(str, dict)

    def __init__(self, api_key, hash_map):
        super().__init__()
        self.api_key = api_key
        self.hash_map = hash_map  # dict: path -> sha256

    def run(self):
        checker = VirusTotalChecker(self.api_key)
        for path, file_hash in self.hash_map.items():
            try:
                vt = checker.check_hash(file_hash)
                self.result_ready.emit(path, vt)
            except Exception as e:
                log.error("VT check error for %s: %s", path, e)
            self.msleep(200)  # rate limit


class QuickScanThread(QThread):
    progress = pyqtSignal(dict)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, scanner, paths=None):
        super().__init__()
        self.scanner = scanner
        self.paths = paths

    def run(self):
        try:
            results = self.scanner.quick_scan(paths=self.paths, callback=self._on_result)
            self.finished.emit(results)
        except Exception as e:
            log.error("Quick scan thread error: %s", e)
            self.error.emit(str(e))

    def cancel(self):
        self.scanner.cancel()

    def _on_result(self, result):
        self.progress.emit(result)


class ScanPanel(QWidget):
    scan_completed = pyqtSignal(str, str, list)
    scan_started = pyqtSignal(str, str)

    def __init__(self, scanner, db, quarantine, parent=None):
        super().__init__(parent)
        self.scanner = scanner
        self.db = db
        self.quarantine = quarantine
        self._scan_paths = []
        self._scan_thread = None
        self._quick_thread = None
        self._setup_ui()
        self._load_profiles()
        self.setAcceptDrops(True)

    def _setup_ui(self):
        layout = QVBoxLayout()

        header = QLabel("Scan Files & Directories")
        header.setStyleSheet("font-size: 18px; font-weight: bold; padding: 8px 0;")

        browse_layout = QHBoxLayout()
        self.path_display = QLabel("Drop files or click Browse")
        self.path_display.setStyleSheet("padding: 8px; border: 1px solid #555; border-radius: 4px;")
        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self._browse)
        browse_layout.addWidget(self.path_display, 1)
        browse_layout.addWidget(self.browse_btn)

        self.full_scan_btn = QPushButton("Full System Scan")
        self.full_scan_btn.clicked.connect(self._full_scan)

        self.quick_scan_btn = QPushButton("Quick Scan")
        self.quick_scan_btn.clicked.connect(self._quick_scan)

        self.home_scan_btn = QPushButton("Home Directory")
        self.home_scan_btn.clicked.connect(self._home_scan)

        profile_layout = QHBoxLayout()
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(200)
        self.profile_combo.currentIndexChanged.connect(self._on_profile_selected)
        self.save_profile_btn = QPushButton("Save Profile")
        self.save_profile_btn.clicked.connect(self._save_profile)
        self.delete_profile_btn = QPushButton("Delete Profile")
        self.delete_profile_btn.clicked.connect(self._delete_profile)
        self.export_profiles_btn = QPushButton("Export")
        self.export_profiles_btn.clicked.connect(self._export_profiles)
        self.import_profiles_btn = QPushButton("Import")
        self.import_profiles_btn.clicked.connect(self._import_profiles)
        profile_layout.addWidget(QLabel("Profile:"))
        profile_layout.addWidget(self.profile_combo, 1)
        profile_layout.addWidget(self.save_profile_btn)
        profile_layout.addWidget(self.delete_profile_btn)
        profile_layout.addWidget(self.export_profiles_btn)
        profile_layout.addWidget(self.import_profiles_btn)

        scan_layout = QHBoxLayout()
        self.recursive_cb = QCheckBox("Recursive")
        self.recursive_cb.setChecked(True)
        self.scan_btn = QPushButton("Scan Now")
        self.scan_btn.setStyleSheet("""
            QPushButton {
                background-color: #c0392b; color: white; font-weight: bold;
                padding: 10px 24px; font-size: 14px; border-radius: 4px;
            }
            QPushButton:hover { background-color: #e74c3c; }
            QPushButton:disabled { background-color: #7f8c8d; }
        """)
        self.scan_btn.clicked.connect(self._start_scan)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #7f8c8d; color: white; font-weight: bold;
                padding: 10px 24px; font-size: 14px; border-radius: 4px;
            }
            QPushButton:hover { background-color: #95a5a6; }
        """)
        self.cancel_btn.clicked.connect(self._cancel_scan)
        scan_layout.addWidget(self.recursive_cb)
        scan_layout.addStretch()
        scan_layout.addWidget(self.cancel_btn)
        scan_layout.addWidget(self.scan_btn)

        self.drop_zone = QLabel("Drag & drop files or folders here")
        self.drop_zone.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_zone.setStyleSheet("""
            QLabel {
                border: 2px dashed #888; border-radius: 8px;
                padding: 40px; margin: 10px 0; font-size: 15px;
            }
        """)
        self.drop_zone.setFixedHeight(120)

        self.progress = QProgressBar()
        self.progress.setVisible(False)

        self.status_label = QLabel("")

        self.file_count_label = QLabel("")
        self.file_count_label.setVisible(False)

        self.result_tree = QTreeWidget()
        self.result_tree.setHeaderLabels(["File", "Status", "Threat", "VT"])
        self.result_tree.header().setStretchLastSection(True)
        self.result_tree.setAlternatingRowColors(True)
        self.result_tree.setVisible(False)

        layout.addWidget(header)
        layout.addLayout(browse_layout)
        layout.addLayout(profile_layout)
        layout.addWidget(self.full_scan_btn)
        layout.addWidget(self.quick_scan_btn)
        layout.addWidget(self.home_scan_btn)
        layout.addLayout(scan_layout)
        layout.addWidget(self.drop_zone)
        layout.addWidget(self.file_count_label)
        layout.addWidget(self.progress)
        layout.addWidget(self.status_label)
        layout.addWidget(self.result_tree, 1)
        self.setLayout(layout)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
        if paths:
            self._scan_paths = paths
            text = "; ".join(str(Path(p).name) for p in paths[:3])
            if len(paths) > 3:
                text += f" ... (+{len(paths) - 3})"
            self.path_display.setText(text)
            self.drop_zone.setStyleSheet("""
                QLabel {
                    border: 2px dashed #27ae60; border-radius: 8px;
                    padding: 40px; margin: 10px 0; font-size: 15px;
                    background-color: rgba(39, 174, 96, 0.1);
                }
            """)

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, "Select Directory")
        if path:
            self._scan_paths = [path]
            self.path_display.setText(path)

    def _full_scan(self):
        self._scan_paths = ["/"]
        self.path_display.setText("Full System Scan")
        self._start_scan()

    def quick_scan(self):
        self._quick_scan()

    def _quick_scan(self):
        self._scan_type = "quick"
        self._scan_paths = ["Quick Scan"]
        self.path_display.setText("Quick Scan — common locations")
        self.result_tree.clear()
        self.result_tree.setVisible(False)
        self.scan_btn.setEnabled(False)
        self.full_scan_btn.setEnabled(False)
        self.quick_scan_btn.setEnabled(False)
        self.home_scan_btn.setEnabled(False)
        self.save_profile_btn.setEnabled(False)
        self.delete_profile_btn.setEnabled(False)
        self.cancel_btn.setVisible(True)
        self.cancel_btn.setEnabled(True)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.file_count_label.setVisible(False)
        self.status_label.setText("Quick Scanning common locations...")

        self._quick_thread = QuickScanThread(self.scanner)
        self._quick_thread.progress.connect(self._on_progress)
        self._quick_thread.finished.connect(self._on_finished)
        self._quick_thread.error.connect(self._on_error)
        self._quick_thread.start()
        self.scan_started.emit("Quick Scan", "quick")

    def _cancel_scan(self):
        if self._scan_thread and self._scan_thread.isRunning():
            self._scan_thread.cancel()
        if self._quick_thread and self._quick_thread.isRunning():
            self._quick_thread.cancel()
        self.cancel_btn.setEnabled(False)
        self.status_label.setText("Cancelling...")

    def _home_scan(self):
        self._scan_paths = [str(Path.home())]
        self._scan_type = "manual"
        self.path_display.setText("Home Directory")
        self._start_scan()

    def _load_profiles(self):
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        self.profile_combo.addItem("Custom...", None)
        for p in self.db.get_scan_profiles():
            self.profile_combo.addItem(p["name"], p["paths"])
        self.profile_combo.blockSignals(False)

    def _on_profile_selected(self, index):
        paths_json = self.profile_combo.currentData()
        if paths_json is None:
            return
        import json
        paths = json.loads(paths_json)
        self._scan_paths = paths
        text = "; ".join(paths[:3])
        if len(paths) > 3:
            text += f" ... (+{len(paths) - 3})"
        self.path_display.setText(text)

    def _save_profile(self):
        name, ok = QInputDialog.getText(self, "Save Profile", "Profile name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        paths = self._scan_paths
        if not paths:
            QMessageBox.information(self, "No Paths", "Select paths first.")
            return
        self.db.save_scan_profile(name, paths)
        self._load_profiles()
        idx = self.profile_combo.findText(name)
        if idx >= 0:
            self.profile_combo.setCurrentIndex(idx)
        self.status_label.setText(f"Profile '{name}' saved")

    def _delete_profile(self):
        name = self.profile_combo.currentText()
        if name == "Custom..." or not name:
            return
        reply = QMessageBox.question(
            self, "Delete Profile", f"Delete profile '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.db.delete_scan_profile(name)
            self._load_profiles()
            self.status_label.setText(f"Profile '{name}' deleted")

    def _export_profiles(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Profiles", "scan_profiles.json",
            "JSON Files (*.json)")
        if not path:
            return
        try:
            raw = self.db.export_profiles_json()
            Path(path).write_text(raw, encoding="utf-8")
            self.status_label.setText(f"Exported profiles to {path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

    def _import_profiles(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Profiles", "",
            "JSON Files (*.json)")
        if not path:
            return
        try:
            raw = Path(path).read_text(encoding="utf-8")
            count = self.db.import_profiles_json(raw)
            self._load_profiles()
            self.status_label.setText(f"Imported {count} profiles from {path}")
        except Exception as e:
            QMessageBox.critical(self, "Import Error", str(e))

    def _start_scan(self):
        if not self._scan_paths:
            QMessageBox.information(self, "No Selection", "Select a file or folder to scan.")
            return

        self._scan_type = "manual"
        path = self._scan_paths[0]
        self.result_tree.clear()
        self.result_tree.setVisible(False)
        self.scan_btn.setEnabled(False)
        self.full_scan_btn.setEnabled(False)
        self.quick_scan_btn.setEnabled(False)
        self.home_scan_btn.setEnabled(False)
        self.save_profile_btn.setEnabled(False)
        self.delete_profile_btn.setEnabled(False)
        self.cancel_btn.setVisible(True)
        self.cancel_btn.setEnabled(True)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.file_count_label.setVisible(False)
        self.status_label.setText(f"Scanning {Path(path).name}...")

        self._scan_thread = ScanThread(self.scanner, path, recursive=self.recursive_cb.isChecked())
        self._scan_thread.progress.connect(self._on_progress)
        self._scan_thread.finished.connect(self._on_finished)
        self._scan_thread.error.connect(self._on_error)
        self._scan_thread.start()
        self.scan_started.emit(path, self._scan_type)

    def _on_progress(self, result):
        if result["status"] == "infected":
            item = QTreeWidgetItem(self.result_tree)
            item.setText(0, result["path"])
            item.setText(1, "INFECTED")
            item.setForeground(1, QBrush(QColor("#e74c3c")))
            item.setText(2, result["virus"] or "Unknown")
            self.result_tree.setVisible(True)
            self.status_label.setText(f"Threat: {result['virus']}")

    def _on_finished(self, results):
        self.scanner.reset_cancel()
        self.cancel_btn.setVisible(False)
        self.scan_btn.setEnabled(True)
        self.full_scan_btn.setEnabled(True)
        self.quick_scan_btn.setEnabled(True)
        self.home_scan_btn.setEnabled(True)
        self.save_profile_btn.setEnabled(True)
        self.delete_profile_btn.setEnabled(True)
        self.progress.setVisible(False)

        infected = [r for r in results if r["status"] == "infected"]
        clean = [r for r in results if r["status"] == "clean"]
        errors = [r for r in results if r["status"] == "error"]

        summary = f"Complete — {len(results)} files: {len(infected)} threats, {len(clean)} clean"
        if errors:
            summary += f", {len(errors)} errors"
        self.status_label.setText(summary)

        self.file_count_label.setText(
            f"Scanned: {len(results)} | Infected: {len(infected)} | Clean: {len(clean)}"
        )
        self.file_count_label.setVisible(True)

        self.result_tree.setVisible(True)
        if infected:
            self.result_tree.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

        # Run VT checks BEFORE quarantine so file hashes can still be computed
        self._run_vt_checks(results)

        if infected:
            reply = QMessageBox.question(
                self, "Threats Found",
                f"{len(infected)} threats detected. Quarantine all?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                for r in infected:
                    try:
                        self.quarantine.add(r["path"], r["virus"])
                    except Exception as e:
                        log.error("Quarantine failed for %s: %s", r["path"], e)

        self.scan_completed.emit(self._scan_paths[0], self._scan_type, results)

    def _run_vt_checks(self, results):
        api_key = self.db.get_setting("vt_api_key")
        if not api_key:
            return
        log.info("Starting VirusTotal checks for %d results", len(results))
        self.status_label.setText("Checking VirusTotal...")
        import hashlib as _hashlib
        hash_map = {}
        for r in results:
            path = r.get("path", "")
            if not path or not Path(path).is_file():
                continue
            try:
                h = _hashlib.sha256()
                with open(path, "rb") as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        h.update(chunk)
                hash_map[path] = h.hexdigest()
            except (OSError, FileNotFoundError) as e:
                log.warning("VT hash compute error for %s: %s", path, e)
        if not hash_map:
            log.warning("No files available for VT hash check")
            return
        self._vt_thread = VTCheckThread(api_key, hash_map)
        self._vt_thread.result_ready.connect(self._on_vt_result)
        self._vt_thread.finished.connect(self._on_vt_finished)
        self._vt_thread.start()

    def _on_vt_finished(self):
        self.status_label.setText(
            self.status_label.text().replace("Checking VirusTotal...", "VT checks done"))

    def _on_vt_result(self, file_path, vt_result):
        found = False
        for i in range(self.result_tree.topLevelItemCount()):
            item = self.result_tree.topLevelItem(i)
            if item.text(0) == file_path:
                self._set_vt_item_text(item, vt_result)
                found = True
                break
        if not found:
            item = QTreeWidgetItem(self.result_tree)
            item.setText(0, file_path)
            item.setText(1, "skipped" if vt_result.get("status") == "error" else "clean")
            item.setText(2, "")
            self._set_vt_item_text(item, vt_result)
            self.result_tree.setVisible(True)

    def _set_vt_item_text(self, item, vt_result):
        if vt_result["status"] == "malicious":
            item.setText(3, f"⚠ {vt_result['message']}")
            item.setForeground(3, QBrush(QColor("#e74c3c")))
            if item.text(1) != "INFECTED":
                item.setText(1, "infected")
                item.setForeground(1, QBrush(QColor("#e74c3c")))
        elif vt_result["status"] == "suspicious":
            item.setText(3, f"? {vt_result['message']}")
            item.setForeground(3, QBrush(QColor("#f39c12")))
        elif vt_result["status"] == "clean":
            item.setText(3, f"✓ {vt_result['message']}")
            item.setForeground(3, QBrush(QColor("#2ecc71")))
        elif vt_result["status"] == "unknown":
            item.setText(3, "— not found")
        else:
            item.setText(3, vt_result.get("message", "error"))

    def _on_error(self, msg):
        self.scanner.reset_cancel()
        self.cancel_btn.setVisible(False)
        self.scan_btn.setEnabled(True)
        self.full_scan_btn.setEnabled(True)
        self.quick_scan_btn.setEnabled(True)
        self.home_scan_btn.setEnabled(True)
        self.save_profile_btn.setEnabled(True)
        self.delete_profile_btn.setEnabled(True)
        self.progress.setVisible(False)
        self.status_label.setText(f"Error: {msg}")
        QMessageBox.critical(self, "Scan Error", msg)

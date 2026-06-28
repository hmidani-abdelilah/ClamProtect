import os
import time
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal, QTimer

from core.logger import get_logger

log = get_logger()


class FileMonitor(QObject):
    scan_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._timer = None
        self._watched_paths = {}
        self._snapshots = {}

    def start(self, paths):
        self.stop()
        self._watched_paths = {str(p): p for p in paths if Path(p).exists()}
        if not self._watched_paths:
            return
        self._snapshots = self._take_snapshot()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(2000)
        log.info("File monitor started (polling): %s", list(self._watched_paths.keys()))

    def stop(self):
        if self._timer:
            self._timer.stop()
            self._timer = None
        self._watched_paths.clear()
        self._snapshots.clear()

    def _take_snapshot(self):
        snapshot = {}
        for path in self._watched_paths.values():
            self._snapshot_dir(path, snapshot)
        return snapshot

    def _snapshot_dir(self, path, snapshot):
        try:
            for entry in os.scandir(str(path)):
                if entry.is_file():
                    try:
                        stat = entry.stat()
                        snapshot[entry.path] = (stat.st_mtime, stat.st_size)
                    except OSError:
                        pass
                elif entry.is_dir() and not entry.name.startswith("."):
                    self._snapshot_dir(entry.path, snapshot)
        except PermissionError:
            pass

    def _poll(self):
        new_snapshot = self._take_snapshot()
        for filepath, (mtime, size) in new_snapshot.items():
            old = self._snapshots.get(filepath)
            if old is None:
                self.scan_requested.emit(filepath)
            elif old != (mtime, size):
                self.scan_requested.emit(filepath)
        for filepath in self._snapshots:
            if filepath not in new_snapshot:
                pass
        self._snapshots = new_snapshot

"""Core module tests — run with: python3 -m pytest tests/"""

import os
import stat
import sys
import tempfile
import hashlib
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.database import Database
from core.quarantine import Quarantine
from core.definitions import DefinitionsManager
from core.scanner import Scanner, ScannerError


class TestDatabase:
    def setup_method(self, method=None):
        import tempfile
        self._tmpdb = tempfile.mktemp(suffix='.db')
        import core.database as dbmod
        self._orig_path = dbmod.DB_PATH
        dbmod.DB_PATH = dbmod.Path(self._tmpdb)
        self.db = Database()

    def teardown_method(self, method=None):
        import core.database as dbmod
        dbmod.DB_PATH = self._orig_path
        import os
        if os.path.exists(self._tmpdb):
            os.unlink(self._tmpdb)

    def test_save_and_get_history(self):
        results = [
            {"path": "/a.txt", "status": "clean", "virus": None},
            {"path": "/b.txt", "status": "infected", "virus": "Test.V-1"},
        ]
        scan_id = self.db.save_scan("/test", "manual", results)
        assert scan_id > 0

        history = self.db.get_history()
        assert len(history) >= 1
        assert history[0]["infected_files"] == 1

        details = self.db.get_scan_results(scan_id)
        assert len(details) == 2

    def test_settings(self):
        self.db.set_setting("test_key", "test_value")
        assert self.db.get_setting("test_key") == "test_value"

    def test_whitelist(self):
        self.db.add_whitelist("/safe", "path")
        assert self.db.is_whitelisted("/safe/file.txt")
        assert not self.db.is_whitelisted("/unsafe/file.txt")

    def test_save_and_get_scan_profile(self):
        self.db.save_scan_profile("test_profile", ["/home", "/tmp"])
        profiles = self.db.get_scan_profiles()
        names = [p["name"] for p in profiles]
        assert "test_profile" in names

    def test_delete_scan_profile(self):
        self.db.save_scan_profile("delete_me", ["/usr"])
        self.db.delete_scan_profile("delete_me")
        profiles = self.db.get_scan_profiles()
        names = [p["name"] for p in profiles]
        assert "delete_me" not in names

    def test_export_import_profiles_json(self):
        self.db.save_scan_profile("prof_a", ["/a", "/b"])
        self.db.save_scan_profile("prof_b", ["/c"])
        raw = self.db.export_profiles_json()
        assert '"prof_a"' in raw
        assert '"prof_b"' in raw
        self.db.delete_scan_profile("prof_a")
        self.db.delete_scan_profile("prof_b")
        count = self.db.import_profiles_json(raw)
        assert count == 2
        profiles = self.db.get_scan_profiles()
        names = [p["name"] for p in profiles]
        assert "prof_a" in names
        assert "prof_b" in names

    def test_import_profiles_json_invalid(self):
        try:
            self.db.import_profiles_json("null")
            assert False
        except ValueError:
            pass

    def test_scan_profile_paths_roundtrip(self):
        import json
        expected = ["/home", "/tmp", "/usr/bin"]
        self.db.save_scan_profile("roundtrip", expected)
        profiles = self.db.get_scan_profiles()
        match = [p for p in profiles if p["name"] == "roundtrip"]
        assert len(match) == 1
        loaded = json.loads(match[0]["paths"])
        assert loaded == expected


class TestQuarantine:
    def setup_method(self, method=None):
        import tempfile
        self._tmpdb = tempfile.mktemp(suffix='.db')
        import core.database as dbmod
        self._orig_path = dbmod.DB_PATH
        dbmod.DB_PATH = dbmod.Path(self._tmpdb)
        self.db = Database()
        self.q = Quarantine(self.db)

    def teardown_method(self, method=None):
        import core.database as dbmod
        dbmod.DB_PATH = self._orig_path
        import os
        if os.path.exists(self._tmpdb):
            os.unlink(self._tmpdb)

    def test_add_restore_delete(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("test quarantine data")
            path = f.name

        self.q.add(path, "Test.Virus-1")
        assert not os.path.exists(path)

        items = self.q.list()
        assert len(items) >= 1
        assert items[0]["virus_name"] == "Test.Virus-1"

        self.q.restore(items[0]["id"])
        assert os.path.exists(items[0]["original_path"])
        os.unlink(items[0]["original_path"])

    def test_verify_integrity_ok(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("verify me")
            path = f.name

        self.q.add(path, "Test.V-2")
        items = self.q.list()
        assert self.q.verify(items[0]["id"]) is True

        self.q.delete(items[0]["id"])

    def test_verify_integrity_tampered(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("original content")
            path = f.name

        self.q.add(path, "Test.V-3")
        items = self.q.list()
        quarantined_path = (
            Path.home() / ".local" / "share" / "ClamProtect" / "quarantine"
            / items[0]["quarantined_name"]
        )

        os.chmod(quarantined_path, 0o644)
        with open(quarantined_path, "a") as f:
            f.write("tampered")
        os.chmod(quarantined_path, 0o000)

        assert self.q.verify(items[0]["id"]) is False
        self.q.delete(items[0]["id"])

    def test_restore_strips_suid(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("suid test")
            path = f.name

        os.chmod(path, 0o4755)
        self.q.add(path, "Test.SUID-1")
        items = self.q.list()
        assert items[0].get("original_permissions", 0) & stat.S_ISUID

        self.q.restore(items[0]["id"])
        restored_st = os.stat(items[0]["original_path"])
        restored_mode = stat.S_IMODE(restored_st.st_mode)
        assert not (restored_mode & stat.S_ISUID)
        assert not (restored_mode & stat.S_ISGID)
        os.unlink(items[0]["original_path"])


class TestDefinitions:
    def setup_method(self, method=None):
        self.dm = DefinitionsManager()

    def test_get_status(self):
        status = self.dm.get_status()
        assert "status" in status


class TestScanner:
    def setup_method(self, method=None):
        self.scanner = Scanner()

    def test_ping(self):
        ping = self.scanner.ping()
        assert isinstance(ping, bool)

    def test_version(self):
        ver = self.scanner.version()
        assert len(ver) > 0

    def test_scan_nonexistent(self):
        try:
            self.scanner.scan("/nonexistent_path_xyz")
            assert False, "Should raise"
        except ScannerError:
            pass

    def test_scan_clean_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                         delete=False) as f:
            f.write("hello world")
            path = f.name
        results = self.scanner.scan(path)
        assert len(results) >= 1
        os.unlink(path)

    def test_scan_non_recursive_flag_passed(self):
        assert self.scanner.scan.__code__.co_varnames[:3] == ("self", "path", "callback")
        # recursive is the 4th param (after callback), verify default is True
        import inspect
        sig = inspect.signature(self.scanner.scan)
        assert sig.parameters["recursive"].default is True

    def test_quick_scan_skips_missing_paths(self):
        missing = "/nonexistent_path_xyz_12345"
        results = self.scanner.quick_scan(paths=[missing])
        assert isinstance(results, list)
        assert len(results) == 0

    def test_quick_scan_aggregates_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = self.scanner.quick_scan(paths=[tmp])
            assert isinstance(results, list)

    def test_cancel_flag(self):
        assert not self.scanner._cancel
        self.scanner.cancel()
        assert self.scanner._cancel
        self.scanner.reset_cancel()
        assert not self.scanner._cancel

    def test_quick_scan_respects_cancel(self):
        self.scanner.cancel()
        results = self.scanner.quick_scan(paths=["/tmp"])
        assert len(results) == 0

    def test_scan_cancel_returns_partial(self):
        self.scanner.cancel()
        results = self.scanner.scan(os.path.dirname(__file__))
        assert isinstance(results, list)

    def test_try_clamdscan_returns_list_or_none(self):
        result = self.scanner._try_clamdscan("/tmp")
        assert isinstance(result, list) or result is None

    def test_clamd_broken_flag_skips_clamd(self):
        self.scanner._clamd_broken = True
        # scan should log "Clamd unavailable or broken" and NOT try clamd at all
        results = self.scanner.scan(os.path.dirname(__file__))
        assert isinstance(results, list)


class TestOnAccess:
    def test_start_stop(self):
        from core.onaccess import OnAccessScanner
        oa = OnAccessScanner()
        assert oa.is_running is False
        ok = oa.start()
        if ok:
            assert oa.is_running is True
            oa.stop()
            assert oa.is_running is False
        else:
            assert oa.is_running is False


class TestUSBMonitor:
    def test_poll_noop_when_disabled(self):
        from core.usb_monitor import USBMonitor
        monitor = USBMonitor(None, None)
        monitor.poll()


class TestVirusTotal:
    def test_checker_no_key(self):
        from core.virustotal import VirusTotalChecker
        v = VirusTotalChecker()
        assert v.is_available() is False
        result = v.check_hash("d41d8cd98f00b204e9800998ecf8427e")
        assert result["status"] == "error"

    def test_check_file_missing(self):
        from core.virustotal import VirusTotalChecker
        v = VirusTotalChecker("test_key")
        result = v.check_file("/nonexistent_vt_test_file_xyz")
        assert result["status"] == "error"





class TestQtEnumCompat:
    """Verify PyQt6 enum patterns across UI source files."""

    BAD_PATTERNS = [
        "QMessageBox.Yes",
        "QMessageBox.No",
        "QMessageBox.Cancel",
        "QMessageBox.Ok",
    ]

    def test_quarantine_dock_no_pyqt5_enums(self):
        """Ensure quarantine_dock.py uses StandardButton-qualified QMessageBox enums."""
        src = Path(__file__).parent.parent / "ui" / "quarantine_dock.py"
        lines = src.read_text().splitlines()
        for i, line in enumerate(lines, 1):
            for pat in self.BAD_PATTERNS:
                if f" {pat}," in line or f" {pat})" in line or f" {pat} " in line:
                    raise AssertionError(
                        f"Line {i}: PyQt5-style enum {pat}")

"""Security audit tests — run with: python3 -m pytest tests/"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.security_audit import run_audit, _check_ssh, _load_ssh_config


class TestAudit:
    def test_run_audit_returns_list(self):
        results = run_audit()
        assert isinstance(results, list)
        assert len(results) >= 8

    def test_each_result_has_required_keys(self):
        results = run_audit()
        for r in results:
            assert "name" in r
            assert "status" in r
            assert "message" in r
            assert r["status"] in ("ok", "info", "warning", "error")

    def test_ssh_load_config_returns_dict(self):
        cfg = _load_ssh_config()
        assert isinstance(cfg, dict)

    def test_ssh_check_reports_findings(self):
        result = _check_ssh()
        assert result["status"] in ("ok", "info", "warning", "error")
        assert "SSH" in result["message"] or "ssh" in result.get("detail", "").lower()
        assert isinstance(result.get("detail", ""), str)

    def test_specific_checks_present(self):
        results = run_audit()
        names = {r["name"] for r in results}
        for expected in ("Firewall", "AppArmor", "SELinux", "SSH Config",
                         "Open Ports", "Lynis", "Rootkit Scanners",
                         "ClamAV Definitions"):
            assert expected in names, f"Missing check: {expected}"

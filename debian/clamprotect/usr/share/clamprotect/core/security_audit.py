import os
import subprocess
from pathlib import Path

from core.logger import get_logger
from core.definitions import DefinitionsManager

log = get_logger()


def _run(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except FileNotFoundError:
        return -1, "", "command not found"
    except subprocess.TimeoutExpired:
        return -1, "", "timed out"


def _check_firewall():
    for cmd, label in [
        (["ufw", "status"], "ufw"),
        (["iptables", "-L", "-n"], "iptables"),
        (["nft", "list", "ruleset"], "nftables"),
    ]:
        rc, out, err = _run(cmd, timeout=5)
        if rc == 0:
            active = "active" in out.lower() or "chain" in out.lower()
            return {"status": "ok" if active else "warning", "message": label, "detail": out[:200]}
        if "permission" in err.lower() or "not root" in err.lower():
            return {"status": "warning", "message": "Firewall check needs root", "detail": f"run {label} as root"}
    return {"status": "error", "message": "No firewall tool found", "detail": "install ufw, iptables, or nftables"}


def _check_apparmor():
    if Path("/sys/module/apparmor/parameters/enabled").exists():
        enabled = Path("/sys/module/apparmor/parameters/enabled").read_text().strip()
        if enabled == "Y":
            rc, out, _ = _run(["aa-status"], timeout=5)
            if rc == 0:
                prof_line = [l for l in out.split("\n") if "profiles" in l]
                detail = prof_line[0] if prof_line else out[:200]
                return {"status": "ok", "message": "AppArmor enabled", "detail": detail}
            prof_path = Path("/sys/kernel/security/apparmor/profiles")
            if prof_path.exists():
                try:
                    if prof_path.is_dir():
                        prof_count = len(list(prof_path.iterdir()))
                    else:
                        prof_count = len(prof_path.read_text().splitlines())
                    return {"status": "ok", "message": "AppArmor enabled", "detail": f"{prof_count} profiles loaded (sysfs)"}
                except PermissionError:
                    return {"status": "warning", "message": "AppArmor enabled", "detail": "sysfs requires root"}
            return {"status": "warning", "message": "AppArmor module loaded", "detail": "aa-status needs root; try with sudo"}
        return {"status": "warning", "message": "AppArmor disabled", "detail": ""}
    return {"status": "error", "message": "AppArmor not present", "detail": ""}


def _check_selinux():
    rc, out, _ = _run(["getenforce"], timeout=5)
    if rc == 0:
        status = out.strip()
        if status == "Enforcing":
            return {"status": "ok", "message": "SELinux enforcing", "detail": ""}
        elif status == "Permissive":
            return {"status": "warning", "message": "SELinux permissive", "detail": ""}
        else:
            return {"status": "error", "message": "SELinux disabled", "detail": ""}
    if Path("/etc/selinux/config").exists():
        return {"status": "warning", "message": "SELinux config present", "detail": "getenforce not found"}
    return {"status": "info", "message": "SELinux not present", "detail": "not installed on this system"}


def _load_ssh_config():
    cfg = {}
    paths = [Path("/etc/ssh/sshd_config")]
    dd = Path("/etc/ssh/sshd_config.d")
    if dd.exists():
        paths.extend(sorted(dd.glob("*.conf")))
    for p in paths:
        if not p.exists():
            continue
        try:
            text = p.read_text()
        except PermissionError:
            continue
        for line in text.split("\n"):
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            parts = s.split(None, 1)
            if len(parts) == 2:
                cfg[parts[0].lower()] = parts[1]
    return cfg


def _check_ssh():
    sshd_config = Path("/etc/ssh/sshd_config")
    if not sshd_config.exists():
        return {"status": "warning", "message": "sshd_config not found", "detail": ""}
    try:
        sshd_config.read_bytes()
    except PermissionError:
        return {"status": "warning", "message": "Cannot read sshd_config", "detail": "insufficient permissions"}

    config = _load_ssh_config()

    def _int(val):
        try:
            return int(val)
        except (ValueError, TypeError):
            return None

    def _time_sec(val):
        if val is None:
            return None
        v = str(val).lower().strip()
        try:
            if v.endswith("m"):
                return int(v[:-1]) * 60
            if v.endswith("h"):
                return int(v[:-1]) * 3600
            if v.endswith("s"):
                return int(v[:-1])
            return int(v)
        except (ValueError, TypeError):
            return None

    checks = [
        ("PermitRootLogin",           ["no", "prohibit-password"], "warning", ["yes", "without-password", "forced-commands-only"]),
        ("PasswordAuthentication",    ["no"],                      "warning", ["yes"]),
        ("PermitEmptyPasswords",      ["no"],                      "warning", ["yes"]),
        ("PubkeyAuthentication",      ["yes"],                     "info",    ["no"]),
        ("ChallengeResponseAuthentication", ["no"],                "warning", ["yes"]),
        ("KbdInteractiveAuthentication",    ["no"],                "warning", ["yes"]),
        ("HostbasedAuthentication",   ["no"],                      "info",    ["yes"]),
        ("IgnoreRhosts",              ["yes"],                     "info",    ["no"]),
        ("X11Forwarding",             ["no"],                      "info",    ["yes"]),
    ]

    findings = []
    insecure = []

    for key, secure_vals, severity, insecure_vals in checks:
        val = config.get(key.lower())
        if val is None:
            continue
        vlow = val.lower()
        if vlow in [s.lower() for s in secure_vals]:
            findings.append(f"{key} {val}")
        elif vlow in [s.lower() for s in insecure_vals]:
            entry = f"{key} {val} \u2716"
            findings.append(entry)
            insecure.append(entry)
        else:
            findings.append(f"{key} {val}")

    # Numeric / special checks
    port_val = config.get("port")
    if port_val:
        findings.append(f"Port {port_val}" + (" \u2716" if port_val == "22" else ""))
        if port_val == "22":
            insecure.append(f"Port 22 (default)")

    mt = _int(config.get("maxauthtries"))
    if mt is not None:
        if mt <= 3:
            findings.append(f"MaxAuthTries {mt}")
        else:
            entry = f"MaxAuthTries {mt} \u2716"
            findings.append(entry)
            insecure.append(entry)

    lgt = _time_sec(config.get("logingracetime"))
    if lgt is not None:
        val_raw = config["logingracetime"]
        if lgt <= 120:
            findings.append(f"LoginGraceTime {val_raw}")
        else:
            entry = f"LoginGraceTime {val_raw} \u2716"
            findings.append(entry)
            insecure.append(entry)

    ci = _int(config.get("clientaliveinterval"))
    if ci is not None:
        if 0 < ci <= 300:
            findings.append(f"ClientAliveInterval {ci}s")
        elif ci == 0:
            entry = "ClientAliveInterval 0 \u2716"
            findings.append(entry)
            insecure.append(entry)
        else:
            findings.append(f"ClientAliveInterval {ci}s")

    for key in ("allowusers", "allowgroups"):
        val = config.get(key)
        if val:
            findings.append(f"{key} {val}")

    if not findings:
        return {"status": "info", "message": "SSH defaults", "detail": "no explicit hardening"}

    detail = "; ".join(findings)
    if insecure:
        return {"status": "warning", "message": f"{len(insecure)} insecure SSH setting(s)", "detail": detail}
    return {"status": "ok", "message": "SSH config securely hardened", "detail": detail}


def _check_open_ports():
    rc, out, _ = _run(["ss", "-tlnp"], timeout=5)
    if rc != 0:
        rc, out, _ = _run(["netstat", "-tlnp"], timeout=5)
    if rc != 0:
        return {"status": "warning", "message": "Cannot check ports", "detail": "ss/netstat not found"}

    lines = [l.strip() for l in out.split("\n") if l.strip()]
    listening = []
    for line in lines:
        if "LISTEN" in line.upper() or "*:" in line:
            parts = line.split()
            if len(parts) >= 4:
                listening.append(parts[3] if "LISTEN" in line.upper() else parts[0])
    if not listening:
        return {"status": "ok", "message": "No listening ports detected", "detail": ""}
    return {"status": "info", "message": f"{len(listening)} listening ports", "detail": ", ".join(listening[:10])}


def _check_rootkit():
    checks = []
    for cmd, name in [
        (["rkhunter", "--version"], "rkhunter"),
        (["chkrootkit", "-V"], "chkrootkit"),
    ]:
        rc, out, _ = _run(cmd, timeout=5)
        if rc == 0:
            checks.append(f"{name} installed: {out.split(chr(10))[0][:60]}")

    if not checks:
        return {"status": "warning", "message": "No rootkit scanner installed", "detail": "install rkhunter or chkrootkit"}

    for log_path, label in [(Path("/var/log/rkhunter.log"), "rkhunter"),
                             (Path("/var/log/chkrootkit.log"), "chkrootkit")]:
        if log_path.exists():
            try:
                last_line = subprocess.run(
                    ["tail", "-1", str(log_path)], capture_output=True, text=True, timeout=5
                ).stdout.strip()
                if last_line:
                    checks.append(f"{label} log: {last_line[:80]}")
            except (PermissionError, OSError):
                checks.append(f"{label} log: requires root")
    return {"status": "info" if checks else "error", "message": "Rootkit scanner(s) found" if checks else "No rootkit scanner", "detail": "; ".join(checks)}


def _check_lynis():
    rc, out, _ = _run(["lynis", "--version"], timeout=5)
    if rc != 0:
        return {"status": "warning", "message": "Lynis not installed", "detail": "install lynis for deeper security audits"}
    version = out.split("\n")[0][:60] if out else "installed"
    lynis_log = Path("/var/log/lynis.log")
    if lynis_log.exists():
        try:
            last_line = subprocess.run(
                ["tail", "-1", str(lynis_log)], capture_output=True, text=True, timeout=5
            ).stdout.strip()[:80]
            return {"status": "info", "message": version, "detail": f"last log: {last_line}"}
        except (PermissionError, OSError):
            return {"status": "info", "message": version, "detail": "log requires root"}
    return {"status": "info", "message": version, "detail": "no previous audit log found"}


def _check_clamav_defs():
    dm = DefinitionsManager()
    status = dm.get_status()
    if status.get("status") == "ok":
        return {"status": "ok", "message": "ClamAV definitions OK", "detail": status.get("last_updated", "")}
    return {"status": "error", "message": "ClamAV issue", "detail": status.get("message", "")}


_CHECKS = [
    ("Firewall", _check_firewall),
    ("AppArmor", _check_apparmor),
    ("SELinux", _check_selinux),
    ("SSH Config", _check_ssh),
    ("Open Ports", _check_open_ports),
    ("Lynis", _check_lynis),
    ("Rootkit Scanners", _check_rootkit),
    ("ClamAV Definitions", _check_clamav_defs),
]


def run_audit():
    log.info("Starting security audit")
    results = []
    for name, check_fn in _CHECKS:
        try:
            result = check_fn()
            result["name"] = name
        except Exception as e:
            log.error("Audit check %s failed: %s", name, e)
            result = {"name": name, "status": "error", "message": str(e), "detail": ""}
        results.append(result)
        log.info("Audit %s: %s", name, result["status"])
    return results

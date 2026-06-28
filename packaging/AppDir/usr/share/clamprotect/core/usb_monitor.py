import subprocess
from pathlib import Path

from core.logger import get_logger

log = get_logger()

_KNOWN_MOUNTS = set()


def _get_mounts():
    mounts = []
    try:
        with open("/proc/mounts") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    mounts.append(parts[1])
    except FileNotFoundError:
        rc, out, _ = _run(["mount"], timeout=5)
        if rc == 0:
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 3:
                    mounts.append(parts[2])
    return set(mounts)


def _run(cmd, timeout=5):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except FileNotFoundError:
        return -1, "", "command not found"
    except subprocess.TimeoutExpired:
        return -1, "", "timed out"


def _is_removable(path):
    try:
        result = subprocess.run(
            ["findmnt", "-o", "FSTYPE,OPTIONS", "-T", str(path)],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "vfat" in line or "ntfs" in line or "exfat" in line or "iso9660" in line:
                    return True
    except Exception:
        pass
    return False


class USBMonitor:
    def __init__(self, scanner, callback):
        self.scanner = scanner
        self.callback = callback
        self._enabled = False
        self._scan_network = False
        self._known = set()

    def start(self, scan_network=False):
        self._scan_network = scan_network
        self._known = _get_mounts()
        self._enabled = True
        log.info("USB monitor started (%d known mounts)", len(self._known))

    def stop(self):
        self._enabled = False
        log.info("USB monitor stopped")

    def poll(self):
        if not self._enabled:
            return
        current = _get_mounts()
        new_mounts = current - self._known
        if not new_mounts:
            return
        for mnt in sorted(new_mounts):
            pp = Path(mnt)
            if not pp.exists():
                continue
            if not self._scan_network and not _is_removable(mnt):
                log.debug("Skipping non-removable mount: %s", mnt)
                continue
            log.info("New mount detected: %s", mnt)
            try:
                results = self.scanner.scan(str(pp))
                infected = [r for r in results if r.get("status") == "infected"]
                if infected and self.callback:
                    self.callback(str(pp), infected)
            except Exception as e:
                log.error("USB scan error on %s: %s", mnt, e)
        self._known = current

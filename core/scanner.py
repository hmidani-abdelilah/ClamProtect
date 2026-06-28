import socket
import subprocess
from pathlib import Path

from core.logger import get_logger

QUICK_SCAN_PATHS = ["/tmp", "/var/tmp", "/home", "/usr/bin", "/etc"]

log = get_logger()


class ScannerError(Exception):
    pass


class Scanner:
    def __init__(self, socket_path="/var/run/clamav/clamd.ctl", timeout=60):
        self.socket_path = socket_path
        self.timeout = timeout
        self._cancel = False
        self._clamd_broken = False

    def cancel(self):
        self._cancel = True

    def reset_cancel(self):
        self._cancel = False

    def ping(self):
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect(self.socket_path)
            sock.sendall(b"nPING\n")
            resp = sock.recv(1024).decode().strip()
            sock.close()
            return resp == "PONG"
        except (socket.error, FileNotFoundError):
            return False

    def version(self):
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect(self.socket_path)
            sock.sendall(b"nVERSION\n")
            resp = sock.recv(1024).decode().strip()
            sock.close()
            return resp
        except (socket.error, FileNotFoundError):
            result = subprocess.run(
                ["clamscan", "--version"],
                capture_output=True, text=True, timeout=10,
            )
            return result.stdout.strip() if result.returncode == 0 else "unknown"

    def scan(self, path, callback=None, recursive=True):
        path = str(Path(path).resolve())
        if not Path(path).exists():
            raise ScannerError(f"Path does not exist: {path}")

        if not recursive:
            log.info("Non-recursive scan requested — using clamscan")
            return self._scan_clamscan(path, callback, recursive=False)

        if self.ping() and not self._clamd_broken:
            log.info("Using clamd socket for scan")
            try:
                results = self._scan_clamd(path, callback)
            except ScannerError as e:
                self._clamd_broken = True
                log.warning("Clamd scan error (%s) — marked broken, using clamscan", e)
                return self._scan_clamscan(path, callback)
            if results and all(r["status"] == "error" for r in results):
                self._clamd_broken = True
                log.info("Clamd returns all errors — marked broken for session, using clamscan")
                return self._scan_clamscan(path, callback)
            self._clamd_broken = False
            return results

        if self._clamd_broken:
            log.info("Clamd known broken, using clamscan")
            return self._scan_clamscan(path, callback)

        log.info("Clamd unavailable, trying clamdscan")
        return self._try_clamdscan(path, callback) or self._scan_clamscan(path, callback)

    def _scan_clamd(self, path, callback=None):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect(self.socket_path)
            sock.sendall(f"nCONTSCAN {path}\n".encode())

            results = []
            buf = b""
            while True:
                if self._cancel:
                    break
                try:
                    chunk = sock.recv(65536)
                except socket.timeout:
                    raise ScannerError("Clamd scan timed out")
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.decode().strip()
                    if not line or line.startswith("---"):
                        continue
                    result = self._parse_line(line)
                    if result:
                        results.append(result)
                        if callback:
                            callback(result)
            return results
        except socket.timeout:
            raise ScannerError("Clamd scan timed out")
        except ConnectionRefusedError:
            raise ScannerError("Clamd refused connection")
        except FileNotFoundError:
            raise ScannerError(f"Clamd socket not found: {self.socket_path}")
        finally:
            sock.close()

    def _scan_clamscan(self, path, callback=None, recursive=True):
        try:
            cmd = ["clamscan", "--no-summary", "--infected"]
            if recursive:
                cmd.append("-r")
            cmd.append(path)
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            results = self._read_clamscan_output(proc, callback)

            if not results and not self._cancel:
                cmd2 = ["clamscan", "--no-summary"]
                if recursive:
                    cmd2.append("-r")
                cmd2.append(path)
                proc2 = subprocess.Popen(
                    cmd2, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                )
                results = self._read_clamscan_output(proc2, callback)
            return results
        except FileNotFoundError:
            raise ScannerError("clamscan not found. Install clamav package.")

    def _try_clamdscan(self, path, callback=None, recursive=True):
        try:
            results = self._scan_clamdscan(path, callback, recursive)
            if results and all(r["status"] == "error" for r in results):
                log.info("Clamdscan also returned all errors — falling through to clamscan")
                return None
            return results
        except ScannerError:
            log.warning("Clamdscan unavailable")
            return None

    def _scan_clamdscan(self, path, callback=None, recursive=True):
        try:
            cmd = ["clamdscan", "--no-summary", "--infected"]
            if recursive:
                cmd.append("-r")
            cmd.append(path)
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            results = self._read_clamscan_output(proc, callback)
            if not results and not self._cancel:
                cmd2 = ["clamdscan", "--no-summary"]
                if recursive:
                    cmd2.append("-r")
                cmd2.append(path)
                proc2 = subprocess.Popen(
                    cmd2, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                )
                results = self._read_clamscan_output(proc2, callback)
            return results
        except FileNotFoundError:
            raise ScannerError("clamdscan not found. Install clamav package.")

    def _read_clamscan_output(self, proc, callback=None):
        results = []
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            result = self._parse_line(line)
            if result:
                results.append(result)
                if callback and result["status"] == "infected":
                    callback(result)
            if self._cancel:
                proc.kill()
                break
        proc.wait(timeout=5)
        return results

    def quick_scan(self, paths=None, callback=None):
        if paths is None:
            paths = QUICK_SCAN_PATHS
        log.info("Quick scan: %s", paths)
        all_results = []
        for p in paths:
            if self._cancel:
                log.info("Quick scan cancelled")
                break
            pp = Path(p)
            if not pp.exists():
                log.warning("Quick scan path not found: %s", p)
                continue
            try:
                all_results.extend(self.scan(str(pp), callback))
            except ScannerError as e:
                log.warning("Quick scan error on %s: %s", p, e)
        return all_results

    def _parse_line(self, line):
        if ": " not in line:
            return None
        filepath, status = line.split(": ", 1)
        if "OK" in status:
            return {"path": filepath, "status": "clean", "virus": None}
        elif "FOUND" in status:
            virus = status.replace(" FOUND", "").strip()
            return {"path": filepath, "status": "infected", "virus": virus}
        elif "ERROR" in status:
            return {"path": filepath, "status": "error", "virus": None}
        return None

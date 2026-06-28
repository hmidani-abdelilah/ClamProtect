import subprocess
import signal

from core.logger import get_logger

log = get_logger()


class OnAccessScanner:
    def __init__(self, socket_path="/var/run/clamav/clamd.ctl"):
        self.socket_path = socket_path
        self._process = None

    @property
    def is_running(self):
        return self._process is not None and self._process.poll() is None

    def start(self):
        if self.is_running:
            log.info("On-access scanner already running")
            return True
        try:
            self._process = subprocess.Popen(
                ["clamonacc", "--fdpass", "--log=/tmp/clamonacc.log",
                 f"--config-file={self.socket_path}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            log.info("On-access scanner started (pid=%d)", self._process.pid)
            return True
        except FileNotFoundError:
            log.warning("clamonacc not found — install clamav-daemon")
            self._process = None
            return False
        except Exception as e:
            log.error("Failed to start clamonacc: %s", e)
            self._process = None
            return False

    def stop(self):
        if self._process is not None:
            try:
                self._process.send_signal(signal.SIGTERM)
                self._process.wait(timeout=5)
                log.info("On-access scanner stopped")
            except Exception as e:
                log.error("Error stopping clamonacc: %s", e)
            self._process = None

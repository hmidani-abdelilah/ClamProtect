import subprocess
from pathlib import Path

from core.logger import get_logger

log = get_logger()


class DefinitionsManager:
    DB_DIR = Path("/var/lib/clamav")

    def get_status(self):
        cvd_files = list(self.DB_DIR.glob("*.cvd")) + list(self.DB_DIR.glob("*.cld"))
        if not cvd_files:
            return {"status": "missing", "message": "No virus definitions found"}

        cvd_file = cvd_files[0]
        mtime = cvd_file.stat().st_mtime
        from datetime import datetime
        last_updated = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")

        try:
            result = subprocess.run(
                ["clamscan", "--version"],
                capture_output=True, text=True, timeout=10,
            )
            version = result.stdout.strip() if result.returncode == 0 else "unknown"
        except FileNotFoundError:
            version = "clamscan not found"

        return {
            "status": "ok",
            "version": version,
            "files": len(cvd_files),
            "last_updated": last_updated,
        }

    def update(self):
        log.info("Starting virus definition update")
        try:
            subprocess.run(["pkill", "-f", "freshclam"],
                           capture_output=True, timeout=5)
            import time
            time.sleep(1)

            result = subprocess.run(
                ["freshclam", "--stdout"],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode == 0:
                log.info("Definition update successful")
                return {"status": "updated", "message": result.stdout.strip()}
            else:
                err = (result.stderr or result.stdout or "").strip()[:200]
                log.warning("Definition update failed: %s", err or "unknown error")
                return {"status": "error", "message": err or "unknown error"}
        except FileNotFoundError:
            return {"status": "error", "message": "freshclam not found"}
        except subprocess.TimeoutExpired:
            return {"status": "error", "message": "Update timed out"}

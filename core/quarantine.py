import hashlib
import os
import shutil
import stat
import uuid
from pathlib import Path

from core.logger import get_logger

log = get_logger()

QUARANTINE_DIR = Path.home() / ".local" / "share" / "ClamProtect" / "quarantine"


class Quarantine:
    def __init__(self, db):
        self.db = db
        QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)

    def add(self, file_path, virus_name=None):
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        dest_name = f"{uuid.uuid4().hex}_{path.name}"
        dest = QUARANTINE_DIR / dest_name

        md5 = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                md5.update(chunk)
        file_hash = md5.hexdigest()
        st = path.stat()
        file_size = st.st_size
        original_permissions = stat.S_IMODE(st.st_mode)

        shutil.copy2(str(path), str(dest))
        dest.chmod(0o000)

        path.unlink()

        self.db.add_to_quarantine(
            str(path.resolve()), dest_name,
            virus_name, file_size, file_hash, original_permissions,
        )

        log.info(
            "Quarantined %s -> %s (%s) mode=%o",
            file_path, dest_name, virus_name or "unknown", original_permissions,
        )
        return dest_name

    def list(self):
        return self.db.get_quarantine()

    def verify(self, item_id):
        item = self.db.get_quarantine_item(item_id)
        if not item:
            raise ValueError("Quarantine item not found")
        if item["restored"]:
            raise ValueError("Item already restored")
        src = QUARANTINE_DIR / item["quarantined_name"]
        if not src.exists():
            return False
        src.chmod(0o644)
        try:
            md5 = hashlib.md5()
            with open(src, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    md5.update(chunk)
            ok = md5.hexdigest() == item["md5_hash"]
            log.info(
                "Verify %s: %s (expected=%s actual=%s)",
                item["quarantined_name"], "OK" if ok else "TAMPERED",
                item["md5_hash"], md5.hexdigest(),
            )
            return ok
        finally:
            src.chmod(0o000)

    def restore(self, item_id):
        item = self.db.get_quarantine_item(item_id)
        if not item:
            raise ValueError("Quarantine item not found")
        if item["restored"]:
            raise ValueError("Item already restored")

        dest = Path(item["original_path"])
        src = QUARANTINE_DIR / item["quarantined_name"]

        if not src.exists():
            raise FileNotFoundError(f"Quarantine file missing: {src}")

        orig_mode = item.get("original_permissions", 0o644)
        if orig_mode & (stat.S_ISUID | stat.S_ISGID):
            log.warning(
                "Stripping SUID/SGID from %s (original mode was %o)",
                item["original_path"], orig_mode,
            )

        dest.parent.mkdir(parents=True, exist_ok=True)
        src.chmod(0o644)
        shutil.move(str(src), str(dest))
        os.chmod(dest, stat.S_IMODE(dest.stat().st_mode) & ~(stat.S_ISUID | stat.S_ISGID))
        self.db.restore_quarantine(item_id)
        log.info("Restored %s -> %s", item["quarantined_name"], item["original_path"])

    def delete(self, item_id):
        item = self.db.get_quarantine_item(item_id)
        if not item:
            raise ValueError("Quarantine item not found")

        src = QUARANTINE_DIR / item["quarantined_name"]
        if src.exists():
            src.chmod(0o644)
            src.unlink()

        self.db.delete_quarantine_entry(item_id)
        log.info("Deleted quarantine file %s", item["quarantined_name"])

import sqlite3
from pathlib import Path

DB_DIR = Path.home() / ".local" / "share" / "ClamProtect"
DB_PATH = DB_DIR / "clamprotect.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS scan_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL,
    scan_type TEXT NOT NULL DEFAULT 'manual',
    status TEXT NOT NULL DEFAULT 'clean',
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    total_files INTEGER DEFAULT 0,
    infected_files INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS scan_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    status TEXT NOT NULL,
    virus_name TEXT,
    FOREIGN KEY (scan_id) REFERENCES scan_history(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS quarantine_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_path TEXT NOT NULL,
    quarantined_name TEXT NOT NULL,
    virus_name TEXT,
    file_size INTEGER DEFAULT 0,
    md5_hash TEXT,
    quarantined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    restored INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS whitelist_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT NOT NULL UNIQUE,
    pattern_type TEXT NOT NULL DEFAULT 'path',
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scan_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    paths TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT OR IGNORE INTO settings (key, value) VALUES
    ('theme', 'system'),
    ('clamd_socket', '/var/run/clamav/clamd.ctl'),
    ('use_clamscan_fallback', 'true'),
    ('watch_directories', ''),
    ('notifications', 'true'),
    ('auto_update', 'true');
"""


class Database:
    def __init__(self):
        DB_DIR.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    def _conn(self):
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def save_scan(self, path, scan_type, results):
        infected = [r for r in results if r.get("status") == "infected"]
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO scan_history
                   (path, scan_type, status, completed_at, total_files, infected_files)
                   VALUES (?, ?, ?, datetime('now'), ?, ?)""",
                (path, scan_type,
                 "infected" if infected else "clean",
                 len(results), len(infected)),
            )
            scan_id = cur.lastrowid
            for r in results:
                conn.execute(
                    "INSERT INTO scan_results (scan_id, file_path, status, virus_name) "
                    "VALUES (?, ?, ?, ?)",
                    (scan_id, r["path"], r["status"], r.get("virus")),
                )
            return scan_id

    def get_history(self, limit=100):
        with self._conn() as conn:
            return [
                dict(r) for r in conn.execute(
                    "SELECT * FROM scan_history ORDER BY started_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            ]

    def get_scan_results(self, scan_id):
        with self._conn() as conn:
            return [
                dict(r) for r in conn.execute(
                    "SELECT * FROM scan_results WHERE scan_id = ?", (scan_id,)
                ).fetchall()
            ]

    def get_latest_scans(self, limit=5):
        with self._conn() as conn:
            return [
                dict(r) for r in conn.execute(
                    "SELECT * FROM scan_results WHERE status = 'infected' "
                    "ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
            ]

    def add_to_quarantine(self, original_path, quarantined_name, virus_name,
                          file_size, md5_hash, original_permissions=0):
        with self._conn() as conn:
            try:
                conn.execute(
                    "ALTER TABLE quarantine_items ADD COLUMN original_permissions"
                    " INTEGER DEFAULT 0")
            except Exception:
                pass
            conn.execute(
                """INSERT INTO quarantine_items
                   (original_path, quarantined_name, virus_name, file_size, md5_hash,
                    original_permissions)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (original_path, quarantined_name, virus_name, file_size, md5_hash,
                 original_permissions),
            )

    def get_quarantine(self):
        with self._conn() as conn:
            return [
                dict(r) for r in conn.execute(
                    "SELECT * FROM quarantine_items WHERE restored = 0 "
                    "ORDER BY quarantined_at DESC"
                ).fetchall()
            ]

    def get_quarantine_item(self, item_id):
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM quarantine_items WHERE id = ?", (item_id,)
            ).fetchone()
            return dict(row) if row else None

    def restore_quarantine(self, item_id):
        with self._conn() as conn:
            conn.execute(
                "UPDATE quarantine_items SET restored = 1 WHERE id = ?",
                (item_id,),
            )

    def delete_quarantine_entry(self, item_id):
        with self._conn() as conn:
            row = conn.execute(
                "SELECT quarantined_name FROM quarantine_items WHERE id = ?",
                (item_id,),
            ).fetchone()
            conn.execute("DELETE FROM quarantine_items WHERE id = ?", (item_id,))
            return dict(row)["quarantined_name"] if row else None

    def get_setting(self, key):
        with self._conn() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else None

    def set_setting(self, key, value):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )

    def add_whitelist(self, pattern, pattern_type="path"):
        with self._conn() as conn:
            try:
                conn.execute(
                    "INSERT INTO whitelist_items (pattern, pattern_type) VALUES (?, ?)",
                    (pattern, pattern_type),
                )
            except sqlite3.IntegrityError:
                pass

    def remove_whitelist(self, pattern):
        with self._conn() as conn:
            conn.execute(
                "DELETE FROM whitelist_items WHERE pattern = ?", (pattern,)
            )

    def get_whitelist(self):
        with self._conn() as conn:
            return [
                dict(r) for r in conn.execute(
                    "SELECT * FROM whitelist_items ORDER BY added_at DESC"
                ).fetchall()
            ]

    def is_whitelisted(self, path):
        path_str = str(Path(path).resolve())
        with self._conn() as conn:
            for row in conn.execute(
                "SELECT pattern, pattern_type FROM whitelist_items"
            ).fetchall():
                if row["pattern_type"] == "path" and path_str.startswith(row["pattern"]):
                    return True
                if row["pattern_type"] == "extension" and path_str.endswith(row["pattern"]):
                    return True
                if row["pattern_type"] == "hash":
                    import hashlib
                    try:
                        md5 = hashlib.md5()
                        with open(path_str, "rb") as f:
                            for chunk in iter(lambda: f.read(65536), b""):
                                md5.update(chunk)
                        if md5.hexdigest() == row["pattern"]:
                            return True
                    except (OSError, FileNotFoundError):
                        pass
        return False

    def get_scan_profiles(self):
        with self._conn() as conn:
            return [
                dict(r) for r in conn.execute(
                    "SELECT * FROM scan_profiles ORDER BY name"
                ).fetchall()
            ]

    def save_scan_profile(self, name, paths):
        import json
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO scan_profiles (name, paths) VALUES (?, ?)",
                (name, json.dumps(paths)),
            )

    def delete_scan_profile(self, name):
        with self._conn() as conn:
            conn.execute("DELETE FROM scan_profiles WHERE name = ?", (name,))

    def export_profiles_json(self):
        import json
        profiles = self.get_scan_profiles()
        data = []
        for p in profiles:
            data.append({"name": p["name"], "paths": json.loads(p["paths"])})
        return json.dumps(data, indent=2, ensure_ascii=False)

    def import_profiles_json(self, raw):
        import json
        data = json.loads(raw)
        if not isinstance(data, list):
            raise ValueError("Expected a list of profiles")
        count = 0
        for entry in data:
            name = entry.get("name")
            paths = entry.get("paths")
            if not name or not isinstance(paths, list):
                continue
            self.save_scan_profile(name, paths)
            count += 1
        return count

    def get_stats(self):
        with self._conn() as conn:
            today = conn.execute(
                "SELECT COUNT(*) as total, COALESCE(SUM(infected_files), 0) as infected "
                "FROM scan_history WHERE date(started_at) = date('now')"
            ).fetchone()
            month = conn.execute(
                "SELECT COUNT(*) as total, COALESCE(SUM(infected_files), 0) as infected "
                "FROM scan_history "
                "WHERE strftime('%Y-%m', started_at) = strftime('%Y-%m', 'now')"
            ).fetchone()
            year = conn.execute(
                "SELECT COUNT(*) as total, COALESCE(SUM(infected_files), 0) as infected "
                "FROM scan_history "
                "WHERE strftime('%Y', started_at) = strftime('%Y', 'now')"
            ).fetchone()
            return {
                "today": {"total": today["total"], "infected": today["infected"]},
                "monthly": {"total": month["total"], "infected": month["infected"]},
                "yearly": {"total": year["total"], "infected": year["infected"]},
            }

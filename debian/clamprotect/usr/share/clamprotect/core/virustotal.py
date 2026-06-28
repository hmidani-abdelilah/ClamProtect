import hashlib
import urllib.request
import urllib.error
import json

from core.logger import get_logger

log = get_logger()

VT_API_URL = "https://www.virustotal.com/api/v3/files/{hash}"


class VirusTotalChecker:
    def __init__(self, api_key=None):
        self.api_key = api_key

    def is_available(self):
        return bool(self.api_key)

    def check_hash(self, file_hash):
        if not self.api_key:
            return {"status": "error", "message": "No API key configured"}
        url = VT_API_URL.format(hash=file_hash.strip())
        req = urllib.request.Request(url)
        req.add_header("x-apikey", self.api_key)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
                attrs = data.get("data", {}).get("attributes", {})
                stats = attrs.get("last_analysis_stats", {})
                malicious = stats.get("malicious", 0)
                suspicious = stats.get("suspicious", 0)
                undetected = stats.get("undetected", 0)
                total = malicious + suspicious + undetected
                if malicious > 0:
                    status = "malicious"
                elif suspicious > 0:
                    status = "suspicious"
                else:
                    status = "clean"
                return {
                    "status": status,
                    "malicious": malicious,
                    "suspicious": suspicious,
                    "total": total,
                    "message": f"{malicious}/{total} engines detected",
                }
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {"status": "unknown", "message": "Hash not found in VirusTotal"}
            return {"status": "error", "message": f"HTTP {e.code}"}
        except urllib.error.URLError as e:
            return {"status": "error", "message": f"Connection error: {e.reason}"}
        except Exception as e:
            log.error("VirusTotal check error: %s", e)
            return {"status": "error", "message": str(e)}

    def check_file(self, file_path):
        try:
            h = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            return self.check_hash(h.hexdigest())
        except (OSError, FileNotFoundError) as e:
            return {"status": "error", "message": str(e)}

"""Nautilus extension — Scan with ClamProtect context menu."""
import subprocess, os
from gi.repository import Nautilus, GObject, GLib

_SCRIPT = os.path.join(os.path.dirname(__file__), "clamprotect-scan")

class ClamProtectExtension(GObject.GObject, Nautilus.MenuProvider):
    def __init__(self):
        super().__init__()

    def _scan(self, menu, files):
        for f in files:
            subprocess.Popen(["clamprotect-scan", f.get_location().get_path()],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def get_file_items(self, files):
        if not files:
            return
        item = Nautilus.MenuItem(
            name="ClamProtectExtension::Scan",
            label="Scan with ClamProtect",
            tip="Scan selected file(s) with ClamProtect",
        )
        item.connect("activate", self._scan, files)
        return [item]

    def get_background_items(self, folder):
        item = Nautilus.MenuItem(
            name="ClamProtectExtension::ScanDir",
            label="Scan Folder with ClamProtect",
            tip="Scan this folder with ClamProtect",
        )
        item.connect("activate", self._scan, [folder])
        return [item]

#! /usr/bin/python3
"""ClamProtect — Modern ClamAV GUI

Usage:
    clamprotect              Launch GUI
    clamprotect --scan PATH  CLI scan mode (for scheduled tasks)
    clamprotect --silent     Suppress output in CLI mode
    clamprotect <subcommand> CLI operations (scan, status, history, quarantine, profile, settings, virustotal)
"""

import os
import sys
import json
import argparse
from pathlib import Path

# Suppress Qt DBus warnings when no session bus (set before PyQt6 import)
if not os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
    os.environ["QT_LOGGING_RULES"] = "qt.qpa.theme.dbus=false"

from PyQt6.QtWidgets import QApplication

from core.scanner import Scanner
from core.database import Database
from core.quarantine import Quarantine
from core.logger import Logger, get_logger


def _configure_platform():
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "")
    log = get_logger()
    if not desktop and os.geteuid() == 0:
        os.environ.setdefault("QT_QPA_PLATFORMTHEME", "generic")
        os.environ.setdefault("QT_WAYLAND_DECORATION", "adwaita")
        log.info("Running as root — Qt: theme=generic decoration=adwaita")
    elif not desktop:
        return
    elif "GNOME" in desktop.upper():
        os.environ.setdefault("QT_QPA_PLATFORMTHEME", "generic")
        os.environ.setdefault("QT_WAYLAND_DECORATION", "adwaita")
        os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
        log.info("GNOME detected — Qt: theme=generic decoration=adwaita platform=xcb")
    else:
        log.info("Desktop: %s — Qt auto-detection", desktop)
        return

    if not os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
        os.environ["QT_LOGGING_RULES"] = "qt.qpa.theme.dbus=false"


def cli_scan(paths, scan_type="manual", silent=False):
    logger = Logger()
    log = get_logger()
    db = Database()
    scanner = Scanner()
    quarantine = Quarantine(db)

    all_results = []
    for p in paths:
        log.info("CLI scan: %s", p)
        try:
            results = scanner.scan(p)
            db.save_scan(p, scan_type, results)
            all_results.extend(results)
        except Exception as e:
            log.error("CLI scan error for %s: %s", p, e)
            print(f"[ERROR] {p}: {e}", file=sys.stderr)

    infected = [r for r in all_results if r["status"] == "infected"]
    for r in infected:
        try:
            quarantine.add(r["path"], r["virus"])
            if not silent:
                print(f"[QUARANTINED] {r['path']} ({r['virus']})")
        except Exception as e:
            if not silent:
                print(f"[ERROR] Quarantine failed for {r['path']}: {e}")

    if not silent:
        clean = [r for r in all_results if r["status"] == "clean"]
        print(json.dumps({
            "total": len(all_results),
            "infected": len(infected),
            "clean": len(clean),
            "status": "infected" if infected else "clean",
        }, indent=2))
    logger.stop()
    sys.exit(1 if infected else 0)


def _cmd_scan(args):
    paths = args.path or ["/"]
    cli_scan(paths, scan_type=args.scan_type, silent=args.silent)


def _cmd_status(args):
    db = Database()
    scanner = Scanner()
    from core.definitions import DefinitionsManager
    dm = DefinitionsManager()

    status = {
        "clamd": scanner.ping(),
        "version": scanner.version(),
        "definitions": dm.get_status(),
    }
    if args.json:
        print(json.dumps(status, indent=2))
    else:
        print(f"Clamd: {'✓ running' if status['clamd'] else '✗ not responding'}")
        print(f"Version: {status['version']}")
        defs = status["definitions"]
        print(f"Definitions: {defs.get('status', 'unknown')}")
    sys.exit(0)


def _cmd_history(args):
    db = Database()
    history = db.get_history(limit=args.limit)
    if args.json:
        print(json.dumps(history, indent=2, default=str))
    else:
        print(f"{'ID':>4} {'Date':<22} {'Path':<30} {'Type':<10} {'Infected':>8}")
        print("-" * 80)
        for h in history:
            print(f"{h['id']:>4} {str(h['started_at'])[:22]:<22} {h['scanned_path'][:30]:<30} {h['scan_type'][:10]:<10} {h['infected_files']:>8}")
    sys.exit(0)


def _cmd_quarantine(args):
    db = Database()
    q = Quarantine(db)
    if args.action == "list":
        items = q.list()
        if args.json:
            print(json.dumps(items, indent=2, default=str))
        else:
            for it in items:
                print(f"{it['id']}: {it['original_path']} ({it['virus_name']})")
    elif args.action == "restore":
        q.restore(args.id)
        print(f"Restored item {args.id}")
    elif args.action == "delete":
        q.delete(args.id)
        print(f"Deleted item {args.id}")
    sys.exit(0)


def _cmd_profile(args):
    db = Database()
    if args.action == "list":
        profiles = db.get_scan_profiles()
        if args.json:
            import json as j
            data = []
            for p in profiles:
                data.append({"name": p["name"], "paths": j.loads(p["paths"])})
            print(j.dumps(data, indent=2))
        else:
            for p in profiles:
                print(f"{p['name']}: {p['paths']}")
    elif args.action == "save":
        db.save_scan_profile(args.name, args.paths)
        print(f"Saved profile '{args.name}'")
    elif args.action == "delete":
        db.delete_scan_profile(args.name)
        print(f"Deleted profile '{args.name}'")
    elif args.action == "export":
        raw = db.export_profiles_json()
        if args.file:
            Path(args.file).write_text(raw)
            print(f"Exported to {args.file}")
        else:
            print(raw)
    elif args.action == "import":
        raw = Path(args.file).read_text()
        count = db.import_profiles_json(raw)
        print(f"Imported {count} profiles")
    sys.exit(0)


def _cmd_settings(args):
    db = Database()
    if args.action == "get":
        val = db.get_setting(args.key)
        print(val if val is not None else "(not set)")
    elif args.action == "set":
        db.set_setting(args.key, args.value)
        print(f"Set {args.key} = {args.value}")
    sys.exit(0)


def _cmd_virustotal(args):
    from core.virustotal import VirusTotalChecker
    db = Database()
    key = db.get_setting("vt_api_key")
    if not key:
        print("No VirusTotal API key configured", file=sys.stderr)
        sys.exit(1)
    checker = VirusTotalChecker(key)
    result = checker.check_file(args.file)
    print(json.dumps(result, indent=2))
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="ClamProtect — Modern ClamAV GUI")
    parser.add_argument("--silent", action="store_true", help="Suppress output")
    # Legacy --scan support
    parser.add_argument("--scan", metavar="PATH", help=argparse.SUPPRESS)

    sub = parser.add_subparsers(dest="command")

    p_scan = sub.add_parser("scan", help="Run antivirus scan")
    p_scan.add_argument("path", nargs="*", help="Paths to scan")
    p_scan.add_argument("--quick", action="store_true", help="Quick scan common locations")
    p_scan.add_argument("--profile", help="Scan using a saved profile")
    p_scan.add_argument("--json", action="store_true", help=argparse.SUPPRESS)

    p_status = sub.add_parser("status", help="Show system status")
    p_status.add_argument("--json", action="store_true", help="JSON output")

    p_history = sub.add_parser("history", help="Show scan history")
    p_history.add_argument("--limit", type=int, default=100, help="Max entries")
    p_history.add_argument("--json", action="store_true", help="JSON output")

    p_quar = sub.add_parser("quarantine", help="Manage quarantine")
    p_quar.add_argument("action", choices=["list", "restore", "delete"])
    p_quar.add_argument("id", nargs="?", type=int, help="Item ID (for restore/delete)")
    p_quar.add_argument("--json", action="store_true", help="JSON output")

    p_prof = sub.add_parser("profile", help="Manage scan profiles")
    p_prof.add_argument("action", choices=["list", "save", "delete", "export", "import"])
    p_prof.add_argument("name", nargs="?", help="Profile name")
    p_prof.add_argument("paths", nargs="*", help="Paths for save action")
    p_prof.add_argument("--file", help="File path for export/import")
    p_prof.add_argument("--json", action="store_true", help="JSON output")

    p_set = sub.add_parser("settings", help="Manage settings")
    p_set.add_argument("action", choices=["get", "set"])
    p_set.add_argument("key", help="Setting key")
    p_set.add_argument("value", nargs="?", help="Setting value")

    p_vt = sub.add_parser("virustotal", help="Check file hash against VirusTotal")
    p_vt.add_argument("file", help="Path to file")

    args = parser.parse_args()

    # Legacy --scan support
    if args.scan:
        cli_scan([args.scan], silent=args.silent)

    if args.command == "scan":
        if args.quick:
            from core.scanner import QUICK_SCAN_PATHS
            cli_scan(QUICK_SCAN_PATHS, scan_type="quick", silent=args.silent)
        elif args.profile:
            import json as j
            db = Database()
            profiles = db.get_scan_profiles()
            for p in profiles:
                if p["name"] == args.profile:
                    paths = j.loads(p["paths"])
                    cli_scan(paths, scan_type="profile", silent=args.silent)
                    return
            print(f"Profile '{args.profile}' not found", file=sys.stderr)
            sys.exit(1)
        else:
            cli_scan(args.path, scan_type="manual", silent=args.silent)
    elif args.command:
        # Route subcommands without --silent propagation (handled inside)
        args.silent = args.silent if hasattr(args, 'silent') else False
        cmd_map = {
            "status": _cmd_status,
            "history": _cmd_history,
            "quarantine": _cmd_quarantine,
            "profile": _cmd_profile,
            "settings": _cmd_settings,
            "virustotal": _cmd_virustotal,
        }
        cmd_map[args.command](args)
    else:
        _configure_platform()
        app = QApplication(sys.argv)
        app.setStyle("Fusion")
        app.setApplicationName("ClamProtect")
        app.setOrganizationName("ClamProtect")

        from ui.main_window import MainWindow
        window = MainWindow()
        window.show()

        sys.exit(app.exec())


if __name__ == "__main__":
    main()

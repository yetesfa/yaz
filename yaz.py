#!/usr/bin/env python3
"""
Yaz (ያዝ) — Wayland-native screenshot + annotation tool for Linux.

"Yaz" is Amharic (ያዝ) for "grab it / catch it / hold it" — exactly what a
screenshot tool does.

The app opens with a welcome screen and a menu bar (File / Edit / View / Tools
/ Preferences / Help). Capture is triggered from inside the app, so the Wayland
compositor recognises us as a focused application. Multi-monitor selection is
built in. Preferences persist via QSettings.

Capture backends are tried in order:
    1. gnome-screenshot  (most reliable on Ubuntu GNOME 46 — Wayland + X11)
    2. grim              (wlroots-based Wayland: Sway, Hyprland)
    3. xdg-desktop-portal  (last resort; limited on GNOME 46 unsandboxed)

CLI:
    yaz                 open the app (welcome screen)
    yaz --capture       open the app and immediately capture a region
    yaz --full          open the app and capture the full screen
    yaz --open FILE     open an existing image for annotation
    yaz --delay N       wait N seconds before capturing

Source code is split across sibling modules:
    yaz_capture.py      capture backends (no Qt)
    yaz_settings.py     DEFAULTS + screen helpers (no Qt)
    yaz_picker.py       fullscreen region overlay
    yaz_canvas.py       annotation canvas + undo commands
    yaz_welcome.py      welcome / launcher screen
    yaz_preferences.py  preferences dialog
    yaz_countdown.py    delayed-capture countdown overlay
    yaz_mw_*.py         MainWindow mixins (chrome / drawing / fileio /
                        capture / shortcuts / dialogs)
    yaz_mainwindow.py   QMainWindow assembling the mixins
    yaz_app.py          QApplication orchestrator
    yaz.py              this file — CLI entry only

Source:     https://github.com/yetesfa/yaz
Issues:     https://github.com/yetesfa/yaz/issues
Developer:  Yetesfa Alemayehu — https://www.linkedin.com/in/yetesfa-alemayehu
License:    MIT — Made in Addis Ababa.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _show_error_dialog(title: str, message: str) -> None:
    """Best-effort GUI error so users who launched from the apps grid see why."""
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox
        QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, f"Yaz — {title}", message)
    except Exception:  # noqa: BLE001
        for cmd in (
            ["zenity", "--error", "--title", f"Yaz — {title}", "--text", message],
            ["kdialog", "--error", message, "--title", f"Yaz — {title}"],
            ["notify-send", "-u", "critical", f"Yaz — {title}", message],
        ):
            try:
                subprocess.run(cmd, check=False, timeout=5)
                return
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="yaz",
        description="Yaz — Wayland screenshot + annotation tool. "
                    "(ያዝ, Amharic: 'grab it'.)",
    )
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--capture", action="store_true",
                   help="Open the app and immediately capture a region")
    g.add_argument("--full", action="store_true",
                   help="Open the app and capture full screen")
    g.add_argument("--open", metavar="FILE",
                   help="Open an existing image for annotation")
    ap.add_argument("--delay", type=int, default=0,
                    help="Seconds to wait before --capture / --full (for hover screenshots)")
    args = ap.parse_args()

    initial = None
    if args.open:
        p = Path(args.open).expanduser()
        if not p.exists():
            print(f"yaz: file not found: {p}", file=sys.stderr)
            return 2
        initial = p

    auto = None
    if args.capture:
        auto = "region"
    elif args.full:
        auto = "full"

    # Defer Qt imports until args are parsed — keeps --help working when
    # PyQt6 isn't installed (matters for the .deb postinst + CI smoke).
    from yaz_app import run_app
    return run_app(initial_image=initial, autostart_capture=auto,
                   autostart_delay=args.delay)


if __name__ == "__main__":
    sys.exit(main())

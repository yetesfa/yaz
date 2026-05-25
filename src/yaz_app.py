"""Application orchestrator: wire QApplication, show MainWindow, autostart.

This is the first module to import Qt-touching siblings; everything
above it (argparse, --help, --version, error fallback) must stay Qt-free
so the CLI metadata commands work without PyQt6 installed.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import QSettings, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication, QMessageBox

from yaz_mainwindow import MainWindow
from yaz_settings import _default_save_dir


def run_app(initial_image: Path | None, autostart_capture: str | None,
            autostart_delay: int = 0) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Yaz")
    app.setApplicationDisplayName("Yaz")
    app.setOrganizationName("Yaz")
    app.setDesktopFileName("yaz")

    # Make sure default save_dir is filled in.
    s = QSettings("Yaz", "Yaz")
    if not s.value("save_dir"):
        s.setValue("save_dir", _default_save_dir())
        s.sync()

    win = MainWindow()
    win.show()

    if initial_image is not None:
        pix = QPixmap(str(initial_image))
        if not pix.isNull():
            win.load_pixmap(pix, source_path=initial_image)
        else:
            QMessageBox.warning(win, "Yaz", f"Could not load {initial_image}")

    if autostart_capture == "region":
        QTimer.singleShot(
            150, lambda: win.capture_region_delayed(autostart_delay)
            if autostart_delay > 0 else win.capture_region())
    elif autostart_capture == "full":
        QTimer.singleShot(
            150, lambda: win.capture_full_delayed(autostart_delay)
            if autostart_delay > 0 else win.capture_full_action())

    return app.exec()

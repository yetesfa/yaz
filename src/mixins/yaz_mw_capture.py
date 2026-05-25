"""MainWindow mixin: the capture flow.

``_do_capture`` is the single entry point — it minimises the window,
shows the countdown overlay if delayed, then routes to either the
OS-native region selector (preferred) or full-screen capture followed by
the in-app picker. The high-level ``capture_*`` methods called from menu
items / toolbar buttons just dispatch into ``_do_capture``.

Mixin only — combine with QMainWindow + the other mw mixins.
"""
from __future__ import annotations

import shutil
import subprocess
import time

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QGuiApplication, QPixmap
from PyQt6.QtWidgets import QApplication, QInputDialog, QMessageBox

from yaz_capture import (
    CaptureCancelled, capture_full_screen, capture_region_native,
)
from yaz_countdown import Countdown
from yaz_picker import pick_region_from
from yaz_settings import DEFAULTS


class CaptureFlowMixin:
    # ---- capture actions ----
    def _restore(self):
        """Bring the main window back without making it look like a relaunch."""
        self.showNormal()
        self.raise_()
        self.activateWindow()

    @staticmethod
    def _virtual_geometry():
        """Bounding rectangle of every screen, in logical coords.
        (Same value across QScreen instances — primary's virtualGeometry
        covers the whole layout.)"""
        return QGuiApplication.primaryScreen().virtualGeometry()

    def _crop_to_screen(self, pixmap, screen):
        """Crop the captured virtual-desktop pixmap to one specific screen.

        We can't trust QScreen.devicePixelRatio() alone — GNOME 46 uses
        fractional scaling and the resulting screenshot ends up at a
        scale that doesn't match any single monitor's DPR. The
        empirical scale (`image / virtual geometry`) works for every
        setup tested: single 1×, single HiDPI, mixed-DPR, fractional
        scaling, portrait rotation, and L-shaped layouts."""
        vg = self._virtual_geometry()
        if pixmap.width() <= 0 or vg.width() <= 0 or vg.height() <= 0:
            return pixmap
        sx = pixmap.width() / vg.width()
        sy = pixmap.height() / vg.height()
        # If sx and sy diverge wildly the pixmap doesn't actually cover
        # the virtual desktop — fall back to no crop rather than slicing
        # the wrong region.
        if abs(sx - sy) / max(sx, sy) > 0.05:
            self.statusBar().showMessage(
                "Screen layout doesn't match the captured image — "
                "returning the full screenshot.", 4000)
            return pixmap
        geom = screen.geometry()
        crop = QRect(
            round((geom.x() - vg.x()) * sx),
            round((geom.y() - vg.y()) * sy),
            round(geom.width() * sx),
            round(geom.height() * sy),
        )
        crop = crop.intersected(pixmap.rect())
        if crop.width() < 2 or crop.height() < 2:
            return pixmap
        return pixmap.copy(crop)

    def _do_capture(self, mode: str, screen=None, delay: int | None = None):
        """mode: 'region' | 'full' | 'screen'.
        delay: seconds before capture. None → use the configured default."""
        if delay is None:
            delay = int(self.qsettings.value(
                "capture_delay", DEFAULTS["capture_delay"]))
        delay = max(0, int(delay))
        self.statusBar().showMessage(
            f"Capturing in {delay}s…" if delay else "Capturing…")
        # Minimize (not hide) so the user sees the window in the taskbar
        # rather than thinking the app closed.
        self.showMinimized()
        QApplication.processEvents()

        if delay > 0:
            cd = Countdown(delay)
            cd.show()
            cd.raise_()
            QApplication.processEvents()
            start = time.monotonic()
            while True:
                elapsed = time.monotonic() - start
                remaining = int(delay - elapsed + 0.999)  # ceil
                if remaining <= 0:
                    break
                if remaining != cd.remaining:
                    cd.set_remaining(remaining)
                QApplication.processEvents()
                time.sleep(0.05)
            cd.hide()
            cd.deleteLater()
            QApplication.processEvents()
            # One more frame so the compositor has erased the countdown.
            time.sleep(0.2)
        else:
            # Brief pause so the minimize is actually painted before we
            # ask the screen for a screenshot.
            time.sleep(0.2)

        # Region mode: prefer the OS-native interactive area selector so
        # the user drags on the *live* screen before any capture is taken
        # (gnome-screenshot -a, or slurp+grim on wlroots). Fall back to
        # the full-capture-then-overlay path only if no native backend is
        # available or it fails for an unexpected reason.
        if mode == "region":
            try:
                region_path = capture_region_native()
            except CaptureCancelled:
                self._restore()
                return
            except Exception:  # noqa: BLE001
                import traceback; traceback.print_exc()
                region_path = None
            if region_path is not None:
                pixmap = QPixmap(str(region_path))
                if pixmap.isNull():
                    self._restore()
                    QMessageBox.warning(
                        self, "Yaz",
                        f"Captured image is empty: {region_path}")
                    return
                self.load_pixmap(pixmap, source_path=None)
                self._restore()
                return

        try:
            path = capture_full_screen()
        except CaptureCancelled:
            self._restore()
            return
        except Exception as ex:  # noqa: BLE001
            import traceback; traceback.print_exc()
            self._restore()
            self._capture_failed_dialog(ex)
            return

        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self._restore()
            QMessageBox.warning(self, "Yaz",
                                f"Captured image is empty: {path}")
            return

        if mode == "screen" and screen is not None:
            pixmap = self._crop_to_screen(pixmap, screen)

        if mode == "region" and self._bool_setting(
                "pick_region_after_capture",
                DEFAULTS["pick_region_after_capture"]):
            rect = pick_region_from(pixmap)
            if rect is None:
                self._restore()
                return
            pixmap = pixmap.copy(rect)

        self.load_pixmap(pixmap, source_path=None)
        self._restore()

    def _capture_failed_dialog(self, ex):
        """Detailed install help so the user can actually get unstuck."""
        mbox = QMessageBox(self)
        mbox.setIcon(QMessageBox.Icon.Critical)
        mbox.setWindowTitle("Yaz — Capture failed")
        mbox.setTextFormat(Qt.TextFormat.RichText)
        mbox.setText(
            "<p>Yaz couldn't capture the screen.</p>"
            "<p>On Ubuntu GNOME the most reliable backend is "
            "<b>gnome-screenshot</b>, but it isn't installed yet.</p>"
        )
        mbox.setInformativeText(
            "<p>Click <b>Install Now</b> to install it with a graphical "
            "password prompt.</p>"
            "<p>Or run this in a terminal:<br>"
            "<code>sudo apt install gnome-screenshot</code></p>"
            "<p>Still stuck? Open an issue at "
            "<a href='https://github.com/yetesfa/yaz/issues'>"
            "github.com/yetesfa/yaz/issues</a>.</p>"
        )
        mbox.setDetailedText(f"{type(ex).__name__}: {ex}")
        install = mbox.addButton("Install Now", QMessageBox.ButtonRole.AcceptRole)
        mbox.addButton(QMessageBox.StandardButton.Close)
        mbox.exec()
        if mbox.clickedButton() is install:
            self._install_gnome_screenshot()

    def _install_gnome_screenshot(self):
        """Use pkexec for graphical sudo. Falls back to instructions."""
        if not shutil.which("pkexec"):
            QMessageBox.information(
                self, "Yaz",
                "Please open a terminal and run:\n\n"
                "    sudo apt install gnome-screenshot"
            )
            return
        try:
            self.statusBar().showMessage("Installing gnome-screenshot…")
            QApplication.processEvents()
            res = subprocess.run(
                ["pkexec", "apt-get", "install", "-y", "gnome-screenshot"],
                capture_output=True, text=True, timeout=120,
            )
            if res.returncode == 0 and shutil.which("gnome-screenshot"):
                QMessageBox.information(
                    self, "Yaz",
                    "gnome-screenshot installed. Try Capture Region again."
                )
                self.statusBar().showMessage("Ready.")
            else:
                QMessageBox.warning(
                    self, "Yaz",
                    f"Install failed (rc={res.returncode}).\n\n"
                    f"{res.stderr.strip() or res.stdout.strip()}"
                )
        except Exception as ex:  # noqa: BLE001
            QMessageBox.warning(self, "Yaz", f"Install failed: {ex}")

    def capture_region(self):
        self._do_capture("region")

    def capture_full_action(self):
        self._do_capture("full")

    def capture_screen(self, screen):
        self._do_capture("screen", screen=screen)

    def capture_region_delayed(self, seconds: int):
        self._do_capture("region", delay=seconds)

    def capture_full_delayed(self, seconds: int):
        self._do_capture("full", delay=seconds)

    def capture_region_custom_delay(self):
        seconds, ok = QInputDialog.getInt(
            self, "Yaz — Delayed capture",
            "Seconds to wait before capture:", value=5, min=1, max=60,
        )
        if ok:
            self._do_capture("region", delay=seconds)

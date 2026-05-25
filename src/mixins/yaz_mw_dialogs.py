"""MainWindow mixin: About + keyboard-shortcuts info dialogs.

Pure presentation — no state changes. Both dialogs are RichText
QMessageBoxes so links stay clickable.

Mixin only — combine with QMainWindow + the other mw mixins.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QMessageBox


class DialogsMixin:
    def _show_about(self):
        mbox = QMessageBox(self)
        mbox.setWindowTitle("About Yaz")
        mbox.setIcon(QMessageBox.Icon.Information)
        mbox.setTextFormat(Qt.TextFormat.RichText)
        mbox.setText(
            "<h2 style='margin:0'>Yaz &middot; ያዝ</h2>"
            "<p>Wayland-native screenshot and annotation tool.</p>"
            "<p><i>&ldquo;Yaz&rdquo; is Amharic (ያዝ) for &ldquo;grab it&rdquo;.</i></p>"
            "<p><b>Developed by Yetesfa Alemayehu</b><br>"
            "<a href='https://www.linkedin.com/in/yetesfa-alemayehu' "
            "style='color:#3a86ff;'>linkedin.com/in/yetesfa-alemayehu</a></p>"
            "<p><a href='https://github.com/yetesfa/yaz' "
            "style='color:#3a86ff;'>github.com/yetesfa/yaz</a>"
            " · <a href='https://github.com/yetesfa/yaz/issues' "
            "style='color:#3a86ff;'>Report a bug</a></p>"
            "<p>Made in Addis Ababa &middot; MIT license</p>"
        )
        for lbl in mbox.findChildren(QLabel):
            lbl.setOpenExternalLinks(True)
            lbl.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextBrowserInteraction)
        mbox.exec()

    def _show_shortcuts(self):
        mbox = QMessageBox(self)
        mbox.setWindowTitle("Yaz — Keyboard Shortcuts")
        mbox.setIcon(QMessageBox.Icon.Information)
        mbox.setTextFormat(Qt.TextFormat.RichText)
        mbox.setText(
            "<p><i>These fire only when Yaz is the focused app. "
            "For a system-wide trigger, use "
            "<b>File → Set Up Global Keyboard Shortcut…</b></i></p>"
            "<table cellpadding=6>"
            "<tr><td><b>Ctrl+R</b></td><td>Capture region</td></tr>"
            "<tr><td><b>Ctrl+Alt+R</b></td><td>Capture full screen</td></tr>"
            "<tr><td><b>Ctrl+Shift+3 / 5 / 0</b></td>"
            "<td>Capture region after 3 / 5 / 10 seconds</td></tr>"
            "<tr><td><b>Ctrl+O</b></td><td>Open image</td></tr>"
            "<tr><td><b>Ctrl+S / Ctrl+Shift+S</b></td><td>Save / Save As</td></tr>"
            "<tr><td><b>Ctrl+Shift+C</b></td><td>Copy to clipboard</td></tr>"
            "<tr><td><b>Ctrl+W</b></td><td>Close image (back to welcome)</td></tr>"
            "<tr><td><b>Ctrl+,</b></td><td>Preferences</td></tr>"
            "<tr><td><b>V / C / R / E / A / L / P / H / T / B</b></td>"
            "<td>Select / Crop / Rect / Ellipse / Arrow / Line / Pen / "
            "Highlight / Text / Blur</td></tr>"
            "<tr><td><b>Shift+F</b></td><td>Toggle fill</td></tr>"
            "<tr><td><b>Ctrl+Z / Ctrl+Y</b></td><td>Undo / Redo</td></tr>"
            "<tr><td><b>Del</b></td><td>Delete selected</td></tr>"
            "<tr><td><b>Ctrl++ / Ctrl+- / Ctrl+0 / Ctrl+F</b></td>"
            "<td>Zoom in / out / reset / fit</td></tr>"
            "</table>"
        )
        mbox.exec()

"""MainWindow mixin: open / save / render / clipboard.

Handles the lifecycle of an image: load a pixmap into the scene, render
the scene back out for save / clipboard, and the file-format / quality
plumbing read out of QSettings.

Mixin only — combine with QMainWindow + the other mw mixins.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import (
    QGuiApplication, QImage, QPainter, QPixmap,
)
from PyQt6.QtWidgets import (
    QFileDialog, QGraphicsPixmapItem, QMessageBox,
)

from yaz_settings import DEFAULTS, _default_save_dir


class FileIoMixin:
    # ---- image loading / saving ----
    def load_pixmap(self, pixmap, source_path: Path | None):
        self.scene.clear()
        self.bg_item = QGraphicsPixmapItem(pixmap)
        self.bg_item.setZValue(-1000)
        self.scene.addItem(self.bg_item)
        self.scene.setSceneRect(self.bg_item.boundingRect())
        self.canvas.setSceneRect(self.scene.sceneRect())
        self.canvas.resetTransform()
        self.current_path = source_path
        self.undo_stack.clear()
        self.stack.setCurrentWidget(self.canvas)
        self.canvas.set_tool("select")
        view_sz = self.canvas.viewport().size()
        if pixmap.width() > view_sz.width() or pixmap.height() > view_sz.height():
            self.canvas.fitInView(self.bg_item,
                                  Qt.AspectRatioMode.KeepAspectRatio)
        self.statusBar().showMessage(
            f"Loaded {pixmap.width()}×{pixmap.height()}"
            + (f" from {source_path}" if source_path else "")
        )
        self.setWindowTitle(
            f"Yaz — {source_path.name}" if source_path else "Yaz")

    def close_image(self):
        self.scene.clear()
        self.bg_item = None
        self.current_path = None
        self.stack.setCurrentWidget(self.welcome)
        self.setWindowTitle("Yaz")
        self.statusBar().showMessage("Ready.")

    def open_image(self):
        start = self.qsettings.value("save_dir", _default_save_dir())
        path, _ = QFileDialog.getOpenFileName(
            self, "Open image", start,
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;All files (*)",
        )
        if not path:
            return
        pix = QPixmap(path)
        if pix.isNull():
            QMessageBox.warning(self, "Yaz", f"Could not load {path}")
            return
        self.load_pixmap(pix, Path(path))

    # ---- rendering / output ----
    def render_image(self):
        rect = self.scene.sceneRect()
        img = QImage(rect.size().toSize(), QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        for it in self.scene.selectedItems():
            it.setSelected(False)
        self.scene.render(p, QRectF(img.rect()), rect)
        p.end()
        return img

    def _default_save_path(self) -> Path:
        import datetime as dt
        base = self.qsettings.value("save_dir", _default_save_dir())
        tmpl = self.qsettings.value("filename_template",
                                    DEFAULTS["filename_template"])
        name = dt.datetime.now().strftime(tmpl)
        ext = self.qsettings.value("format", DEFAULTS["format"]).lower()
        return Path(base) / f"{name}.{ext}"

    def save(self):
        if self.bg_item is None:
            return
        target = self._default_save_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        self._write_to(target)

    def save_as(self):
        if self.bg_item is None:
            return
        start = str(self._default_save_path())
        path, _ = QFileDialog.getSaveFileName(
            self, "Save image", start,
            "PNG (*.png);;JPEG (*.jpg *.jpeg);;All files (*)",
        )
        if path:
            self._write_to(Path(path))

    def _write_to(self, path: Path):
        img = self.render_image()
        quality = int(self.qsettings.value(
            "jpg_quality", DEFAULTS["jpg_quality"]))
        ok = img.save(str(path), quality=quality if path.suffix.lower()
                      in (".jpg", ".jpeg") else -1)
        if not ok:
            QMessageBox.warning(self, "Yaz", f"Could not save to {path}")
            return
        self.current_path = path
        self.setWindowTitle(f"Yaz — {path.name}")
        self.statusBar().showMessage(f"Saved {path}", 5000)
        if self._bool_setting("copy_after_save", DEFAULTS["copy_after_save"]):
            self.copy_to_clipboard(silent=True)

    def copy_to_clipboard(self, silent=False):
        if self.bg_item is None:
            return
        img = self.render_image()
        QGuiApplication.clipboard().setImage(img)
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
                img.save(tf.name, "PNG")
                with open(tf.name, "rb") as src:
                    subprocess.run(
                        ["wl-copy", "--type", "image/png"],
                        stdin=src, check=False, timeout=5,
                    )
            os.unlink(tf.name)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        if not silent:
            self.statusBar().showMessage("Copied to clipboard.", 3000)

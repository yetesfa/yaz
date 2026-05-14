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

Developed by Yetesfa Alemayehu — https://www.linkedin.com/in/yetesfa-alemayehu
Made in Addis Ababa. MIT license.
"""
from __future__ import annotations

import argparse
import math
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlparse


# ============================================================================
# Capture backends
# ============================================================================

class CaptureCancelled(Exception):
    """User dismissed the capture UI — not an error."""


class PortalCancelled(CaptureCancelled):
    """Portal-specific cancel (response code 1)."""


def capture_full_screen() -> Path:
    """Capture full virtual screen via the first working backend."""
    last_error: Exception | None = None

    if shutil.which("gnome-screenshot"):
        try:
            return _capture_with_gnome_screenshot()
        except Exception as ex:  # noqa: BLE001
            last_error = ex

    if shutil.which("grim"):
        try:
            return _capture_with_grim()
        except Exception as ex:  # noqa: BLE001
            last_error = ex

    try:
        return capture_via_portal(interactive=False)
    except Exception as ex:  # noqa: BLE001
        last_error = ex

    raise RuntimeError(
        "No working screenshot backend.\n\n"
        "Install gnome-screenshot for reliable capture:\n"
        "    sudo apt install gnome-screenshot\n\n"
        f"(Last backend error: {last_error})"
    )


def _capture_with_gnome_screenshot() -> Path:
    fd, name = tempfile.mkstemp(prefix="yaz-", suffix=".png")
    os.close(fd)
    out = Path(name)
    res = subprocess.run(
        ["gnome-screenshot", "-f", str(out)],
        capture_output=True, timeout=30, text=True,
    )
    if res.returncode != 0 or not out.exists() or out.stat().st_size == 0:
        out.unlink(missing_ok=True)
        raise RuntimeError(
            f"gnome-screenshot failed (rc={res.returncode}): {res.stderr.strip()}"
        )
    return out


def _capture_with_grim() -> Path:
    fd, name = tempfile.mkstemp(prefix="yaz-", suffix=".png")
    os.close(fd)
    out = Path(name)
    res = subprocess.run(
        ["grim", str(out)],
        capture_output=True, timeout=30, text=True,
    )
    if res.returncode != 0 or not out.exists() or out.stat().st_size == 0:
        out.unlink(missing_ok=True)
        raise RuntimeError(f"grim failed (rc={res.returncode}): {res.stderr.strip()}")
    return out


def capture_via_portal(interactive: bool = True) -> Path:
    """Call org.freedesktop.portal.Screenshot via Gio/D-Bus."""
    import gi
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib

    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    token = "yaz_" + secrets.token_hex(8)
    sender = bus.get_unique_name()[1:].replace(".", "_")
    request_path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"

    state: dict = {}
    loop = GLib.MainLoop()

    def on_response(_conn, _sender, _obj, _iface, _signal, params):
        code, results = params.unpack()
        state["code"] = code
        state["results"] = results
        loop.quit()

    sub_id = bus.signal_subscribe(
        "org.freedesktop.portal.Desktop",
        "org.freedesktop.portal.Request",
        "Response",
        request_path,
        None,
        Gio.DBusSignalFlags.NONE,
        on_response,
    )

    options = {
        "handle_token": GLib.Variant("s", token),
        "interactive": GLib.Variant("b", interactive),
        "modal": GLib.Variant("b", True),
    }

    bus.call_sync(
        "org.freedesktop.portal.Desktop",
        "/org/freedesktop/portal/desktop",
        "org.freedesktop.portal.Screenshot",
        "Screenshot",
        GLib.Variant("(sa{sv})", ("", options)),
        GLib.VariantType("(o)"),
        Gio.DBusCallFlags.NONE,
        -1,
        None,
    )

    GLib.timeout_add_seconds(90, lambda: (state.setdefault("code", 2), loop.quit())[1])
    loop.run()
    bus.signal_unsubscribe(sub_id)

    code = state.get("code")
    if code == 1:
        raise PortalCancelled()
    if code != 0:
        raise RuntimeError(
            f"Portal returned code {code}. Install gnome-screenshot for a "
            "more reliable backend on GNOME 46:\n    sudo apt install gnome-screenshot"
        )
    uri = (state.get("results") or {}).get("uri")
    if not uri:
        raise RuntimeError("Portal returned no image URI.")
    return Path(unquote(urlparse(uri).path))


# ============================================================================
# Region picker (flameshot-style overlay)
# ============================================================================

def pick_region_from(pixmap, qt) -> "object | None":
    """Show a fullscreen overlay; return a QRect or None if cancelled."""
    Qt = qt["Qt"]; QRect = qt["QRect"]; QPoint = qt["QPoint"]
    QColor = qt["QColor"]; QFont = qt["QFont"]; QPainter = qt["QPainter"]
    QPen = qt["QPen"]; QBrush = qt["QBrush"]
    QApplication = qt["QApplication"]; QWidget = qt["QWidget"]
    QGuiApplication = qt["QGuiApplication"]

    class Picker(QWidget):
        def __init__(self, pix):
            super().__init__(
                None,
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.BypassWindowManagerHint,
            )
            self.pixmap = pix
            self.setCursor(Qt.CursorShape.CrossCursor)
            self.start: QPoint | None = None
            self.end: QPoint | None = None
            self.committed: QRect | None = None
            geom = QGuiApplication.primaryScreen().virtualGeometry()
            self.setGeometry(geom)
            self.showFullScreen()
            self.activateWindow()
            self.raise_()

        def paintEvent(self, _ev):
            p = QPainter(self)
            p.drawPixmap(self.rect(), self.pixmap, self.pixmap.rect())
            # Darker overlay (≈70% black) so the un-dimmed selection clearly
            # pops out.
            p.fillRect(self.rect(), QColor(0, 0, 0, 180))
            if self.start and self.end:
                r = QRect(self.start, self.end).normalized()
                src = QRect(
                    int(r.x() * self.pixmap.width() / self.width()),
                    int(r.y() * self.pixmap.height() / self.height()),
                    int(r.width() * self.pixmap.width() / self.width()),
                    int(r.height() * self.pixmap.height() / self.height()),
                )
                p.drawPixmap(r, self.pixmap, src)
                pen = QPen(QColor("#3a86ff"), 2)
                p.setPen(pen)
                p.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                p.drawRect(r)
                label = f"{r.width()} × {r.height()}"
                p.setPen(QColor("white"))
                font = QFont(); font.setPointSize(11); font.setBold(True)
                p.setFont(font)
                badge_y = max(0, r.y() - 24)
                badge = QRect(r.x(), badge_y, 120, 22)
                p.fillRect(badge, QColor(0, 0, 0, 200))
                p.drawText(badge.adjusted(8, 0, 0, 0),
                           Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                           label)
            # Always-visible hint bar at the bottom.
            hint_h = 44
            hint_bar = QRect(0, self.height() - hint_h, self.width(), hint_h)
            p.fillRect(hint_bar, QColor(20, 20, 24, 220))
            p.setPen(QColor("#ffffff"))
            font = QFont(); font.setPointSize(11); font.setBold(True)
            p.setFont(font)
            p.drawText(
                hint_bar,
                Qt.AlignmentFlag.AlignCenter,
                "Drag with the crosshair to select a region   ·   "
                "Enter = whole screen   ·   Esc = cancel"
            )

        def mousePressEvent(self, e):
            if e.button() == Qt.MouseButton.LeftButton:
                self.start = e.pos()
                self.end = e.pos()
                self.update()

        def mouseMoveEvent(self, e):
            if self.start is not None:
                self.end = e.pos()
                self.update()

        def mouseReleaseEvent(self, e):
            if e.button() == Qt.MouseButton.LeftButton and self.start is not None:
                self.end = e.pos()
                r = QRect(self.start, self.end).normalized()
                if r.width() > 4 and r.height() > 4:
                    self.committed = r
                self.close()

        def keyPressEvent(self, e):
            if e.key() == Qt.Key.Key_Escape:
                self.committed = None
                self.close()
            elif e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.committed = QRect(0, 0, self.width(), self.height())
                self.close()
            else:
                super().keyPressEvent(e)

    picker = Picker(pixmap)
    loop = QApplication.instance()
    # Block until the picker closes (we don't want a nested .exec()).
    while picker.isVisible():
        loop.processEvents(qt["QEventLoop"].ProcessEventsFlag.WaitForMoreEvents)

    if picker.committed is None:
        return None
    w_ratio = pixmap.width() / max(picker.width(), 1)
    h_ratio = pixmap.height() / max(picker.height(), 1)
    r = picker.committed
    return QRect(
        int(r.x() * w_ratio),
        int(r.y() * h_ratio),
        int(r.width() * w_ratio),
        int(r.height() * h_ratio),
    )


# ============================================================================
# Qt import helper
# ============================================================================

def _load_qt() -> dict:
    from PyQt6.QtCore import (
        Qt, QPoint, QPointF, QRect, QRectF, QLineF, QSize, QSettings,
        QStandardPaths, QEventLoop, QTimer,
    )
    from PyQt6.QtGui import (
        QAction, QActionGroup, QBrush, QColor, QFont, QGuiApplication, QIcon,
        QImage, QKeySequence, QPainter, QPainterPath, QPen, QPixmap, QPolygonF,
        QUndoCommand, QUndoStack, QShortcut,
    )
    from PyQt6.QtWidgets import (
        QApplication, QCheckBox, QColorDialog, QComboBox, QDialog,
        QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QGraphicsEllipseItem,
        QGraphicsItem, QGraphicsLineItem, QGraphicsPathItem, QGraphicsPixmapItem,
        QGraphicsRectItem, QGraphicsScene, QGraphicsTextItem, QGraphicsView,
        QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMainWindow,
        QMenu, QMenuBar, QMessageBox, QPushButton, QScrollArea, QSizePolicy,
        QSpinBox, QStackedWidget, QStatusBar, QToolBar, QToolButton, QVBoxLayout,
        QWidget,
    )
    return locals()


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


# ============================================================================
# Settings
# ============================================================================

DEFAULTS = {
    "save_dir": "",                                   # filled at runtime
    "filename_template": "Screenshot %Y-%m-%d %H-%M-%S",
    "format": "PNG",
    "jpg_quality": 92,
    "capture_delay": 0,
    "copy_after_save": False,
    "pick_region_after_capture": True,
    "color": "#e53935",
    "stroke": 4,
    "show_toolbar": True,
    "show_statusbar": True,
}


def _default_save_dir() -> str:
    for env in ("XDG_PICTURES_DIR",):
        v = os.environ.get(env)
        if v:
            return v
    cand = Path.home() / "Pictures"
    return str(cand if cand.exists() else Path.home())


def friendly_screen_name(scr) -> str:
    """Best-effort human name for a QScreen.

    Handles common cases:
      • Apple panels: "APP" + "Color LCD"      → "Built-in Display"
      • Laptop panels by output name (eDP-*, LVDS-*, DSI-*)
                                               → "Built-in Display"
      • Generic / numeric EDID model strings   → fall back to connector name
      • Useful model fields (HP / Samsung etc) → use the model verbatim
    """
    mfr = (scr.manufacturer() or "").strip()
    model = (scr.model() or "").strip()
    out = (scr.name() or "Display").strip()

    # Output-name first: a laptop's internal panel always uses eDP-*, LVDS-*
    # or DSI-* regardless of what its EDID says. This catches BOE / LG /
    # Samsung laptop panels with junk EDID model strings.
    low_out = out.lower()
    if low_out.startswith(("edp", "lvds", "dsi")):
        return "Built-in Display"

    # Apple-style builtin reporting.
    if mfr.upper() == "APP" and "LCD" in model.upper():
        return "Built-in Display"

    # Useful model? (Reject generic placeholders + hex-id-looking strings.)
    if model:
        low = model.lower()
        looks_generic = low in ("color lcd", "lcd", "display", "monitor", "")
        looks_hex = (model.startswith(("0x", "0X")) or
                     all(c in "0123456789abcdefABCDEF" for c in model))
        if not (looks_generic or looks_hex):
            return model

    # Final fallback: connector type makes it informative even without EDID.
    for prefix, label in (
        ("dp-", "DisplayPort"),
        ("hdmi-", "HDMI"),
        ("vga-", "VGA"),
        ("dvi-", "DVI"),
        ("usb-c-", "USB-C Display"),
    ):
        if low_out.startswith(prefix):
            # Append the connector index if present, e.g. "DisplayPort 3".
            tail = out.split("-", 1)[1] if "-" in out else ""
            return f"{label} {tail}".strip()
    return out


def describe_screen(scr) -> tuple[str, str]:
    """Return (label, tooltip) for a screen, including resolution and scale."""
    name = friendly_screen_name(scr)
    g = scr.geometry()
    dpr = scr.devicePixelRatio()
    size_main = f"{g.width()} × {g.height()}"
    if abs(dpr - 1.0) > 0.05:
        size_main += f"  @ {dpr:g}×"
    tooltip_lines = [
        f"Output: {scr.name() or '—'}",
        f"Manufacturer: {scr.manufacturer() or '—'}",
        f"Model: {scr.model() or '—'}",
        f"Logical size: {g.width()} × {g.height()} px",
        f"Position: ({g.x()}, {g.y()})",
        f"Device pixel ratio: {dpr:g}",
        f"Refresh rate: {scr.refreshRate():.0f} Hz",
    ]
    return f"{name}  ·  {size_main}", "\n".join(tooltip_lines)


# ============================================================================
# Application
# ============================================================================

def run_app(initial_image: Path | None, autostart_capture: str | None,
            autostart_delay: int = 0) -> int:
    qt = _load_qt()
    # Pull bound names into the function for readability.
    Qt = qt["Qt"]
    QPoint = qt["QPoint"]; QPointF = qt["QPointF"]; QRect = qt["QRect"]
    QRectF = qt["QRectF"]; QLineF = qt["QLineF"]; QSize = qt["QSize"]
    QSettings = qt["QSettings"]; QTimer = qt["QTimer"]
    QAction = qt["QAction"]; QActionGroup = qt["QActionGroup"]
    QBrush = qt["QBrush"]; QColor = qt["QColor"]; QFont = qt["QFont"]
    QGuiApplication = qt["QGuiApplication"]; QImage = qt["QImage"]
    QKeySequence = qt["QKeySequence"]; QPainter = qt["QPainter"]
    QPainterPath = qt["QPainterPath"]; QPen = qt["QPen"]; QPixmap = qt["QPixmap"]
    QPolygonF = qt["QPolygonF"]
    QUndoCommand = qt["QUndoCommand"]; QUndoStack = qt["QUndoStack"]
    QApplication = qt["QApplication"]; QCheckBox = qt["QCheckBox"]
    QColorDialog = qt["QColorDialog"]; QComboBox = qt["QComboBox"]
    QDialog = qt["QDialog"]; QDialogButtonBox = qt["QDialogButtonBox"]
    QFileDialog = qt["QFileDialog"]; QFormLayout = qt["QFormLayout"]
    QFrame = qt["QFrame"]
    QGraphicsEllipseItem = qt["QGraphicsEllipseItem"]
    QGraphicsItem = qt["QGraphicsItem"]; QGraphicsLineItem = qt["QGraphicsLineItem"]
    QGraphicsPathItem = qt["QGraphicsPathItem"]
    QGraphicsPixmapItem = qt["QGraphicsPixmapItem"]
    QGraphicsRectItem = qt["QGraphicsRectItem"]; QGraphicsScene = qt["QGraphicsScene"]
    QGraphicsTextItem = qt["QGraphicsTextItem"]; QGraphicsView = qt["QGraphicsView"]
    QHBoxLayout = qt["QHBoxLayout"]; QInputDialog = qt["QInputDialog"]
    QLabel = qt["QLabel"]; QLineEdit = qt["QLineEdit"]
    QMainWindow = qt["QMainWindow"]; QMessageBox = qt["QMessageBox"]
    QPushButton = qt["QPushButton"]; QSizePolicy = qt["QSizePolicy"]
    QSpinBox = qt["QSpinBox"]; QStackedWidget = qt["QStackedWidget"]
    QToolBar = qt["QToolBar"]; QToolButton = qt["QToolButton"]
    QVBoxLayout = qt["QVBoxLayout"]; QWidget = qt["QWidget"]

    # ------------------------------------------------------------------ Arrow
    class ArrowItem(QGraphicsLineItem):
        def __init__(self, p1, p2, pen):
            super().__init__(QLineF(p1, p2))
            self.setPen(pen)

        def _head_size(self) -> float:
            return max(10.0, self.pen().widthF() * 3.5)

        def set_end(self, p):
            line = self.line()
            line.setP2(p)
            self.setLine(line)

        def boundingRect(self):
            h = self._head_size()
            return super().boundingRect().adjusted(-h, -h, h, h)

        def paint(self, painter, option, widget=None):
            super().paint(painter, option, widget)
            line = self.line()
            if line.length() < 1:
                return
            angle = math.atan2(line.dy(), line.dx())
            h = self._head_size()
            head_angle = math.radians(25)
            p2 = line.p2()
            p3 = QPointF(p2.x() - h * math.cos(angle - head_angle),
                         p2.y() - h * math.sin(angle - head_angle))
            p4 = QPointF(p2.x() - h * math.cos(angle + head_angle),
                         p2.y() - h * math.sin(angle + head_angle))
            painter.setPen(self.pen())
            painter.setBrush(QBrush(self.pen().color()))
            painter.drawPolygon(QPolygonF([p2, p3, p4]))

    # ------------------------------------------------------------------ Undo
    class AddItemCommand(QUndoCommand):
        def __init__(self, scene, item):
            super().__init__("annotation")
            self._scene = scene
            self._item = item
            self._added = True

        def redo(self):
            if not self._added:
                self._scene.addItem(self._item)
                self._added = True

        def undo(self):
            if self._added:
                self._scene.removeItem(self._item)
                self._added = False

    class RemoveItemsCommand(QUndoCommand):
        """Delete a set of items. Items remain referenced so undo can re-add them."""

        def __init__(self, scene, items):
            super().__init__(
                "delete" if len(items) == 1 else f"delete {len(items)} items")
            self._scene = scene
            self._items = list(items)

        def redo(self):
            for it in self._items:
                if it.scene() is self._scene:
                    self._scene.removeItem(it)

        def undo(self):
            for it in self._items:
                if it.scene() is None:
                    self._scene.addItem(it)

    class MoveItemsCommand(QUndoCommand):
        """Restore old/new positions of items dragged in select mode."""

        def __init__(self, changes):
            super().__init__(
                "move" if len(changes) == 1 else f"move {len(changes)} items")
            # changes: [(item, old_pos, new_pos), ...]
            self._changes = list(changes)
            self._first = True  # items already at new_pos when command is pushed

        def redo(self):
            if self._first:
                self._first = False
                return
            for it, _old, new in self._changes:
                it.setPos(new)

        def undo(self):
            for it, old, _new in self._changes:
                it.setPos(old)

    class CropCommand(QUndoCommand):
        """Replace the background pixmap and remove existing items, but keep
        them around so undo restores the pre-crop scene exactly."""

        def __init__(self, window, old_bg_pixmap, old_items_snapshot, new_bg_pixmap):
            super().__init__("crop")
            self._window = window
            self._old_bg = old_bg_pixmap
            self._items = old_items_snapshot  # [(item, pos)]
            self._new_bg = new_bg_pixmap
            self._first = True  # already applied manually when pushed

        def _swap_bg(self, pixmap):
            scene = self._window.scene
            if self._window.bg_item is not None:
                scene.removeItem(self._window.bg_item)
            new_bg = QGraphicsPixmapItem(pixmap)
            new_bg.setZValue(-1000)
            scene.addItem(new_bg)
            self._window.bg_item = new_bg
            scene.setSceneRect(new_bg.boundingRect())
            self._window.canvas.setSceneRect(scene.sceneRect())

        def redo(self):
            if self._first:
                self._first = False
                return
            for it, _pos in self._items:
                if it.scene() is self._window.scene:
                    self._window.scene.removeItem(it)
            self._swap_bg(self._new_bg)

        def undo(self):
            self._swap_bg(self._old_bg)
            for it, pos in self._items:
                if it.scene() is None:
                    self._window.scene.addItem(it)
                it.setPos(pos)

    # ---------------------------------------------------------------- Canvas
    class Canvas(QGraphicsView):
        def __init__(self, window):
            super().__init__(window)
            self.window_ref = window
            self.setRenderHints(QPainter.RenderHint.Antialiasing |
                                QPainter.RenderHint.SmoothPixmapTransform)
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.setMouseTracking(True)
            self.setTransformationAnchor(
                QGraphicsView.ViewportAnchor.AnchorUnderMouse)
            self._tool = "select"
            self._temp = None
            self._start = None
            self._path = None
            self._move_snapshot: list = []  # [(item, pos)] for undoable moves

        def set_tool(self, name):
            self._tool = name
            if name == "select":
                self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
                self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
            else:
                self.setDragMode(QGraphicsView.DragMode.NoDrag)
                self.viewport().setCursor(Qt.CursorShape.CrossCursor)
            for it in self.scene().items() if self.scene() else []:
                if it is self.window_ref.bg_item:
                    continue
                it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable,
                           name == "select")
                it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable,
                           name == "select")

        def wheelEvent(self, e):
            if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
                factor = 1.15 if e.angleDelta().y() > 0 else 1 / 1.15
                self.scale(factor, factor)
                e.accept()
                return
            super().wheelEvent(e)

        def _make_pen(self, highlighter=False):
            c = QColor(self.window_ref.color)
            if highlighter:
                c.setAlpha(110)
                pen = QPen(c, max(12, self.window_ref.stroke * 3))
            else:
                pen = QPen(c, self.window_ref.stroke)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            return pen

        def _make_brush(self):
            if self.window_ref.fill:
                c = QColor(self.window_ref.color); c.setAlpha(60)
                return QBrush(c)
            return QBrush(Qt.BrushStyle.NoBrush)

        def mousePressEvent(self, e):
            if e.button() != Qt.MouseButton.LeftButton or self._tool == "select":
                super().mousePressEvent(e)
                # After selection is updated, snapshot the items the user is
                # about to drag (if any) so we can emit an undoable move on
                # release.
                if self._tool == "select" and e.button() == Qt.MouseButton.LeftButton:
                    self._move_snapshot = [
                        (it, it.pos()) for it in self.scene().selectedItems()
                        if it is not self.window_ref.bg_item
                    ]
                return
            pos = self.mapToScene(e.pos())
            self._start = pos
            t = self._tool

            if t == "rect":
                self._temp = QGraphicsRectItem(QRectF(pos, pos))
                self._temp.setPen(self._make_pen())
                self._temp.setBrush(self._make_brush())
                self.scene().addItem(self._temp)
            elif t == "ellipse":
                self._temp = QGraphicsEllipseItem(QRectF(pos, pos))
                self._temp.setPen(self._make_pen())
                self._temp.setBrush(self._make_brush())
                self.scene().addItem(self._temp)
            elif t == "line":
                self._temp = QGraphicsLineItem(QLineF(pos, pos))
                self._temp.setPen(self._make_pen())
                self.scene().addItem(self._temp)
            elif t == "arrow":
                self._temp = ArrowItem(pos, pos, self._make_pen())
                self.scene().addItem(self._temp)
            elif t == "pen":
                self._path = QPainterPath(pos)
                self._temp = QGraphicsPathItem(self._path)
                self._temp.setPen(self._make_pen())
                self.scene().addItem(self._temp)
            elif t == "highlight":
                self._path = QPainterPath(pos)
                self._temp = QGraphicsPathItem(self._path)
                self._temp.setPen(self._make_pen(highlighter=True))
                self.scene().addItem(self._temp)
            elif t == "text":
                text, ok = QInputDialog.getText(self, "Add text",
                                                "Annotation text:")
                if ok and text:
                    item = QGraphicsTextItem(text)
                    item.setDefaultTextColor(QColor(self.window_ref.color))
                    f = QFont()
                    f.setPointSize(max(8, self.window_ref.stroke * 4))
                    f.setBold(True)
                    item.setFont(f)
                    item.setPos(pos)
                    self.scene().addItem(item)
                    self.window_ref.undo_stack.push(
                        AddItemCommand(self.scene(), item))
                self._start = None
            elif t in ("crop", "blur"):
                colour = "red" if t == "crop" else "blue"
                pen = QPen(QColor(colour), 1, Qt.PenStyle.DashLine)
                self._temp = QGraphicsRectItem(QRectF(pos, pos))
                self._temp.setPen(pen)
                self.scene().addItem(self._temp)

        def mouseMoveEvent(self, e):
            if self._start is None:
                super().mouseMoveEvent(e)
                return
            pos = self.mapToScene(e.pos())
            t = self._tool
            if t in ("rect", "ellipse", "crop", "blur") and self._temp is not None:
                self._temp.setRect(QRectF(self._start, pos).normalized())
            elif t == "line" and self._temp is not None:
                self._temp.setLine(QLineF(self._start, pos))
            elif t == "arrow" and self._temp is not None:
                self._temp.set_end(pos)
            elif t in ("pen", "highlight") and self._temp is not None:
                self._path.lineTo(pos)
                self._temp.setPath(self._path)

        def mouseReleaseEvent(self, e):
            if self._start is None:
                super().mouseReleaseEvent(e)
                # If we snapshotted items in select mode, see if any moved.
                if self._tool == "select" and self._move_snapshot:
                    changes = [
                        (it, old, it.pos())
                        for it, old in self._move_snapshot
                        if it.pos() != old
                    ]
                    if changes:
                        self.window_ref.undo_stack.push(MoveItemsCommand(changes))
                    self._move_snapshot = []
                return
            t = self._tool
            if t == "crop" and self._temp is not None:
                rect = self._temp.rect()
                self.scene().removeItem(self._temp)
                if rect.width() > 4 and rect.height() > 4:
                    self.window_ref.apply_crop(rect)
            elif t == "blur" and self._temp is not None:
                rect = self._temp.rect()
                self.scene().removeItem(self._temp)
                if rect.width() > 4 and rect.height() > 4:
                    self.window_ref.apply_blur(rect)
            elif self._temp is not None:
                br = self._temp.sceneBoundingRect()
                if br.width() < 2 and br.height() < 2:
                    self.scene().removeItem(self._temp)
                else:
                    self.window_ref.undo_stack.push(
                        AddItemCommand(self.scene(), self._temp))
            self._temp = None
            self._start = None
            self._path = None

        def keyPressEvent(self, e):
            if e.key() == Qt.Key.Key_Delete and self.scene() is not None:
                self.window_ref._delete_selection()
                return
            super().keyPressEvent(e)

        def contextMenuEvent(self, e):
            scene = self.scene()
            if scene is None:
                return
            scene_pos = self.mapToScene(e.pos())
            item = scene.itemAt(scene_pos, self.transform())
            QMenu = qt["QMenu"]
            menu = QMenu(self)
            if item is not None and item is not self.window_ref.bg_item:
                # Right-click on an annotation: act on it.
                if not item.isSelected():
                    scene.clearSelection()
                    item.setSelected(True)
                act_color = menu.addAction("Change color…")
                act_color.triggered.connect(self.window_ref._pick_color)
                act_width = menu.addAction("Change width…")
                act_width.triggered.connect(
                    self.window_ref._prompt_change_width)
                menu.addSeparator()
                act_delete = menu.addAction("Delete")
                act_delete.triggered.connect(self.window_ref._delete_selection)
                menu.addSeparator()
                act_front = menu.addAction("Bring to Front")
                act_front.triggered.connect(
                    lambda: self.window_ref._z_change(+1))
                act_back = menu.addAction("Send to Back")
                act_back.triggered.connect(
                    lambda: self.window_ref._z_change(-1))
            else:
                # Right-click on empty area: scene-wide options.
                act_clear = menu.addAction("Clear All Annotations")
                act_clear.triggered.connect(
                    self.window_ref._clear_all_annotations)
                act_clear.setEnabled(bool(self.window_ref._annotation_items()))
                act_paste = menu.addAction("Select All Annotations")
                act_paste.triggered.connect(
                    self.window_ref._select_all_annotations)
                act_paste.setEnabled(bool(self.window_ref._annotation_items()))
            menu.exec(e.globalPos())

    # --------------------------------------------------------------- Welcome
    class Welcome(QWidget):
        """Welcome / launcher screen shown when no image is loaded.

        Layout (top to bottom):
          • Corner: discreet Preferences shortcut
          • Hero: brand + tagline
          • Primary row: three action cards (region / full / open)
          • Section: delayed capture (header + small chips)
          • Section: per-monitor capture (only if >1 monitor)
          • Footer: PrintScreen tip + "set up shortcut" link
        """

        def __init__(self, window):
            super().__init__(window)
            self.setObjectName("welcome")
            self.setStyleSheet("""
                QWidget#welcome    { background: #15171c; }
                QLabel#brand       { color: #ffffff; font-size: 40pt; font-weight: 700; letter-spacing: 1px; }
                QLabel#amharic     { color: #ffd166; font-size: 36pt; font-weight: 700; }
                QLabel#tag         { color: #ffd166; font-size: 11pt; font-style: italic; }
                QLabel#sub         { color: #9aa0ad; font-size: 11pt; }
                QLabel#section     { color: #c8ccd6; font-size: 11pt; font-weight: 600; letter-spacing: 0.4px; }
                QLabel#footer      { color: #6a6f7d; font-size: 10pt; }

                /* "Card" buttons for primary actions */
                QPushButton.card {
                    background: #232631;
                    color: #ffffff;
                    border: 1px solid #2e3240;
                    border-radius: 10px;
                    padding: 22px 14px;
                    font-size: 12pt;
                    text-align: center;
                }
                QPushButton.card:hover   { background: #2b2f3c; border-color: #3a86ff; }
                QPushButton.card-primary { background: #3a86ff; border: none; color: white; font-weight: bold; }
                QPushButton.card-primary:hover { background: #2c6fd9; }

                /* "Chip" buttons for secondary options */
                QPushButton.chip {
                    background: #1e2129;
                    color: #d4d8e1;
                    border: 1px solid #2a2d38;
                    border-radius: 16px;
                    padding: 6px 14px;
                    font-size: 10pt;
                }
                QPushButton.chip:hover { background: #2a2d38; color: #ffffff; }

                /* Plain link-style button (corner, footer) */
                QPushButton.link {
                    background: transparent;
                    color: #9aa0ad;
                    border: none;
                    padding: 4px 8px;
                    font-size: 10pt;
                }
                QPushButton.link:hover { color: #ffffff; text-decoration: underline; }
            """)

            outer = QVBoxLayout(self)
            outer.setContentsMargins(60, 24, 60, 32)
            outer.setSpacing(0)

            # ---------- top-right preferences shortcut ----------
            top_bar = QHBoxLayout()
            top_bar.addStretch(1)
            prefs_btn = QPushButton("⚙  Preferences")
            prefs_btn.setProperty("class", "link")
            prefs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            prefs_btn.clicked.connect(window.show_preferences)
            top_bar.addWidget(prefs_btn)
            shortcut_btn = QPushButton("⌨  Global shortcut…")
            shortcut_btn.setProperty("class", "link")
            shortcut_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            shortcut_btn.clicked.connect(window.setup_global_shortcut)
            top_bar.addWidget(shortcut_btn)
            outer.addLayout(top_bar)

            outer.addStretch(1)

            # ---------- hero ----------
            hero = QHBoxLayout()
            hero.setSpacing(14)
            hero.addStretch(1)
            brand = QLabel("Yaz")
            brand.setObjectName("brand")
            hero.addWidget(brand)
            dot = QLabel("·"); dot.setObjectName("brand")
            dot.setStyleSheet("color:#3a86ff;")
            hero.addWidget(dot)
            amh = QLabel("ያዝ"); amh.setObjectName("amharic")
            hero.addWidget(amh)
            hero.addStretch(1)
            outer.addLayout(hero)

            tag = QLabel('Amharic for "grab it"')
            tag.setObjectName("tag")
            tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
            outer.addWidget(tag)
            outer.addSpacing(28)

            # ---------- primary cards ----------
            cards = QHBoxLayout()
            cards.setSpacing(14)
            cards.addStretch(1)

            def make_card(text: str, on_click, primary: bool = False):
                btn = QPushButton(text)
                btn.setProperty("class", "card-primary" if primary else "card")
                btn.setMinimumSize(220, 120)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(on_click)
                # Re-apply stylesheet so property-based selectors take effect.
                btn.setStyleSheet(self.styleSheet())
                return btn

            cards.addWidget(make_card(
                "📐\n\nCapture region\nDrag the area you want",
                window.capture_region, primary=True))
            cards.addWidget(make_card(
                "🖥\n\nCapture full screen\nEverything visible",
                window.capture_full_action))
            cards.addWidget(make_card(
                "📂\n\nOpen image\nAnnotate an existing file",
                window.open_image))
            cards.addStretch(1)
            outer.addLayout(cards)

            outer.addSpacing(28)

            # ---------- delayed capture section ----------
            delay_header = QLabel(
                "⏱  DELAYED CAPTURE  —  set up the hover state first")
            delay_header.setObjectName("section")
            delay_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
            outer.addWidget(delay_header)
            outer.addSpacing(8)

            chips = QHBoxLayout()
            chips.setSpacing(8)
            chips.addStretch(1)
            for sec in (3, 5, 10):
                c = QPushButton(f"Region · {sec}s")
                c.setProperty("class", "chip")
                c.setStyleSheet(self.styleSheet())
                c.setCursor(Qt.CursorShape.PointingHandCursor)
                c.clicked.connect(lambda _c=False, s=sec: window.capture_region_delayed(s))
                chips.addWidget(c)
            cfull = QPushButton("Full · 5s")
            cfull.setProperty("class", "chip")
            cfull.setStyleSheet(self.styleSheet())
            cfull.setCursor(Qt.CursorShape.PointingHandCursor)
            cfull.clicked.connect(lambda: window.capture_full_delayed(5))
            chips.addWidget(cfull)
            ccustom = QPushButton("Custom…")
            ccustom.setProperty("class", "chip")
            ccustom.setStyleSheet(self.styleSheet())
            ccustom.setCursor(Qt.CursorShape.PointingHandCursor)
            ccustom.clicked.connect(window.capture_region_custom_delay)
            chips.addWidget(ccustom)
            chips.addStretch(1)
            outer.addLayout(chips)

            # ---------- per-monitor section (only if >1) ----------
            screens = QGuiApplication.screens()
            if len(screens) > 1:
                outer.addSpacing(22)
                mon_header = QLabel("🖥  SPECIFIC MONITOR")
                mon_header.setObjectName("section")
                mon_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
                outer.addWidget(mon_header)
                outer.addSpacing(8)

                primary = QGuiApplication.primaryScreen()
                # Order screens by their x coordinate so the button row mirrors
                # the physical layout left-to-right.
                ordered = sorted(screens, key=lambda s: (s.geometry().x(), s.geometry().y()))
                mon_row = QHBoxLayout()
                mon_row.setSpacing(8)
                mon_row.addStretch(1)
                for scr in ordered:
                    label, tip = describe_screen(scr)
                    if scr is primary:
                        label = "⭐ " + label + "  ·  Primary"
                    btn = QPushButton(label)
                    btn.setProperty("class", "chip")
                    btn.setStyleSheet(self.styleSheet())
                    btn.setCursor(Qt.CursorShape.PointingHandCursor)
                    btn.setToolTip(tip)
                    btn.clicked.connect(lambda _c=False, s=scr: window.capture_screen(s))
                    mon_row.addWidget(btn)
                mon_row.addStretch(1)
                outer.addLayout(mon_row)

            outer.addStretch(2)

            # ---------- footer ----------
            footer = QHBoxLayout()
            footer.addStretch(1)
            tip = QLabel(
                "Tip — bind <b>PrintScreen</b> to <code>yaz --capture</code> "
                "for instant access."
            )
            tip.setTextFormat(Qt.TextFormat.RichText)
            tip.setObjectName("footer")
            footer.addWidget(tip)
            set_up = QPushButton("Set up now →")
            set_up.setProperty("class", "link")
            set_up.setStyleSheet(self.styleSheet())
            set_up.setCursor(Qt.CursorShape.PointingHandCursor)
            set_up.clicked.connect(window.setup_global_shortcut)
            footer.addWidget(set_up)
            footer.addStretch(1)
            outer.addLayout(footer)

            # Subtle credit line under the footer.
            credit = QLabel(
                "Built by <a href='https://www.linkedin.com/in/yetesfa-alemayehu' "
                "style='color:#6a6f7d;'>Yetesfa Alemayehu</a>"
            )
            credit.setTextFormat(Qt.TextFormat.RichText)
            credit.setObjectName("footer")
            credit.setAlignment(Qt.AlignmentFlag.AlignCenter)
            credit.setOpenExternalLinks(True)
            credit.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextBrowserInteraction)
            outer.addWidget(credit)

    # ------------------------------------------------------------ Preferences
    class PreferencesDialog(QDialog):
        def __init__(self, window):
            super().__init__(window)
            self.window_ref = window
            self.settings = window.qsettings
            self.setWindowTitle("Yaz — Preferences")
            self.resize(520, 0)

            form = QFormLayout()

            # Save directory
            dir_row = QHBoxLayout()
            self.save_dir_edit = QLineEdit(
                self.settings.value("save_dir", _default_save_dir()))
            dir_btn = QPushButton("Browse…")
            dir_btn.clicked.connect(self._pick_dir)
            dir_row.addWidget(self.save_dir_edit)
            dir_row.addWidget(dir_btn)
            form.addRow("Default save folder:", dir_row)

            self.tmpl_edit = QLineEdit(self.settings.value(
                "filename_template", DEFAULTS["filename_template"]))
            form.addRow("Filename template:", self.tmpl_edit)
            hint = QLabel("Uses strftime codes — %Y year, %m month, "
                          "%d day, %H %M %S time.")
            hint.setStyleSheet("color: #888; font-size: 9pt;")
            form.addRow("", hint)

            self.format_combo = QComboBox()
            self.format_combo.addItems(["PNG", "JPG"])
            self.format_combo.setCurrentText(
                self.settings.value("format", DEFAULTS["format"]))
            form.addRow("Default format:", self.format_combo)

            self.jpg_spin = QSpinBox()
            self.jpg_spin.setRange(10, 100)
            self.jpg_spin.setValue(
                int(self.settings.value("jpg_quality", DEFAULTS["jpg_quality"])))
            self.jpg_spin.setSuffix(" %")
            form.addRow("JPG quality:", self.jpg_spin)

            self.delay_spin = QSpinBox()
            self.delay_spin.setRange(0, 30)
            self.delay_spin.setValue(
                int(self.settings.value("capture_delay",
                                        DEFAULTS["capture_delay"])))
            self.delay_spin.setSuffix(" s")
            form.addRow("Capture delay:", self.delay_spin)

            self.copy_check = QCheckBox("Copy image to clipboard when saved")
            self.copy_check.setChecked(self._b("copy_after_save"))
            form.addRow("", self.copy_check)

            self.region_check = QCheckBox(
                "Show region picker after capture (uncheck = edit full screen)")
            self.region_check.setChecked(self._b("pick_region_after_capture"))
            form.addRow("", self.region_check)

            self.color_btn = QPushButton()
            self._color = QColor(
                self.settings.value("color", DEFAULTS["color"]))
            self._refresh_color_btn()
            self.color_btn.clicked.connect(self._pick_color)
            form.addRow("Default annotation color:", self.color_btn)

            self.stroke_spin = QSpinBox()
            self.stroke_spin.setRange(1, 64)
            self.stroke_spin.setValue(
                int(self.settings.value("stroke", DEFAULTS["stroke"])))
            form.addRow("Default stroke width:", self.stroke_spin)

            btns = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok
                | QDialogButtonBox.StandardButton.Cancel
                | QDialogButtonBox.StandardButton.RestoreDefaults
            )
            btns.accepted.connect(self._save_and_close)
            btns.rejected.connect(self.reject)
            btns.button(
                QDialogButtonBox.StandardButton.RestoreDefaults
            ).clicked.connect(self._restore_defaults)

            outer = QVBoxLayout(self)
            outer.addLayout(form)
            outer.addWidget(btns)

        def _b(self, key):
            v = self.settings.value(key, DEFAULTS[key])
            if isinstance(v, bool):
                return v
            return str(v).lower() in ("true", "1", "yes")

        def _pick_dir(self):
            d = QFileDialog.getExistingDirectory(
                self, "Default save folder", self.save_dir_edit.text())
            if d:
                self.save_dir_edit.setText(d)

        def _refresh_color_btn(self):
            self.color_btn.setText(self._color.name())
            self.color_btn.setStyleSheet(
                f"QPushButton {{ background:{self._color.name()}; "
                f"color:white; padding:6px 10px; }}"
            )

        def _pick_color(self):
            c = QColorDialog.getColor(self._color, self,
                                      "Default annotation color")
            if c.isValid():
                self._color = c
                self._refresh_color_btn()

        def _restore_defaults(self):
            self.save_dir_edit.setText(_default_save_dir())
            self.tmpl_edit.setText(DEFAULTS["filename_template"])
            self.format_combo.setCurrentText(DEFAULTS["format"])
            self.jpg_spin.setValue(DEFAULTS["jpg_quality"])
            self.delay_spin.setValue(DEFAULTS["capture_delay"])
            self.copy_check.setChecked(DEFAULTS["copy_after_save"])
            self.region_check.setChecked(DEFAULTS["pick_region_after_capture"])
            self._color = QColor(DEFAULTS["color"])
            self._refresh_color_btn()
            self.stroke_spin.setValue(DEFAULTS["stroke"])

        def _save_and_close(self):
            s = self.settings
            s.setValue("save_dir", self.save_dir_edit.text())
            s.setValue("filename_template", self.tmpl_edit.text())
            s.setValue("format", self.format_combo.currentText())
            s.setValue("jpg_quality", self.jpg_spin.value())
            s.setValue("capture_delay", self.delay_spin.value())
            s.setValue("copy_after_save", self.copy_check.isChecked())
            s.setValue("pick_region_after_capture", self.region_check.isChecked())
            s.setValue("color", self._color.name())
            s.setValue("stroke", self.stroke_spin.value())
            s.sync()
            self.window_ref.apply_settings()
            self.accept()

    # ----------------------------------------------------------- Countdown
    class Countdown(QWidget):
        """Floating circular countdown shown during a delayed capture.

        Hides itself one frame before the capture fires so it doesn't appear
        in the screenshot."""

        def __init__(self, seconds: int):
            super().__init__(
                None,
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.Tool
                | Qt.WindowType.BypassWindowManagerHint,
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            self.remaining = seconds
            self.resize(140, 140)
            screen = QGuiApplication.primaryScreen().availableGeometry()
            # Park top-right so the user can still hover anywhere except that
            # corner. ~30px margin keeps it visually clear of the screen edge.
            self.move(screen.right() - 170, screen.top() + 60)

        def set_remaining(self, n: int):
            self.remaining = n
            self.update()

        def paintEvent(self, _ev):
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            ring = self.rect().adjusted(10, 10, -10, -10)
            p.setBrush(QColor(20, 20, 24, 235))
            p.setPen(QPen(QColor("#3a86ff"), 3))
            p.drawEllipse(ring)
            p.setPen(QColor("white"))
            font = QFont(); font.setPointSize(54); font.setBold(True)
            p.setFont(font)
            p.drawText(ring, Qt.AlignmentFlag.AlignCenter, str(self.remaining))

    # --------------------------------------------------------- MainWindow
    class MainWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Yaz")
            self.resize(1200, 800)
            # Dark-themed chrome — matches the welcome screen and gives a more
            # polished editor look than Qt's default OS theme.
            self.setStyleSheet("""
                QMainWindow      { background: #15171c; }
                QStatusBar       { background: #1a1d24; color: #b6bac4; }
                QMenuBar         { background: #1a1d24; color: #d4d8e1; }
                QMenuBar::item:selected { background: #2a2d38; }
                QMenu            { background: #1a1d24; color: #d4d8e1; border: 1px solid #2a2d38; }
                QMenu::item:selected    { background: #2a2d38; }
                QToolBar         { background: #1a1d24; border: none; padding: 6px; spacing: 4px; }
                QToolBar::separator {
                    background: #2a2d38; width: 1px; margin: 6px 6px;
                }
                QToolButton      {
                    background: transparent; color: #d4d8e1;
                    padding: 6px 10px; border-radius: 4px;
                }
                QToolButton:hover    { background: #2a2d38; color: #ffffff; }
                QToolButton:checked  { background: #3a86ff; color: white; }
                QToolButton:disabled { color: #4a4f5a; }
                QGraphicsView { background: #0e1015; border: none; }
                QSpinBox      {
                    background: #232631; color: #ffffff;
                    border: 1px solid #2e3240; border-radius: 3px;
                    padding: 2px 4px;
                }
                QLabel        { color: #b6bac4; }
            """)

            self.qsettings = QSettings("Yaz", "Yaz")
            self.color = QColor(self.qsettings.value("color", DEFAULTS["color"]))
            self.stroke = int(self.qsettings.value("stroke", DEFAULTS["stroke"]))
            self.fill = False
            self.current_path: Path | None = None
            self.bg_item = None
            self.undo_stack = QUndoStack(self)

            # Central widget: stacked welcome vs. canvas.
            self.stack = QStackedWidget(self)
            self.setCentralWidget(self.stack)

            self.welcome = Welcome(self)
            self.stack.addWidget(self.welcome)

            self.scene = QGraphicsScene(self)
            self.scene.selectionChanged.connect(self._refresh_edit_actions)
            self.scene.changed.connect(lambda _r: self._refresh_edit_actions())
            self.canvas = Canvas(self)
            self.canvas.setScene(self.scene)
            self.stack.addWidget(self.canvas)

            self.stack.setCurrentWidget(self.welcome)
            self.stack.currentChanged.connect(lambda _i: self._apply_chrome_visibility())

            # Toolbars + menus.
            self._tool_actions = {}
            self._tool_group = QActionGroup(self)
            self._tool_group.setExclusive(True)
            self._build_tool_bar()
            self._build_menu_bar()
            self._refresh_edit_actions()

            self.setStatusBar(qt["QStatusBar"](self))
            self.statusBar().showMessage("Ready.")

            # Visibility of toolbar/statusbar from settings.
            self._apply_chrome_visibility()

        # ---- settings ----
        def apply_settings(self):
            self.color = QColor(self.qsettings.value("color", DEFAULTS["color"]))
            self.stroke = int(self.qsettings.value("stroke", DEFAULTS["stroke"]))
            self._refresh_color_btn()
            self.stroke_spin.setValue(self.stroke)

        def _apply_chrome_visibility(self):
            show_tb_pref = self._bool_setting(
                "show_toolbar", DEFAULTS["show_toolbar"])
            show_sb_pref = self._bool_setting(
                "show_statusbar", DEFAULTS["show_statusbar"])
            # Toolbar only makes sense in editor mode — drawing tools have no
            # target on the welcome screen.
            on_welcome = (hasattr(self, "stack")
                          and self.stack.currentWidget() is self.welcome)
            self.tool_bar.setVisible(show_tb_pref and not on_welcome)
            self.statusBar().setVisible(show_sb_pref)

        def _bool_setting(self, key, default):
            v = self.qsettings.value(key, default)
            if isinstance(v, bool):
                return v
            return str(v).lower() in ("true", "1", "yes")

        # ---- ui construction ----
        def _build_tool_bar(self):
            tb = QToolBar("Tools", self)
            tb.setMovable(False)
            tb.setIconSize(QSize(20, 20))
            self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)
            self.tool_bar = tb

            def add_tool(label, key, name, default=False):
                a = QAction(label, self)
                a.setShortcut(QKeySequence(key))
                a.setCheckable(True)
                a.setToolTip(f"{label} ({key})")
                a.triggered.connect(lambda _c=False, n=name: self._set_tool(n))
                self._tool_group.addAction(a)
                tb.addAction(a)
                self._tool_actions[name] = a
                if default:
                    a.setChecked(True)

            add_tool("Select", "V", "select", default=True)
            add_tool("Crop",       "C", "crop")
            tb.addSeparator()
            add_tool("Rect",       "R", "rect")
            add_tool("Ellipse",    "E", "ellipse")
            add_tool("Arrow",      "A", "arrow")
            add_tool("Line",       "L", "line")
            add_tool("Pen",        "P", "pen")
            add_tool("Highlight",  "H", "highlight")
            add_tool("Text",       "T", "text")
            add_tool("Blur",       "B", "blur")
            tb.addSeparator()

            # Color swatch — small coloured square next to a "Color" label.
            color_widget = QWidget(self)
            cl = QHBoxLayout(color_widget)
            cl.setContentsMargins(8, 0, 4, 0); cl.setSpacing(6)
            color_label = QLabel("Color")
            cl.addWidget(color_label)
            self.color_btn = QToolButton(self)
            self.color_btn.setFixedSize(26, 22)
            self.color_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.color_btn.setToolTip("Annotation color")
            self.color_btn.clicked.connect(self._pick_color)
            cl.addWidget(self.color_btn)
            tb.addWidget(color_widget)
            self._refresh_color_btn()

            # Width spinner.
            width_widget = QWidget(self)
            wl = QHBoxLayout(width_widget)
            wl.setContentsMargins(10, 0, 4, 0); wl.setSpacing(6)
            wl.addWidget(QLabel("Width"))
            self.stroke_spin = QSpinBox(self)
            self.stroke_spin.setRange(1, 64)
            self.stroke_spin.setValue(self.stroke)
            self.stroke_spin.setFixedWidth(64)
            self.stroke_spin.setToolTip("Stroke width in pixels")
            self.stroke_spin.valueChanged.connect(self._set_stroke)
            wl.addWidget(self.stroke_spin)
            tb.addWidget(width_widget)

            self.fill_action = QAction("Fill", self)
            self.fill_action.setCheckable(True)
            self.fill_action.setShortcut(QKeySequence("Shift+F"))
            self.fill_action.toggled.connect(self._set_fill)
            tb.addAction(self.fill_action)

            tb.addSeparator()

            # Undo / Redo on the main toolbar for visibility.
            self.undo_action = self.undo_stack.createUndoAction(self, "Undo")
            self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
            self.undo_action.setToolTip("Undo (Ctrl+Z)")
            tb.addAction(self.undo_action)

            self.redo_action = self.undo_stack.createRedoAction(self, "Redo")
            self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
            self.redo_action.setToolTip("Redo (Ctrl+Y)")
            tb.addAction(self.redo_action)

            tb.addSeparator()

            # Delete button — enabled when annotations are selected.
            self.delete_action = QAction("Delete", self)
            self.delete_action.setShortcut(QKeySequence.StandardKey.Delete)
            self.delete_action.setToolTip("Delete selected annotations (Del)")
            self.delete_action.triggered.connect(self._delete_selection)
            self.delete_action.setEnabled(False)
            tb.addAction(self.delete_action)

            self.clear_action = QAction("Clear All", self)
            self.clear_action.setToolTip("Remove every annotation, keep the image")
            self.clear_action.triggered.connect(self._clear_all_annotations)
            self.clear_action.setEnabled(False)
            tb.addAction(self.clear_action)

        def _build_menu_bar(self):
            mb = self.menuBar()

            # File
            file_menu = mb.addMenu("&File")
            cap_menu = file_menu.addMenu("New &Capture")

            self.action_capture_region = QAction("Capture &Region", self)
            self.action_capture_region.setShortcut("Ctrl+R")
            self.action_capture_region.triggered.connect(self.capture_region)
            cap_menu.addAction(self.action_capture_region)

            self.action_capture_full = QAction("Capture &Full Screen", self)
            # Ctrl+Alt+R avoids browser hard-reload (Ctrl+Shift+R) conflict.
            self.action_capture_full.setShortcut("Ctrl+Alt+R")
            self.action_capture_full.triggered.connect(self.capture_full_action)
            cap_menu.addAction(self.action_capture_full)

            cap_menu.addSeparator()
            # Delayed capture submenu (essential for hover-state screenshots).
            delay_menu = cap_menu.addMenu("Capture Region with &Delay")
            for sec, sc in ((3, "Ctrl+Shift+3"), (5, "Ctrl+Shift+5"), (10, "Ctrl+Shift+0")):
                a = QAction(f"Capture region after &{sec} seconds", self)
                a.setShortcut(sc)
                a.triggered.connect(lambda _c=False, s=sec: self.capture_region_delayed(s))
                delay_menu.addAction(a)
            custom = QAction("Custom delay…", self)
            custom.triggered.connect(self.capture_region_custom_delay)
            delay_menu.addAction(custom)

            screens = QGuiApplication.screens()
            if len(screens) > 1:
                cap_menu.addSeparator()
                primary = QGuiApplication.primaryScreen()
                ordered = sorted(
                    screens, key=lambda s: (s.geometry().x(), s.geometry().y()))
                for scr in ordered:
                    label, tip = describe_screen(scr)
                    prefix = "⭐ " if scr is primary else "🖥 "
                    a = QAction(f"{prefix}Capture {label}", self)
                    a.setToolTip(tip)
                    a.triggered.connect(lambda _c=False, s=scr: self.capture_screen(s))
                    cap_menu.addAction(a)

            self.action_open = QAction("&Open Image…", self)
            self.action_open.setShortcut(QKeySequence.StandardKey.Open)
            self.action_open.triggered.connect(self.open_image)
            file_menu.addAction(self.action_open)

            file_menu.addSeparator()
            self.action_save = QAction("&Save", self)
            self.action_save.setShortcut(QKeySequence.StandardKey.Save)
            self.action_save.triggered.connect(self.save)
            file_menu.addAction(self.action_save)

            self.action_save_as = QAction("Save &As…", self)
            self.action_save_as.setShortcut("Ctrl+Shift+S")
            self.action_save_as.triggered.connect(self.save_as)
            file_menu.addAction(self.action_save_as)

            self.action_copy_clip = QAction("&Copy to Clipboard", self)
            self.action_copy_clip.setShortcut("Ctrl+Shift+C")
            self.action_copy_clip.triggered.connect(self.copy_to_clipboard)
            file_menu.addAction(self.action_copy_clip)

            file_menu.addSeparator()
            self.action_global_shortcut = QAction(
                "Set Up &Global Keyboard Shortcut…", self)
            self.action_global_shortcut.triggered.connect(self.setup_global_shortcut)
            file_menu.addAction(self.action_global_shortcut)

            self.action_prefs = QAction("&Preferences…", self)
            self.action_prefs.setShortcut("Ctrl+,")
            self.action_prefs.triggered.connect(self.show_preferences)
            file_menu.addAction(self.action_prefs)

            file_menu.addSeparator()
            self.action_close = QAction("Close &Image", self)
            self.action_close.setShortcut("Ctrl+W")
            self.action_close.triggered.connect(self.close_image)
            file_menu.addAction(self.action_close)

            self.action_quit = QAction("&Quit", self)
            self.action_quit.setShortcut(QKeySequence.StandardKey.Quit)
            self.action_quit.triggered.connect(QApplication.quit)
            file_menu.addAction(self.action_quit)

            # Edit — reuse toolbar actions so menu and toolbar stay in sync.
            edit_menu = mb.addMenu("&Edit")
            edit_menu.addAction(self.undo_action)
            edit_menu.addAction(self.redo_action)
            edit_menu.addSeparator()
            edit_menu.addAction(self.delete_action)
            edit_menu.addAction(self.clear_action)
            edit_menu.addSeparator()
            select_all = QAction("Select &All Annotations", self)
            select_all.setShortcut(QKeySequence.StandardKey.SelectAll)
            select_all.triggered.connect(self._select_all_annotations)
            edit_menu.addAction(select_all)

            # View
            view_menu = mb.addMenu("&View")
            zi = QAction("Zoom &In", self); zi.setShortcut("Ctrl++")
            zi.triggered.connect(lambda: self.canvas.scale(1.15, 1.15))
            view_menu.addAction(zi)
            zo = QAction("Zoom &Out", self); zo.setShortcut("Ctrl+-")
            zo.triggered.connect(lambda: self.canvas.scale(1 / 1.15, 1 / 1.15))
            view_menu.addAction(zo)
            zr = QAction("&Reset Zoom", self); zr.setShortcut("Ctrl+0")
            zr.triggered.connect(self.canvas.resetTransform)
            view_menu.addAction(zr)
            fit = QAction("&Fit to Window", self); fit.setShortcut("Ctrl+F")
            fit.triggered.connect(self._fit_to_view)
            view_menu.addAction(fit)
            view_menu.addSeparator()
            self.action_show_tb = QAction("Show &Toolbar", self)
            self.action_show_tb.setCheckable(True)
            self.action_show_tb.setChecked(
                self._bool_setting("show_toolbar", DEFAULTS["show_toolbar"]))
            self.action_show_tb.toggled.connect(self._toggle_toolbar)
            view_menu.addAction(self.action_show_tb)
            self.action_show_sb = QAction("Show &Status Bar", self)
            self.action_show_sb.setCheckable(True)
            self.action_show_sb.setChecked(
                self._bool_setting("show_statusbar", DEFAULTS["show_statusbar"]))
            self.action_show_sb.toggled.connect(self._toggle_statusbar)
            view_menu.addAction(self.action_show_sb)

            # Tools menu mirrors the toolbar group
            tools_menu = mb.addMenu("&Tools")
            for a in self._tool_actions.values():
                tools_menu.addAction(a)

            # Help
            help_menu = mb.addMenu("&Help")
            sc = QAction("&Keyboard Shortcuts", self)
            sc.setShortcut("F1")
            sc.triggered.connect(self._show_shortcuts)
            help_menu.addAction(sc)
            ab = QAction("&About Yaz", self)
            ab.triggered.connect(self._show_about)
            help_menu.addAction(ab)

        # ---- toolbar / state handlers ----
        def _set_tool(self, name):
            self.canvas.set_tool(name)
            self.statusBar().showMessage(f"Tool: {name}")

        def _pick_color(self):
            c = QColorDialog.getColor(self.color, self, "Annotation color")
            if c.isValid():
                self.color = c
                self.qsettings.setValue("color", c.name())
                self._refresh_color_btn()
                n = self._apply_color_to_selection(c)
                if n:
                    self.statusBar().showMessage(
                        f"Color updated on {n} item{'s' if n != 1 else ''}", 2500)

        def _refresh_color_btn(self):
            self.color_btn.setStyleSheet(
                f"QToolButton {{ background:{self.color.name()}; "
                f"border: 1px solid #3a3d48; border-radius: 4px; }}"
                f"QToolButton:hover {{ border-color: #3a86ff; }}"
            )

        def _set_stroke(self, v):
            self.stroke = v
            self.qsettings.setValue("stroke", v)
            n = self._apply_stroke_to_selection(v)
            if n:
                self.statusBar().showMessage(
                    f"Width set to {v}px on {n} item{'s' if n != 1 else ''}", 2500)

        def _set_fill(self, v):
            self.fill = v

        def _prompt_change_width(self):
            """Right-click menu helper — opens a quick spin dialog."""
            value, ok = QInputDialog.getInt(
                self, "Yaz — Stroke width",
                "Width in pixels:", value=self.stroke, min=1, max=64,
            )
            if not ok:
                return
            self.stroke_spin.blockSignals(True)
            self.stroke_spin.setValue(value)
            self.stroke_spin.blockSignals(False)
            self.stroke = value
            self.qsettings.setValue("stroke", value)
            n = self._apply_stroke_to_selection(value)
            if n:
                self.statusBar().showMessage(
                    f"Width set to {value}px on {n} item{'s' if n != 1 else ''}", 2500)

        # ---- live property edits on selected items ----
        def _apply_stroke_to_selection(self, width: int) -> int:
            """Update stroke width on selected annotations. Returns count touched."""
            if self.scene is None:
                return 0
            n = 0
            for it in self.scene.selectedItems():
                if it is self.bg_item:
                    continue
                if isinstance(it, QGraphicsTextItem):
                    f = it.font()
                    f.setPointSize(max(8, width * 4))
                    it.setFont(f)
                    n += 1
                    continue
                pen_fn = getattr(it, "pen", None)
                set_pen = getattr(it, "setPen", None)
                if callable(pen_fn) and callable(set_pen):
                    pen = QPen(pen_fn())
                    if pen.color().alpha() < 255:
                        # Highlighter heuristic: keep its 3x scale.
                        pen.setWidth(max(12, width * 3))
                    else:
                        pen.setWidth(width)
                    set_pen(pen)
                    n += 1
            return n

        def _apply_color_to_selection(self, color) -> int:
            """Update color (pen + fill) on selected annotations. Returns count."""
            if self.scene is None:
                return 0
            n = 0
            for it in self.scene.selectedItems():
                if it is self.bg_item:
                    continue
                if isinstance(it, QGraphicsTextItem):
                    it.setDefaultTextColor(color)
                    n += 1
                    continue
                pen_fn = getattr(it, "pen", None)
                set_pen = getattr(it, "setPen", None)
                if callable(pen_fn) and callable(set_pen):
                    pen = QPen(pen_fn())
                    new_pen_color = QColor(color)
                    # Preserve highlighter alpha.
                    if pen.color().alpha() < 255:
                        new_pen_color.setAlpha(pen.color().alpha())
                    pen.setColor(new_pen_color)
                    set_pen(pen)
                    # Filled rect/ellipse → update the brush too.
                    brush_fn = getattr(it, "brush", None)
                    set_brush = getattr(it, "setBrush", None)
                    if callable(brush_fn) and callable(set_brush):
                        b = brush_fn()
                        if b.style() != Qt.BrushStyle.NoBrush:
                            fc = QColor(color); fc.setAlpha(60)
                            set_brush(QBrush(fc))
                    n += 1
            return n

        def _toggle_toolbar(self, on):
            self.tool_bar.setVisible(on)
            self.qsettings.setValue("show_toolbar", on)

        def _toggle_statusbar(self, on):
            self.statusBar().setVisible(on)
            self.qsettings.setValue("show_statusbar", on)

        def _delete_selection(self):
            if self.scene is None:
                return
            items = [it for it in self.scene.selectedItems()
                     if it is not self.bg_item]
            if not items:
                return
            self.undo_stack.push(RemoveItemsCommand(self.scene, items))

        def _annotation_items(self):
            return [it for it in self.scene.items() if it is not self.bg_item]

        def _clear_all_annotations(self):
            items = self._annotation_items()
            if not items:
                return
            self.undo_stack.push(RemoveItemsCommand(self.scene, items))

        def _select_all_annotations(self):
            # Only meaningful in select mode; flip if needed.
            if self.canvas._tool != "select":
                self._tool_actions["select"].setChecked(True)
                self.canvas.set_tool("select")
            for it in self._annotation_items():
                it.setSelected(True)

        def _refresh_edit_actions(self):
            """Enable Delete/Clear All based on current scene state."""
            if not hasattr(self, "delete_action"):
                return
            has_sel = any(
                it is not self.bg_item
                for it in self.scene.selectedItems()
            ) if self.scene is not None else False
            has_any = bool(self._annotation_items()) if self.scene else False
            self.delete_action.setEnabled(has_sel)
            self.clear_action.setEnabled(has_any)

        def _z_change(self, direction: int):
            """+1 = bring forward (max z + 1), -1 = send back (min z - 1).
            The background pixmap stays at z = -1000."""
            others = [it for it in self._annotation_items()
                      if not it.isSelected()]
            if direction > 0:
                target = max((o.zValue() for o in others), default=0) + 1
            else:
                target = min((o.zValue() for o in others), default=0) - 1
                if target < -999:  # never go behind/equal to bg
                    target = -999
            for it in self.scene.selectedItems():
                if it is not self.bg_item:
                    it.setZValue(target)

        def _fit_to_view(self):
            if self.bg_item is None:
                return
            self.canvas.fitInView(self.bg_item, Qt.AspectRatioMode.KeepAspectRatio)

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

        # ---- crop / blur (work on scene) ----
        def apply_crop(self, rect):
            rect = rect.intersected(self.scene.sceneRect())
            if rect.width() < 2 or rect.height() < 2 or self.bg_item is None:
                return
            new_bg = QPixmap(rect.size().toSize())
            new_bg.fill(Qt.GlobalColor.transparent)
            painter = QPainter(new_bg)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            self.scene.render(painter, QRectF(new_bg.rect()), rect)
            painter.end()

            # Snapshot pre-crop state so the operation is undoable.
            old_bg = QPixmap(self.bg_item.pixmap())
            items_snapshot = [
                (it, it.pos()) for it in self.scene.items()
                if it is not self.bg_item
            ]

            # Apply crop now: remove items + swap bg + reset rect.
            for it, _ in items_snapshot:
                self.scene.removeItem(it)
            self.scene.removeItem(self.bg_item)
            bg_item = QGraphicsPixmapItem(new_bg)
            bg_item.setZValue(-1000)
            self.scene.addItem(bg_item)
            self.bg_item = bg_item
            self.scene.setSceneRect(bg_item.boundingRect())
            self.canvas.setSceneRect(self.scene.sceneRect())
            self.canvas.resetTransform()

            self.undo_stack.push(
                CropCommand(self, old_bg, items_snapshot, new_bg))

        def apply_blur(self, rect):
            rect = rect.intersected(self.scene.sceneRect())
            if rect.width() < 2 or rect.height() < 2:
                return
            patch = QPixmap(rect.size().toSize())
            patch.fill(Qt.GlobalColor.transparent)
            p = QPainter(patch)
            self.scene.render(p, QRectF(patch.rect()), rect)
            p.end()
            scale = 14
            small = patch.scaled(max(1, patch.width() // scale),
                                 max(1, patch.height() // scale),
                                 Qt.AspectRatioMode.IgnoreAspectRatio,
                                 Qt.TransformationMode.FastTransformation)
            blurred = small.scaled(patch.width(), patch.height(),
                                   Qt.AspectRatioMode.IgnoreAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
            item = QGraphicsPixmapItem(blurred)
            item.setPos(rect.topLeft())
            item.setZValue(500)
            self.scene.addItem(item)
            self.undo_stack.push(AddItemCommand(self.scene, item))

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

        # ---- preferences ----
        def show_preferences(self):
            dlg = PreferencesDialog(self)
            dlg.exec()

        # ---- global keyboard shortcut ----
        def setup_global_shortcut(self):
            """Register a GNOME system-wide shortcut so Yaz works from any app."""
            options = {
                "Ctrl+Shift+Print": "<Primary><Shift>Print",
                "Super+Shift+S": "<Super><Shift>s",
                "Ctrl+Alt+S": "<Primary><Alt>s",
                "Ctrl+Print": "<Primary>Print",
            }
            choice, ok = QInputDialog.getItem(
                self, "Yaz — Global shortcut",
                "Pick a system-wide shortcut that triggers Yaz from any app "
                "(including browsers).\n\n"
                "Avoid Ctrl+Shift+R (browser hard-reload).",
                list(options.keys()), 0, False,
            )
            if not ok:
                return
            binding = options[choice]
            mode_choice, ok2 = QInputDialog.getItem(
                self, "Yaz — Global shortcut action",
                "What should the shortcut do?",
                ["Capture Region", "Capture Region (3s delay)",
                 "Capture Region (5s delay)", "Capture Full Screen"], 0, False,
            )
            if not ok2:
                return
            cmd_args = {
                "Capture Region": "--capture",
                "Capture Region (3s delay)": "--capture --delay 3",
                "Capture Region (5s delay)": "--capture --delay 5",
                "Capture Full Screen": "--full",
            }[mode_choice]
            launcher = str(Path(__file__).resolve().parent / "yaz")
            command = f"{launcher} {cmd_args}"

            try:
                self._install_gnome_shortcut(binding, command)
            except Exception as ex:  # noqa: BLE001
                QMessageBox.warning(
                    self, "Yaz",
                    f"Could not register shortcut automatically:\n\n{ex}\n\n"
                    "You can set it manually in Settings → Keyboard → "
                    "Custom Shortcuts.\n"
                    f"Command: {command}"
                )
                return
            mbox = QMessageBox(self)
            mbox.setIcon(QMessageBox.Icon.Information)
            mbox.setWindowTitle("Yaz")
            mbox.setTextFormat(Qt.TextFormat.RichText)
            mbox.setText(
                "<h3 style='margin:0'>Shortcut set!</h3>"
                f"<p>Press <b>{choice}</b> from any app to trigger "
                f"<i>{mode_choice}</i>.</p>"
            )
            mbox.exec()

        def _install_gnome_shortcut(self, binding: str, command: str):
            base = "org.gnome.settings-daemon.plugins.media-keys"
            kb_id = "yaz"
            kb_path = (
                "/org/gnome/settings-daemon/plugins/media-keys/"
                f"custom-keybindings/{kb_id}/"
            )

            res = subprocess.run(
                ["gsettings", "get", base, "custom-keybindings"],
                capture_output=True, text=True, check=True,
            )
            current = res.stdout.strip()
            if current in ("@as []", "[]"):
                paths: list[str] = []
            else:
                # Existing list is "['/.../a/', '/.../b/']"
                paths = [
                    p.strip().strip("'\"")
                    for p in current.strip("[]").split(",")
                    if p.strip()
                ]
            if kb_path not in paths:
                paths.append(kb_path)
            new = "[" + ", ".join(f"'{p}'" for p in paths) + "]"
            subprocess.run(
                ["gsettings", "set", base, "custom-keybindings", new],
                check=True,
            )

            schema = f"{base}.custom-keybinding:{kb_path}"
            for key, value in (
                ("name", "Yaz"),
                ("command", command),
                ("binding", binding),
            ):
                subprocess.run(
                    ["gsettings", "set", schema, key, value],
                    check=True,
                )

        # ---- about / help ----
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
                "<p>Made in Addis Ababa &middot; MIT license</p>"
            )
            # Make the LinkedIn link clickable.
            for lbl in mbox.findChildren(qt["QLabel"]):
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
            crop = qt["QRect"](
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

            import time
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
                rect = pick_region_from(pixmap, qt)
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

    # --------------------------------------------------------- run
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


# ============================================================================
# Entry point
# ============================================================================

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

    return run_app(initial_image=initial, autostart_capture=auto,
                   autostart_delay=args.delay)


if __name__ == "__main__":
    sys.exit(main())

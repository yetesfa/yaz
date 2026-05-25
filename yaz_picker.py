"""Flameshot-style fullscreen overlay region picker.

Used as a fallback when no native OS region selector is available. Spans
all monitors via ``virtualGeometry()`` and converts the widget-coordinate
selection back to pixmap-coordinate (handles HiDPI / fractional DPR).
"""
from __future__ import annotations

from PyQt6.QtCore import QEventLoop, QPoint, QRect, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QGuiApplication, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QWidget


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


def pick_region_from(pixmap) -> QRect | None:
    """Show a fullscreen overlay; return a QRect or None if cancelled."""
    picker = Picker(pixmap)
    loop = QApplication.instance()
    # Block until the picker closes — nested .exec() corrupts the Qt event
    # loop on Wayland under some compositors.
    while picker.isVisible():
        loop.processEvents(QEventLoop.ProcessEventsFlag.WaitForMoreEvents)

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

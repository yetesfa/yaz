"""Floating circular countdown shown during a delayed capture.

Hides itself one frame before the capture fires so it doesn't appear in
the screenshot.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen
from PyQt6.QtWidgets import QWidget


class Countdown(QWidget):
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

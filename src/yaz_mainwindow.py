"""The single QMainWindow assembling every mw-mixin into one class.

Layout:
  • stack: QStackedWidget swapping Welcome ↔ Canvas
  • toolbar: drawing tools + color/width + undo/redo + delete
  • menubar: File / Edit / View / Tools / Help
  • statusbar: messages + chrome visibility

The class body here is intentionally tiny — every method comes from a
mixin in ``yaz_mw_*``. Putting ``QMainWindow`` last in the bases ensures
the mixins resolve first in MRO without shadowing any Qt method.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtGui import QActionGroup, QColor, QUndoStack
from PyQt6.QtWidgets import (
    QGraphicsScene, QMainWindow, QStackedWidget, QStatusBar,
)
from PyQt6.QtCore import QSettings

from yaz_canvas import Canvas
from yaz_mw_capture import CaptureFlowMixin
from yaz_mw_chrome import ChromeMixin
from yaz_mw_dialogs import DialogsMixin
from yaz_mw_drawing import DrawingMixin
from yaz_mw_fileio import FileIoMixin
from yaz_mw_shortcuts import ShortcutsMixin
from yaz_settings import DEFAULTS
from yaz_welcome import Welcome


class MainWindow(
    ChromeMixin,
    DrawingMixin,
    FileIoMixin,
    CaptureFlowMixin,
    ShortcutsMixin,
    DialogsMixin,
    QMainWindow,
):
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

        self.setStatusBar(QStatusBar(self))
        self.statusBar().showMessage("Ready.")

        # Visibility of toolbar/statusbar from settings.
        self._apply_chrome_visibility()

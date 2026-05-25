"""MainWindow mixin: toolbar, menu bar, and chrome visibility.

Builds every QAction the menu and toolbar share, then routes them at the
``self._set_tool`` / ``self.capture_*`` / ``self.save`` methods defined
in sibling mixins. ``apply_settings`` re-syncs the in-memory mirror after
the Preferences dialog writes new values.

Mixin only — must be combined with QMainWindow + the other mw mixins.
"""
from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QAction, QColor, QGuiApplication, QKeySequence
from PyQt6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QSpinBox, QToolBar, QToolButton, QWidget,
)

from yaz_settings import DEFAULTS, describe_screen


class ChromeMixin:
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

    def _toggle_toolbar(self, on):
        self.tool_bar.setVisible(on)
        self.qsettings.setValue("show_toolbar", on)

    def _toggle_statusbar(self, on):
        self.statusBar().setVisible(on)
        self.qsettings.setValue("show_statusbar", on)

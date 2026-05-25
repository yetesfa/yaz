"""MainWindow mixin: tools, color/stroke, edit ops, crop, blur, z-order.

Everything that mutates the annotation canvas after a tool is chosen
lives here. Each user-visible mutation goes through a QUndoCommand from
:mod:`yaz_canvas` so undo stays coherent.

Mixin only — combine with QMainWindow + the other mw mixins.
"""
from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QColorDialog, QGraphicsPixmapItem, QGraphicsTextItem, QInputDialog,
)

from yaz_canvas import AddItemCommand, CropCommand, RemoveItemsCommand


class DrawingMixin:
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

    # ---- selection / structural edits ----
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

"""Annotation canvas + custom graphics items + undo commands.

``Canvas`` is the QGraphicsView the user paints on; ``ArrowItem`` is the
only custom QGraphicsItem we need (an arrow with a filled head). The
``*Command`` classes are the four QUndoCommand subclasses pushed by the
canvas + MainWindow to keep the undo stack coherent.

Every user-visible scene mutation must go through one of these commands —
otherwise undo silently desyncs.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF, QUndoCommand,
)
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem, QGraphicsItem, QGraphicsLineItem, QGraphicsPathItem,
    QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsTextItem, QGraphicsView,
    QInputDialog, QMenu,
)


# ---------------------------------------------------------------- Arrow
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


# ----------------------------------------------------------------- Undo
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

"""Selection overlay helpers for the Qt frontend."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6 import QtCore, QtGui, QtWidgets

from core.layers import HitKind
from models.styling import Colour, Colours
from qt.scene_data import DATA_HANDLE, DATA_IDX, DATA_KIND

if TYPE_CHECKING:
    from models.geo import Point
    from qt.app import QtApp

HANDLE_R = 5
IDLE_PAD = 4
Z_OUTLINE = 80
Z_HANDLE = 90
Z_MARQUEE = 95
Z_DRAG_OUTLINE = 85


def _qcolour(col: Colour) -> QtGui.QColor:
    return QtGui.QColor(col.red, col.green, col.blue, col.alpha)


def _outline_pen() -> QtGui.QPen:
    pen = QtGui.QPen(_qcolour(Colours.sys.sky))
    pen.setWidth(2)
    pen.setStyle(QtCore.Qt.PenStyle.DashLine)
    return pen


def _marquee_pen() -> QtGui.QPen:
    pen = QtGui.QPen(_qcolour(Colours.sys.ocean))
    pen.setWidth(2)
    pen.setStyle(QtCore.Qt.PenStyle.DashLine)
    return pen


def _handle_pen() -> QtGui.QPen:
    pen = QtGui.QPen(_qcolour(Colours.sys.ocean))
    pen.setWidth(2)
    return pen


def _handle_brush() -> QtGui.QBrush:
    return QtGui.QBrush(_qcolour(Colours.white))


def _clear_brush() -> QtGui.QBrush:
    return QtGui.QBrush(QtCore.Qt.BrushStyle.NoBrush)


@dataclass(slots=True)
class _Handles:
    a: QtWidgets.QGraphicsEllipseItem | None = None
    b: QtWidgets.QGraphicsEllipseItem | None = None


class QtSelectionOverlay:
    """Selection overlay drawing and state."""

    def __init__(self, app: QtApp) -> None:
        """Create a selection overlay manager.

        Args;
            app: The parent Qt app.
        """
        self.app = app
        self.scene = app.scene
        self._outlines: list[QtWidgets.QGraphicsRectItem] = []
        self._drag_outline: QtWidgets.QGraphicsRectItem | None = None
        self._handles = _Handles()
        self._marquee: QtWidgets.QGraphicsRectItem | None = None

    def refresh(self) -> None:
        """Rebuild overlays from the current selection."""
        primary = (
            (self.app.selection_kind, self.app.selection_index)
            if self.app.selection_kind and self.app.selection_index is not None
            else None
        )
        self.show_many(self.app.multi_sel, primary=primary)

    # ---------- selection ----------
    def show(self, kind: HitKind, idx: int) -> None:
        """Show selection for a single item.

        Args;
            kind: The hit kind.
            idx: The item index.
        """
        self.show_many([(kind, idx)], primary=(kind, idx))

    def show_many(self, items: list[tuple[HitKind, int]], primary: tuple[HitKind, int] | None = None) -> None:
        """Show selection for multiple items.

        Args;
            items: The items to highlight.
            primary: Optional primary selection.
        """
        self.clear(keep_marquee=True)

        if not items:
            return

        for kind, idx in items:
            rect = self._bbox_for_hit(kind, idx)
            if rect is None:
                continue
            if kind in (HitKind.icon, HitKind.label):
                rect = rect.adjusted(-IDLE_PAD, -IDLE_PAD, IDLE_PAD, IDLE_PAD)
            outline = QtWidgets.QGraphicsRectItem(rect)
            outline.setPen(_outline_pen())
            outline.setBrush(_clear_brush())
            outline.setZValue(Z_OUTLINE)
            outline.setAcceptedMouseButtons(QtCore.Qt.MouseButton.NoButton)
            self.scene.addItem(outline)
            self._outlines.append(outline)

        if primary and primary[0] == HitKind.line:
            idx = primary[1]
            a, b = self._line_endpoints(idx)
            if a and b:
                ax, ay = self._coords(a)
                bx, by = self._coords(b)
                self._handles.a = self._create_handle(ax, ay, which="a", idx=idx)
                self._handles.b = self._create_handle(bx, by, which="b", idx=idx)

    def clear(self, keep_marquee: bool = False) -> None:
        """Clear selection overlays.

        Args;
            keep_marquee: Whether to preserve the marquee overlay.
        """
        for outline in self._outlines:
            self._safe_remove(outline)
        self._outlines.clear()

        if self._drag_outline is not None:
            self._safe_remove(self._drag_outline)
            self._drag_outline = None

        for handle in (self._handles.a, self._handles.b):
            if handle is not None:
                self._safe_remove(handle)
        self._handles = _Handles()

        if not keep_marquee:
            self.clear_marquee()

    def set_outline_bbox(self, x1: float, y1: float, x2: float, y2: float) -> None:
        """Set the drag outline to a bounding box.

        Args;
            x1: First x coordinate.
            y1: First y coordinate.
            x2: Second x coordinate.
            y2: Second y coordinate.
        """
        rect = QtCore.QRectF(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
        if self._drag_outline is None:
            item = QtWidgets.QGraphicsRectItem(rect)
            item.setPen(_outline_pen())
            item.setBrush(_clear_brush())
            item.setZValue(Z_DRAG_OUTLINE)
            item.setAcceptedMouseButtons(QtCore.Qt.MouseButton.NoButton)
            self.scene.addItem(item)
            self._drag_outline = item
        else:
            try:
                self._drag_outline.setRect(rect)
            except RuntimeError:
                self._drag_outline = None
                self.set_outline_bbox(x1, y1, x2, y2)
                return

    def update_line_handles(self, idx: int, a: QtCore.QPointF | Point, b: QtCore.QPointF | Point) -> None:
        """Update line handle positions.

        Args;
            idx: The line index.
            a: The first endpoint.
            b: The second endpoint.
        """
        ax, ay = self._coords(a)
        bx, by = self._coords(b)
        if self._handles.a is not None:
            self._move_handle(self._handles.a, ax, ay)
        if self._handles.b is not None:
            self._move_handle(self._handles.b, bx, by)

    # ---------- marquee ----------
    def show_marquee(self, a: QtCore.QPointF) -> None:
        """Show a marquee selection.

        Args;
            a: The marquee origin.
        """
        self.clear_marquee()
        rect = QtCore.QRectF(a, a)
        item = QtWidgets.QGraphicsRectItem(rect)
        item.setPen(_marquee_pen())
        item.setBrush(_clear_brush())
        item.setZValue(Z_MARQUEE)
        item.setAcceptedMouseButtons(QtCore.Qt.MouseButton.NoButton)
        self.scene.addItem(item)
        self._marquee = item

    def update_marquee(self, a: QtCore.QPointF, b: QtCore.QPointF) -> None:
        """Update marquee selection bounds.

        Args;
            a: The marquee origin.
            b: The marquee end point.
        """
        if self._marquee is None:
            self.show_marquee(a)
        rect = QtCore.QRectF(min(a.x(), b.x()), min(a.y(), b.y()), abs(a.x() - b.x()), abs(a.y() - b.y()))
        if self._marquee is not None:
            self._marquee.setRect(rect)

    def clear_marquee(self) -> None:
        """Clear marquee selection."""
        if self._marquee is not None:
            self._safe_remove(self._marquee)
            self._marquee = None

    # ---------- internals ----------
    def _bbox_for_hit(self, kind: HitKind, idx: int) -> QtCore.QRectF | None:
        items = self.app.renderer.items_for_hit(kind, idx)
        if not items:
            return None
        rect: QtCore.QRectF | None = None
        for item in items:
            ib = item.sceneBoundingRect()
            rect = ib if rect is None else rect.united(ib)
        return rect

    def _line_endpoints(self, idx: int) -> tuple[QtCore.QPointF | None, QtCore.QPointF | None]:
        if idx < 0 or idx >= len(self.app.params.lines):
            return (None, None)
        ln = self.app.params.lines[idx]
        return (QtCore.QPointF(ln.a.x, ln.a.y), QtCore.QPointF(ln.b.x, ln.b.y))

    def _create_handle(self, x: float, y: float, *, which: str, idx: int) -> QtWidgets.QGraphicsEllipseItem:
        item = QtWidgets.QGraphicsEllipseItem(x - HANDLE_R, y - HANDLE_R, HANDLE_R * 2, HANDLE_R * 2)
        item.setBrush(_handle_brush())
        item.setPen(_handle_pen())
        item.setZValue(Z_HANDLE)
        item.setData(DATA_KIND, HitKind.line.value)
        item.setData(DATA_IDX, idx)
        item.setData(DATA_HANDLE, which)
        self.scene.addItem(item)
        return item

    @staticmethod
    def _move_handle(item: QtWidgets.QGraphicsEllipseItem, x: float, y: float) -> None:
        item.setRect(x - HANDLE_R, y - HANDLE_R, HANDLE_R * 2, HANDLE_R * 2)

    @staticmethod
    def _coords(p: QtCore.QPointF | Point) -> tuple[float, float]:
        if isinstance(p, QtCore.QPointF):
            return float(p.x()), float(p.y())
        return float(p.x), float(p.y)

    def _safe_remove(self, item: QtWidgets.QGraphicsItem) -> None:
        try:
            self.scene.removeItem(item)
        except RuntimeError:
            return

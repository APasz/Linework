"""Draw tool behaviour for the Qt frontend."""

from __future__ import annotations

from math import atan2, pi
from typing import TYPE_CHECKING

from PySide6 import QtCore, QtGui, QtWidgets

from core.commands import AddLine
from models.geo import Line, Point
from models.styling import CapStyle, scaled_pattern
from qt.input import MotionEvent
from qt.tools.base import ToolBase, ToolName

if TYPE_CHECKING:
    from qt.app import QtApp

Z_PREVIEW = 60


def _pen_for_line(line: Line) -> QtGui.QPen:
    """Build a Qt pen for a line preview.

    Args;
        line: The line to render.

    Returns;
        The configured pen.
    """
    col = line.col
    pen = QtGui.QPen(QtGui.QColor(col.red, col.green, col.blue, col.alpha))
    pen.setWidth(max(1, int(line.width)))
    pen.setCapStyle(
        {
            CapStyle.ROUND: QtCore.Qt.PenCapStyle.RoundCap,
            CapStyle.BUTT: QtCore.Qt.PenCapStyle.FlatCap,
            CapStyle.PROJECTING: QtCore.Qt.PenCapStyle.SquareCap,
        }[line.capstyle]
    )
    dash = scaled_pattern(line.style, line.width)
    if dash:
        pen.setDashPattern([float(d) for d in dash])
        pen.setDashOffset(float(line.dash_offset))
    return pen


class DrawTool(ToolBase):
    """Tool for drawing lines."""

    name: ToolName = ToolName.draw
    cursor = QtCore.Qt.CursorShape.CrossCursor
    tool_hints: str = "Ctrl: Invert Cardinal  |  Shift: Editor  |  Alt: Invert Grid Snap"

    def __init__(self) -> None:
        """Create the draw tool state."""
        self._start: Point | None = None
        self._preview_item: QtWidgets.QGraphicsLineItem | None = None
        self._dragging = False

    def on_deactivate(self, app: QtApp) -> None:
        """Handle tool deactivation.

        Args;
            app: The parent Qt app.
        """
        super().on_deactivate(app)
        self._start = None
        self._preview_item = None
        self._dragging = False

    def on_press(self, app: QtApp, evt: MotionEvent) -> None:
        """Handle press events for drawing.

        Args;
            app: The parent Qt app.
            evt: The motion event.
        """
        mods = evt.mods
        p0 = app.snap(Point(x=evt.x, y=evt.y), ignore_grid=mods.alt)

        if not bool(app.params.drag_to_draw):
            self._dragging = False
            if self._start is None:
                self._start = p0
                return
            p = app.snap(Point(x=evt.x, y=evt.y), ignore_grid=mods.alt)
            b = self._maybe_cardinal(app, self._start, p, mods.ctrl)
            app.clear_preview()
            self._preview_item = None
            if (self._start.x, self._start.y) == (b.x, b.y):
                self._start = None
                return
            snap = not mods.alt
            line = Line(
                a=self._start,
                b=b,
                col=app.params.brush_colour,
                width=app.params.brush_width,
                capstyle=CapStyle.ROUND,
                style=app.params.line_style,
                dash_offset=app.params.line_dash_offset,
                snap=snap,
            )
            added = False
            if not mods.shift or app.editors.edit(app, line):
                app.cmd.push_and_do(AddLine(app.params, line, on_after=app.redraw))
                app.mark_dirty()
                added = True
            if added and app.params.continuous_draw:
                self._start = b
            else:
                self._start = None
            return

        self._dragging = True
        if self._start is None or not app.params.continuous_draw:
            self._start = p0

    def on_motion(self, app: QtApp, evt: MotionEvent) -> None:
        """Handle motion events for drawing.

        Args;
            app: The parent Qt app.
            evt: The motion event.
        """
        if not self._start:
            return
        if app.params.drag_to_draw and not (self._dragging or app.params.continuous_draw):
            return
        mods = evt.mods
        p = app.snap(Point(x=evt.x, y=evt.y), ignore_grid=mods.alt)
        b = self._maybe_cardinal(app, self._start, p, mods.ctrl)
        self._preview_line(app, self._start, b)

    def on_release(self, app: QtApp, evt: MotionEvent) -> None:
        """Handle release events for drawing.

        Args;
            app: The parent Qt app.
            evt: The motion event.
        """
        if not bool(app.params.drag_to_draw):
            return
        self._dragging = False
        if not self._start:
            return
        mods = evt.mods
        p = app.snap(Point(x=evt.x, y=evt.y), ignore_grid=mods.alt)
        b = self._maybe_cardinal(app, self._start, p, mods.ctrl)
        app.clear_preview()
        self._preview_item = None

        added = False
        if self.moved_enough(self._start, b):
            snap = not mods.alt
            line = Line(
                a=self._start,
                b=b,
                col=app.params.brush_colour,
                width=app.params.brush_width,
                capstyle=CapStyle.ROUND,
                style=app.params.line_style,
                dash_offset=app.params.line_dash_offset,
                snap=snap,
            )
            if not mods.shift or app.editors.edit(app, line):
                app.cmd.push_and_do(AddLine(app.params, line, on_after=app.redraw))
                app.mark_dirty()
                added = True

        if added and app.params.continuous_draw:
            self._start = b
        else:
            self._start = None

    def on_cancel(self, app: QtApp) -> None:
        """Handle tool cancellation.

        Args;
            app: The parent Qt app.
        """
        app.clear_preview()
        self._start = None
        self._preview_item = None
        self._dragging = False

    def _preview_line(self, app: QtApp, a: Point, b: Point) -> None:
        """Create or update the preview line item.

        Args;
            app: The parent Qt app.
            a: The start point.
            b: The end point.
        """
        line = Line(
            a=a,
            b=b,
            col=app.params.brush_colour,
            width=app.params.brush_width,
            capstyle=CapStyle.ROUND,
            style=app.params.line_style,
            dash_offset=app.params.line_dash_offset,
        )
        if self._preview_item is None:
            item = QtWidgets.QGraphicsLineItem(a.x, a.y, b.x, b.y)
            item.setPen(_pen_for_line(line))
            item.setZValue(Z_PREVIEW)
            app.add_preview_item(item)
            self._preview_item = item
        else:
            self._preview_item.setLine(a.x, a.y, b.x, b.y)
            self._preview_item.setPen(_pen_for_line(line))

    @staticmethod
    def _maybe_cardinal(app: QtApp, a: Point, b: Point, invert: bool) -> Point:
        """Snap a line endpoint to the nearest cardinal/diagonal.

        Args;
            app: The parent Qt app.
            a: The line start point.
            b: The raw end point.
            invert: Whether to invert the cardinal snap flag.

        Returns;
            The adjusted end point.
        """
        use_cardinal = bool(app.params.cardinal_snap) ^ bool(invert)
        if not use_cardinal:
            return b
        dx, dy = (b.x - a.x), (b.y - a.y)
        if dx == 0 and dy == 0:
            return b
        ang = atan2(dy, dx)
        step = pi / 4.0
        k = int(round(ang / step)) % 8

        if k in (0, 4):
            return Point(x=b.x, y=a.y)
        if k in (2, 6):
            return Point(x=a.x, y=b.y)

        sgnx = 1 if dx >= 0 else -1
        sgny = 1 if dy >= 0 else -1
        m = min(abs(dx), abs(dy))
        sx = a.x + sgnx * m
        sy = a.y + sgny * m
        sx = 0 if sx < 0 else min(sx, app.params.width)
        sy = 0 if sy < 0 else min(sy, app.params.height)
        return Point(x=sx, y=sy)

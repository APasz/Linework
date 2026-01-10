"""Eraser tool that splits lines at the cursor location."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6 import QtCore

from core.commands import SplitLine
from core.layers import HitKind
from models.geo import Line, Point
from qt.hit_test import hit_test
from qt.input import MotionEvent
from qt.tools.base import ToolBase, ToolName

if TYPE_CHECKING:
    from qt.app import QtApp


SPLIT_TOLERANCE = 1e-4


class EraserTool(ToolBase):
    """Tool that erases by splitting lines where the cursor hits."""

    name: ToolName = ToolName.erase
    cursor = QtCore.Qt.CursorShape.PointingHandCursor
    tool_hints = "Drag to split lines"

    def __init__(self) -> None:
        self._dragging = False
        self._last_split: tuple[int, Point] | None = None

    def on_press(self, app: "QtApp", evt: MotionEvent) -> None:
        """Handle press events by attempting a split.

        Args;
            app: The parent Qt app.
            evt: The motion event.
        """
        self._dragging = True
        self._maybe_split(app, evt)

    def on_motion(self, app: "QtApp", evt: MotionEvent) -> None:
        """Handle drag motions while erasing.

        Args;
            app: The parent Qt app.
            evt: The motion event.
        """
        if not self._dragging:
            return
        self._maybe_split(app, evt)

    def on_release(self, app: "QtApp", evt: MotionEvent) -> None:
        """End an erase drag.

        Args;
            app: The parent Qt app.
            evt: The motion event.
        """
        self._dragging = False
        self._last_split = None

    def on_cancel(self, app: "QtApp") -> None:
        """Cancel the current erase gesture.

        Args;
            app: The parent Qt app.
        """
        self._dragging = False
        self._last_split = None

    def _maybe_split(self, app: "QtApp", evt: MotionEvent) -> None:
        """Attempt to split the line under the cursor.

        Args;
            app: The parent Qt app.
            evt: The motion event.
        """
        hit = hit_test(app.scene, evt.x, evt.y, radius=6)
        if hit is None or hit.kind is not HitKind.line or hit.tag_idx is None:
            return
        idx = hit.tag_idx
        if not (0 <= idx < len(app.params.lines)):
            return
        line = app.params.lines[idx]
        point, t = _project_on_segment(line, Point(x=evt.x, y=evt.y))
        if t <= SPLIT_TOLERANCE or t >= 1.0 - SPLIT_TOLERANCE:
            return
        if self._last_split and self._last_split[0] == idx:
            last = self._last_split[1]
            if abs(last.x - point.x) <= 1 and abs(last.y - point.y) <= 1:
                return

        first_end, second_start = _gap_points_along(line, t, app.params.grid_size, snap=line.snap)
        if first_end is None or second_start is None:
            first_end, second_start = point, point

        cmd = SplitLine(
            app.params,
            idx,
            point,
            on_after=app.redraw,
            first_end=first_end,
            second_start=second_start,
        )
        # Manually execute so we can skip stacking/toast when no split occurs.
        cmd.do()
        if not getattr(cmd, "executed", False):
            return
        app.cmd.push_done(cmd)
        app.select_set([(HitKind.line, idx), (HitKind.line, idx + 1)])
        app.mark_dirty()
        if hasattr(app, "status"):
            app.status.temp(f"Split line {idx} at ({point.x},{point.y})", 1200)
        self._last_split = (idx, point)


def _project_on_segment(line: Line, target: Point) -> tuple[Point, float]:
    """Return the nearest point and parameter along the line segment."""

    ax, ay = line.a.x, line.a.y
    bx, by = line.b.x, line.b.y
    dx = bx - ax
    dy = by - ay
    if dx == 0 and dy == 0:
        return Point(x=ax, y=ay), 0.0
    px, py = target.x, target.y
    length_sq = dx * dx + dy * dy
    t = ((px - ax) * dx + (py - ay) * dy) / float(length_sq)
    t_clamped = max(0.0, min(1.0, t))
    proj_x = ax + t_clamped * dx
    proj_y = ay + t_clamped * dy
    return Point(x=int(round(proj_x)), y=int(round(proj_y))), t_clamped


def _offset_point(line: Line, dist: float) -> Point:
    """Return a point dist units from line.a along the segment."""
    ux, uy, length = line.unit()
    if length <= 0:
        return line.a
    px = line.a.x + ux * dist
    py = line.a.y + uy * dist
    return Point(x=int(round(px)), y=int(round(py)))


def _gap_points_along(line: Line, t: float, grid_size: int, *, snap: bool) -> tuple[Point | None, Point | None]:
    """Return endpoints for two segments separated by a small gap around t."""
    ux, uy, length = line.unit()
    if length <= 0:
        return (None, None)

    grid = max(1, int(grid_size)) if grid_size is not None else 1
    half_gap = grid / 2.0

    centre_dist = t * length
    before = centre_dist - half_gap
    after = centre_dist + half_gap

    if snap and grid > 0:
        before = round(before / grid) * grid
        after = round(after / grid) * grid

    before = max(0.0, before)
    after = min(length, after)

    # ensure the gap stays inside the segment
    if after - before < 1.0:
        return (None, None)
    if before <= 0.0 or after >= length:
        return (None, None)

    return _offset_point(line, before), _offset_point(line, after)

"""Selection tool behaviour."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from typing import TYPE_CHECKING

from canvas.layers import Hit_Kind, Layer_Type, test_hit
from controllers.commands import Move_Line, Move_Line_End
from controllers.tools.draw import Draw_Tool
from controllers.tools_base import DragAction, DragGroup, DragIcon, DragLabel, DragMarquee, ToolBase
from models.geo import Point
from models.styling import TkCursor
from ui.bars import Tool_Name
from ui.input import MotionEvent, get_mods

if TYPE_CHECKING:
    from controllers.app import App


@dataclass
class DragLineEndpoint(DragAction):
    """Drag action for line endpoints."""

    idx: int
    which: str
    start_other: Point
    start: Point

    def update(self, app: App, evt: MotionEvent | tk.Event) -> None:
        mods = get_mods(evt)
        p = app.snap(Point(x=evt.x, y=evt.y), ignore_grid=mods.alt)
        q = Draw_Tool._maybe_cardinal(app, self.start_other, p, invert=mods.ctrl)
        a, b = (q, self.start_other) if self.which == "a" else (self.start_other, q)

        app.layers.clear_preview()
        lin = app.params.lines[self.idx]
        app.canvas.create_with_line(
            lin.with_points(a, b),
            tag_type=Layer_Type.preview,
        )

        app.selection.update_line_handles(self.idx, a, b)

        bb = app.canvas.bbox(Layer_Type.preview.value)
        if bb:
            x1, y1, x2, y2 = bb
            app.selection.set_outline_bbox(x1, y1, x2, y2)

    def commit(self, app: App, evt: MotionEvent | tk.Event) -> None:
        app.layers.clear_preview()
        mods = get_mods(evt)
        p = app.snap(Point(x=evt.x, y=evt.y), ignore_grid=mods.alt)
        p = Draw_Tool._maybe_cardinal(app, self.start_other, p, invert=mods.ctrl)

        app.cmd.push_and_do(
            Move_Line_End(
                app.params,
                self.idx,
                "a" if self.which == "a" else "b",
                old_point=self.start,
                new_point=p,
                on_after=lambda: app.layers.redraw(Layer_Type.lines),
            )
        )
        app.selection.update_bbox()
        app._set_selected(Hit_Kind.line, self.idx)
        app.mark_dirty()

    def cancel(self, app: App) -> None:
        app.layers.clear_preview()
        app.selection.update_bbox()


@dataclass
class DragLine(DragAction):
    """Drag action for moving lines."""

    idx: int
    start_mouse: Point
    start_a: Point
    start_b: Point

    def _delta(self, app: App, evt: MotionEvent | tk.Event) -> tuple[int, int, bool]:
        mods = get_mods(evt)
        cur = app.snap(Point(x=evt.x, y=evt.y), ignore_grid=mods.alt)
        start = app.snap(self.start_mouse, ignore_grid=mods.alt)
        return cur.x - start.x, cur.y - start.y, mods.alt

    def _points(self, app: App, evt: MotionEvent | tk.Event) -> tuple[Point, Point]:
        dx, dy, alt = self._delta(app, evt)
        a = app.snap(Point(x=self.start_a.x + dx, y=self.start_a.y + dy), ignore_grid=alt)
        b = app.snap(Point(x=self.start_b.x + dx, y=self.start_b.y + dy), ignore_grid=alt)
        return a, b

    def update(self, app: App, evt: MotionEvent | tk.Event) -> None:
        a, b = self._points(app, evt)
        ln = app.params.lines[self.idx]

        app.layers.clear_preview()
        app.canvas.create_with_line(
            ln.with_points(a, b),
            tag_type=Layer_Type.preview,
        )

        app.selection.update_line_handles(self.idx, a, b)

        bb = app.canvas.bbox(Layer_Type.preview.value)
        if bb:
            x1, y1, x2, y2 = bb
            app.selection.set_outline_bbox(x1, y1, x2, y2)

    def commit(self, app: App, evt: MotionEvent | tk.Event) -> None:
        a, b = self._points(app, evt)
        app.layers.clear_preview()
        app.cmd.push_and_do(
            Move_Line(
                app.params,
                self.idx,
                old_a=self.start_a,
                old_b=self.start_b,
                new_a=a,
                new_b=b,
                on_after=lambda: app.layers.redraw(Layer_Type.lines),
            )
        )
        app.selection.update_bbox()
        app._set_selected(Hit_Kind.line, self.idx)
        app.mark_dirty()

    def cancel(self, app: App) -> None:
        app.layers.clear_preview()
        app.selection.update_bbox()


class Select_Tool(ToolBase):
    """Tool for selection and dragging."""

    name: Tool_Name = Tool_Name.select
    kind: Hit_Kind | None = None
    cursor: TkCursor = TkCursor.ARROW
    tool_hints: str = "Ctrl: Toggle / Add-Marquee  |  Alt: Ignore Grid"

    def __init__(self) -> None:
        """Initialise the selection tool."""
        super().__init__()
        self._drag: DragAction | None = None

    def on_press(self, app: App, evt: MotionEvent | tk.Event) -> None:
        """Handle press events for selection and dragging.

        Args;
            app: The application instance.
            evt: The event.
        """
        mods = get_mods(evt)
        hit = test_hit(app.canvas, evt.x, evt.y)

        if not hit:
            if not mods.ctrl:
                app.select_clear()
            self._drag = DragMarquee(a=app.snap(Point(x=evt.x, y=evt.y)), add=mods.ctrl)
            app.selection.show_marquee(self._drag.a)
            return

        if hit.kind == Hit_Kind.line and hit.point and (hit.tag_idx is not None):
            ln = app.params.lines[hit.tag_idx]
            other = ln.b if hit.point == "a" else ln.a
            start = ln.a if hit.point == "a" else ln.b
            self._drag = DragLineEndpoint(idx=hit.tag_idx, which=hit.point, start_other=other, start=start)
            return

        if mods.ctrl and hit.tag_idx is not None:
            if app.is_selected(hit.kind, hit.tag_idx):
                app.select_remove(hit.kind, hit.tag_idx)
            else:
                app.select_add(hit.kind, hit.tag_idx, make_primary=False)
            return

        if hit.tag_idx is not None and app.is_selected(hit.kind, hit.tag_idx) and len(app.multi_sel) > 1:
            labels = [(i, app.params.labels[i].p) for k, i in app.multi_sel if k == Hit_Kind.label]
            icons = [(i, app.params.icons[i].p) for k, i in app.multi_sel if k == Hit_Kind.icon]
            lines = [(i, app.params.lines[i].a, app.params.lines[i].b) for k, i in app.multi_sel if k == Hit_Kind.line]
            self._drag = DragGroup(
                items=list(app.multi_sel), start_mouse=Point(x=evt.x, y=evt.y), labels=labels, icons=icons, lines=lines
            )
            return

        app.select_set([(hit.kind, hit.tag_idx if hit.tag_idx is not None else -1)])

        if hit.kind == Hit_Kind.line and hit.tag_idx is not None:
            ln = app.params.lines[hit.tag_idx]
            self._drag = DragLine(
                idx=hit.tag_idx,
                start_mouse=Point(x=evt.x, y=evt.y),
                start_a=ln.a,
                start_b=ln.b,
            )
            return

        if hit.kind == Hit_Kind.label and hit.tag_idx is not None:
            lb = app.params.labels[hit.tag_idx]
            self._drag = DragLabel(idx=hit.tag_idx, start=lb.p, offset_dx=evt.x - lb.p.x, offset_dy=evt.y - lb.p.y)
            return

        if hit.kind == Hit_Kind.icon and hit.tag_idx is not None:
            ic = app.params.icons[hit.tag_idx]
            self._drag = DragIcon(idx=hit.tag_idx, start=ic.p, offset_dx=evt.x - ic.p.x, offset_dy=evt.y - ic.p.y)
            return

        self._drag = None

    def on_motion(self, app: App, evt: MotionEvent | tk.Event) -> None:
        """Handle motion events for selection drags.

        Args;
            app: The application instance.
            evt: The event.
        """
        if self._drag:
            self._drag.update(app, evt)

    def on_release(self, app: App, evt: MotionEvent | tk.Event) -> None:
        """Handle release events for selection drags.

        Args;
            app: The application instance.
            evt: The event.
        """
        if self._drag:
            self._drag.commit(app, evt)
            self._drag = None

    def on_cancel(self, app: App) -> None:
        """Cancel any active selection drag.

        Args;
            app: The application instance.
        """
        if self._drag:
            self._drag.cancel(app)
            self._drag = None

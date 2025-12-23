from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING

from canvas.layers import Hit_Kind, Layer_Type
from controllers.commands import Add_Line
from controllers.tools_base import ToolBase
from models.geo import Line, Point
from models.styling import CapStyle, TkCursor, use_manual_tk_dash
from ui.bars import Tool_Name
from ui.input import MotionEvent, get_mods

if TYPE_CHECKING:
    from controllers.app import App


class Draw_Tool(ToolBase):
    name: Tool_Name = Tool_Name.draw
    kind: Hit_Kind | None = Hit_Kind.line
    cursor: TkCursor = TkCursor.CROSSHAIR
    tool_hints: str = "Ctrl: Invert Cardinal  |  Shift: Editor  |  Alt: Ignore Grid"

    def preview_line(self, app: App, a: Point, b: Point, **opts) -> int:
        if use_manual_tk_dash(opts.get("style")):
            self.clear_preview(app)
            app.canvas.create_with_points(
                a,
                b,
                **opts,
                tag_type=Layer_Type.preview,
            )
            return 0
        if self._preview_ids:
            app.canvas.coords(self._preview_ids[0], a.x, a.y, b.x, b.y)
        else:
            lid = app.canvas.create_with_points(
                a,
                b,
                **opts,
                tag_type=Layer_Type.preview,
            )
            self._preview_ids.append(lid)
        return self._preview_ids[0]

    def on_deactivate(self, app: App):
        super().on_deactivate(app)
        self._start = None

    def on_press(self, app: App, evt: MotionEvent | tk.Event):
        mods = get_mods(evt)
        p0 = app.snap(Point(x=evt.x, y=evt.y), ignore_grid=get_mods(evt).alt)

        # Click-click mode
        if not bool(app.var_drag_to_draw.get()):
            if self._start is None:
                self._start = p0
            else:
                p = app.snap(Point(x=evt.x, y=evt.y), ignore_grid=mods.alt)
                b = self._maybe_cardinal(app, self._start, p, mods.ctrl)
                self.clear_preview(app)
                if (self._start.x, self._start.y) == (b.x, b.y):
                    self._start = None
                    return
                line = Line(
                    a=self._start,
                    b=b,
                    col=app.params.brush_colour,
                    width=app.params.brush_width,
                    capstyle=CapStyle.ROUND,
                    style=app.params.line_style,
                    dash_offset=app.params.line_dash_offset,
                )
                if not mods.shift or app.editors.edit(app, line):
                    app.cmd.push_and_do(
                        Add_Line(app.params, line, on_after=lambda: app.layers.redraw(Layer_Type.lines))
                    )
                    app.mark_dirty()
                self._start = None
            return

        self._start = p0

    def on_motion(self, app: App, evt: MotionEvent | tk.Event):
        if not self._start:
            return
        mods = get_mods(evt)
        p = app.snap(Point(x=evt.x, y=evt.y), ignore_grid=mods.alt)
        b = self._maybe_cardinal(app, self._start, p, mods.ctrl)

        self.preview_line(
            app,
            self._start,
            b,
            col=app.params.brush_colour,
            width=app.params.brush_width,
            style=app.params.line_style,
            capstyle=CapStyle.ROUND,
            dash_offset=app.params.line_dash_offset,
        )

    def on_release(self, app: App, evt: MotionEvent | tk.Event):
        if not bool(app.var_drag_to_draw.get()):
            return

        if not self._start:
            return
        mods = get_mods(evt)
        p = app.snap(Point(x=evt.x, y=evt.y), ignore_grid=mods.alt)
        b = self._maybe_cardinal(app, self._start, p, mods.ctrl)
        self.clear_preview(app)

        if self.moved_enough(self._start, b):
            line = Line(
                a=self._start,
                b=b,
                col=app.params.brush_colour,
                width=app.params.brush_width,
                capstyle=CapStyle.ROUND,
                style=app.params.line_style,
                dash_offset=app.params.line_dash_offset,
            )
            if not mods.shift or app.editors.edit(app, line):
                app.cmd.push_and_do(Add_Line(app.params, line, on_after=lambda: app.layers.redraw(Layer_Type.lines)))
                app.mark_dirty()

        self._start = None

    def on_cancel(self, app: App):
        self.clear_preview(app)
        self._start = None

    # ---- helpers ----

    @staticmethod
    def _maybe_cardinal(app: App, a: Point, b: Point, invert: bool) -> Point:
        use_cardinal = bool(app.var_cardinal.get()) ^ bool(invert)
        if not use_cardinal:
            return b
        dx, dy = (b.x - a.x), (b.y - a.y)
        if dx == 0 and dy == 0:
            return b
        from math import atan2, pi

        # nearest of 8 directions (multiples of 45°)
        ang = atan2(dy, dx)
        step = pi / 4.0
        k = int(round(ang / step)) % 8  # 0..7

        # axis: lock one coord
        if k in (0, 4):  # E / W
            return Point(x=b.x, y=a.y)
        if k in (2, 6):  # N / S
            return Point(x=a.x, y=b.y)

        # diagonals: equal |dx|=|dy|, keep on-grid
        sgnx = 1 if dx >= 0 else -1
        sgny = 1 if dy >= 0 else -1
        m = min(abs(dx), abs(dy))
        sx = a.x + sgnx * m
        sy = a.y + sgny * m
        # clamp
        sx = 0 if sx < 0 else min(sx, app.params.width)
        sy = 0 if sy < 0 else min(sy, app.params.height)
        return Point(x=sx, y=sy)

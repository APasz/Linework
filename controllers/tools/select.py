from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from typing import TYPE_CHECKING

from canvas.layers import Hit_Kind, Layer_Name, test_hit
from controllers.commands import Move_Line_End
from controllers.tools_base import DragAction, DragIcon, DragLabel, DragMarquee, ToolBase
from controllers.tools.draw import Draw_Tool
from models.geo import Point
from models.styling import TkCursor
from ui.bars import Tool_Name
from ui.input import get_mods

if TYPE_CHECKING:
    from controllers.app import App


@dataclass
class DragLineEndpoint(DragAction):
    idx: int
    which: str  # "a" or "b"
    start_other: Point
    start: Point

    def update(self, app, evt: tk.Event) -> None:
        mods = get_mods(evt)
        p = app.snap(Point(x=evt.x, y=evt.y), ignore_grid=mods.alt)
        q = Draw_Tool._maybe_cardinal(app, self.start_other, p, shift=mods.shift)
        a, b = (q, self.start_other) if self.which == "a" else (self.start_other, q)

        app.layers.clear_preview()
        lin = app.params.lines[self.idx]
        app.canvas.create_with_line(
            lin.with_points(a, b),
            override_base_tags=[Layer_Name.preview],
        )

        app.selection.update_line_handles(self.idx, a, b)

        if app.selection.ids.outline and app.canvas.type(app.selection.ids.outline):
            x1, y1 = min(a.x, b.x), min(a.y, b.y)
            x2, y2 = max(a.x, b.x), max(a.y, b.y)
            app.canvas.coords(app.selection.ids.outline, x1, y1, x2, y2)

    def commit(self, app, evt: tk.Event) -> None:
        app.layers.clear_preview()
        mods = get_mods(evt)
        p = app.snap(Point(x=evt.x, y=evt.y), ignore_grid=mods.alt)
        p = Draw_Tool._maybe_cardinal(app, self.start_other, p, shift=mods.shift)

        app.cmd.push_and_do(
            Move_Line_End(
                app.params,
                self.idx,
                "a" if self.which == "a" else "b",
                old_point=self.start,
                new_point=p,
                on_after=lambda: app.layers.redraw(Layer_Name.lines),
            )
        )
        app.selection.update_bbox()
        app.mark_dirty()

    def cancel(self, app) -> None:
        app.layers.clear_preview()
        app.selection.update_bbox()


class Select_Tool(ToolBase):
    name: Tool_Name = Tool_Name.select
    kind: Hit_Kind = Hit_Kind.miss
    cursor: TkCursor = TkCursor.ARROW
    tool_hints: str = "Shift: Editor  |  Alt: Ignore Grid"

    def __init__(self) -> None:
        super().__init__()
        self._drag: DragAction | None = None

    def on_activate(self, app: App) -> None:
        pass

    def on_press(self, app, evt: tk.Event) -> None:
        hit = test_hit(app.canvas, int(evt.x), int(evt.y))
        if not hit:
            app._set_selected(Hit_Kind.miss, None)
            self._drag = DragMarquee(a=app.snap(Point(x=evt.x, y=evt.y)))
            app.selection.show_marquee(self._drag.a)
            return

        app._set_selected(hit.kind, hit.tag_idx)

        if hit.kind == Hit_Kind.line and hit.endpoint:
            ln = app.params.lines[hit.tag_idx]
            other = ln.b if hit.endpoint == "a" else ln.a
            start = ln.a if hit.endpoint == "a" else ln.b
            self._drag = DragLineEndpoint(
                idx=hit.tag_idx if hit.tag_idx is not None else -1,
                which=hit.endpoint,
                start_other=other,
                start=start,
            )
            return

        if hit.kind == Hit_Kind.label and hit.tag_idx is not None:
            lb = app.params.labels[hit.tag_idx]
            self._drag = DragLabel(
                idx=hit.tag_idx,
                start=lb.p,
                offset_dx=int(evt.x) - lb.p.x,
                offset_dy=int(evt.y) - lb.p.y,
            )
            return

        if hit.kind == Hit_Kind.icon and hit.tag_idx is not None:
            ic = app.params.icons[hit.tag_idx]
            self._drag = DragIcon(
                idx=hit.tag_idx,
                start=ic.p,
                offset_dx=int(evt.x) - ic.p.x,
                offset_dy=int(evt.y) - ic.p.y,
            )
            return

        self._drag = None

    def on_motion(self, app, evt: tk.Event) -> None:
        if self._drag:
            self._drag.update(app, evt)

    def on_release(self, app, evt: tk.Event) -> None:
        if self._drag:
            self._drag.commit(app, evt)
            self._drag = None

    def on_cancel(self, app) -> None:
        if self._drag:
            self._drag.cancel(app)
            self._drag = None

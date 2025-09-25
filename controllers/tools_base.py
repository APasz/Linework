from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from canvas.layers import Hit_Kind, Layer_Manager, Layer_Name
from canvas.selection import SelectionOverlay
from controllers.commands import Command_Stack, Move_Icon, Move_Label
from models.geo import CanvasLW, Point
from models.params import Params
from models.styling import TkCursor
from ui.bars import Bars, Tool_Name
from ui.input import get_mods

if TYPE_CHECKING:
    from controllers.app import App


@dataclass(slots=True)
class ToolContext:
    """Narrow interface Tools actually need. Pass your App if you want, but this keeps coupling sane."""

    canvas: CanvasLW
    params: Params
    layers: Layer_Manager
    status: Bars.Status
    commands: Command_Stack
    selection: SelectionOverlay
    snap: Callable[[Point], Point]
    redraw: Callable[[Layer_Name | None], None]


@runtime_checkable
class Tool(Protocol):
    name: Tool_Name
    cursor: TkCursor
    kind: Hit_Kind
    tool_hints: str

    def on_activate(self, app: App) -> None: ...
    def on_deactivate(self, app: App) -> None: ...

    def on_press(self, app: App, evt: tk.Event) -> None: ...
    def on_motion(self, app: App, evt: tk.Event) -> None: ...
    def on_release(self, app: App, evt: tk.Event) -> None: ...
    def on_key(self, app: App, evt: tk.Event) -> None: ...
    def on_cancel(self, app: App) -> None: ...


def _offgrid(p, g: int) -> bool:
    return g > 0 and ((p.x % g) != 0 or (p.y % g) != 0)


class ToolBase:
    """Common helpers for all tools. Keep it boring, keep it reliable."""

    cursor: TkCursor = TkCursor.CIRCLE
    kind: Hit_Kind = Hit_Kind.miss

    def __init__(self) -> None:
        self._preview_ids: list[int] = []
        self._start: Point | None = None

    def on_activate(self, app: App) -> None:
        pass

    def on_deactivate(self, app: App) -> None:
        self.clear_preview(app)

    def begin(self, p: Point) -> None:
        self._start = p

    def moved_enough(self, a: Point, b: Point, tol: int = 1) -> bool:
        dx, dy = a.x - b.x, a.y - b.y
        return (dx * dx + dy * dy) >= (tol * tol)

    def preview_line(self, app: App, a: Point, b: Point, **opts) -> int:
        if self._preview_ids:
            app.canvas.coords(self._preview_ids[0], a.x, a.y, b.x, b.y)
        else:
            lid = app.canvas.create_with_points(
                a,
                b,
                override_base_tags=[Layer_Name.preview],
                **opts,
            )
            self._preview_ids.append(lid)
        return self._preview_ids[0]

    def clear_preview(self, app: App) -> None:
        for iid in self._preview_ids:
            app.canvas.delete(iid)
        self._preview_ids.clear()
        app.layers.clear_preview()

    def on_key(self, app: App, evt: tk.Event) -> None:
        pass


class DragAction(Protocol):
    """Tiny state objects for Select_Tool drags: update/commit/cancel."""

    def update(self, app: App, evt: tk.Event) -> None: ...
    def commit(self, app: App, evt: tk.Event) -> None: ...
    def cancel(self, app: App) -> None: ...


@dataclass
class DragLabel(DragAction):
    idx: int
    start: Point
    offset_dx: int
    offset_dy: int

    def update(self, app, evt: tk.Event) -> None:
        mods = get_mods(evt)
        lab = app.params.labels[self.idx]
        p = app.snap(
            Point(x=evt.x - self.offset_dx, y=evt.y - self.offset_dy),
            ignore_grid=(mods.alt or not lab.snap or _offgrid(self.start, app.params.grid_size)),
        )
        dx, dy = p.x - self.start.x, p.y - self.start.y

        lb = app.params.labels[self.idx]
        app.layers.clear_preview()
        app.canvas.create_with_label(lb.with_point(p), override_base_tags=[Layer_Name.preview])

        sel = app.selection
        if not hasattr(self, "_base_sel"):
            self._base_sel = {
                "outline": app.canvas.coords(sel.ids.outline or 0) if sel.ids.outline else None,
                "handle": app.canvas.coords(sel.ids.handle_a or 0) if sel.ids.handle_a else None,
            }
        base = getattr(self, "_base_sel", {})
        if sel.ids.outline and base.get("outline"):
            x1, y1, x2, y2 = base["outline"]
            app.canvas.coords(sel.ids.outline, x1 + dx, y1 + dy, x2 + dx, y2 + dy)
        if sel.ids.handle_a and base.get("handle"):
            x1, y1, x2, y2 = base["handle"]
            app.canvas.coords(sel.ids.handle_a, x1 + dx, y1 + dy, x2 + dx, y2 + dy)

    def commit(self, app, evt: tk.Event) -> None:
        mods = get_mods(evt)
        lab = app.params.labels[self.idx]
        p = app.snap(
            Point(x=evt.x - self.offset_dx, y=evt.y - self.offset_dy),
            ignore_grid=(mods.alt or not lab.snap or _offgrid(self.start, app.params.grid_size)),
        )
        app.layers.clear_preview()
        app.cmd.push_and_do(
            Move_Label(
                app.params,
                self.idx,
                old_point=self.start,
                new_point=p,
                on_after=lambda: app.layers.redraw(Layer_Name.labels),
            )
        )
        app.selection.update_bbox()
        app.mark_dirty()

    def cancel(self, app) -> None:
        app.layers.clear_preview()
        app.selection.update_bbox()


@dataclass
class DragIcon(DragAction):
    idx: int
    start: Point
    offset_dx: int
    offset_dy: int

    def update(self, app, evt: tk.Event) -> None:
        mods = get_mods(evt)
        ico = app.params.icons[self.idx]
        p = app.snap(
            Point(x=evt.x - self.offset_dx, y=evt.y - self.offset_dy),
            ignore_grid=(mods.alt or not ico.snap or _offgrid(self.start, app.params.grid_size)),
        )
        dx, dy = p.x - self.start.x, p.y - self.start.y

        ico = app.params.icons[self.idx]
        app.layers.clear_preview()
        app.canvas.create_with_iconlike(ico.with_point(p), override_base_tags=[Layer_Name.preview])

        sel = app.selection
        if not hasattr(self, "_base_sel"):
            self._base_sel = {
                "outline": app.canvas.coords(sel.ids.outline or 0) if sel.ids.outline else None,
                "handle": app.canvas.coords(sel.ids.handle_a or 0) if sel.ids.handle_a else None,
            }
        base = getattr(self, "_base_sel", {})
        if sel.ids.outline and base.get("outline"):
            x1, y1, x2, y2 = base["outline"]
            app.canvas.coords(sel.ids.outline, x1 + dx, y1 + dy, x2 + dx, y2 + dy)
        if sel.ids.handle_a and base.get("handle"):
            x1, y1, x2, y2 = base["handle"]
            app.canvas.coords(sel.ids.handle_a, x1 + dx, y1 + dy, x2 + dx, y2 + dy)

    def commit(self, app, evt: tk.Event) -> None:
        mods = get_mods(evt)
        ico = app.params.icons[self.idx]
        p = app.snap(
            Point(x=evt.x - self.offset_dx, y=evt.y - self.offset_dy),
            ignore_grid=(mods.alt or not ico.snap or _offgrid(self.start, app.params.grid_size)),
        )
        app.layers.clear_preview()
        app.cmd.push_and_do(
            Move_Icon(
                app.params,
                self.idx,
                old_point=self.start,
                new_point=p,
                on_after=lambda: app.layers.redraw(Layer_Name.icons),
            )
        )
        app.selection.update_bbox()
        app.mark_dirty()

    def cancel(self, app) -> None:
        app.layers.clear_preview()
        app.selection.update_bbox()


@dataclass
class DragMarquee(DragAction):
    a: Point

    def update(self, app, evt: tk.Event) -> None:
        b = app.snap(Point(x=evt.x, y=evt.y))
        app.selection.update_marquee(self.a, b)

    def commit(self, app, evt: tk.Event) -> None:
        b = app.snap(Point(x=evt.x, y=evt.y))
        x1, y1 = min(self.a.x, b.x), min(self.a.y, b.y)
        x2, y2 = max(self.a.x, b.x), max(self.a.y, b.y)

        for iid in reversed(app.canvas.find_overlapping(x1, y1, x2, y2)):
            for t in app.canvas.gettags(iid):
                if ":" in t:
                    k, sidx = t.split(":", 1)
                    try:
                        kind = Hit_Kind(k)
                        app._set_selected(kind, int(sidx))
                        app.selection.clear_marquee()
                        app.selection.update_bbox()
                        return
                    except Exception:
                        continue
        app.selection.clear_marquee()

    def cancel(self, app) -> None:
        app.selection.clear_marquee()


class ToolManager:
    """Owns the current tool, routes events, handles activation/deactivation."""

    def __init__(self, app: App, tools: dict[Tool_Name, Tool]) -> None:
        self.app = app
        self.tools = tools
        self.current: Tool = next(iter(tools.values()))

    def activate(self, name: Tool_Name) -> None:
        if hasattr(self.current, "on_deactivate"):
            self.current.on_deactivate(self.app)
        from canvas.layers import Hit_Kind

        self.app._set_selected(Hit_Kind.miss, None)
        self.current = self.tools[name]
        if hasattr(self.current, "on_activate"):
            self.current.on_activate(self.app)
        cur = getattr(self.current, "cursor", None)
        self.app.canvas.config(cursor=cur.value if isinstance(cur, TkCursor) else "")

    # routed events
    def on_press(self, evt: tk.Event) -> None:
        self.current.on_press(self.app, evt)

    def on_motion(self, evt: tk.Event) -> None:
        self.current.on_motion(self.app, evt)

    def on_release(self, evt: tk.Event) -> None:
        self.current.on_release(self.app, evt)

    def on_key(self, evt: tk.Event) -> None:
        if hasattr(self.current, "on_key"):
            self.current.on_key(self.app, evt)

    def cancel(self) -> None:
        if hasattr(self.current, "on_cancel"):
            self.current.on_cancel(self.app)

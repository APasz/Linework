from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from canvas.layers import Hit_Kind, Layer_Manager, Layer_Type, TagNS, tag_parse_multi
from canvas.selection import SelectionOverlay
from controllers.commands import Command_Stack, Move_Icon, Move_Label, Move_Line_End, Multi
from models.geo import CanvasLW, Point
from models.params import Params
from models.styling import TkCursor
from ui.bars import Bars, Tool_Name
from ui.input import get_mods

if TYPE_CHECKING:
    from controllers.app import App

CLAMP_DRAG_BBOX = True


def _visible_viewport_bbox(canvas) -> tuple[int, int, int, int] | None:
    try:
        x1 = int(canvas.canvasx(0))
        y1 = int(canvas.canvasy(0))
        x2 = int(canvas.canvasx(canvas.winfo_width()))
        y2 = int(canvas.canvasy(canvas.winfo_height()))
        return (x1, y1, x2, y2)
    except Exception:
        return None


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
    redraw: Callable[[Layer_Type | None], None]


@runtime_checkable
class Tool(Protocol):
    name: Tool_Name
    cursor: TkCursor
    kind: Hit_Kind | None
    tool_hints: str

    def on_activate(self, app: App): ...
    def on_deactivate(self, app: App): ...

    def on_press(self, app: App, evt: tk.Event): ...
    def on_motion(self, app: App, evt: tk.Event): ...
    def on_release(self, app: App, evt: tk.Event): ...
    def on_key(self, app: App, evt: tk.Event): ...
    def on_cancel(self, app: App): ...


class ToolBase:
    """Common helpers for all tools. Keep it boring, keep it reliable."""

    name: Tool_Name
    cursor: TkCursor = TkCursor.CIRCLE
    kind: Hit_Kind | None = None
    tool_hints: str

    def __init__(self):
        self._preview_ids: list[int] = []
        self._start: Point | None = None

    def on_activate(self, app: App):
        pass

    def on_deactivate(self, app: App):
        self.clear_preview(app)

    def moved_enough(self, a: Point, b: Point, tol: int = 1) -> bool:
        dx, dy = a.x - b.x, a.y - b.y
        return (dx * dx + dy * dy) >= (tol * tol)

    def clear_preview(self, app: App):
        for iid in self._preview_ids:
            app.canvas.delete_lw(iid)
        self._preview_ids.clear()
        app.layers.clear_preview()

    def on_press(self, app: App, evt: tk.Event):
        pass

    def on_motion(self, app: App, evt: tk.Event):
        pass

    def on_release(self, app: App, evt: tk.Event):
        pass

    def on_key(self, app: App, evt: tk.Event):
        pass

    def on_cancel(self, app: App):
        pass


class DragAction(Protocol):
    """Tiny state objects for Select_Tool drags: update/commit/cancel."""

    def update(self, app: App, evt: tk.Event): ...
    def commit(self, app: App, evt: tk.Event): ...
    def cancel(self, app: App): ...


@dataclass
class DragLabel(DragAction):
    idx: int
    start: Point
    offset_dx: int
    offset_dy: int

    def update(self, app, evt: tk.Event):
        mods = get_mods(evt)
        lab = app.params.labels[self.idx]
        p = app.snap(
            Point(x=evt.x - self.offset_dx, y=evt.y - self.offset_dy),
            ignore_grid=(mods.alt or not lab.snap),
        )
        dx, dy = p.x - self.start.x, p.y - self.start.y

        lb = app.params.labels[self.idx]
        app.layers.clear_preview()
        app.canvas.create_with_label(lb.with_point(p), tag_type=Layer_Type.preview)

        try:
            bb = app.canvas.bbox(Layer_Type.preview.value)
            if bb:
                x1, y1, x2, y2 = bb
                if CLAMP_DRAG_BBOX:
                    vbb = _visible_viewport_bbox(app.canvas)
                    if vbb:
                        vx1, vy1, vx2, vy2 = vbb
                        cx1 = max(x1, vx1)
                        cy1 = max(y1, vy1)
                        cx2 = min(x2, vx2)
                        cy2 = min(y2, vy2)
                        if cx1 < cx2 and cy1 < cy2:
                            x1, y1, x2, y2 = cx1, cy1, cx2, cy2
                app.selection.set_outline_bbox(x1, y1, x2, y2)
        except Exception:
            sel = app.selection
            if sel.ids.outline:
                ox1, oy1, ox2, oy2 = app.canvas.coords(sel.ids.outline)
                app.selection.set_outline_bbox(ox1 + dx, oy1 + dy, ox2 + dx, oy2 + dy)

    def commit(self, app, evt: tk.Event):
        mods = get_mods(evt)
        lab = app.params.labels[self.idx]
        p = app.snap(
            Point(x=evt.x - self.offset_dx, y=evt.y - self.offset_dy),
            ignore_grid=(mods.alt or not lab.snap),
        )
        g = app.params.grid_size
        off_grid = g > 0 and ((p.x % g) != 0 or (p.y % g) != 0)
        if mods.alt or off_grid:
            lab.snap = False
        elif g > 0:
            lab.snap = True
        app.layers.clear_preview()
        app.cmd.push_and_do(
            Move_Label(
                app.params,
                self.idx,
                old_point=self.start,
                new_point=p,
                on_after=lambda: app.layers.redraw(Layer_Type.labels),
            )
        )
        app.selection.update_bbox()
        app._set_selected(Hit_Kind.label, self.idx)
        app.mark_dirty()

    def cancel(self, app):
        app.layers.clear_preview()
        app.selection.update_bbox()


@dataclass
class DragIcon(DragAction):
    idx: int
    start: Point
    offset_dx: int
    offset_dy: int

    def update(self, app, evt: tk.Event):
        mods = get_mods(evt)
        ico = app.params.icons[self.idx]
        p = app.snap(
            Point(x=evt.x - self.offset_dx, y=evt.y - self.offset_dy),
            ignore_grid=(mods.alt or not ico.snap),
        )

        ic = app.params.icons[self.idx]
        app.layers.clear_preview()
        app.canvas.create_with_iconlike(ic.with_point(p), tag_type=Layer_Type.preview)

        try:
            bb = app.canvas.bbox(Layer_Type.preview.value)
            if bb:
                x1, y1, x2, y2 = bb
                if CLAMP_DRAG_BBOX:
                    vbb = _visible_viewport_bbox(app.canvas)
                    if vbb:
                        vx1, vy1, vx2, vy2 = vbb
                        cx1 = max(x1, vx1)
                        cy1 = max(y1, vy1)
                        cx2 = min(x2, vx2)
                        cy2 = min(y2, vy2)
                        if cx1 < cx2 and cy1 < cy2:
                            x1, y1, x2, y2 = cx1, cy1, cx2, cy2
                app.selection.set_outline_bbox(x1, y1, x2, y2)
        except Exception:
            pass

    def commit(self, app, evt: tk.Event):
        mods = get_mods(evt)
        ico = app.params.icons[self.idx]
        p = app.snap(
            Point(x=evt.x - self.offset_dx, y=evt.y - self.offset_dy),
            ignore_grid=(mods.alt or not ico.snap),
        )
        g = app.params.grid_size
        off_grid = g > 0 and ((p.x % g) != 0 or (p.y % g) != 0)
        if mods.alt or off_grid:
            ico.snap = False
        elif g > 0:
            ico.snap = True
        app.layers.clear_preview()
        app.cmd.push_and_do(
            Move_Icon(
                app.params,
                self.idx,
                old_point=self.start,
                new_point=p,
                on_after=lambda: app.layers.redraw(Layer_Type.icons),
            )
        )
        app.selection.update_bbox()
        app._set_selected(Hit_Kind.icon, self.idx)
        app.mark_dirty()

    def cancel(self, app):
        app.layers.clear_preview()
        app.selection.update_bbox()


@dataclass
class DragMarquee(DragAction):
    a: Point
    add: bool = False

    def update(self, app, evt: tk.Event):
        b = app.snap(Point(x=evt.x, y=evt.y))
        app.selection.update_marquee(self.a, b)

    def commit(self, app, evt: tk.Event):
        b = app.snap(Point(x=evt.x, y=evt.y))
        x1, y1 = min(self.a.x, b.x), min(self.a.y, b.y)
        x2, y2 = max(self.a.x, b.x), max(self.a.y, b.y)

        hits: list[tuple[Hit_Kind, int]] = []
        seen: set[tuple[str, int]] = set()
        for iid in app.canvas.find_overlapping(x1, y1, x2, y2):
            toks = tag_parse_multi(app.canvas.gettags(iid))
            ht = next((t for t in toks if t.ns is TagNS.hit and t.idx is not None), None)
            if not ht or not isinstance(ht.kind, Hit_Kind) or ht.idx is None:
                continue
            key = (ht.kind.value, ht.idx)
            if key not in seen:
                seen.add(key)
                hits.append((ht.kind, ht.idx))
        app.selection.clear_marquee()
        if not hits:
            return
        if self.add:
            app.select_merge(hits)
        else:
            app.select_set(hits)

    def cancel(self, app):
        app.selection.clear_marquee()


@dataclass
class DragGroup(DragAction):
    """Drag many items together by delta."""

    items: list[tuple[Hit_Kind, int]]
    start_mouse: Point
    # original positions cached
    labels: list[tuple[int, Point]]  # (idx, orig p)
    icons: list[tuple[int, Point]]  # (idx, orig p)
    lines: list[tuple[int, Point, Point]]  # (idx, orig a, orig b)

    def _delta(self, app, evt: tk.Event) -> tuple[int, int, bool]:
        mods = get_mods(evt)
        cur = app.snap(Point(x=evt.x, y=evt.y), ignore_grid=mods.alt)
        a = app.snap(self.start_mouse, ignore_grid=mods.alt)
        return (cur.x - a.x, cur.y - a.y, mods.alt)

    def update(self, app, evt: tk.Event):
        dx, dy, alt = self._delta(app, evt)
        app.layers.clear_preview()

        for idx, p0 in self.labels:
            lb = app.params.labels[idx]
            p = Point(x=p0.x + dx, y=p0.y + dy)
            p = app.snap(p, ignore_grid=(alt or not lb.snap))
            app.canvas.create_with_label(lb.with_point(p), tag_type=Layer_Type.preview)
        for idx, p0 in self.icons:
            ic = app.params.icons[idx]
            p = Point(x=p0.x + dx, y=p0.y + dy)
            p = app.snap(p, ignore_grid=(alt or not ic.snap))
            app.canvas.create_with_iconlike(ic.with_point(p), tag_type=Layer_Type.preview)
        for idx, a0, b0 in self.lines:
            ln = app.params.lines[idx]
            a = app.snap(Point(x=a0.x + dx, y=a0.y + dy), ignore_grid=alt)
            b = app.snap(Point(x=b0.x + dx, y=b0.y + dy), ignore_grid=alt)
            app.canvas.create_with_line(ln.with_points(a, b), tag_type=Layer_Type.preview)

        bb = app.canvas.bbox(Layer_Type.preview.value)
        if bb:
            x1, y1, x2, y2 = bb
            app.selection.set_outline_bbox(x1, y1, x2, y2)

    def commit(self, app, evt: tk.Event):
        dx, dy, alt = self._delta(app, evt)
        app.layers.clear_preview()
        subs = []

        for idx, p0 in self.labels:
            lb = app.params.labels[idx]
            p = app.snap(Point(x=p0.x + dx, y=p0.y + dy), ignore_grid=(alt or not lb.snap))
            subs.append(
                Move_Label(
                    app.params, idx, old_point=p0, new_point=p, on_after=lambda: app.layers.redraw(Layer_Type.labels)
                )
            )
        for idx, p0 in self.icons:
            ic = app.params.icons[idx]
            p = app.snap(Point(x=p0.x + dx, y=p0.y + dy), ignore_grid=(alt or not ic.snap))
            subs.append(
                Move_Icon(
                    app.params, idx, old_point=p0, new_point=p, on_after=lambda: app.layers.redraw(Layer_Type.icons)
                )
            )
        for idx, a0, b0 in self.lines:
            a = app.snap(Point(x=a0.x + dx, y=a0.y + dy), ignore_grid=alt)
            b = app.snap(Point(x=b0.x + dx, y=b0.y + dy), ignore_grid=alt)
            # translate both ends via two endpoint moves
            ln = app.params.lines[idx]
            subs.append(
                Move_Line_End(
                    app.params,
                    idx,
                    "a",
                    old_point=ln.a,
                    new_point=a,
                    on_after=lambda: app.layers.redraw(Layer_Type.lines),
                )
            )
            subs.append(
                Move_Line_End(
                    app.params,
                    idx,
                    "b",
                    old_point=ln.b,
                    new_point=b,
                    on_after=lambda: app.layers.redraw(Layer_Type.lines),
                )
            )

        app.cmd.push_and_do(Multi(subs))
        app.selection.update_bbox()
        app.mark_dirty()

    def cancel(self, app):
        app.layers.clear_preview()
        app.selection.update_bbox()


class Tool_Manager:
    """Owns the current tool, routes events, handles activation/deactivation."""

    def __init__(self, app: App, tools: dict[Tool_Name, Tool]):
        self.app = app
        self.tools = tools
        self.current: Tool = next(iter(tools.values()))

    def activate(self, name: Tool_Name):
        if hasattr(self.current, "on_deactivate"):
            self.current.on_deactivate(self.app)

        self.app.select_clear()
        self.app.selection.clear_marquee()
        self.app.status.release("sel")

        self.current = self.tools[name]
        if hasattr(self.current, "on_activate"):
            self.current.on_activate(self.app)
        cur = getattr(self.current, "cursor", None)
        self.app.canvas.config(cursor=cur.value if isinstance(cur, TkCursor) else "")
        self.app.canvas.tag_raise_l(Layer_Type.selection)

    def on_press(self, evt: tk.Event):
        setattr(evt, "mods", get_mods(evt))
        self.current.on_press(self.app, evt)

    def on_motion(self, evt: tk.Event):
        setattr(evt, "mods", get_mods(evt))
        self.current.on_motion(self.app, evt)

    def on_release(self, evt: tk.Event):
        setattr(evt, "mods", get_mods(evt))
        self.current.on_release(self.app, evt)

    def on_key(self, evt: tk.Event):
        setattr(evt, "mods", get_mods(evt))
        self.current.on_key(self.app, evt)

    def cancel(self):
        self.current.on_cancel(self.app)

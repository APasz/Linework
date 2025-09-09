from __future__ import annotations

import math
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from canvas.layers import L_PREV, Hit_Kind, Layer_Manager, Layer_Name, test_hit
from controllers.commands import Add_Icon, Add_Label, Add_Line, Command_Stack, Move_Icon, Move_Label
from models.geo import Icon, Label, Line, Point
from models.params import Params
from models.styling import TkCursor, scaled_pattern
from ui.bars import Bars, Side

SHIFT_MASK = 0x0001  # Tk modifier mask for Shift


# --- minimal app protocol the tools need ---
class Applike(Protocol):
    root: tk.Tk
    canvas: tk.Canvas
    params: Params
    cmd: Command_Stack
    status: Bars.Status
    layers: Layer_Manager
    mark_dirty: Callable
    drag_to_draw: Callable[..., bool]
    cardinal: Callable[..., bool]

    def snap(self, point: Point, /) -> Point: ...
    def layers_redraw(self, *layers: Layer_Name): ...
    def prompt_text(self, title: str, prompt: str, /) -> str | None: ...
    def _set_selected(self, kind: Hit_Kind, idx: int | None): ...


class Tool_Name(StrEnum):
    draw = "draw"
    label = "label"
    icon = "icon"
    select = "select"


# ---- base tool ----
class Tool(Protocol):
    name: Tool_Name
    cursor: TkCursor | None
    kind: Hit_Kind

    def on_press(self, app: Applike, evt: tk.Event, /): ...
    def on_motion(self, app: Applike, evt: tk.Event, /): ...
    def on_release(self, app: Applike, evt: tk.Event, /): ...
    def on_cancel(self, app: Applike): ...


# ---- DrawTool ----
class Draw_Tool(Tool):
    name: Tool_Name = Tool_Name.draw
    cursor: TkCursor | None = TkCursor.CROSSHAIR
    kind: Hit_Kind = Hit_Kind.line

    def __init__(self):
        self.start: Point | None = None
        self.preview_id: int | None = None
        self._is_dragging: bool = False  # only used in drag-to-draw mode

    # --- utilities ---
    def _snap(self, app: Applike, point: Point) -> Point:
        g = app.params.grid_size
        W, H = app.params.width, app.params.height
        X, Y = point.x, point.y
        if g > 0:
            sx, sy = round(X / g) * g, round(Y / g) * g
            max_x, max_y = (W // g) * g, (H // g) * g
            sx = 0 if sx < 0 else max_x if sx > max_x else sx
            sy = 0 if sy < 0 else max_y if sy > max_y else sy
            return Point(x=sx, y=sy)
        # no grid: clamp to canvas
        x = 0 if X < 0 else W if X > W else X
        y = 0 if Y < 0 else H if Y > H else Y
        return Point(x=x, y=y)

    def _clear_preview(self, app: Applike):
        if self.preview_id:
            app.canvas.delete(self.preview_id)
            self.preview_id = None
        app.layers.clear_preview()

    def _update_preview_to(self, app: Applike, end: Point, evt: tk.Event | None = None):
        if not self.start:
            return
        if evt is not None and self._dir_snap_on(app, evt):
            end = self._snap_directional(app, end, self.start)

        dash = scaled_pattern(app.params.line_style, app.params.brush_width)

        # Annotate as Any so Pylance doesn’t over-constrain values due to "tags"
        opts: dict[str, Any] = {
            "fill": app.params.brush_colour.hex,
            "width": app.params.brush_width,
            "capstyle": self.start.capstyle,
            "tags": (L_PREV,),
        }
        if dash:
            opts["dash"] = dash
            if app.params.line_dash_offset:
                opts["dashoffset"] = int(app.params.line_dash_offset)

        if self.preview_id is None:
            self.preview_id = app.canvas.create_line(self.start.x, self.start.y, end.x, end.y, **opts)
        else:
            app.canvas.coords(self.preview_id, self.start.x, self.start.y, end.x, end.y)
            reapply: dict[str, Any] = {k: v for k, v in opts.items() if k != "tags"}
            app.canvas.itemconfig(self.preview_id, **reapply)
            app.canvas.tag_raise(L_PREV)

    def _commit_segment(self, app: Applike, end: Point, evt: tk.Event | None = None):
        if not self.start:
            return
        if evt is not None and self._dir_snap_on(app, evt):
            end = self._snap_directional(app, end, self.start)

        if end.x == self.start.x and end.y == self.start.y:
            self._clear_preview(app)
            self.start = None
            app.status.temp("Ignored zero-length segment", ms=1000, priority=50, side=Side.centre)
            return

        ln = Line(
            a=self.start,
            b=end,
            col=app.params.brush_colour,
            width=app.params.brush_width,
            capstyle=self.start.capstyle,
            style=app.params.line_style,
            dash_offset=app.params.line_dash_offset,
        )
        app.cmd.push_and_do(Add_Line(app.params, ln, on_after=lambda: app.layers_redraw(Layer_Name.lines)))
        app.mark_dirty()
        self._clear_preview(app)
        self.start = None

    def _dir_snap_on(self, app: Applike, evt: tk.Event) -> bool:
        """Return True if direction cardial should be applied for this event."""
        base = app.cardinal()  # your UI toggle
        shift = bool(getattr(evt, "state", 0) & SHIFT_MASK)
        return (not base) if shift else base  # Shift inverts

    def _snap_directional(self, app: Applike, point: Point, start: Point) -> Point:
        """
        Snap (x,y) to grid/clamp, then constrain the vector from start -> (x,y)
        to the nearest 45° octant. Finally re-snap/clamp to grid.
        """
        # 1) normal grid snap + clamp
        spoint = self._snap(app, point)

        dx, dy = spoint.x - start.x, spoint.y - start.y
        if dx == 0 and dy == 0:
            return spoint

        # 2) quantise angle to nearest 45°
        ang = math.atan2(dy, dx)  # [-pi, pi]
        step = math.pi / 4.0  # 45°
        qang = round(ang / step) * step  # nearest octant

        # keep the same length (in pixels)
        r = math.hypot(dx, dy)
        qx = start.x + r * math.cos(qang)
        qy = start.y + r * math.sin(qang)

        # 3) final snap/clamp to grid/canvas (and cast to int)
        return self._snap(app, Point(x=round(qx), y=round(qy)))

    # --- Tool interface ---
    def on_press(self, app: Applike, evt: tk.Event):
        point = self._snap(app, Point(x=evt.x, y=evt.y))
        if app.drag_to_draw():
            # drag mode: press sets start; release will commit
            if self.start is None:
                self.start = point
                self._is_dragging = True
                r = max(2, app.params.brush_width // 2)
                app.canvas.create_oval(
                    point.x - r,
                    point.y - r,
                    point.x + r,
                    point.y + r,
                    outline="",
                    fill=app.params.brush_colour.hex,
                    tags=(L_PREV,),
                )
        else:
            # click-click: press toggles between set-start and commit
            if self.start is None:
                self.start = point
                r = max(2, app.params.brush_width // 2)
                app.canvas.create_oval(
                    point.x - r,
                    point.y - r,
                    point.x + r,
                    point.y + r,
                    outline="",
                    fill=app.params.brush_colour.hex,
                    tags=(L_PREV,),
                )
            else:
                # second click commits at this snapped press position
                self._commit_segment(app, point, evt)

    def on_motion(self, app: Applike, evt: tk.Event):
        if self.start is None:
            return
        point = self._snap(app, Point(x=evt.x, y=evt.y))
        self._update_preview_to(app, point, evt)
        app.status.hold("drawline", f"({self.start.x},{self.start.y}) → ({point.x},{point.y})")

    def on_hover(self, app: Applike, evt: tk.Event):
        if self.start is None or app.drag_to_draw():
            return
        point = self._snap(app, Point(x=evt.x, y=evt.y))
        self._update_preview_to(app, point, evt)
        app.status.hold("drawline", f"({self.start.x},{self.start.y}) → ({point.x},{point.y})")

    def on_release(self, app: Applike, evt: tk.Event):
        if self.start is None:
            return
        if app.drag_to_draw():
            point = self._snap(app, Point(x=evt.x, y=evt.y))
            self._commit_segment(app, point, evt)
            self._is_dragging = False
        app.status.release("drawline")

    def on_cancel(self, app: Applike):
        self._clear_preview(app)
        self.start = None
        self._is_dragging = False
        app.status.release("drawline")


# ---- LabelTool ----
@dataclass
class Label_Tool:
    name: Tool_Name = Tool_Name.label
    cursor: TkCursor | None = TkCursor.XTERM
    kind: Hit_Kind = Hit_Kind.label

    def on_press(self, app: Applike, evt: tk.Event):
        point = app.snap(Point(x=evt.x, y=evt.y))

        text = app.prompt_text("New Label", "Text:")
        if not text:
            return
        lab = Label(p=point, text=text, col=app.params.brush_colour, size=12)
        app.cmd.push_and_do(Add_Label(app.params, lab, on_after=lambda: app.layers_redraw(Layer_Name.labels)))
        app.mark_dirty()
        app.status.temp(f"Label @ ({point.x},{point.y})", 2500)

    def on_motion(self, app: Applike, evt: tk.Event): ...
    def on_release(self, app: Applike, evt: tk.Event): ...
    def on_cancel(self, app: Applike): ...


# ---- IconTool ----
@dataclass
class Icon_Tool:
    get_icon_name: Callable
    name: Tool_Name = Tool_Name.icon
    cursor: TkCursor | None = TkCursor.HAND2
    kind: Hit_Kind = Hit_Kind.icon

    def on_press(self, app: Applike, evt: tk.Event):
        point = app.snap(Point(x=evt.x, y=evt.y))

        ico = Icon(p=point, name=self.get_icon_name(), col=app.params.brush_colour, size=16, rotation=0)
        app.cmd.push_and_do(Add_Icon(app.params, ico, on_after=lambda: app.layers_redraw(Layer_Name.icons)))
        app.mark_dirty()
        app.status.temp(f"Icon @ ({point.x},{point.y})", 2500)

    def on_motion(self, app: Applike, evt: tk.Event): ...
    def on_release(self, app: Applike, evt: tk.Event): ...
    def on_cancel(self, app: Applike): ...


# ---- SelectTool (drag labels/icons) ----
@dataclass
class Select_Tool:
    name: Tool_Name = Tool_Name.select
    cursor: TkCursor | None = TkCursor.ARROW
    _drag_kind: Hit_Kind = Hit_Kind.miss
    _drag_canvas_id: int | None = None  # for labels
    _drag_index: int | None = None  # model index for the selection
    _drag_icon_ids: tuple[int, ...] | None = None  # concrete item ids of the icon
    _start_pos: Point | None = None
    _press_center: Point | None = None
    _dragged: bool = False

    def _centre_of_tag(self, canvas: tk.Canvas, tag: str) -> Point | None:
        bbox = canvas.bbox(tag) or (lambda ids: canvas.bbox(ids[0]) if ids else None)(canvas.find_withtag(tag))
        if not bbox:
            return None
        return Point(x=round((bbox[0] + bbox[2]) / 2), y=round((bbox[1] + bbox[3]) / 2))

    def on_press(self, app: Applike, evt: tk.Event):
        hit = test_hit(app.canvas, evt.x, evt.y)
        self._dragged = False
        self._press_center = None

        if not hit:
            self._drag_kind = Hit_Kind.miss
            self._drag_canvas_id = None
            self._drag_index = None
            self._drag_icon_ids = None
            self._start_pos = None
            return

        app.canvas.focus_set()
        try:
            app.canvas.grab_set()
        except tk.TclError:
            pass

        app._set_selected(hit.kind, hit.tag_idx)
        self._drag_kind = hit.kind
        self._drag_canvas_id = hit.canvas_idx
        self._drag_index = hit.tag_idx
        self._start_pos = Point(x=evt.x, y=evt.y)

        if self._drag_kind == Hit_Kind.icon and self._drag_index is not None:
            tag = f"{Hit_Kind.icon.value}:{self._drag_index}"
            self._drag_icon_ids = tuple(app.canvas.find_withtag(tag))
            centre = self._centre_of_tag(app.canvas, tag)
            if centre:
                self._press_center = centre
        elif self._drag_kind == Hit_Kind.label and self._drag_canvas_id is not None:
            coords = app.canvas.coords(self._drag_canvas_id)
            if coords:
                self._press_center = Point(x=round(coords[0]), y=round(coords[1]))

    def on_motion(self, app: Applike, evt: tk.Event):
        if not self._start_pos or not self._drag_kind:
            return
        dx, dy = evt.x - self._start_pos.x, evt.y - self._start_pos.y
        if dx or dy:
            self._dragged = True
        if self._drag_kind == Hit_Kind.label and self._drag_canvas_id is not None:
            app.canvas.move(self._drag_canvas_id, dx, dy)
        elif self._drag_kind == Hit_Kind.icon and self._drag_index is not None:
            app.canvas.move(f"{Hit_Kind.icon.value}:{self._drag_index}", dx, dy)
        self._start_pos = Point(x=evt.x, y=evt.y)

    def on_release(self, app: Applike, evt: tk.Event):
        try:
            app.canvas.grab_release()
        except tk.TclError:
            pass
        if not self._drag_kind:
            return

        if self._drag_kind == Hit_Kind.label:
            cid = int(self._drag_canvas_id or 0)
            coords = app.canvas.coords(cid)
            end_center = Point(x=round(coords[0]), y=round(coords[1])) if coords else Point(x=evt.x, y=evt.y)

            if not (self._dragged and self._moved_enough(self._press_center, end_center)):
                # click only → do nothing; keep off-grid positions
                self._reset()
                return

            spoint = self._maybe_snap_point(
                app, end_center, kind=Hit_Kind.label, index=self._label_index_from_canvas(app, cid), evt=evt
            )
            idx = self._label_index_from_canvas(app, cid)
            old = app.params.labels[idx].p
            if spoint != old:
                app.cmd.push_and_do(
                    Move_Label(app.params, idx, old, spoint, on_after=lambda: app.layers_redraw(Layer_Name.labels))
                )
                app.mark_dirty()
            else:
                app.layers_redraw(Layer_Name.labels)

        elif self._drag_kind == Hit_Kind.icon:
            # compute end center from the ids we actually dragged
            if self._drag_icon_ids:
                bbox = None
                for cid in self._drag_icon_ids:
                    b = app.canvas.bbox(cid)
                    if b:
                        bbox = (
                            b
                            if bbox is None
                            else (min(bbox[0], b[0]), min(bbox[1], b[1]), max(bbox[2], b[2]), max(bbox[3], b[3]))
                        )
                if bbox:
                    end_center = Point(x=round((bbox[0] + bbox[2]) / 2), y=round((bbox[1] + bbox[3]) / 2))
                else:
                    end_center = Point(x=evt.x, y=evt.y)
            else:
                end_center = Point(x=evt.x, y=evt.y)

            if not (self._dragged and self._moved_enough(self._press_center, end_center)):
                self._reset()
                return

            # resolve model index from dragged ids
            idx = self._drag_index
            if idx is None:
                idx = self._infer_index_from_ids(app.canvas, self._drag_icon_ids or (), Hit_Kind.icon)
            if idx is None:
                idx = self._nearest_icon_index(app, end_center)
            if idx is None:
                self._reset()
                return

            spoint = self._maybe_snap_point(app, end_center, kind=Hit_Kind.icon, index=idx, evt=evt)
            old = app.params.icons[idx].p
            if spoint != old:
                app.cmd.push_and_do(
                    Move_Icon(app.params, idx, old, spoint, on_after=lambda: app.layers_redraw(Layer_Name.icons))
                )
                app.mark_dirty()
            else:
                app.layers_redraw(Layer_Name.icons)

        self._reset()

    def on_cancel(self, app: Applike):
        self._reset()

    def _reset(self):
        self._drag_kind = Hit_Kind.miss
        self._drag_canvas_id = None
        self._drag_index = None
        self._drag_icon_ids = None
        self._start_pos = None
        self._press_center = None
        self._dragged = False

    # helper: map canvas text id -> label index (rebuild cheaply)
    def _label_index_from_canvas(self, app: Applike, cid: int) -> int:
        # rebuild a fresh map (labels aren't huge)
        # draw order matches params.labels order in painters, but ids differ per redraw
        # so we re-hit labels by position/text match:
        tags = app.canvas.gettags(cid)
        for tag in tags:
            if tag.startswith(f"{Hit_Kind.label.value}:"):
                return int(tag.split(":", 1)[1])

        x, y = app.canvas.coords(cid)[:2]
        text = app.canvas.itemcget(cid, "text")
        for i, lab in enumerate(app.params.labels):
            if lab.text == text and abs(lab.p.x - x) < 2 and abs(lab.p.y - y) < 2:
                return i
        # fallback: nearest by distance
        best_i, best_d = 0, 1e9
        for i, lab in enumerate(app.params.labels):
            d = (lab.p.x - x) ** 2 + (lab.p.y - y) ** 2
            if d < best_d:
                best_d, best_i = d, i
        return best_i

    def _infer_index_from_ids(self, canvas: tk.Canvas, ids: tuple[int, ...], prefix: Hit_Kind) -> int | None:
        """Return the most common '<prefix>:K' tag index across these item ids."""
        counts: dict[int, int] = {}
        needle = prefix.value + ":"
        for cid in ids:
            for t in canvas.gettags(cid):
                if t.startswith(needle):
                    try:
                        k = int(t.split(":", 1)[1])
                        counts[k] = counts.get(k, 0) + 1
                    except ValueError:
                        pass
        if not counts:
            return None
        # majority vote
        return max(counts.items(), key=lambda kv: kv[1])[0]

    def _nearest_icon_index(self, app: Applike, point: Point) -> int | None:
        best_i, best_d = None, float("inf")
        for i, ico in enumerate(app.params.icons):
            d = (ico.p.x - point.x) * (ico.p.x - point.x) + (ico.p.y - point.y) * (ico.p.y - point.y)
            if d < best_d:
                best_d, best_i = d, i
        return best_i

    def _moved_enough(self, a: Point | None, b: Point | None, tol: int = 1) -> bool:
        if not a or not b:
            return False
        return abs(a.x - b.x) > tol or abs(a.y - b.y) > tol

    def _snap_enabled_for(self, app: Applike, kind: Hit_Kind, index: int, evt: tk.Event | None) -> bool:
        # App-wide toggle
        base = app.cardinal()
        # Ctrl inverts (hold to bypass, or hold to force if base==False)
        ctrl = (getattr(evt, "state", 0) & 0x0004) != 0  # ControlMask bit on X11/Windows; tweak on mac if needed
        want = base ^ ctrl
        # Per-object preference (only matters if want==True)
        if not want:
            return False
        if kind == Hit_Kind.label:
            return bool(getattr(app.params.labels[index], "snap", True))
        if kind == Hit_Kind.icon:
            return bool(getattr(app.params.icons[index], "snap", True))
        return True

    def _maybe_snap_point(
        self, app: Applike, point: Point, *, kind: Hit_Kind, index: int, evt: tk.Event | None = None
    ) -> Point:
        if self._snap_enabled_for(app, kind, index, evt):
            return app.snap(point)
        return point

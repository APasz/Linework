from __future__ import annotations

import math
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from canvas.hit_test import test_hit
from canvas.layers import L_PREV, Layer_Manager, LayerName
from controllers.commands import Add_Icon, Add_Label, Add_Line, Command_Stack, Move_Icon, Move_Label
from models.geo import Line, Point
from models.linestyle import scaled_pattern
from models.objects import Icon, Label
from models.params import Params
from ui.status import Status

SHIFT_MASK = 0x0001  # Tk modifier mask for Shift


# --- minimal app protocol the tools need ---
class Applike(Protocol):
    root: tk.Tk
    canvas: tk.Canvas
    params: Params
    cmd: Command_Stack
    status: Status
    layers: Layer_Manager
    mark_dirty: Callable
    drag_to_draw: Callable[..., bool]
    snapping: Callable[..., bool]

    def snap(self, x: int, y: int, /) -> tuple[int, int]: ...
    def layers_redraw(self, *layers: LayerName): ...
    def prompt_text(self, title: str, prompt: str, /) -> str | None: ...
    def _set_selected(self, kind: str | None, idx: int | None): ...


# ---- base tool ----
class Tool(Protocol):
    name: str
    cursor: str | None

    def on_press(self, app: Applike, evt: tk.Event, /): ...
    def on_motion(self, app: Applike, evt: tk.Event, /): ...
    def on_release(self, app: Applike, evt: tk.Event, /): ...
    def on_cancel(self, app: Applike): ...


# ---- DrawTool ----
class Draw_Tool(Tool):
    name = "draw"
    cursor = "crosshair"

    def __init__(self):
        self.start: Point | None = None
        self.preview_id: int | None = None
        self._is_dragging: bool = False  # only used in drag-to-draw mode

    # --- utilities ---
    def _snap(self, app: Applike, x: int, y: int) -> tuple[int, int]:
        g = app.params.grid_size
        W, H = app.params.width, app.params.height
        if g > 0:
            sx, sy = round(x / g) * g, round(y / g) * g
            max_x, max_y = (W // g) * g, (H // g) * g
            sx = 0 if sx < 0 else max_x if sx > max_x else sx
            sy = 0 if sy < 0 else max_y if sy > max_y else sy
            return sx, sy
        # no grid: clamp to canvas
        x = 0 if x < 0 else W if x > W else x
        y = 0 if y < 0 else H if y > H else y
        return x, y

    def _clear_preview(self, app: Applike):
        if self.preview_id:
            app.canvas.delete(self.preview_id)
            self.preview_id = None
        app.layers.clear_preview()

    def _update_preview_to(self, app: Applike, x2: int, y2: int, evt: tk.Event | None = None):
        if not self.start:
            return
        if evt is not None and self._dir_snap_on(app, evt):
            x2, y2 = self._snap_directional(app, x2, y2, self.start)

        params = app.params
        x1, y1 = self.start.x, self.start.y

        dash = scaled_pattern(params.line_style, params.brush_width)

        # Annotate as Any so Pylance doesn’t over-constrain values due to "tags"
        opts: dict[str, Any] = {
            "fill": params.brush_colour.hex,
            "width": params.brush_width,
            "capstyle": self.start.capstyle,
            "tags": (L_PREV,),
        }
        if dash:
            opts["dash"] = dash
            if params.line_dash_offset:
                opts["dashoffset"] = int(params.line_dash_offset)

        if self.preview_id is None:
            self.preview_id = app.canvas.create_line(x1, y1, x2, y2, **opts)
        else:
            app.canvas.coords(self.preview_id, x1, y1, x2, y2)
            reapply: dict[str, Any] = {k: v for k, v in opts.items() if k != "tags"}
            app.canvas.itemconfig(self.preview_id, **reapply)
            app.canvas.tag_raise(L_PREV)

    def _commit_segment(self, app: Applike, x2: int, y2: int, evt: tk.Event | None = None):
        if not self.start:
            return
        if evt is not None and self._dir_snap_on(app, evt):
            x2, y2 = self._snap_directional(app, x2, y2, self.start)

        if x2 == self.start.x and y2 == self.start.y:
            self._clear_preview(app)
            self.start = None
            app.status.temp("Ignored zero-length segment", ms=1000, priority=50, side="left")
            return

        params = app.params
        ln = Line(
            x1=self.start.x,
            y1=self.start.y,
            x2=x2,
            y2=y2,
            col=params.brush_colour,
            width=params.brush_width,
            capstyle=self.start.capstyle,
            style=params.line_style,
            dash_offset=params.line_dash_offset,
        )
        app.cmd.push_and_do(Add_Line(params, ln, on_after=lambda: app.layers_redraw("lines")))
        app.mark_dirty()
        self._clear_preview(app)
        self.start = None

    def _dir_snap_on(self, app: Applike, evt: tk.Event) -> bool:
        """Return True if direction snapping should be applied for this event."""
        base = app.snapping()  # your UI toggle
        shift = bool(getattr(evt, "state", 0) & SHIFT_MASK)
        return (not base) if shift else base  # Shift inverts

    def _snap_directional(self, app: Applike, x: int, y: int, start: Point) -> tuple[int, int]:
        """
        Snap (x,y) to grid/clamp, then constrain the vector from start -> (x,y)
        to the nearest 45° octant. Finally re-snap/clamp to grid.
        """
        # 1) normal grid snap + clamp
        sx, sy = self._snap(app, x, y)

        dx, dy = sx - start.x, sy - start.y
        if dx == 0 and dy == 0:
            return sx, sy

        # 2) quantise angle to nearest 45°
        ang = math.atan2(dy, dx)  # [-pi, pi]
        step = math.pi / 4.0  # 45°
        qang = round(ang / step) * step  # nearest octant

        # keep the same length (in pixels)
        r = math.hypot(dx, dy)
        qx = start.x + r * math.cos(qang)
        qy = start.y + r * math.sin(qang)

        # 3) final snap/clamp to grid/canvas (and cast to int)
        qxs, qys = self._snap(app, int(round(qx)), int(round(qy)))
        return qxs, qys

    # --- Tool interface ---
    def on_press(self, app: Applike, evt: tk.Event):
        x, y = self._snap(app, evt.x, evt.y)
        if app.drag_to_draw():
            # drag mode: press sets start; release will commit
            if self.start is None:
                self.start = Point(x, y)
                self._is_dragging = True
                r = max(2, app.params.brush_width // 2)
                app.canvas.create_oval(
                    x - r, y - r, x + r, y + r, outline="", fill=app.params.brush_colour.hex, tags=(L_PREV,)
                )
        else:
            # click-click: press toggles between set-start and commit
            if self.start is None:
                self.start = Point(x, y)
                r = max(2, app.params.brush_width // 2)
                app.canvas.create_oval(
                    x - r, y - r, x + r, y + r, outline="", fill=app.params.brush_colour.hex, tags=(L_PREV,)
                )
            else:
                # second click commits at this snapped press position
                self._commit_segment(app, x, y, evt)

    def on_motion(self, app: Applike, evt: tk.Event):
        if self.start is None:
            return
        x2, y2 = self._snap(app, evt.x, evt.y)
        self._update_preview_to(app, x2, y2, evt)
        app.status.hold("drawline", f"({self.start.x},{self.start.y}) → ({x2},{y2})")

    def on_hover(self, app: Applike, evt: tk.Event):
        if self.start is None or app.drag_to_draw():
            return
        x2, y2 = self._snap(app, evt.x, evt.y)
        self._update_preview_to(app, x2, y2, evt)
        app.status.hold("drawline", f"({self.start.x},{self.start.y}) → ({x2},{y2})")

    def on_release(self, app: Applike, evt: tk.Event):
        if self.start is None:
            return
        if app.drag_to_draw():
            x2, y2 = self._snap(app, evt.x, evt.y)
            self._commit_segment(app, x2, y2, evt)
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
    name: str = "label"
    cursor: str | None = "xterm"

    def on_press(self, app: Applike, evt: tk.Event):
        x, y = app.snap(evt.x, evt.y)
        text = app.prompt_text("New Label", "Text:")
        if not text:
            return
        lab = Label(x=x, y=y, text=text, col=app.params.brush_colour, size=12)
        app.cmd.push_and_do(Add_Label(app.params, lab, on_after=lambda: app.layers_redraw("labels")))
        app.mark_dirty()
        app.status.temp(f"Label @ ({x},{y})")

    def on_motion(self, app: Applike, evt: tk.Event): ...
    def on_release(self, app: Applike, evt: tk.Event): ...
    def on_cancel(self, app: Applike): ...


# ---- IconTool ----
@dataclass
class Icon_Tool:
    get_icon_name: Callable
    name: str = "icon"
    cursor: str | None = "hand2"

    def on_press(self, app: Applike, e: tk.Event):
        x, y = app.snap(e.x, e.y)
        ico = Icon(x=x, y=y, name=self.get_icon_name(), col=app.params.brush_colour, size=16, rotation=0)
        app.cmd.push_and_do(Add_Icon(app.params, ico, on_after=lambda: app.layers_redraw("icons")))
        app.mark_dirty()
        app.status.temp(f"Icon @ ({x},{y})")

    def on_motion(self, app: Applike, e: tk.Event): ...
    def on_release(self, app: Applike, e: tk.Event): ...
    def on_cancel(self, app: Applike): ...


# ---- SelectTool (drag labels/icons) ----
@dataclass
class Select_Tool:
    name: str = "select"
    cursor: str | None = "arrow"
    _drag_kind: Literal["label", "icon", "line", ""] = ""
    _drag_canvas_id: int | None = None  # for labels
    _drag_index: int | None = None  # model index for the selection
    _drag_icon_ids: tuple[int, ...] | None = None  # concrete item ids of the icon
    _start_xy: tuple[int, int] | None = None
    _press_center: tuple[int, int] | None = None
    _dragged: bool = False

    def _centre_of_tag(self, canvas: tk.Canvas, tag: str) -> tuple[int, int] | None:
        bbox = canvas.bbox(tag) or (lambda ids: canvas.bbox(ids[0]) if ids else None)(canvas.find_withtag(tag))
        if not bbox:
            return None
        return ((bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2)

    def on_press(self, app: Applike, evt: tk.Event):
        hit = test_hit(app.canvas, evt.x, evt.y)
        self._dragged = False
        self._press_center = None

        if not hit:
            self._drag_kind = ""
            self._drag_canvas_id = None
            self._drag_index = None
            self._drag_icon_ids = None
            self._start_xy = None
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
        self._start_xy = (evt.x, evt.y)

        if self._drag_kind == "icon" and self._drag_index is not None:
            tag = f"icon:{self._drag_index}"
            self._drag_icon_ids = tuple(app.canvas.find_withtag(tag))
            centre = self._centre_of_tag(app.canvas, tag)
            if centre:
                self._press_center = centre
        elif self._drag_kind == "label" and self._drag_canvas_id is not None:
            coords = app.canvas.coords(self._drag_canvas_id)
            if coords:
                self._press_center = (int(round(coords[0])), int(round(coords[1])))

    def on_motion(self, app: Applike, evt: tk.Event):
        if not self._start_xy or not self._drag_kind:
            return
        dx, dy = evt.x - self._start_xy[0], evt.y - self._start_xy[1]
        if dx or dy:
            self._dragged = True
        if self._drag_kind == "label" and self._drag_canvas_id is not None:
            app.canvas.move(self._drag_canvas_id, dx, dy)
        elif self._drag_kind == "icon" and self._drag_index is not None:
            app.canvas.move(f"icon:{self._drag_index}", dx, dy)
        self._start_xy = (evt.x, evt.y)

    def on_release(self, app: Applike, e: tk.Event):
        try:
            app.canvas.grab_release()
        except tk.TclError:
            pass
        if not self._drag_kind:
            return

        if self._drag_kind == "label":
            cid = int(self._drag_canvas_id or 0)
            coords = app.canvas.coords(cid)
            end_center = (int(round(coords[0])), int(round(coords[1]))) if coords else (e.x, e.y)

            if not (self._dragged and self._moved_enough(self._press_center, end_center)):
                # click only → do nothing; keep off-grid positions
                self._reset()
                return

            sx, sy = self._maybe_snap_point(
                app, end_center[0], end_center[1], kind="label", index=self._label_index_from_canvas(app, cid)
            )
            idx = self._label_index_from_canvas(app, cid)
            old = (app.params.labels[idx].x, app.params.labels[idx].y)
            if (sx, sy) != old:
                app.cmd.push_and_do(
                    Move_Label(app.params, idx, old, (sx, sy), on_after=lambda: app.layers_redraw("labels"))
                )
                app.mark_dirty()
            else:
                app.layers_redraw("labels")

        elif self._drag_kind == "icon":
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
                    end_center = ((bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2)
                else:
                    end_center = (e.x, e.y)
            else:
                end_center = (e.x, e.y)

            if not (self._dragged and self._moved_enough(self._press_center, end_center)):
                self._reset()
                return

            # resolve model index from dragged ids
            idx = self._infer_index_from_ids(app.canvas, self._drag_icon_ids or (), "icon")
            if idx is None:
                idx = self._nearest_icon_index(app, end_center[0], end_center[1])
                if idx is None:
                    self._reset()
                    return

            sx, sy = self._maybe_snap_point(app, end_center[0], end_center[1], kind="icon", index=idx)
            old = (app.params.icons[idx].x, app.params.icons[idx].y)
            if (sx, sy) != old:
                app.cmd.push_and_do(
                    Move_Icon(app.params, idx, old, (sx, sy), on_after=lambda: app.layers_redraw("icons"))
                )
                app.mark_dirty()
            else:
                app.layers_redraw("icons")

        self._reset()

    def on_cancel(self, app: Applike):
        self._reset()

    def _reset(self):
        self._drag_kind = ""
        self._drag_canvas_id = None
        self._drag_index = None
        self._drag_icon_ids = None
        self._start_xy = None
        self._press_center = None
        self._dragged = False

    # helper: map canvas text id -> label index (rebuild cheaply)
    def _label_index_from_canvas(self, app: Applike, cid: int) -> int:
        # rebuild a fresh map (labels aren't huge)
        # draw order matches params.labels order in painters, but ids differ per redraw
        # so we re-hit labels by position/text match:
        tags = app.canvas.gettags(cid)
        for tag in tags:
            if tag.startswith("label:"):
                return int(tag.split(":", 1)[1])

        x, y = app.canvas.coords(cid)[:2]
        text = app.canvas.itemcget(cid, "text")
        for i, lab in enumerate(app.params.labels):
            if lab.text == text and abs(lab.x - x) < 2 and abs(lab.y - y) < 2:
                return i
        # fallback: nearest by distance
        best_i, best_d = 0, 1e9
        for i, lab in enumerate(app.params.labels):
            d = (lab.x - x) ** 2 + (lab.y - y) ** 2
            if d < best_d:
                best_d, best_i = d, i
        return best_i

    def _infer_index_from_ids(self, canvas: tk.Canvas, ids: tuple[int, ...], prefix: str) -> int | None:
        """Return the most common '<prefix>:K' tag index across these item ids."""
        counts: dict[int, int] = {}
        needle = prefix + ":"
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

    def _nearest_icon_index(self, app: Applike, cx: int, cy: int) -> int | None:
        best_i, best_d = None, float("inf")
        for i, ico in enumerate(app.params.icons):
            d = (ico.x - cx) * (ico.x - cx) + (ico.y - cy) * (ico.y - cy)
            if d < best_d:
                best_d, best_i = d, i
        return best_i

    def _moved_enough(self, a: tuple[int, int] | None, b: tuple[int, int] | None, tol: int = 1) -> bool:
        if not a or not b:
            return False
        return abs(a[0] - b[0]) > tol or abs(a[1] - b[1]) > tol

    def _snap_enabled_for(self, app: Applike, evt: tk.Event | None, kind: str, index: int) -> bool:
        # App-wide toggle
        base = app.snapping()
        # Ctrl inverts (hold to bypass, or hold to force if base==False)
        ctrl = (getattr(evt, "state", 0) & 0x0004) != 0  # ControlMask bit on X11/Windows; tweak on mac if needed
        want = base ^ ctrl
        # Per-object preference (only matters if want==True)
        if not want:
            return False
        if kind == "label":
            return bool(getattr(app.params.labels[index], "snap", True))
        if kind == "icon":
            return bool(getattr(app.params.icons[index], "snap", True))
        return True

    def _maybe_snap_point(self, app: Applike, x: int, y: int, *, kind: str, index: int, evt: tk.Event | None = None):
        if self._snap_enabled_for(app, evt, kind, index):
            return app.snap(x, y)
        return (x, y)

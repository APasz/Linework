from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Protocol, Literal, Optional

import tkinter as tk

from models.params import Params
from models.geo import Line, Point
from models.objects import Label, Icon
from canvas.hit_test import hit_under_cursor
from controllers.commands import CommandStack, AddLine, AddLabel, AddIcon, MoveLabel, MoveIcon
from canvas.layers import L_PREV


# --- minimal app protocol the tools need ---
class AppLike(Protocol):
    root: tk.Tk
    canvas: tk.Canvas
    params: Params
    cmd: CommandStack
    status: tk.StringVar

    def snap(self, x: int, y: int) -> tuple[int, int]: ...
    def layers_redraw(self, *layers: str) -> None: ...  # delegate to LayerManager
    def prompt_text(self, title: str, prompt: str) -> Optional[str]: ...


# ---- base tool ----
class Tool(Protocol):
    name: str
    cursor: str | None

    def on_press(self, app: AppLike, e: tk.Event) -> None: ...
    def on_motion(self, app: AppLike, e: tk.Event) -> None: ...
    def on_release(self, app: AppLike, e: tk.Event) -> None: ...
    def on_cancel(self, app: AppLike) -> None: ...


# ---- DrawTool ----
class DrawTool(Tool):
    cursor = "crosshair"

    def __init__(self):
        self.start: Point | None = None
        self.preview_id: int | None = None

    # --- utilities ---
    def _snap(self, app: AppLike, x: int, y: int) -> tuple[int, int]:
        g = app.params.grid_size
        if g <= 0:
            return x, y
        return (round(x / g) * g, round(y / g) * g)

    def _clear_preview(self, app: AppLike):
        if self.preview_id:
            app.canvas.delete(self.preview_id)
            self.preview_id = None
        # belt & braces if something leaked:
        app.layers.clear_preview()

    def _update_preview(self, app: AppLike, x2: int, y2: int):
        """Create or move the temporary rubber-band line."""
        p = app.params
        x1, y1 = self.start.x, self.start.y
        if self.preview_id is None:
            self.preview_id = app.canvas.create_line(
                x1,
                y1,
                x2,
                y2,
                fill=p.brush_color.hex,
                width=p.brush_width,
                capstyle=self.start.capstyle,
                tags=(L_PREV,),
            )
        else:
            app.canvas.coords(self.preview_id, x1, y1, x2, y2)
            # in case something else was drawn after it:
            app.canvas.tag_raise(L_PREV)

    # --- Tool interface ---
    def on_press(self, app: AppLike, e):
        x, y = self._snap(app, e.x, e.y)
        if self.start is None:
            # first click -> set start & seed a dot if you like
            self.start = Point(x, y)
            # optional marker at the first point:
            r = max(2, app.params.brush_width // 2)
            app.canvas.create_oval(
                x - r, y - r, x + r, y + r, outline="", fill=app.params.brush_color.hex, tags=(L_PREV,)
            )
        else:
            # second click behaves like release
            self.on_release(app, e)

    def on_motion(self, app: AppLike, e):
        # plain <Motion> OR <B1-Motion> both land here; we only care if we have a start
        if self.start is None:
            return
        x2, y2 = self._snap(app, e.x, e.y)
        self._update_preview(app, x2, y2)

    def on_release(self, app: AppLike, e):
        if self.start is None:
            return
        x2, y2 = self._snap(app, e.x, e.y)

        # finalize: create command and clear preview
        p = app.params
        ln = Line(
            x1=self.start.x,
            y1=self.start.y,
            x2=x2,
            y2=y2,
            col=p.brush_color,
            width=p.brush_width,
            capstyle=self.start.capstyle,
        )
        # Use the same pattern as Label/Icon
        app.cmd.push_and_do(AddLine(p, ln, on_after=lambda: app.layers_redraw("lines")))

        self._clear_preview(app)
        self.start = None

    def on_cancel(self, app: AppLike):
        self._clear_preview(app)
        self.start = None


# ---- LabelTool ----
@dataclass
class LabelTool:
    name: str = "label"
    cursor: str | None = "xterm"

    def on_press(self, app: AppLike, e: tk.Event) -> None:
        x, y = app.snap(e.x, e.y)
        text = app.prompt_text("New Label", "Text:")
        if not text:
            return
        lab = Label(x=x, y=y, text=text, col=app.params.brush_color, anchor="nw", size=12)
        app.cmd.push_and_do(AddLabel(app.params, lab, on_after=lambda: app.layers_redraw("labels")))
        app.status.set(f"Placed label at ({x},{y})")

    def on_motion(self, app: AppLike, e: tk.Event) -> None: ...
    def on_release(self, app: AppLike, e: tk.Event) -> None: ...
    def on_cancel(self, app: AppLike) -> None: ...


# ---- IconTool ----
@dataclass
class IconTool:
    get_icon_name: Callable  # e.g., lambda: self.var_icon.get()
    name: str = "icon"
    cursor: str | None = "hand2"

    def on_press(self, app: AppLike, e: tk.Event) -> None:
        x, y = app.snap(e.x, e.y)
        ico = Icon(x=x, y=y, name=self.get_icon_name(), col=app.params.brush_color, size=16, rotation=0)
        app.cmd.push_and_do(AddIcon(app.params, ico, on_after=lambda: app.layers_redraw("icons")))
        app.status.set(f"Placed icon at ({x},{y})")

    def on_motion(self, app: AppLike, e: tk.Event) -> None: ...
    def on_release(self, app: AppLike, e: tk.Event) -> None: ...
    def on_cancel(self, app: AppLike) -> None: ...


# ---- SelectTool (drag labels/icons) ----
@dataclass
class SelectTool:
    name: str = "select"
    cursor: str | None = "arrow"
    _drag_kind: Literal["label", "icon", ""] = ""
    _drag_token: int | None = None
    _start_xy: tuple[int, int] | None = None

    def on_press(self, app: AppLike, e: tk.Event) -> None:
        hit = hit_under_cursor(app.canvas, e.x, e.y)
        if not hit:
            self._drag_kind = ""
            return
        self._drag_kind = hit.kind  # pyright: ignore[reportAttributeAccessIssue]
        self._drag_token = hit.token
        self._start_xy = (e.x, e.y)

    def on_motion(self, app: AppLike, e: tk.Event) -> None:
        if not self._start_xy or not self._drag_kind:
            return
        dx, dy = e.x - self._start_xy[0], e.y - self._start_xy[1]
        if self._drag_kind == "label":
            app.canvas.move(self._drag_token, dx, dy)  # token is canvas id
        elif self._drag_kind == "icon":
            tag = f"icon:{self._drag_token}"  # token is index
            app.canvas.move(tag, dx, dy)
        self._start_xy = (e.x, e.y)

    def on_release(self, app: AppLike, e: tk.Event) -> None:
        if not self._drag_kind:
            return
        # compute snapped destination and write a Move* command
        if self._drag_kind == "label":
            cid = int(self._drag_token or 1)
            x, y = app.canvas.coords(cid)[:2]
            sx, sy = app.snap(int(round(x)), int(round(y)))
            # read old model pos
            idx = self._label_index_from_canvas(app, cid)
            old = (app.params.labels[idx].x, app.params.labels[idx].y)
            if (sx, sy) != old:
                app.cmd.push_and_do(
                    MoveLabel(app.params, idx, old, (sx, sy), on_after=lambda: app.layers_redraw("labels"))
                )
            else:
                app.layers_redraw("labels")  # just normalize coords
        elif self._drag_kind == "icon":
            idx = int(self._drag_token or 1)
            bbox = app.canvas.bbox(f"icon:{idx}")
            cx = (bbox[0] + bbox[2]) // 2
            cy = (bbox[1] + bbox[3]) // 2
            sx, sy = app.snap(cx, cy)
            old = (app.params.icons[idx].x, app.params.icons[idx].y)
            if (sx, sy) != old:
                app.cmd.push_and_do(
                    MoveIcon(app.params, idx, old, (sx, sy), on_after=lambda: app.layers_redraw("icons"))
                )
            else:
                app.layers_redraw("icons")

        self._drag_kind = ""
        self._drag_token = None
        self._start_xy = None

    def on_cancel(self, app: AppLike) -> None:
        self._drag_kind = ""
        self._drag_token = None
        self._start_xy = None

    # helper: map canvas text id -> label index (rebuild cheaply)
    def _label_index_from_canvas(self, app: AppLike, cid: int) -> int:
        # rebuild a fresh map (labels aren't huge)
        # draw order matches params.labels order in painters, but ids differ per redraw
        # so we re-hit labels by position/text match:
        tags = app.canvas.gettags(cid)
        for t in tags:
            if t.startswith("label:"):
                return int(t.split(":", 1)[1])

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

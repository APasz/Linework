from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Protocol, Literal, Optional

import tkinter as tk

from models.params import Params
from models.geo import Line, Point
from models.objects import Label, Icon
from canvas.hit_test import hit_under_cursor
from controllers.commands import CommandStack, AddLine, AddLabel, AddIcon, MoveLabel, MoveIcon


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
@dataclass
class DrawTool:
    name: str = "draw"
    cursor: str | None = "crosshair"
    _pending: Optional[Point] = None

    def on_press(self, app: AppLike, e: tk.Event) -> None:
        x, y = app.snap(e.x, e.y)
        if self._pending is None:
            self._pending = Point(x, y)
            r = max(2, app.params.brush_width // 2)
            app.canvas.create_oval(
                x - r, y - r, x + r, y + r, outline="", fill=app.params.brush_color.hex, tags=("temp:dot",)
            )
            app.status.set(f"First point set at ({x},{y}). Click another point")
        else:
            p = self._pending
            ln = Line(p.x, p.y, x, y, app.params.brush_color, app.params.brush_width, p.capstyle)
            app.cmd.push_and_do(AddLine(app.params, ln, on_after=lambda: app.layers_redraw("lines")))
            self._pending = None
            app.canvas.delete("temp:dot")
            app.status.set(f"Drew line: ({p.x},{p.y}) -> ({x},{y})")

    def on_motion(self, app: AppLike, e: tk.Event) -> None:
        pass

    def on_release(self, app: AppLike, e: tk.Event) -> None:
        pass

    def on_cancel(self, app: AppLike) -> None:
        self._pending = None
        app.canvas.delete("temp:dot")
        app.status.set("Ready")


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

from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, Literal

import tkinter as tk

from models.params import Params
from models.geo import Line, Point
from models.objects import Label, Icon
from canvas.hit_test import hit_under_cursor
from controllers.commands import CommandStack, AddLine, AddLabel, AddIcon, MoveLabel, MoveIcon
from canvas.layers import L_PREV, LayerManager, LayerName


# --- minimal app protocol the tools need ---
class AppLike(Protocol):
    root: tk.Tk
    canvas: tk.Canvas
    params: Params
    cmd: CommandStack
    status: tk.StringVar
    layers: LayerManager

    def snap(self, x: int, y: int, /) -> tuple[int, int]: ...
    def layers_redraw(self, *layers: LayerName) -> None: ...
    def prompt_text(self, title: str, prompt: str, /) -> str | None: ...
    def drag_to_draw(self) -> bool: ...


# ---- base tool ----
class Tool(Protocol):
    name: str
    cursor: str | None

    def on_press(self, app: AppLike, evt: tk.Event, /) -> None: ...
    def on_motion(self, app: AppLike, evt: tk.Event, /) -> None: ...
    def on_release(self, app: AppLike, evt: tk.Event, /) -> None: ...
    def on_cancel(self, app: AppLike) -> None: ...


# ---- DrawTool ----
# controllers/tools.py
class DrawTool(Tool):
    name = "draw"
    cursor = "crosshair"

    def __init__(self):
        self.start: Point | None = None
        self.preview_id: int | None = None
        self._is_dragging: bool = False  # only used in drag-to-draw mode

    # --- utilities ---
    def _snap(self, app: AppLike, x: int, y: int) -> tuple[int, int]:
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

    def _clear_preview(self, app: AppLike):
        if self.preview_id:
            app.canvas.delete(self.preview_id)
            self.preview_id = None
        app.layers.clear_preview()

    def _update_preview_to(self, app: AppLike, x2: int, y2: int):
        if not self.start:
            return
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
            app.canvas.tag_raise(L_PREV)

    def _commit_segment(self, app: AppLike, x2: int, y2: int):
        if not self.start:
            return
        if x2 == self.start.x and y2 == self.start.y:
            self._clear_preview(app)
            self.start = None
            app.status.set("Ignored zero-length segment")
            return
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
        app.cmd.push_and_do(AddLine(p, ln, on_after=lambda: app.layers_redraw("lines")))
        self._clear_preview(app)
        self.start = None

    # --- Tool interface ---
    def on_press(self, app: AppLike, evt: tk.Event):
        x, y = self._snap(app, evt.x, evt.y)
        if app.drag_to_draw():
            # drag mode: press sets start; release will commit
            if self.start is None:
                self.start = Point(x, y)
                self._is_dragging = True
                r = max(2, app.params.brush_width // 2)
                app.canvas.create_oval(
                    x - r, y - r, x + r, y + r, outline="", fill=app.params.brush_color.hex, tags=(L_PREV,)
                )
            # if already have start, ignore extra presses; release will handle
        else:
            # click-click: press toggles between set-start and commit
            if self.start is None:
                self.start = Point(x, y)
                r = max(2, app.params.brush_width // 2)
                app.canvas.create_oval(
                    x - r, y - r, x + r, y + r, outline="", fill=app.params.brush_color.hex, tags=(L_PREV,)
                )
            else:
                # second click commits at this snapped press position
                self._commit_segment(app, x, y)

    def on_motion(self, app: AppLike, evt: tk.Event):
        if self.start is None:
            return
        if app.drag_to_draw():
            # only preview while dragging (B1-Motion)
            x2, y2 = self._snap(app, evt.x, evt.y)
            self._update_preview_to(app, x2, y2)
            app.status.set(f"Drew line: ({self.start.x},{self.start.y}) -> ({x2},{y2})")

    # optional: for click-click, preview while hovering between clicks
    def on_hover(self, app: AppLike, evt: tk.Event):
        if self.start is None or app.drag_to_draw():
            return
        x2, y2 = self._snap(app, evt.x, evt.y)
        self._update_preview_to(app, x2, y2)
        app.status.set(f"Drew line: ({self.start.x},{self.start.y}) -> ({x2},{y2})")

    def on_release(self, app: AppLike, evt: tk.Event):
        if self.start is None:
            return
        if app.drag_to_draw():
            # commit to release position
            x2, y2 = self._snap(app, evt.x, evt.y)
            self._commit_segment(app, x2, y2)
            self._is_dragging = False
        else:
            # click-click: release does nothing (press does the work)
            pass

    def on_cancel(self, app: AppLike):
        self._clear_preview(app)
        self.start = None
        self._is_dragging = False


# ---- LabelTool ----
@dataclass
class LabelTool:
    name: str = "label"
    cursor: str | None = "xterm"

    def on_press(self, app: AppLike, evt: tk.Event) -> None:
        x, y = app.snap(evt.x, evt.y)
        text = app.prompt_text("New Label", "Text:")
        if not text:
            return
        lab = Label(x=x, y=y, text=text, col=app.params.brush_color, size=12)
        app.cmd.push_and_do(AddLabel(app.params, lab, on_after=lambda: app.layers_redraw("labels")))
        app.status.set(f"Placed label at ({x},{y})")

    def on_motion(self, app: AppLike, evt: tk.Event) -> None: ...
    def on_release(self, app: AppLike, evt: tk.Event) -> None: ...
    def on_cancel(self, app: AppLike) -> None: ...


# ---- IconTool ----
@dataclass
class IconTool:
    get_icon_name: Callable
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
            # clicked empty space -> abort any pending drag
            self._drag_kind = ""
            self._drag_token = None
            self._start_xy = None
            return
        # ensure release comes back to this canvas
        app.canvas.focus_set()
        try:
            app.canvas.grab_set()
        except tk.TclError:
            pass

        self._drag_kind = hit.kind  # pyright: ignore[reportAttributeAccessIssue] # "label" | "icon"
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
        # always release the grab so the pointer is “dropped”
        try:
            app.canvas.grab_release()
        except tk.TclError:
            pass

        if not self._drag_kind:
            return

        if self._drag_kind == "label":
            cid = int(self._drag_token or 1)
            coords = app.canvas.coords(cid)
            if coords:
                x, y = coords[:2]
                sx, sy = app.snap(int(round(x)), int(round(y)))
            else:
                # label item not found (e.g., layer redraw); use pointer
                sx, sy = app.snap(e.x, e.y)

            idx = self._label_index_from_canvas(app, cid)
            old = (app.params.labels[idx].x, app.params.labels[idx].y)
            if (sx, sy) != old:
                app.cmd.push_and_do(
                    MoveLabel(app.params, idx, old, (sx, sy), on_after=lambda: app.layers_redraw("labels"))
                )
            else:
                app.layers_redraw("labels")

        elif self._drag_kind == "icon":
            # 1) start from the index we captured on press
            idx = int(self._drag_token or -1)

            def _valid(i: int) -> bool:
                return 0 <= i < len(app.params.icons)

            # 2) if it's no longer valid, attempt to re-derive from tags under cursor
            if not _valid(idx):
                derived = None
                for item in app.canvas.find_withtag("current"):
                    for t in app.canvas.gettags(item):
                        if t.startswith("icon:"):
                            try:
                                cand = int(t.split(":", 1)[1])
                                if _valid(cand):
                                    derived = cand
                                    break
                            except ValueError:
                                pass
                    if derived is not None:
                        break
                if derived is None:
                    # last resort: scan any icon tag present on the canvas
                    for item in app.canvas.find_withtag("icon"):
                        for t in app.canvas.gettags(item):
                            if t.startswith("icon:"):
                                try:
                                    cand = int(t.split(":", 1)[1])
                                    if _valid(cand):
                                        derived = cand
                                        break
                                except ValueError:
                                    pass
                        if derived is not None:
                            break
                if derived is None:
                    # we can't resolve a valid model index; normalize redraw and abort
                    app.layers_redraw("icons")
                    self._drag_kind = ""
                    self._drag_token = None
                    self._start_xy = None
                    return
                idx = derived

            tag = f"icon:{idx}"

            # 3) compute final center safely
            bbox = app.canvas.bbox(tag)
            if bbox is None:
                ids = app.canvas.find_withtag(tag)
                if ids:
                    bbox = app.canvas.bbox(ids[0])

            if bbox is None:
                # fallback to mouse position
                cx, cy = e.x, e.y
            else:
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

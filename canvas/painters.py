from __future__ import annotations
import tkinter as tk
from typing import Protocol
from canvas.layers import L_GRID, L_LINES, L_LABELS, L_ICONS
from models.params import Params
from models.geo import Line
from models.objects import Label, Icon


class Scene(Protocol):
    params: Params

    def lines(self) -> list[Line]: ...
    def labels(self) -> list[Label]: ...
    def icons(self) -> list[Icon]: ...


class PaintersImpl:
    """Stateless-ish painters that read from a scene (wrapping your Params)."""

    def __init__(self, scene: Scene):
        self.s = scene

    # ------- grid -------
    def paint_grid(self, canvas: tk.Canvas) -> None:
        p = self.s.params
        g = p.grid_size
        if g <= 0:
            return
        w, h = p.width, p.height
        for x in range(0, w + 1, g):
            canvas.create_line(x, 0, x, h, fill=p.grid_colour.hex, tags=(L_GRID,))
        for y in range(0, h + 1, g):
            canvas.create_line(0, y, w, y, fill=p.grid_colour.hex, tags=(L_GRID,))
        canvas.tag_lower(L_GRID)

    # ------- lines -------
    def paint_lines(self, canvas: tk.Canvas) -> None:
        for ln in self.s.lines():
            canvas.create_line(
                ln.x1,
                ln.y1,
                ln.x2,
                ln.y2,
                fill=ln.col.hex,
                width=ln.width,
                capstyle=ln.capstyle,
                tags=("line", L_LINES),
            )

    # ------- labels -------
    def paint_labels(self, canvas: tk.Canvas) -> None:
        for idx, lab in enumerate(self.s.labels()):
            canvas.create_text(
                lab.x,
                lab.y,
                text=lab.text,
                fill=lab.col.hex,
                anchor=lab.anchor,
                font=("TkDefaultFont", lab.size),
                tags=("label", L_LABELS, f"label:{idx}"),
            )

    # ------- icons -------
    def paint_icons(self, canvas: tk.Canvas) -> None:
        for idx, ico in enumerate(self.s.icons()):
            self._paint_icon(canvas, ico, idx)

    def _paint_icon(self, canvas: tk.Canvas, ico: Icon, idx: int) -> None:
        tag = f"icon:{idx}"
        s, x, y, col = ico.size, ico.x, ico.y, ico.col.hex
        if ico.name == "signal":
            r = s // 2
            canvas.create_oval(x - r, y - r, x + r, y + r, fill=col, outline="", tags=(tag, "icon", L_ICONS))
            canvas.create_rectangle(
                x - r // 3, y + r, x + r // 3, y + s, fill=col, outline="", tags=(tag, "icon", L_ICONS)
            )
        elif ico.name == "buffer":
            w = s
            h = s // 2
            canvas.create_rectangle(
                x - w // 2, y - h // 2, x + w // 2, y + h // 2, outline=col, width=2, tags=(tag, "icon", L_ICONS)
            )
        elif ico.name == "crossing":
            L = s
            canvas.create_line(x - L, y - L, x + L, y + L, fill=col, width=2, tags=(tag, "icon", L_ICONS))
            canvas.create_line(x - L, y + L, x + L, y - L, fill=col, width=2, tags=(tag, "icon", L_ICONS))
        elif ico.name == "switch":
            L = s
            canvas.create_line(x, y, x + L, y, fill=col, width=2, tags=(tag, "icon", L_ICONS))
            canvas.create_line(x, y, x + L, y + L // 2, fill=col, width=2, tags=(tag, "icon", L_ICONS))
        else:
            r = s // 3
            canvas.create_oval(x - r, y - r, x + r, y + r, fill=col, outline="", tags=(tag, "icon", L_ICONS))

from __future__ import annotations

import math
import tkinter as tk
from typing import Protocol

from canvas.layers import L_GRID, L_ICONS, L_LABELS, L_LINES
from models.geo import Line
from models.linestyle import scaled_pattern
from models.objects import Icon, Label
from models.params import Params


class Scene(Protocol):
    params: Params

    def lines(self) -> list[Line]: ...
    def labels(self) -> list[Label]: ...
    def icons(self) -> list[Icon]: ...


# ------- helpers -------
def _rot(x: float, y: float, cx: float, cy: float, deg: float) -> tuple[float, float]:
    r = math.radians(deg)
    dx, dy = x - cx, y - cy
    cs, sn = math.cos(r), math.sin(r)
    return (cx + dx * cs - dy * sn, cy + dx * sn + dy * cs)


class Painters_Impl:
    """Stateless-ish painters that read from a scene (wrapping Params)"""

    def __init__(self, scene: Scene):
        self.s = scene

    # ------- grid -------
    def paint_grid(self, canvas: tk.Canvas):
        p = self.s.params
        g = p.grid_size
        if not p.grid_visible or g <= 0:
            return

        w, h = p.width, p.height
        for x in range(0, w + 1, g):
            canvas.create_line(x, 0, x, h, fill=p.grid_colour.hex, tags=(L_GRID,))
        for y in range(0, h + 1, g):
            canvas.create_line(0, y, w, y, fill=p.grid_colour.hex, tags=(L_GRID,))
        canvas.tag_lower(L_GRID)

    # ------- lines -------
    def paint_lines(self, canvas: tk.Canvas):
        for idx, lin in enumerate(self.s.lines()):
            self._paint_line(canvas, lin, idx)

    def _paint_line(self, canvas: tk.Canvas, lin: Line, idx: int):
        tag = ("line", L_LINES, f"line:{idx}")
        canvas.create_line(
            lin.a.x,
            lin.a.y,
            lin.b.x,
            lin.b.y,
            fill=lin.col.hex,
            width=lin.width,
            capstyle=lin.capstyle.value,
            dash=scaled_pattern(getattr(lin, "style", None), lin.width) or [],
            tags=tag,
        )

    # ------- labels -------
    def paint_labels(self, canvas: tk.Canvas):
        for idx, lab in enumerate(self.s.labels()):
            self._paint_label(canvas, lab, idx)

    def _paint_label(self, canvas: tk.Canvas, lab: Label, idx: int):
        tag = ("label", L_LABELS, f"label:{idx}")
        canvas.create_text(
            lab.x,
            lab.y,
            text=lab.text,
            fill=lab.col.hex,
            anchor=lab.anchor.tk,
            font=("TkDefaultFont", lab.size),
            angle=lab.rotation,
            tags=tag,
        )

    # ------- icons -------
    def paint_icons(self, canvas: tk.Canvas):
        for idx, ico in enumerate(self.s.icons()):
            self._paint_icon(canvas, ico, idx)

    def _paint_icon(self, canvas: tk.Canvas, ico: Icon, idx: int):
        tag = ("icon", L_ICONS, f"icon:{idx}")
        s, x, y, col = ico.size, ico.x, ico.y, ico.col.hex
        x, y, s, col, rot = ico.x, ico.y, ico.size, ico.col.hex, float(ico.rotation or 0)
        if ico.name == "signal":
            r = s // 2
            canvas.create_oval(x - r, y - r, x + r, y + r, fill=col, outline="", tags=tag)
            mx0, my0 = x - r // 3, y + r
            mx1, my1 = x + r // 3, y + r
            mx2, my2 = x + r // 3, y + s
            mx3, my3 = x - r // 3, y + s
            parts = [_rot(px, py, x, y, rot) for (px, py) in [(mx0, my0), (mx1, my1), (mx2, my2), (mx3, my3)]]
            canvas.create_polygon(*sum(parts, ()), fill=col, outline="", tags=tag)
        elif ico.name == "buffer":
            w, h = s, s // 2
            corners = [
                (x - w // 2, y - h // 2),
                (x + w // 2, y - h // 2),
                (x + w // 2, y + h // 2),
                (x - w // 2, y + h // 2),
            ]
            pts = [_rot(px, py, x, y, rot) for (px, py) in corners]
            canvas.create_polygon(*sum(pts, ()), outline=col, width=2, fill="", tags=tag)

        elif ico.name == "crossing":
            L = s
            x1, y1 = _rot(x - L, y - L, x, y, rot)
            x2, y2 = _rot(x + L, y + L, x, y, rot)
            x3, y3 = _rot(x - L, y + L, x, y, rot)
            x4, y4 = _rot(x + L, y - L, x, y, rot)
            canvas.create_line(x1, y1, x2, y2, fill=col, width=2, tags=tag)
            canvas.create_line(x3, y3, x4, y4, fill=col, width=2, tags=tag)

        elif ico.name == "switch":
            L = s
            a1, b1 = _rot(x, y, x, y, rot)
            a2, b2 = _rot(x + L, y, x, y, rot)
            a3, b3 = _rot(x + L, y + L // 2, x, y, rot)
            canvas.create_line(a1, b1, a2, b2, fill=col, width=2, tags=tag)
            canvas.create_line(a1, b1, a3, b3, fill=col, width=2, tags=tag)
        else:
            r = s // 3
            canvas.create_oval(x - r, y - r, x + r, y + r, fill=col, outline="", tags=tag)

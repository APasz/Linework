from __future__ import annotations

from typing import Protocol

from canvas.layers import Layer_Name
from models.geo import CanvasLW, Icon, Label, Line, Point
from models.params import Params
from models.styling import CapStyle


class Scene(Protocol):
    params: Params

    def lines(self) -> list[Line]: ...
    def labels(self) -> list[Label]: ...
    def icons(self) -> list[Icon]: ...


class Painters_Impl:
    """Stateless-ish painters that read from a scene (wrapping Params)"""

    def __init__(self, scene: Scene):
        self.s = scene

    # ------- grid -------
    def paint_grid(self, canvas: CanvasLW):
        params = self.s.params
        g = params.grid_size
        if not params.grid_visible or g <= 0:
            return

        w, h = params.width, params.height
        line = Line(a=Point(x=0, y=0), b=Point(x=0, y=0), col=params.grid_colour, width=1, capstyle=CapStyle.BUTT)

        for x in range(0, w + 1, g):
            canvas.create_with_line(
                line.with_xy(x, 0, x, h),
                override_base_tages=[Layer_Name.grid],  # ensure proper layer
            )
        for y in range(0, h + 1, g):
            canvas.create_with_line(
                line.with_xy(0, y, w, y),
                override_base_tages=[Layer_Name.grid],
            )

    # ------- lines -------
    def paint_lines(self, canvas: CanvasLW):
        for idx, lin in enumerate(self.s.lines()):
            if (lin.a.x, lin.a.y) == (lin.b.x, lin.b.y):
                continue
            self._paint_line(canvas, lin, idx)

    def _paint_line(self, canvas: CanvasLW, lin: Line, idx: int):
        canvas.create_with_line(lin, idx=idx)

    # ------- labels -------
    def paint_labels(self, canvas: CanvasLW):
        for idx, lab in enumerate(self.s.labels()):
            self._paint_label(canvas, lab, idx)

    def _paint_label(self, canvas: CanvasLW, lab: Label, idx: int):
        canvas.create_with_label(lab, idx=idx)

    # ------- icons -------
    def paint_icons(self, canvas: CanvasLW):
        for idx, ico in enumerate(self.s.icons()):
            self._paint_icon(canvas, ico, idx)

    def _paint_icon(self, canvas: CanvasLW, ico: Icon, idx: int):
        canvas.create_with_icon(ico, idx=idx)

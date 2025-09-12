from __future__ import annotations

from canvas.layers import Layer_Name
from models.geo import CanvasLW, Label, Line, Point
from models.params import Params
from models.styling import CapStyle


class Scene:
    def __init__(self, params: Params):
        self.params = params

    def lines(self):
        return self.params.lines

    def labels(self):
        return self.params.labels

    def icons(self):
        return self.params.icons


class Painters:
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
                override_base_tags=[Layer_Name.grid],  # ensure proper layer
            )
        for y in range(0, h + 1, g):
            canvas.create_with_line(
                line.with_xy(0, y, w, y),
                override_base_tags=[Layer_Name.grid],
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

    def _paint_icon(self, canvas: CanvasLW, ico, idx: int):
        canvas.create_with_iconlike(ico, idx=idx)

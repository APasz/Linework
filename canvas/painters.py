from __future__ import annotations
from typing import TYPE_CHECKING

from canvas.layers import Layer_Type
from models.geo import CanvasLW, Label, Line, Point
from models.params import Params
from models.styling import CapStyle

if TYPE_CHECKING:
    from controllers.app import App


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
    def __init__(self, app: App, scene: Scene, canvas: CanvasLW):
        self.app = app
        self.scene = scene
        self.canvas = canvas

    # ------- grid -------
    def paint_grid(self):
        params = self.scene.params
        g = params.grid_size
        if not params.grid_visible or g <= 0:
            return

        w, h = params.width, params.height
        line = Line(a=Point(x=0, y=0), b=Point(x=0, y=0), col=params.grid_colour, width=1, capstyle=CapStyle.BUTT)

        for x in range(0, w + 1, g):
            self.canvas.create_with_line(
                line.with_xy(x, 0, x, h),
                tag_type=Layer_Type.grid,
            )
        for y in range(0, h + 1, g):
            self.canvas.create_with_line(
                line.with_xy(0, y, w, y),
                tag_type=Layer_Type.grid,
            )

    # ------- lines -------
    def paint_lines(self):
        for idx, lin in enumerate(self.scene.lines()):
            if (lin.a.x, lin.a.y) == (lin.b.x, lin.b.y):
                continue
            self._paint_line(lin, idx)

    def _paint_line(self, lin: Line, idx: int):
        self.canvas.create_with_line(lin, idx=idx)

    # ------- labels -------
    def paint_labels(self):
        for idx, lab in enumerate(self.scene.labels()):
            self._paint_label(lab, idx)

    def _paint_label(self, lab: Label, idx: int):
        self.canvas.create_with_label(lab, idx=idx)

    # ------- icons -------
    def paint_icons(self):
        for idx, ico in enumerate(self.scene.icons()):
            self._paint_icon(ico, idx)

    def _paint_icon(self, ico, idx: int):
        self.canvas.create_with_iconlike(ico, idx=idx)

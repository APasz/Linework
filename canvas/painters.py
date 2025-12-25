"""Canvas painters for grid, lines, labels, and icons."""

from __future__ import annotations

from typing import TYPE_CHECKING

from canvas.layers import Layer_Type, Tag
from models.geo import Iconlike, Label, Line, Point
from models.params import Params
from models.styling import CapStyle, Colour
from PIL import Image, ImageTk

if TYPE_CHECKING:
    from controllers.app import App


class Scene:
    """Lightweight view over Params for paint iteration."""

    def __init__(self, params: Params) -> None:
        """Create a scene for the given params.

        Args;
            params: The params to expose.
        """
        self.params = params

    def lines(self) -> list[Line]:
        """Return line items."""
        return self.params.lines

    def labels(self) -> list[Label]:
        """Return label items."""
        return self.params.labels

    def icons(self) -> list[Iconlike]:
        """Return icon items."""
        return self.params.icons


class Painters:
    """Canvas painter helpers."""

    def __init__(self, app: App) -> None:
        """Create painters for an application instance.

        Args;
            app: The application instance.
        """
        self.app = app
        self.scene = app.scene
        self.canvas = app.canvas

    @staticmethod
    def _checker(w: int, h: int, tile: int, a: Colour, b: str = "#cccccc") -> Image.Image:
        img = Image.new("RGB", (w, h), a.hexh)
        for y in range(0, h, tile):
            start = ((y // tile) % 2) * tile
            for x in range(start, w, tile * 2):
                Image.Image.paste(img, b, (x, y, x + tile, y + tile))
        return img

    # ------- grid -------
    def paint_grid(self) -> None:
        """Paint the background grid."""
        params = self.app.params
        g = params.grid_size
        if not params.grid_visible or g <= 0:
            return

        w, h = params.width, params.height
        if not self.canvas.cache.checker_bg or self.canvas.cache.checker_bg[0] != g:
            img = self._checker(w, h, g, params.grid_colour)
            self.canvas.cache.checker_bg = (g, ImageTk.PhotoImage(img, master=self.canvas))
        self.canvas.create_image(
            0,
            0,
            image=self.canvas.cache.checker_bg[1],
            anchor="nw",
            tags=Tag.layer(Layer_Type.grid).to_strings(),
        )
        self.canvas.create_rectangle(
            0,
            0,
            w,
            h,
            outline="",
            fill=self.app.params.bg_colour.hexh,
            stipple=self.canvas._stipple_for_alpha(self.app.params.bg_colour.alpha) or "",
            tags=Tag.layer(Layer_Type.grid).to_strings(),
        )

        line = Line(a=Point(x=0, y=0), b=Point(x=0, y=0), col=params.grid_colour, width=1, capstyle=CapStyle.BUTT)

        for x in range(g, w + 1, g):
            self.canvas.create_with_line(
                line.with_xy(x, 0, x, h),
                override_tag=Tag.layer(Layer_Type.grid),
                tag_type=Layer_Type.grid,
            )
        for y in range(g, h + 1, g):
            self.canvas.create_with_line(
                line.with_xy(0, y, w, y),
                override_tag=Tag.layer(Layer_Type.grid),
                tag_type=Layer_Type.grid,
            )

    # ------- lines -------
    def paint_lines(self) -> None:
        """Paint line layers."""
        for idx, lin in enumerate(self.scene.lines()):
            if (lin.a.x, lin.a.y) == (lin.b.x, lin.b.y):
                continue
            self._paint_line(lin, idx)

    def _paint_line(self, lin: Line, idx: int) -> None:
        self.canvas.create_with_line(lin, idx=idx)

    # ------- labels -------
    def paint_labels(self) -> None:
        """Paint label layers."""
        for idx, lab in enumerate(self.scene.labels()):
            self._paint_label(lab, idx)

    def _paint_label(self, lab: Label, idx: int) -> None:
        self.canvas.create_with_label(lab, idx=idx)

    # ------- icons -------
    def paint_icons(self) -> None:
        """Paint icon layers."""
        for idx, ico in enumerate(self.scene.icons()):
            self._paint_icon(ico, idx)

    def _paint_icon(self, ico: Iconlike, idx: int) -> None:
        self.canvas.create_with_iconlike(ico, idx=idx)

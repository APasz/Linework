"""Qt scene that draws the Linework background and grid."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6 import QtCore, QtGui, QtWidgets

from models.styling import Colour

if TYPE_CHECKING:
    from models.params import Params
    from qt.app import QtApp

CHECKER_TILE = 8


def _qcolour(col: Colour) -> QtGui.QColor:
    return QtGui.QColor(col.red, col.green, col.blue, col.alpha)


class QtCanvasScene(QtWidgets.QGraphicsScene):
    """Graphics scene that paints the canvas background and grid."""

    def __init__(self, app: QtApp) -> None:
        """Create the canvas scene.

        Args;
            app: The parent Qt app.
        """
        super().__init__(app)
        self.app = app
        self._checker_cache: dict[int, QtGui.QBrush] = {}

    def drawBackground(self, painter: QtGui.QPainter, rect: QtCore.QRectF) -> None:  # type: ignore[override]
        """Draw the canvas background and grid.

        Args;
            painter: The active painter.
            rect: The exposed scene rect.
        """
        params = self.app.params
        canvas = QtCore.QRectF(0, 0, params.width, params.height)
        clip = rect.intersected(canvas)
        if clip.isEmpty():
            return
        painter.save()
        if params.bg_colour.alpha < 255:
            painter.fillRect(clip, self._checker_brush(CHECKER_TILE))
        painter.fillRect(clip, QtGui.QBrush(_qcolour(params.bg_colour)))
        if params.grid_visible and params.grid_size > 0:
            self._draw_grid(painter, clip, params)
        painter.restore()

    def _checker_brush(self, tile: int) -> QtGui.QBrush:
        cached = self._checker_cache.get(tile)
        if cached:
            return cached
        size = tile * 2
        pixmap = QtGui.QPixmap(size, size)
        light = QtGui.QColor(235, 235, 235)
        dark = QtGui.QColor(200, 200, 200)
        pixmap.fill(light)
        painter = QtGui.QPainter(pixmap)
        painter.fillRect(0, 0, tile, tile, dark)
        painter.fillRect(tile, tile, tile, tile, dark)
        painter.end()
        brush = QtGui.QBrush(pixmap)
        self._checker_cache[tile] = brush
        return brush

    @staticmethod
    def _grid_start(value: int, grid: int) -> int:
        if value <= grid:
            return grid
        return ((value + grid - 1) // grid) * grid

    def _draw_grid(self, painter: QtGui.QPainter, rect: QtCore.QRectF, params: Params) -> None:
        g = int(params.grid_size)
        if g <= 0:
            return
        pen = QtGui.QPen(_qcolour(params.grid_colour))
        pen.setWidth(1)
        painter.setPen(pen)

        left = max(0, int(rect.left()))
        right = min(params.width, int(rect.right()))
        top = max(0, int(rect.top()))
        bottom = min(params.height, int(rect.bottom()))
        if right <= 0 or bottom <= 0:
            return

        max_x = min(params.width - 1, right)
        max_y = min(params.height - 1, bottom)

        path = QtGui.QPainterPath()
        x = self._grid_start(left, g)
        while x <= max_x:
            path.moveTo(x, top)
            path.lineTo(x, bottom)
            x += g
        y = self._grid_start(top, g)
        while y <= max_y:
            path.moveTo(left, y)
            path.lineTo(right, y)
            y += g
        if not path.isEmpty():
            painter.drawPath(path)

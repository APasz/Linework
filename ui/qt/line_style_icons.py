"""Line style preview icons for Qt widgets."""

from __future__ import annotations

from PySide6 import QtCore, QtGui

from models.styling import LineStyle, pen_dash_pattern


def line_style_icon(
    style: LineStyle, size: QtCore.QSize, colour: QtGui.QColor, *, width: int = 2
) -> QtGui.QIcon:
    """Return a QIcon preview of a line style."""
    pixmap = QtGui.QPixmap(size)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)

    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

    pen = QtGui.QPen(colour)
    pen.setWidth(width)
    pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
    dash = pen_dash_pattern(style, width)
    if dash:
        pen.setDashPattern([float(d) for d in dash])

    painter.setPen(pen)
    y = size.height() / 2.0
    x0 = 2
    x1 = max(x0 + 1, size.width() - 2)
    painter.drawLine(QtCore.QPointF(x0, y), QtCore.QPointF(x1, y))
    painter.end()

    return QtGui.QIcon(pixmap)

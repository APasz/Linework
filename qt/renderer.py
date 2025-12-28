"""Qt scene renderer for Linework models."""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, radians, sin
from pathlib import Path

from PIL import Image
from PySide6 import QtCore, QtGui, QtWidgets

from core.layers import HitKind
from models.assets import Builtins, Primitives, Style, _open_rgba
from models.geo import BuiltinIcon, Iconlike, Label, Line, PictureIcon
from models.params import Params
from models.styling import Anchor, CapStyle, Colour, JoinStyle, LineStyle, pen_dash_pattern
from qt.scene_data import DATA_IDX, DATA_KIND

Z_LINES = 0
Z_ICONS = 10
Z_LABELS = 20


@dataclass(frozen=True, slots=True)
class _PixmapKey:
    path: str
    w: int
    h: int
    rot: int


def _qcolour(col: Colour) -> QtGui.QColor:
    return QtGui.QColor(col.red, col.green, col.blue, col.alpha)


def _cap_style(cap: CapStyle) -> QtCore.Qt.PenCapStyle:
    return {
        CapStyle.ROUND: QtCore.Qt.PenCapStyle.RoundCap,
        CapStyle.BUTT: QtCore.Qt.PenCapStyle.FlatCap,
        CapStyle.PROJECTING: QtCore.Qt.PenCapStyle.SquareCap,
    }[cap]


def _join_style(join: JoinStyle) -> QtCore.Qt.PenJoinStyle:
    return {
        JoinStyle.MITER: QtCore.Qt.PenJoinStyle.MiterJoin,
        JoinStyle.ROUND: QtCore.Qt.PenJoinStyle.RoundJoin,
        JoinStyle.BEVEL: QtCore.Qt.PenJoinStyle.BevelJoin,
    }[join]


def _anchor_local(anchor: Anchor, w: float, h: float) -> tuple[float, float]:
    if anchor in (Anchor.NW, Anchor.W, Anchor.SW):
        ax = 0.0
    elif anchor in (Anchor.NE, Anchor.E, Anchor.SE):
        ax = w
    else:
        ax = w / 2.0

    if anchor in (Anchor.NW, Anchor.N, Anchor.NE):
        ay = 0.0
    elif anchor in (Anchor.SW, Anchor.S, Anchor.SE):
        ay = h
    else:
        ay = h / 2.0
    return (ax, ay)


def _dash_pattern(style: LineStyle | None, width: int) -> list[float]:
    pat = pen_dash_pattern(style, width)
    return [float(p) for p in pat] if pat else []


def _pen_for_line(line: Line) -> QtGui.QPen:
    pen = QtGui.QPen(_qcolour(line.col))
    width = max(1, int(line.width))
    pen.setWidth(width)
    pen.setCapStyle(_cap_style(line.capstyle))
    dash = _dash_pattern(line.style, width)
    if dash:
        pen.setDashPattern(dash)
        pen.setDashOffset(float(line.dash_offset) / width)
    return pen


def _pen_for_style(colour: Colour, style: Style, scale: float) -> QtGui.QPen:
    pen = QtGui.QPen(_qcolour(colour))
    width = max(1, round(style.stroke_width * scale))
    pen.setWidth(width)
    pen.setCapStyle(_cap_style(style.line_cap))
    pen.setJoinStyle(_join_style(style.line_join))
    if style.dash:
        pen.setDashPattern([float(max(1, round(d * scale))) for d in style.dash])
    return pen


def _brush_for_style(colour: Colour, style: Style) -> QtGui.QBrush:
    return QtGui.QBrush(_qcolour(colour)) if style.fill else QtGui.QBrush(QtCore.Qt.BrushStyle.NoBrush)


class QtSceneRenderer:
    """Render Linework params into a Qt graphics scene."""

    def __init__(self, scene: QtWidgets.QGraphicsScene) -> None:
        """Create a renderer bound to a scene.

        Args;
            scene: The target graphics scene.
        """
        self.scene = scene
        self._pixmap_cache: dict[_PixmapKey, QtGui.QPixmap] = {}
        self._items_by_key: dict[tuple[str, int], list[QtWidgets.QGraphicsItem]] = {}

    def render(self, params: Params) -> None:
        """Render the current params into the scene.

        Args;
            params: The model parameters to render.
        """
        self.scene.clear()
        self._items_by_key.clear()
        self.scene.setSceneRect(0, 0, params.width, params.height)

        self._draw_lines(params.lines)
        self._draw_icons(params.icons)
        self._draw_labels(params.labels)

    # ---------- lines ----------
    def _draw_lines(self, lines: list[Line]) -> None:
        for idx, line in enumerate(lines):
            if (line.a.x, line.a.y) == (line.b.x, line.b.y):
                continue
            self.add_line(line, idx=idx)

    # ---------- labels ----------
    def _draw_labels(self, labels: list[Label]) -> None:
        for idx, label in enumerate(labels):
            self.add_label(label, idx=idx)

    # ---------- icons ----------
    def _draw_icons(self, icons: list[Iconlike]) -> None:
        for idx, icon in enumerate(icons):
            self.add_icon(icon, idx=idx)

    def add_line(
        self,
        line: Line,
        *,
        idx: int | None = None,
        z: int = Z_LINES,
        tag: bool = True,
    ) -> QtWidgets.QGraphicsLineItem:
        """Add a line item to the scene.

        Args;
            line: The line model.
            idx: Optional line index to tag.
            z: The z-order value.
            tag: Whether to tag for hit testing.

        Returns;
            The created graphics item.
        """
        item = QtWidgets.QGraphicsLineItem(line.a.x, line.a.y, line.b.x, line.b.y)
        item.setPen(_pen_for_line(line))
        item.setZValue(z)
        if tag and idx is not None:
            item.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
            self._tag_item(item, HitKind.line, idx)
        self.scene.addItem(item)
        return item

    def add_label(
        self,
        label: Label,
        *,
        idx: int | None = None,
        z: int = Z_LABELS,
        tag: bool = True,
    ) -> QtWidgets.QGraphicsTextItem:
        """Add a label item to the scene.

        Args;
            label: The label model.
            idx: Optional label index to tag.
            z: The z-order value.
            tag: Whether to tag for hit testing.

        Returns;
            The created graphics item.
        """
        item = QtWidgets.QGraphicsTextItem(label.text)
        font = QtGui.QFont()
        font.setPixelSize(max(1, int(label.size)))
        item.setFont(font)
        item.setDefaultTextColor(_qcolour(label.col))

        bounds = item.boundingRect()
        w, h = bounds.width(), bounds.height()
        ax, ay = _anchor_local(label.anchor, w, h)
        item.setTransformOriginPoint(ax, ay)
        item.setPos(label.p.x - ax, label.p.y - ay)
        if label.rotation:
            # Qt rotates clockwise in scene coordinates; flip to match CCW label semantics.
            item.setRotation(float(-label.rotation))

        item.setZValue(z)
        if tag and idx is not None:
            item.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
            self._tag_item(item, HitKind.label, idx)
        self.scene.addItem(item)
        return item

    def add_icon(
        self,
        icon: Iconlike,
        *,
        idx: int | None = None,
        z: int = Z_ICONS,
        tag: bool = True,
    ) -> list[QtWidgets.QGraphicsItem]:
        """Add an icon to the scene.

        Args;
            icon: The icon model.
            idx: Optional icon index to tag.
            z: The z-order value.
            tag: Whether to tag for hit testing.

        Returns;
            The created graphics items.
        """
        if isinstance(icon, PictureIcon):
            item = self._draw_picture_icon(icon, idx if tag else None, z=z, tag=tag)
            return [item] if item is not None else []
        return self._draw_builtin_icon(icon, idx if tag else None, z=z, tag=tag)

    def _draw_picture_icon(
        self,
        icon: PictureIcon,
        idx: int | None,
        *,
        z: int = Z_ICONS,
        tag: bool = True,
    ) -> QtWidgets.QGraphicsPixmapItem | None:
        bw, bh = icon.bbox_wh()
        cx, cy = icon.anchor.centre_for(icon.p.x, icon.p.y, bw, bh, icon.rotation)
        pixmap = self._pixmap_for_picture(icon, bw, bh)
        if pixmap is None:
            return None
        w = pixmap.width()
        h = pixmap.height()
        item = QtWidgets.QGraphicsPixmapItem(pixmap)
        item.setOffset(-w / 2.0, -h / 2.0)
        item.setPos(cx, cy)
        item.setZValue(z)
        if tag and idx is not None:
            item.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
            self._tag_item(item, HitKind.icon, idx)
        self.scene.addItem(item)
        return item

    def _pixmap_for_picture(self, icon: PictureIcon, bw: int, bh: int) -> QtGui.QPixmap | None:
        rot = int(icon.rotation or 0) % 360
        key = _PixmapKey(str(Path(icon.src)), bw, bh, rot)
        cached = self._pixmap_cache.get(key)
        if cached is not None:
            return cached

        im = _open_rgba(icon.src, bw, bh)
        if rot:
            im = im.rotate(-rot, resample=Image.Resampling.BICUBIC, expand=True)
        qimage = _qimage_from_pil(im)
        pixmap = QtGui.QPixmap.fromImage(qimage)
        self._pixmap_cache[key] = pixmap
        return pixmap

    def _draw_builtin_icon(
        self,
        icon: BuiltinIcon,
        idx: int | None,
        *,
        z: int = Z_ICONS,
        tag: bool = True,
    ) -> list[QtWidgets.QGraphicsItem]:
        idef = Builtins.icon_def(icon.name)
        minx, miny, vbw, vbh = idef.viewbox
        s = icon.size / max(vbw, vbh)
        vis_w = s * vbw
        vis_h = s * vbh
        cx, cy = icon.anchor.centre_for(icon.p.x, icon.p.y, round(vis_w), round(vis_h), int(icon.rotation or 0))

        ang = radians(float(icon.rotation or 0))
        cs, sn = cos(ang), sin(ang)

        def M(px: float, py: float) -> tuple[float, float]:
            x0 = (px - (minx + vbw / 2.0)) * s
            y0 = (py - (miny + vbh / 2.0)) * s
            xr = x0 * cs - y0 * sn
            yr = x0 * sn + y0 * cs
            return (cx + xr, cy + yr)

        items: list[QtWidgets.QGraphicsItem] = []
        for prim in idef.prims:
            if isinstance(prim, Primitives.Circle):
                cxp, cyp = M(prim.cx, prim.cy)
                rr = prim.r * s
                item = QtWidgets.QGraphicsEllipseItem(cxp - rr, cyp - rr, rr * 2.0, rr * 2.0)
                self._apply_style(item, prim.style, icon.col, s)
            elif isinstance(prim, Primitives.Rect):
                x0, y0 = M(prim.x, prim.y)
                x1, y1 = M(prim.x + prim.w, prim.y)
                x2, y2 = M(prim.x + prim.w, prim.y + prim.h)
                x3, y3 = M(prim.x, prim.y + prim.h)
                poly = QtGui.QPolygonF(
                    [
                        QtCore.QPointF(x0, y0),
                        QtCore.QPointF(x1, y1),
                        QtCore.QPointF(x2, y2),
                        QtCore.QPointF(x3, y3),
                    ]
                )
                item = QtWidgets.QGraphicsPolygonItem(poly)
                self._apply_style(item, prim.style, icon.col, s)
            elif isinstance(prim, Primitives.Line):
                x1, y1 = M(prim.x1, prim.y1)
                x2, y2 = M(prim.x2, prim.y2)
                item = QtWidgets.QGraphicsLineItem(x1, y1, x2, y2)
                self._apply_style(item, prim.style, icon.col, s)
            elif isinstance(prim, Primitives.Polyline):
                points = [QtCore.QPointF(*M(px, py)) for px, py in prim.points]
                if prim.closed:
                    poly = QtGui.QPolygonF(points)
                    item = QtWidgets.QGraphicsPolygonItem(poly)
                else:
                    path = QtGui.QPainterPath()
                    if points:
                        path.moveTo(points[0])
                        for pt in points[1:]:
                            path.lineTo(pt)
                    item = QtWidgets.QGraphicsPathItem(path)
                self._apply_style(item, prim.style, icon.col, s)
            else:
                continue

            item.setZValue(z)
            if tag and idx is not None:
                item.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
                self._tag_item(item, HitKind.icon, idx)
            self.scene.addItem(item)
            items.append(item)

        return items

    # ---------- helpers ----------
    def _tag_item(self, item: QtWidgets.QGraphicsItem, kind: HitKind, idx: int) -> None:
        item.setData(DATA_KIND, kind.value)
        item.setData(DATA_IDX, idx)
        key = (kind.value, idx)
        self._items_by_key.setdefault(key, []).append(item)

    def items_for_hit(self, kind: HitKind, idx: int) -> list[QtWidgets.QGraphicsItem]:
        """Return items associated with a hit kind/index.

        Args;
            kind: The hit kind.
            idx: The item index.

        Returns;
            The matching graphics items.
        """
        return list(self._items_by_key.get((kind.value, idx), []))

    @staticmethod
    def _apply_style(
        item: QtWidgets.QGraphicsItem,
        style: Style,
        colour: Colour,
        scale: float,
    ) -> None:
        item_types = (
            QtWidgets.QGraphicsLineItem,
            QtWidgets.QGraphicsPathItem,
            QtWidgets.QGraphicsPolygonItem,
            QtWidgets.QGraphicsEllipseItem,
            QtWidgets.QGraphicsRectItem,
        )
        if not isinstance(item, item_types):
            return

        if style.stroke:
            pen = _pen_for_style(colour, style, scale)
        else:
            pen = QtGui.QPen(QtCore.Qt.PenStyle.NoPen)
        if style.fill:
            brush = _brush_for_style(colour, style)
        else:
            brush = QtGui.QBrush(QtCore.Qt.BrushStyle.NoBrush)

        item.setPen(pen)
        if isinstance(
            item,
            (
                QtWidgets.QGraphicsPathItem,
                QtWidgets.QGraphicsPolygonItem,
                QtWidgets.QGraphicsEllipseItem,
                QtWidgets.QGraphicsRectItem,
            ),
        ):
            item.setBrush(brush)


def _qimage_from_pil(im: Image.Image) -> QtGui.QImage:
    rgba = im.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    qimage = QtGui.QImage(data, rgba.width, rgba.height, QtGui.QImage.Format.Format_RGBA8888)
    return qimage.copy()

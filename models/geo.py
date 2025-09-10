from collections.abc import Collection
import math
import tkinter as tk
from enum import StrEnum
from typing import Self

from canvas.layers import Hit_Kind, Layer_Name, layer_tag, tag_list
from models.styling import Anchor, CapStyle, Colour, LineStyle, Model, scaled_pattern


class Point(Model):
    x: int
    y: int
    capstyle: CapStyle = CapStyle.ROUND


class Line(Model):
    a: Point
    b: Point
    col: Colour
    width: int
    capstyle: CapStyle = CapStyle.ROUND
    style: LineStyle = LineStyle.SOLID
    dash_offset: int = 0

    def with_points(self, a: Point, b: Point) -> Self:
        return self.model_copy(update={"a": a, "b": b})

    def with_xy(self, x1: int, y1: int, x2: int, y2: int) -> Self:
        return self.model_copy(update={"a": Point(x=x1, y=y1), "b": Point(x=x2, y=y2)})


class Label(Model):
    p: Point
    text: str
    col: Colour
    anchor: Anchor = Anchor.NW
    size: int = 12
    rotation: int = 0
    snap: bool = True

    def with_point(self, p: Point) -> Self:
        return self.model_copy(update={"p": p})

    def with_xy(self, x: int, y: int) -> Self:
        return self.model_copy(update={"p": Point(x=x, y=y)})


class Icon_Name(StrEnum):
    SIGNAL = "signal"
    SWITCH = "switch"
    BUFFER = "buffer"
    CROSSING = "crossing"


class Icon(Model):
    p: Point
    name: Icon_Name
    col: Colour
    anchor: Anchor = Anchor.SE
    size: int = 16
    rotation: int = 0
    snap: bool = True

    def with_point(self, p: Point) -> Self:
        return self.model_copy(update={"p": p})

    def with_xy(self, x: int, y: int) -> Self:
        return self.model_copy(update={"p": Point(x=x, y=y)})


class ItemID(int): ...


def _flat_points(*points: Point) -> tuple[int, ...]:
    out: list[int] = []
    for p in points:
        out += [int(p.x), int(p.y)]
    return tuple(out)


def tag_sort(
    overrides: Collection[Layer_Name] | None,
    extra: Collection[str] | None,
    kind: Hit_Kind,
    layer: Layer_Name,
    idx: int | None,
) -> list[str]:
    if overrides:
        tags = [layer_tag(lay) for lay in overrides]
    elif idx is not None:
        tags = tag_list(kind, idx, layer)
    else:
        tags = [layer_tag(layer)]
    if extra:
        tags.extend(extra)
    return tags


class CanvasLW(tk.Canvas):
    """Typed convenience wrappers"""

    # ---------- creation ----------
    def create_with_points(
        self,
        a: Point,
        b: Point,
        *,
        col: Colour,
        width: int,
        capstyle: CapStyle,
        style: LineStyle | None = None,
        idx: int | None = None,
        dash_offset: int = 0,
        extra_tags: Collection[str] | None = None,
        override_base_tags: Collection[Layer_Name] | None = None,
    ) -> ItemID:
        extra_tags = extra_tags or tuple()
        dash = scaled_pattern(style, width)

        iid = super().create_line(
            a.x,
            a.y,
            b.x,
            b.y,
            fill=col.hex,
            width=width,
            capstyle=capstyle.value,
            dash=dash or [],
            dashoffset=(dash_offset if dash else 0),
            tags=tag_sort(override_base_tags, extra_tags, Hit_Kind.line, Layer_Name.lines, idx),
        )
        return ItemID(iid)

    def create_with_line(
        self,
        line: Line,
        *,
        idx: int | None = None,
        extra_tags: Collection[str] = (),
        override_base_tags: Collection[Layer_Name] | None = None,
    ) -> ItemID:
        dash = scaled_pattern(line.style, line.width)
        iid = super().create_line(
            line.a.x,
            line.a.y,
            line.b.x,
            line.b.y,
            fill=line.col.hex,
            width=line.width,
            capstyle=line.capstyle.value,
            dash=dash or [],
            dashoffset=(line.dash_offset if dash else 0),
            tags=tag_sort(override_base_tags, extra_tags, Hit_Kind.line, Layer_Name.lines, idx),
        )
        return ItemID(iid)

    def create_with_label(
        self,
        label: Label,
        *,
        idx: int | None = None,
        extra_tags: Collection[str] = (),
        override_base_tags: Collection[Layer_Name] | None = None,
    ) -> ItemID:
        iid = super().create_text(
            label.p.x,
            label.p.y,
            text=label.text,
            fill=label.col.hex,
            anchor=label.anchor.tk,
            font=("TkDefaultFont", label.size),
            angle=label.rotation,
            tags=tag_sort(override_base_tags, extra_tags, Hit_Kind.label, Layer_Name.labels, idx),
        )
        return ItemID(iid)

    def create_with_icon(
        self,
        icon: Icon,
        *,
        idx: int | None = None,
        extra_tags: Collection[str] = (),
        override_base_tags: Collection[Layer_Name] | None = None,
    ) -> None:
        x, y, s, col, rot = icon.p.x, icon.p.y, icon.size, icon.col.hex, float(icon.rotation or 0)

        def _rot(x: float, y: float, cx: float, cy: float, deg: float) -> tuple[float, float]:
            r = math.radians(deg)
            dx, dy = x - cx, y - cy
            cs, sn = math.cos(r), math.sin(r)
            return (cx + dx * cs - dy * sn, cy + dx * sn + dy * cs)

        tag = tag_sort(override_base_tags, extra_tags, Hit_Kind.icon, Layer_Name.icons, idx)

        if icon.name == Icon_Name.SIGNAL:
            r = s // 2
            super().create_oval(x - r, y - r, x + r, y + r, fill=col, outline="", tags=tag)
            mx0, my0 = x - r // 3, y + r
            mx1, my1 = x + r // 3, y + r
            mx2, my2 = x + r // 3, y + s
            mx3, my3 = x - r // 3, y + s
            parts = [_rot(px, py, x, y, rot) for (px, py) in [(mx0, my0), (mx1, my1), (mx2, my2), (mx3, my3)]]
            super().create_polygon(*sum(parts, ()), fill=col, outline="", tags=tag)
        elif icon.name == Icon_Name.BUFFER:
            w, h = s, s // 2
            corners = [
                (x - w // 2, y - h // 2),
                (x + w // 2, y - h // 2),
                (x + w // 2, y + h // 2),
                (x - w // 2, y + h // 2),
            ]
            pts = [_rot(px, py, x, y, rot) for (px, py) in corners]
            super().create_polygon(*sum(pts, ()), outline=col, width=2, fill="", tags=tag)

        elif icon.name == Icon_Name.CROSSING:
            L = s
            x1, y1 = _rot(x - L, y - L, x, y, rot)
            x2, y2 = _rot(x + L, y + L, x, y, rot)
            x3, y3 = _rot(x - L, y + L, x, y, rot)
            x4, y4 = _rot(x + L, y - L, x, y, rot)
            super().create_line(x1, y1, x2, y2, fill=col, width=2, tags=tag)
            super().create_line(x3, y3, x4, y4, fill=col, width=2, tags=tag)

        elif icon.name == Icon_Name.SWITCH:
            L = s
            a1, b1 = _rot(x, y, x, y, rot)
            a2, b2 = _rot(x + L, y, x, y, rot)
            a3, b3 = _rot(x + L, y + L // 2, x, y, rot)
            super().create_line(a1, b1, a2, b2, fill=col, width=2, tags=tag)
            super().create_line(a1, b1, a3, b3, fill=col, width=2, tags=tag)
        else:
            r = s // 3
            super().create_oval(x - r, y - r, x + r, y + r, fill=col, outline="", tags=tag)
        return None

    # ---------- updates ----------
    def coords_p(self, item: ItemID, *points: Point) -> None:
        super().coords(item, *_flat_points(*points))

    def move_by(self, item: ItemID, dx: int, dy: int) -> None:
        super().move(item, dx, dy)

    def move_center_to(self, item: ItemID, target: Point) -> None:
        bbox = super().bbox(item)
        if not bbox:
            return
        cx = (bbox[0] + bbox[2]) / 2
        cy = (bbox[1] + bbox[3]) / 2
        super().move(item, int(round(target.x - cx)), int(round(target.y - cy)))

    # ---------- queries ----------
    def center_of_tag(self, tag: str) -> Point | None:
        bbox = super().bbox(tag) or (lambda ids: super().bbox(ids[0]) if ids else None)(super().find_withtag(tag))
        if not bbox:
            return None
        return Point(x=round((bbox[0] + bbox[2]) / 2), y=round((bbox[1] + bbox[3]) / 2))

    def tag_raise_l(self, layer: Layer_Name) -> None:
        return super().tag_raise(layer_tag(layer))

    def tag_lower_l(self, layer: Layer_Name) -> None:
        return super().tag_lower(layer_tag(layer))

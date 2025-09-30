import math
import tkinter as tk
from collections import OrderedDict
from collections.abc import Collection
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal, Self, overload

from PIL import Image, ImageTk
from pydantic import Field, model_validator

from canvas.layers import Hit_Kind, Layer_Type, Tag
from models.assets import Builtins, Formats, Icon_Name, Primitives, Style, _open_rgba, probe_wh
from models.styling import Anchor, CapStyle, Colour, JoinStyle, LineStyle, Model, scaled_pattern

MAX_CACHE = 128


class Point(Model):
    x: int
    y: int
    capstyle: CapStyle = CapStyle.ROUND

    def clamped_to(self, w: int, h: int, grid: int = 0) -> "Point": ...


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

    def unit(
        self,
        x1: float | None = None,
        y1: float | None = None,
        x2: float | None = None,
        y2: float | None = None,
    ) -> tuple[float, float, float]:
        ax = x1 if x1 is not None else self.a.x
        ay = y1 if y1 is not None else self.a.y
        bx = x2 if x2 is not None else self.b.x
        by = y2 if y2 is not None else self.b.y
        dx, dy = (bx - ax), (by - ay)
        L = math.hypot(dx, dy)
        if L <= 0:
            return 0.0, 0.0, 0.0
        return dx / L, dy / L, L

    def scaled_pattern(self, *, style: LineStyle | None = None, width: int | None = None):
        return scaled_pattern(style or self.style, width or self.width)


class Label(Model):
    p: Point
    text: str
    col: Colour
    anchor: Anchor = Anchor.W
    size: int = 12
    rotation: int = 37  # Intentional
    snap: bool = True

    def with_point(self, p: Point) -> Self:
        return self.model_copy(update={"p": p})

    def with_xy(self, x: int, y: int) -> Self:
        return self.model_copy(update={"p": Point(x=x, y=y)})


class Icon_Type(StrEnum):
    builtin = "builtin"
    picture = "picture"


class Icon_Source(Model):
    kind: Icon_Type
    name: Icon_Name | None = None
    src: Path | None = None

    @model_validator(mode="after")
    def _check(self):
        if self.kind is Icon_Type.builtin:
            if self.name is None or self.src is not None:
                raise ValueError("builtin Icon_Source requires name and forbids src")
        else:
            if self.src is None or self.name is not None:
                raise ValueError("picture Icon_Source requires src and forbids name")
        return self

    @classmethod
    def builtin(cls, name: Icon_Name | str) -> "Icon_Source":
        return cls(kind=Icon_Type.builtin, name=Icon_Name(name))

    @classmethod
    def picture(cls, src: Path | str) -> "Icon_Source":
        return cls(kind=Icon_Type.picture, src=Path(src))

    @classmethod
    def coerce(cls, x: "Icon_Source | Iconlike | Path | str | Icon_Name") -> "Icon_Source":
        if isinstance(x, Icon_Source):
            return x
        if isinstance(x, Icon_Name):
            return cls.builtin(x)
        if isinstance(x, str):
            # try value→enum first, else assume file path
            try:
                return cls.builtin(Icon_Name(x))
            except Exception:
                return cls.picture(x)
        if isinstance(x, Path):
            return cls.picture(x)
        if isinstance(x, Builtin_Icon):
            return cls.builtin(x.name)
        if isinstance(x, Picture_Icon):
            return cls.picture(x.src)
        raise TypeError(f"Cannot coerce {type(x)} to Icon_Source")


class Base_Icon(Model):
    p: Point
    col: Colour
    anchor: Anchor = Anchor.SE
    size: int = 48
    rotation: int = 0
    snap: bool = True

    def with_point(self, p: Point) -> Self:
        return self.model_copy(update={"p": p})

    def with_xy(self, x: int, y: int) -> Self:
        return self.model_copy(update={"p": Point(x=x, y=y)})

    def bbox_wh(self) -> tuple[int, int]:
        raise NotImplementedError


class Builtin_Icon(Base_Icon):
    kind: Literal["builtin"] = "builtin"
    name: Icon_Name

    def bbox_wh(self) -> tuple[int, int]:
        s = self.size
        return (s, s)


class Picture_Icon(Base_Icon):
    kind: Literal["picture"] = "picture"
    src: Path
    size: int = 192
    format: Formats | None = None
    preserve_aspect: bool = True

    def bbox_wh(self) -> tuple[int, int]:
        # tiny helper (see below)
        w, h = probe_wh(self.src, self.format)
        if w <= 0 or h <= 0:
            return (self.size, self.size)
        if self.preserve_aspect:
            s = self.size / max(w, h)
            return (max(1, round(w * s)), max(1, round(h * s)))
        return (self.size, self.size)


Iconlike = Annotated[Builtin_Icon | Picture_Icon, Field(discriminator="kind")]


class ItemID(int): ...


def _flat_points(*points: Point) -> tuple[int, ...]:
    out: list[int] = []
    for p in points:
        out += [p.x, p.y]
    return tuple(out)


def tag_sort(
    tag_type: Layer_Type,
    base_kind: Layer_Type | Hit_Kind | None = None,
    idx: int | None = None,
    override: Tag | None = None,
    extra: Collection[Tag] | None = None,
) -> list[str]:
    tags: set[Tag] = {Tag.layer(tag_type)}
    if override:
        tags.add(override)
    else:
        tags.add(Tag(tag_type.tagns(), base_kind, idx))
    if extra:
        tags.update(extra)

    strings: list[str] = []
    for tag in tags:
        strings.extend(tag.to_strings())
    return strings


Deletable = int | ItemID | str


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
        extra_tags: Collection[Tag] | None = None,
        override_tag: Tag | None = None,
        tag_type: Layer_Type = Layer_Type.lines,
    ) -> ItemID:
        dash = scaled_pattern(style, width)

        iid = super().create_line(
            a.x,
            a.y,
            b.x,
            b.y,
            fill=col.hexh,
            width=width,
            capstyle=capstyle.value,
            dash=dash or [],
            dashoffset=(dash_offset if dash else 0),
            tags=tag_sort(tag_type, base_kind=Hit_Kind.line, idx=idx, override=override_tag, extra=extra_tags),
        )
        return ItemID(iid)

    def create_with_line(
        self,
        line: Line,
        *,
        idx: int | None = None,
        extra_tags: Collection[Tag] | None = None,
        override_tag: Tag | None = None,
        tag_type: Layer_Type = Layer_Type.lines,
    ) -> ItemID:
        dash = line.scaled_pattern()
        iid = super().create_line(
            line.a.x,
            line.a.y,
            line.b.x,
            line.b.y,
            fill=line.col.hexh,
            width=line.width,
            capstyle=line.capstyle.value,
            dash=dash or [],
            dashoffset=(line.dash_offset if dash else 0),
            tags=tag_sort(tag_type, base_kind=Hit_Kind.line, idx=idx, override=override_tag, extra=extra_tags),
        )
        return ItemID(iid)

    def create_with_label(
        self,
        label: Label,
        *,
        idx: int | None = None,
        extra_tags: Collection[Tag] | None = None,
        override_tag: Tag | None = None,
        tag_type: Layer_Type = Layer_Type.labels,
    ) -> ItemID:
        iid = super().create_text(
            label.p.x,
            label.p.y,
            text=label.text,
            fill=label.col.hexh,
            anchor=label.anchor.tk,
            font=("TkDefaultFont", label.size),
            angle=label.rotation,
            tags=tag_sort(tag_type, base_kind=Hit_Kind.label, idx=idx, override=override_tag, extra=extra_tags),
        )
        return ItemID(iid)

    @overload
    def create_with_iconlike(
        self,
        icon: Builtin_Icon,
        *,
        idx: int | None = None,
        extra_tags: Collection[Tag] | None = None,
        override_tag: Tag | None = None,
        tag_type: Layer_Type = Layer_Type.icons,
    ): ...

    @overload
    def create_with_iconlike(
        self,
        icon: Picture_Icon,
        *,
        idx: int | None = None,
        extra_tags: Collection[Tag] | None = None,
        override_tag: Tag | None = None,
        tag_type: Layer_Type = Layer_Type.icons,
    ) -> ItemID: ...

    def create_with_iconlike(
        self,
        icon: Iconlike,
        *,
        idx: int | None = None,
        extra_tags: Collection[Tag] | None = None,
        override_tag: Tag | None = None,
        tag_type: Layer_Type = Layer_Type.icons,
    ) -> ItemID | None:
        if isinstance(icon, Picture_Icon):
            return self.create_with_picture(
                icon,
                idx=idx,
                extra_tags=extra_tags,
                override_tag=override_tag,
                tag_type=tag_type,
            )
        else:
            return self.create_with_icon(
                icon,
                idx=idx,
                extra_tags=extra_tags,
                override_tag=override_tag,
                tag_type=tag_type,
            )

    def create_with_icon(
        self,
        icon: Builtin_Icon,
        *,
        idx: int | None = None,
        extra_tags: Collection[Tag] | None = None,
        override_tag: Tag | None = None,
        tag_type: Layer_Type = Layer_Type.icons,
    ):
        tag = tag_sort(tag_type, base_kind=Hit_Kind.icon, idx=idx, override=override_tag, extra=extra_tags)
        col = icon.col.hexh
        size = float(icon.size)
        rot = float(icon.rotation or 0.0)

        idef = Builtins.icon_def(icon.name)
        minx, miny, vbw, vbh = idef.viewbox
        s = size / max(vbw, vbh)

        vis_w = s * vbw
        vis_h = s * vbh
        cx, cy = icon.anchor.centre_for(icon.p.x, icon.p.y, round(vis_w), round(vis_h), int(icon.rotation or 0))

        ang = math.radians(rot)
        cs, sn = math.cos(ang), math.sin(ang)

        def M(px: float, py: float) -> tuple[float, float]:
            x0 = (px - (minx + vbw / 2.0)) * s
            y0 = (py - (miny + vbh / 2.0)) * s
            xr = x0 * cs - y0 * sn
            yr = x0 * sn + y0 * cs
            return (cx + xr, cy + yr)

        def _opts_line(sty: Style) -> dict:
            if not sty.stroke:
                return {}
            w = max(1.0, sty.stroke_width * s)
            join = {JoinStyle.ROUND: "round", JoinStyle.BEVEL: "bevel", JoinStyle.MITER: "miter"}[sty.line_join]
            cap = {CapStyle.ROUND: "round", CapStyle.BUTT: "butt", CapStyle.PROJECTING: "projecting"}[sty.line_cap]
            opts: dict[str, str | float | int | tuple[int | float, ...]] = dict(width=w, joinstyle=join, capstyle=cap)
            if sty.dash:
                opts["dash"] = tuple(max(1.0, d * s) for d in sty.dash)
            return opts

        def _opts_poly(sty: Style) -> dict:
            if not sty.stroke:
                return {}
            w = max(1.0, sty.stroke_width * s)
            join = {JoinStyle.ROUND: "round", JoinStyle.BEVEL: "bevel", JoinStyle.MITER: "miter"}[sty.line_join]
            return dict(width=w, joinstyle=join)

        for prim in idef.prims:
            if isinstance(prim, Primitives.Circle):
                cxp, cyp = M(prim.cx, prim.cy)
                rr = prim.r * s
                fill = col if prim.style.fill else ""
                outline = col if prim.style.stroke else ""
                width = max(1.0, prim.style.stroke_width * s) if prim.style.stroke else 1.0
                super().create_oval(
                    cxp - rr, cyp - rr, cxp + rr, cyp + rr, fill=fill, outline=outline, width=width, tags=tag
                )

            elif isinstance(prim, Primitives.Rect):
                x0, y0 = M(prim.x, prim.y)
                x1, y1 = M(prim.x + prim.w, prim.y)
                x2, y2 = M(prim.x + prim.w, prim.y + prim.h)
                x3, y3 = M(prim.x, prim.y + prim.h)
                pts = [x0, y0, x1, y1, x2, y2, x3, y3]
                opts = _opts_poly(prim.style)
                fill = col if prim.style.fill else ""
                outline = col if prim.style.stroke else ""
                super().create_polygon(*pts, fill=fill, outline=outline, tags=tag, **opts)

            elif isinstance(prim, Primitives.Line):
                x1, y1 = M(prim.x1, prim.y1)
                x2, y2 = M(prim.x2, prim.y2)
                opts = _opts_line(prim.style)
                super().create_line(x1, y1, x2, y2, fill=col if prim.style.stroke else "", tags=tag, **opts)

            elif isinstance(prim, Primitives.Polyline):
                pts = []
                for px, py in prim.points:
                    X, Y = M(px, py)
                    pts += [X, Y]
                if prim.closed:
                    opts = _opts_poly(prim.style)
                    super().create_polygon(
                        *pts,
                        outline=col if prim.style.stroke else "",
                        fill=col if prim.style.fill else "",
                        tags=tag,
                        **opts,
                    )
                else:
                    opts = _opts_line(prim.style)
                    super().create_line(*pts, fill=col if prim.style.stroke else "", tags=tag, **opts)

            elif isinstance(prim, Primitives.Path):
                # Not supported on Tk canvas; pre-approximate to Polyline if need curves
                continue

        return None

    def create_with_picture(
        self,
        pic: "Picture_Icon",
        *,
        idx: int | None = None,
        extra_tags: Collection[Tag] | None = None,
        override_tag: Tag | None = None,
        tag_type: Layer_Type = Layer_Type.icons,
    ) -> ItemID:
        tag = tag_sort(tag_type, base_kind=Hit_Kind.icon, idx=idx, override=override_tag, extra=extra_tags)

        bw, bh = pic.bbox_wh()
        cx, cy = pic.anchor.centre_for(pic.p.x, pic.p.y, bw, bh, pic.rotation)

        # LRU init
        cache = getattr(self, "_picture_cache", None)
        if cache is None:
            cache = self._picture_cache = OrderedDict()
        item_map = getattr(self, "_item_images", None)
        if item_map is None:
            item_map = self._item_images = {}

        key = (str(Path(pic.src)), bw, bh, pic.rotation % 360)

        ph = cache.get(key)
        if ph is not None:
            # Mark as recently used
            cache.move_to_end(key)
        else:
            im = _open_rgba(pic.src, bw, bh)
            rot = pic.rotation % 360
            if rot:
                im = im.rotate(-rot, resample=Image.Resampling.BICUBIC, expand=True)
            # Tie the image to this canvas’ Tk master
            ph = ImageTk.PhotoImage(im, master=self)
            cache[key] = ph

            # Evict least-recently-used if above capacity
            while len(cache) > MAX_CACHE:
                cache.popitem(last=False)  # LRU eviction

        iid = super().create_image(cx, cy, image=ph, tags=tag)
        item_map[iid] = ph  # keep a per-item ref so it doesn't get GC'd while displayed
        return ItemID(iid)

    @overload
    def delete_lw(self, *items: int | ItemID): ...
    @overload
    def delete_lw(self, *items: Layer_Type): ...
    @overload
    def delete_lw(self, *items: str): ...
    @overload
    def delete_lw(self, *items: Tag): ...

    def delete_lw(self, *items):
        args: list[Deletable] = []
        ids: set[int] = set()
        for it in items:
            if isinstance(it, (int, ItemID)):
                i = int(it)
                args.append(i)
                ids.add(i)
            elif isinstance(it, Layer_Type):
                args.append(it.value)
            elif isinstance(it, Tag):
                args.extend(it.to_strings())
                if isinstance(it.kind, Layer_Type):
                    args.append(it.kind.value)
            elif isinstance(it, str):
                args.append(it)

        super().delete(*args)
        item_map = getattr(self, "_item_images", {})
        for iid in ids:
            item_map.pop(iid, None)

    # ---------- updates ----------
    def coords_p(self, item: ItemID, *points: Point):
        super().coords(item, *_flat_points(*points))

    def move_by(self, item: ItemID, dx: int, dy: int):
        super().move(item, dx, dy)

    def move_centre_to(self, item: ItemID, target: Point):
        bbox = super().bbox(item)
        if not bbox:
            return
        cx = (bbox[0] + bbox[2]) / 2
        cy = (bbox[1] + bbox[3]) / 2
        super().move(item, round(target.x - cx), round(target.y - cy))

    # ---------- queries ----------
    def centre_of_tag(self, tag: str) -> Point | None:
        bbox = super().bbox(tag) or (lambda ids: super().bbox(ids[0]) if ids else None)(super().find_withtag(tag))
        if not bbox:
            return None
        return Point(x=round((bbox[0] + bbox[2]) / 2), y=round((bbox[1] + bbox[3]) / 2))

    def tag_raise_l(self, layer: Layer_Type):
        return super().tag_raise(layer.value)

    def tag_lower_l(self, layer: Layer_Type):
        return super().tag_lower(layer.value)

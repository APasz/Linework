from __future__ import annotations

import io
import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from shutil import copy2
from typing import Any, Literal
import xml.etree.ElementTree as ET

import cairosvg
from PIL import Image

from models.styling import CapStyle, JoinStyle


class Formats(StrEnum):
    webp = "webp"
    png = "png"
    svg = "svg"
    jpg = "jpg"
    jpeg = "jpeg"
    bmp = "bmp"

    @classmethod
    def check(cls, path: Path) -> "Formats | None":
        suf = path.suffix[1:].lower()
        try:
            return Formats(suf)
        except ValueError:
            return None

    @property
    def mime(self) -> str:
        return "image/svg+xml" if self is Formats.svg else f"image/{self.value}"


NUM = re.compile(r"^\s*(\d+(\.\d+)?)(px|pt|em|ex|in|cm|mm|pc|%)?\s*$")


@lru_cache(maxsize=512)
def probe_wh(path: Path, fmt: str | None = None) -> tuple[int, int]:
    p = Path(path)
    ext = (fmt or p.suffix[1:]).lower()
    if ext == "svg":
        try:
            root = ET.fromstring(p.read_text(encoding="utf-8"))

            w = root.get("width")
            h = root.get("height")
            vb = root.get("viewBox")

            def _num(s):
                m = NUM.match(s) if s else None
                return float(m.group(1)) if m else None

            wf, hf = _num(w), _num(h)
            if wf and hf:
                return round(wf), round(hf)
            if vb:
                _, _, vbw, vbh = (float(x) for x in vb.replace(",", " ").split())
                return max(1, round(vbw)), max(1, round(vbh))
        except Exception:
            pass
        return (0, 0)
    else:
        # raster
        try:
            with Image.open(p) as im:
                return im.width, im.height
        except Exception:
            return (0, 0)


class Asset_Library:
    def __init__(self, root: Path):
        self.root = root
        self.icons_dir = root.parent.absolute() / "assets" / "icons"
        self.icons_dir.mkdir(parents=True, exist_ok=True)

    def list_pictures(self) -> list[Path]:
        pics = []
        for p in self.icons_dir.iterdir():
            if Formats.check(p):
                pics.append(p)
        pics.sort(key=lambda p: p.name.lower())
        return pics

    def import_files(self, paths: list[Path]) -> list[Path]:
        out = []
        for p in paths:
            if not Formats.check(p):
                continue
            dest = self.icons_dir / p.name
            i = 1
            while dest.exists():
                dest = self.icons_dir / f"{p.stem}_{i}{p.suffix}"
                i += 1
            copy2(p, dest)
            out.append(dest)
        return out


_ICON_LIB: Asset_Library | None = None


def get_asset_library(project_root: Path) -> Asset_Library:
    """Given a .linework project path, return a cached Asset_Library rooted to it"""
    global _ICON_LIB
    if _ICON_LIB is None or _ICON_LIB.root != project_root:
        _ICON_LIB = Asset_Library(project_root)
    return _ICON_LIB


def _open_rgba(src: Path, w: int, h: int) -> Image.Image:
    ext = src.suffix[1:].lower()
    if ext == "svg":
        # rasterize just this SVG icon to target size
        try:
            data = src.read_bytes()
            png = cairosvg.svg2png(bytestring=data, output_width=w, output_height=h)
            return Image.open(io.BytesIO(png)).convert("RGBA")  # pyright: ignore[reportArgumentType]
        except Exception:
            return Image.new("RGBA", (max(1, w), max(1, h)), (0, 0, 0, 0))
    else:
        im = Image.open(src).convert("RGBA")
        if im.size != (w, h):
            im = im.resize((w, h), Image.Resampling.LANCZOS)
        return im


# === Names ===========================================================
class Icon_Name(StrEnum):
    SIGNAL = "signal"
    SWITCH_LEFT = "switch_left"
    SWITCH_RIGHT = "switch_right"
    BUFFER = "buffer"
    CROSSING = "crossing"


# === Styles ==========================================================
@dataclass(frozen=True, slots=True)
class Style:
    fill: bool = True
    stroke: bool = False
    stroke_width: float = 80.0
    line_join: JoinStyle = JoinStyle.ROUND
    line_cap: CapStyle = CapStyle.ROUND
    dash: tuple[float, ...] = ()


FILL = Style(fill=True, stroke=False)
STROKE = Style(fill=False, stroke=True, stroke_width=80.0)
STROKE_THIN = Style(fill=False, stroke=True, stroke_width=60.0)


class Primitive:
    style: Style


class Primitives:
    # === Primitives (vector) ============================================
    @dataclass(frozen=True, slots=True)
    class Circle(Primitive):
        cx: float
        cy: float
        r: float
        style: Style = FILL

    @dataclass(frozen=True, slots=True)
    class Rect(Primitive):
        x: float
        y: float
        w: float
        h: float
        style: Style = FILL
        rx: float = 0.0  # rounded corners
        ry: float = 0.0

    @dataclass(frozen=True, slots=True)
    class Line(Primitive):
        x1: float
        y1: float
        x2: float
        y2: float
        style: Style = STROKE

    @dataclass(frozen=True, slots=True)
    class Polyline(Primitive):
        points: tuple[tuple[float, float], ...]
        closed: bool = False
        style: Style = STROKE

    @dataclass(frozen=True, slots=True)
    class Path:
        d: str
        style: Style = STROKE


@dataclass(frozen=True, slots=True)
class IconDef:
    viewbox: tuple[float, float, float, float]  # (minx, miny, width, height)
    prims: Sequence[Primitive]


class Builtins:
    @classmethod
    def _signal(cls) -> IconDef:
        vb = (-500.0, -500.0, 1000.0, 1000.0)
        r = 280.0
        stem_w = 160.0
        stem_h = 300.0
        return IconDef(
            viewbox=vb,
            prims=[
                Primitives.Circle(0.0, -120.0, r, FILL),
                Primitives.Rect(-stem_w / 2, r - 120.0, stem_w, stem_h, FILL),
            ],
        )

    @classmethod
    def _buffer(cls) -> IconDef:
        vb = (-500.0, -500.0, 1000.0, 1000.0)
        w, h = 760.0, 320.0
        return IconDef(
            viewbox=vb,
            prims=[Primitives.Rect(-w / 2, -h / 2, w, h, Style(fill=False, stroke=True, stroke_width=80.0))],
        )

    @classmethod
    def _crossing(cls) -> IconDef:
        vb = (-500.0, -500.0, 1000.0, 1000.0)
        L = 400.0
        return IconDef(
            viewbox=vb,
            prims=[
                Primitives.Line(-L, -L, L, L, STROKE),
                Primitives.Line(-L, L, L, -L, STROKE),
            ],
        )

    @classmethod
    def _switch(cls, dir: Literal["left", "right"]) -> IconDef:
        vb = (-500.0, -500.0, 1000.0, 1000.0)
        L = 420.0
        off = 260.0 if dir == "right" else -260.0
        return IconDef(
            viewbox=vb,
            prims=[
                Primitives.Line(-L, 0.0, L, 0.0, STROKE),  # main
                Primitives.Line(-L, 0.0, L, off, STROKE_THIN),  # diverge
            ],
        )

    @classmethod
    def icon_def(cls, name: Icon_Name) -> IconDef:
        ICONS: dict[Icon_Name, IconDef] = {
            Icon_Name.SIGNAL: cls._signal(),
            Icon_Name.BUFFER: cls._buffer(),
            Icon_Name.CROSSING: cls._crossing(),
            Icon_Name.SWITCH_LEFT: cls._switch("left"),
            Icon_Name.SWITCH_RIGHT: cls._switch("right"),
        }
        return ICONS[name]


def _builtin_icon_plan(name: Icon_Name, size: int, col_svg: str) -> list[tuple[str, dict[str, Any]]]:
    """
    Build a device-agnostic drawing plan for a builtin icon using the single
    source of truth in Builtins.icon_def. Coordinates are expressed around
    the origin and scaled to `size` so renderers can translate/rotate.
    """
    idef = Builtins.icon_def(name)
    minx, miny, vbw, vbh = idef.viewbox
    s = size / max(vbw, vbh) if max(vbw, vbh) else 1.0
    cx = minx + vbw / 2.0
    cy = miny + vbh / 2.0

    def T(px: float, py: float) -> tuple[int, int]:
        """Transform idef-space to origin-centered, scaled icon-space."""
        return round((px - cx) * s), round((py - cy) * s)

    plan: list[tuple[str, dict[str, Any]]] = []

    for prim in idef.prims:
        sty = prim.style
        width = max(1, round((sty.stroke_width or 1.0) * s))
        stroke = col_svg if sty.stroke else None
        fill = col_svg if sty.fill else None
        dash = None
        if sty.dash:
            dash = [max(1, round(d * s)) for d in sty.dash]

        if isinstance(prim, Primitives.Circle):
            x, y = T(prim.cx, prim.cy)
            r = max(1, round(prim.r * s))
            entry: dict[str, Any] = {"cx": x, "cy": y, "r": r}
            if fill:
                entry["fill"] = fill
            if stroke:
                entry["stroke"] = stroke
                entry["width"] = width
            plan.append(("circle", entry))

        elif isinstance(prim, Primitives.Rect):
            x0, y0 = T(prim.x, prim.y)
            w = round(prim.w * s)
            h = round(prim.h * s)
            entry: dict[str, Any] = {"x": x0, "y": y0, "w": w, "h": h}
            if fill:
                entry["fill"] = fill
            if stroke:
                entry["stroke"] = stroke
                entry["width"] = width
            plan.append(("rect", entry))

        elif isinstance(prim, Primitives.Line):
            x1, y1 = T(prim.x1, prim.y1)
            x2, y2 = T(prim.x2, prim.y2)
            entry: dict[str, Any] = {
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "width": width,
                "stroke": stroke or col_svg,
            }
            entry["cap"] = sty.line_cap.value
            if dash:
                entry["dash"] = dash
            plan.append(("line", entry))

        elif isinstance(prim, Primitives.Polyline):
            pts = []
            for px, py in prim.points:
                tx, ty = T(px, py)
                pts.append((tx, ty))
            entry: dict[str, Any] = {
                "points": pts,
                "closed": prim.closed,
            }
            if fill:
                entry["fill"] = fill
            if stroke:
                entry["stroke"] = stroke
                entry["width"] = width
            entry["join"] = sty.line_join.value
            if dash:
                entry["dash"] = dash
            plan.append(("polyline", entry))

        else:
            # Unknown primitive; ignore rather than exploding in export
            continue

    return plan

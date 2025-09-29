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
    # ---- generic ----
    PLUS = "plus"
    MINUS = "minus"
    CHECK = "check"
    CROSS_MARK = "crossmark"
    PLAY = "play"
    PAUSE = "pause"
    STOP = "stop"
    ARROW_UP = "arrow_up"
    ARROW_RIGHT = "arrow_right"
    ARROW_DOWN = "arrow_down"
    ARROW_LEFT = "arrow_left"
    CIRCLE_DOT = "circle_dot"
    SQUARE = "square"
    # ---- railway ----
    SIGNAL = "signal"
    SWITCH_LEFT = "switch_left"
    SWITCH_RIGHT = "switch_right"
    BUFFER = "buffer"
    BRIDGE = "bridge"
    TUNNEL = "tunnel"
    CROSSOVER = "crossover"
    DOUBLE_SLIP = "double_slip"
    # ---- electrical ----
    RESISTOR = "resistor"
    CAPACITOR = "capacitor"
    INDUCTOR = "inductor"
    DIODE = "diode"
    GROUND = "ground"
    SWITCH_SPST = "switch_spst"


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
    def _plus(cls) -> IconDef:
        vb = (-500.0, -500.0, 1000.0, 1000.0)
        L = 360.0
        return IconDef(vb, [Primitives.Line(-L, 0.0, L, 0.0, STROKE), Primitives.Line(0.0, -L, 0.0, L, STROKE)])

    @classmethod
    def _minus(cls) -> IconDef:
        vb = (-500.0, -500.0, 1000.0, 1000.0)
        L = 380.0
        return IconDef(vb, [Primitives.Line(-L, 0.0, L, 0.0, STROKE)])

    @classmethod
    def _check(cls) -> IconDef:
        vb = (-500.0, -500.0, 1000.0, 1000.0)
        pts = ((-320.0, -20.0), (-80.0, 220.0), (340.0, -220.0))
        return IconDef(vb, [Primitives.Polyline(points=pts, closed=False, style=STROKE)])

    @classmethod
    def _cross_mark(cls) -> IconDef:
        vb = (-500.0, -500.0, 1000.0, 1000.0)
        L = 380.0
        return IconDef(vb, [Primitives.Line(-L, -L, L, L, STROKE), Primitives.Line(-L, L, L, -L, STROKE)])

    @classmethod
    def _play(cls) -> IconDef:
        vb = (-500.0, -500.0, 1000.0, 1000.0)
        tri = ((-160.0, -280.0), (-160.0, 280.0), (260.0, 0.0))
        return IconDef(vb, [Primitives.Polyline(points=tri, closed=True, style=FILL)])

    @classmethod
    def _pause(cls) -> IconDef:
        vb = (-500.0, -500.0, 1000.0, 1000.0)
        w, h, gap = 160.0, 520.0, 140.0
        return IconDef(
            vb,
            [
                Primitives.Rect(-gap / 2 - w, -h / 2, w, h, FILL),
                Primitives.Rect(+gap / 2, -h / 2, w, h, FILL),
            ],
        )

    @classmethod
    def _stop(cls) -> IconDef:
        vb = (-500.0, -500.0, 1000.0, 1000.0)
        s = 520.0
        return IconDef(vb, [Primitives.Rect(-s / 2, -s / 2, s, s, FILL)])

    @classmethod
    def _arrow(cls, dir: str) -> IconDef:
        vb = (-500.0, -500.0, 1000.0, 1000.0)
        L, head = 340.0, 220.0
        # default: right
        shaft = Primitives.Line(-L, 0.0, L - head * 0.4, 0.0, STROKE)
        head_poly = Primitives.Polyline(
            points=((L - head, -head * 0.55), (L, 0.0), (L - head, head * 0.55)), closed=True, style=FILL
        )
        icon = IconDef(vb, [shaft, head_poly])
        if dir == "up":
            return cls._rotate(icon, -90)
        if dir == "down":
            return cls._rotate(icon, 90)
        if dir == "left":
            return cls._rotate(icon, 180)
        return icon

    # -------- railway --------
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
    def _switch(cls, dir: Literal["left", "right"]) -> IconDef:
        vb = (-500.0, -500.0, 1000.0, 1000.0)
        L = 420.0
        off = 260.0 if dir == "right" else -260.0
        return IconDef(
            viewbox=vb,
            prims=[
                Primitives.Line(-L, 0.0, L, 0.0, STROKE),
                Primitives.Line(-L, 0.0, L, off, STROKE_THIN),
            ],
        )

    @classmethod
    def _bridge(cls) -> IconDef:
        vb = (-500.0, -500.0, 1000.0, 1000.0)
        deck_w, deck_h = 760.0, 120.0
        leg_w, leg_h = 120.0, 300.0
        return IconDef(
            vb,
            [
                Primitives.Rect(-deck_w / 2, -80.0 - deck_h, deck_w, deck_h, FILL),
                Primitives.Rect(-deck_w / 3 - leg_w / 2, -80.0, leg_w, leg_h, FILL),
                Primitives.Rect(deck_w / 3 - leg_w / 2, -80.0, leg_w, leg_h, FILL),
            ],
        )

    @classmethod
    def _tunnel(cls) -> IconDef:
        vb = (-500.0, -500.0, 1000.0, 1000.0)
        w, h = 760.0, 520.0
        opening = Primitives.Rect(-w / 2, -h / 2, w, h, Style(fill=False, stroke=True, stroke_width=80.0))
        lintel = Primitives.Rect(-w / 2, -h / 2 - 80.0, w, 80.0, FILL)
        return IconDef(vb, [opening, lintel])

    @classmethod
    def _crossover(cls) -> IconDef:
        vb = (-500.0, -500.0, 1000.0, 1000.0)
        off = 220.0
        L = 420.0
        return IconDef(
            vb,
            [
                Primitives.Line(-L, -off, L, +off, STROKE_THIN),
                Primitives.Line(-L, +off, L, -off, STROKE_THIN),
            ],
        )

    @classmethod
    def _double_slip(cls) -> IconDef:
        vb = (-500.0, -500.0, 1000.0, 1000.0)
        L = 420.0
        off = 200.0
        return IconDef(
            vb,
            [
                Primitives.Line(-L, -L, L, L, STROKE_THIN),
                Primitives.Line(-L, L, L, -L, STROKE_THIN),
                Primitives.Line(-off, 0.0, off, 0.0, STROKE_THIN),
                Primitives.Line(0.0, -off, 0.0, off, STROKE_THIN),
            ],
        )

    # -------- electrical --------
    @classmethod
    def _resistor(cls) -> IconDef:
        vb = (-500.0, -500.0, 1000.0, 1000.0)
        # leads
        leadL = Primitives.Line(-420.0, 0.0, -260.0, 0.0, STROKE)
        leadR = Primitives.Line(260.0, 0.0, 420.0, 0.0, STROKE)
        # zigzag body
        zz = [
            (-260.0, 0.0),
            (-220.0, -120.0),
            (-180.0, 120.0),
            (-140.0, -120.0),
            (-100.0, 120.0),
            (-60.0, -120.0),
            (-20.0, 120.0),
            (20.0, -120.0),
            (60.0, 120.0),
            (100.0, -120.0),
            (140.0, 120.0),
            (180.0, -120.0),
            (220.0, 0.0),
        ]
        body = Primitives.Polyline(points=tuple(zz), closed=False, style=STROKE)
        return IconDef(vb, [leadL, body, leadR])

    @classmethod
    def _capacitor(cls) -> IconDef:
        vb = (-500.0, -500.0, 1000.0, 1000.0)
        return IconDef(
            vb,
            [
                Primitives.Line(-420.0, 0.0, -80.0, 0.0, STROKE),
                Primitives.Line(-80.0, -200.0, -80.0, 200.0, STROKE),
                Primitives.Line(+80.0, -200.0, +80.0, 200.0, STROKE),
                Primitives.Line(+80.0, 0.0, 420.0, 0.0, STROKE),
            ],
        )

    @classmethod
    def _inductor(cls) -> IconDef:
        vb = (-500.0, -500.0, 1000.0, 1000.0)
        r = 80.0
        cx = [-160.0, 0.0, 160.0]
        loops = [Primitives.Circle(x, 0.0, r, STROKE) for x in cx]
        return IconDef(
            vb,
            [
                Primitives.Line(-420.0, 0.0, -240.0, 0.0, STROKE),
                *loops,
                Primitives.Line(240.0, 0.0, 420.0, 0.0, STROKE),
            ],
        )

    @classmethod
    def _diode(cls) -> IconDef:
        vb = (-500.0, -500.0, 1000.0, 1000.0)
        tri = Primitives.Polyline(points=((-60.0, -180.0), (-60.0, 180.0), (160.0, 0.0)), closed=True, style=FILL)
        bar = Primitives.Line(200.0, -220.0, 200.0, 220.0, STROKE)
        return IconDef(
            vb,
            [
                Primitives.Line(-420.0, 0.0, -120.0, 0.0, STROKE),
                tri,
                bar,
                Primitives.Line(200.0, 0.0, 420.0, 0.0, STROKE),
            ],
        )

    @classmethod
    def _ground(cls) -> IconDef:
        vb = (-500.0, -500.0, 1000.0, 1000.0)
        return IconDef(
            vb,
            [
                Primitives.Line(0.0, -300.0, 0.0, -60.0, STROKE),
                Primitives.Line(-200.0, 0.0, 200.0, 0.0, STROKE),
                Primitives.Line(-140.0, 60.0, 140.0, 60.0, STROKE),
                Primitives.Line(-80.0, 120.0, 80.0, 120.0, STROKE),
            ],
        )

    @classmethod
    def _switch_spst(cls) -> IconDef:
        vb = (-500.0, -500.0, 1000.0, 1000.0)
        return IconDef(
            vb,
            [
                Primitives.Line(-420.0, 0.0, -80.0, 0.0, STROKE),
                Primitives.Line(80.0, 0.0, 420.0, 0.0, STROKE),
                Primitives.Line(-80.0, 0.0, 160.0, -160.0, STROKE),  # movable arm (open)
            ],
        )

    @staticmethod
    def _rotate(icon: IconDef, deg: float) -> IconDef:
        from math import cos, radians, sin

        c, s = cos(radians(deg)), sin(radians(deg))
        prims: list[Primitive] = []
        for p in icon.prims:
            if isinstance(p, Primitives.Line):
                x1, y1 = c * p.x1 - s * p.y1, s * p.x1 + c * p.y1
                x2, y2 = c * p.x2 - s * p.y2, s * p.x2 + c * p.y2
                prims.append(Primitives.Line(x1, y1, x2, y2, p.style))
            elif isinstance(p, Primitives.Rect):
                prims.append(p)  # leave axis-aligned rects; heads use polyline
            elif isinstance(p, Primitives.Circle):
                prims.append(Primitives.Circle(c * p.cx - s * p.cy, s * p.cx + c * p.cy, p.r, p.style))
            elif isinstance(p, Primitives.Polyline):
                pts = tuple((c * x - s * y, s * x + c * y) for (x, y) in p.points)
                prims.append(Primitives.Polyline(points=pts, closed=p.closed, style=p.style))
            else:
                prims.append(p)
        return IconDef(icon.viewbox, prims)

    @classmethod
    def icon_def(cls, name: Icon_Name) -> IconDef:
        ICONS: dict[Icon_Name, IconDef] = {
            # --- generic ---
            Icon_Name.PLUS: cls._plus(),
            Icon_Name.MINUS: cls._minus(),
            Icon_Name.CHECK: cls._check(),
            Icon_Name.CROSS_MARK: cls._cross_mark(),
            Icon_Name.PLAY: cls._play(),
            Icon_Name.PAUSE: cls._pause(),
            Icon_Name.STOP: cls._stop(),
            Icon_Name.ARROW_UP: cls._arrow("up"),
            Icon_Name.ARROW_RIGHT: cls._arrow("right"),
            Icon_Name.ARROW_DOWN: cls._arrow("down"),
            Icon_Name.ARROW_LEFT: cls._arrow("left"),
            Icon_Name.CIRCLE_DOT: IconDef((-500, -500, 1000, 1000), [Primitives.Circle(0.0, 0.0, 300.0, FILL)]),
            Icon_Name.SQUARE: IconDef((-500, -500, 1000, 1000), [Primitives.Rect(-300.0, -300.0, 600.0, 600.0, FILL)]),
            # --- railway ---
            Icon_Name.SIGNAL: cls._signal(),
            Icon_Name.BUFFER: cls._buffer(),
            Icon_Name.SWITCH_LEFT: cls._switch("left"),
            Icon_Name.SWITCH_RIGHT: cls._switch("right"),
            Icon_Name.BRIDGE: cls._bridge(),
            Icon_Name.TUNNEL: cls._tunnel(),
            Icon_Name.CROSSOVER: cls._crossover(),
            Icon_Name.DOUBLE_SLIP: cls._double_slip(),
            # --- electrical ---
            Icon_Name.RESISTOR: cls._resistor(),
            Icon_Name.CAPACITOR: cls._capacitor(),
            Icon_Name.INDUCTOR: cls._inductor(),
            Icon_Name.DIODE: cls._diode(),
            Icon_Name.GROUND: cls._ground(),
            Icon_Name.SWITCH_SPST: cls._switch_spst(),
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

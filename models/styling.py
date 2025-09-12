from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Mapping
from enum import Enum, StrEnum
from functools import lru_cache
from types import MappingProxyType
from typing import ClassVar, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, computed_field, model_validator


class Model(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    def replace(self, **updates) -> Self:
        return self.model_copy(update=updates)


class Anchor(Enum):
    NW = "nw"
    N = "n"
    NE = "ne"
    W = "w"
    C = "center"
    E = "e"
    SW = "sw"
    S = "s"
    SE = "se"

    # ---- parsing / normalisation ----
    @classmethod
    def parse(cls, value: str | Anchor | None) -> "Anchor":
        if isinstance(value, Anchor):
            return value
        if not value:
            return cls.C
        v = value.lower().strip()
        if v == "centre":
            v = "center"
        return next((a for a in cls if a.value == v), cls.C)

    # ---- targets ----
    @property
    def tk(self) -> TK_CARDINALS:
        """Tkinter Canvas.create_text(anchor=...)"""
        return self.value

    @property
    def pil(self) -> PIL_CARDINALS | None:
        """Pillow ImageDraw.text(anchor=...) — None means let Pillow default."""
        return _PIL[self]

    @property
    def svg(self) -> tuple[TextAnchor, DominantBaseline]:
        return _SVG[self]

    def _centre(self, px: int, py: int, w: int, h: int) -> tuple[int, int]:
        if self in (Anchor.NW, Anchor.W, Anchor.SW):
            dx = +w / 2
        elif self in (Anchor.NE, Anchor.E, Anchor.SE):
            dx = -w / 2
        else:
            dx = 0.0

        if self in (Anchor.NW, Anchor.N, Anchor.NE):
            dy = +h / 2
        elif self in (Anchor.SW, Anchor.S, Anchor.SE):
            dy = -h / 2
        else:
            dy = 0.0
        return round(px + dx), round(py + dy)

    def offset(self, w: int, h: int) -> tuple[float, float]:
        # vector from centre to this anchor in unrotated space
        ax = (
            -w / 2
            if self in (Anchor.NW, Anchor.W, Anchor.SW)
            else (w / 2 if self in (Anchor.NE, Anchor.E, Anchor.SE) else 0.0)
        )
        ay = (
            -h / 2
            if self in (Anchor.NW, Anchor.N, Anchor.NE)
            else (h / 2 if self in (Anchor.SW, Anchor.S, Anchor.SE) else 0.0)
        )
        return ax, ay

    def centre_for(self, px: int | float, py: int | float, w: int, h: int, rot_deg: int = 0) -> tuple[int, int]:
        # apply rotated offset to find the item centre
        from math import cos, radians, sin

        dx, dy = self.offset(w, h)
        if rot_deg:
            r = radians(rot_deg)
            dx, dy = (dx * cos(r) - dy * sin(r), dx * sin(r) + dy * cos(r))
        return round(px - dx), round(py - dy)


TK_CARDINALS = Literal["nw", "n", "ne", "w", "center", "e", "sw", "s", "se"]
PIL_CARDINALS = Literal["lt", "mt", "rt", "lm", "mm", "rm", "lb", "mb", "rb"]
TextAnchor = Literal["start", "middle", "end"]
DominantBaseline = Literal["hanging", "middle", "text-after-edge"]

_PIL: Final[Mapping[Anchor, PIL_CARDINALS]] = {
    Anchor.NW: "lt",
    Anchor.N: "mt",
    Anchor.NE: "rt",
    Anchor.W: "lm",
    Anchor.C: "mm",
    Anchor.E: "rm",
    Anchor.SW: "lb",
    Anchor.S: "mb",
    Anchor.SE: "rb",
}


_SVG: Final[Mapping[Anchor, tuple[TextAnchor, DominantBaseline]]] = {
    Anchor.NW: ("start", "hanging"),
    Anchor.N: ("middle", "hanging"),
    Anchor.NE: ("end", "hanging"),
    Anchor.W: ("start", "middle"),
    Anchor.C: ("middle", "middle"),
    Anchor.E: ("end", "middle"),
    Anchor.SW: ("start", "text-after-edge"),
    Anchor.S: ("middle", "text-after-edge"),
    Anchor.SE: ("end", "text-after-edge"),
}


class LineStyle(StrEnum):
    SOLID = "solid"
    DASH = "dash"
    LONG = "long"
    SHORT = "short"
    DOT = "dot"
    DASH_DOT = "dashdot"
    DASH_DOT_DOT = "dashdotdot"


class CapStyle(StrEnum):
    ROUND = "round"
    BUTT = "butt"
    PROJECTING = "projecting"


class JoinStyle(StrEnum):
    MITER = "miter"
    ROUND = "round"
    BEVEL = "bevel"


# Base patterns defined in *stroke-width units*
# (i.e., multiply by actual width in px to get real pixel pattern)
_BASE: dict[LineStyle | None, tuple[float, ...]] = {
    None: (),  # solid
    LineStyle.SOLID: (),
    LineStyle.DASH: (3, 2),
    LineStyle.LONG: (6, 3),
    LineStyle.SHORT: (2, 2),
    LineStyle.DOT: (0.1, 1.9),
    LineStyle.DASH_DOT: (3, 2, 0.1, 2),
    LineStyle.DASH_DOT_DOT: (3, 2, 0.1, 2, 0.1, 2),
}


def _normalise_pairs(seq: Iterable[int]) -> tuple[int, ...]:
    """Ensure even-length (on/off pairs) and no zeros except for tiny 'dot' hack."""
    arr = list(seq)
    if not arr:
        return ()
    if len(arr) % 2 == 1:
        arr *= 2
    # prevent pathological zero/negative lengths
    for i, v in enumerate(arr):
        if v <= 0:
            arr[i] = 1
    return tuple(arr)


def scaled_pattern(style: LineStyle | None, width_px: int) -> tuple[int, ...]:
    """
    Return a pixel pattern (ints) scaled by stroke width.
    - style: key into _BASE
    - width_px: actual stroke width in pixels
    """
    base = _BASE.get(style, _BASE[None])
    if not base:
        return ()
    w = max(1, width_px)
    # scale each segment by width; clamp to at least 1px so it remains visible
    scaled = [max(1, round(seg * w)) for seg in base]
    return _normalise_pairs(scaled)


def svg_dasharray(style: LineStyle | None, width_px: int) -> str | None:
    """
    SVG stroke-dasharray string scaled by width, or None for solid.
    """
    pat = scaled_pattern(style, width_px)
    if not pat:
        return None
    return ",".join(str(x) for x in pat)


class Colour(Model):
    red: int
    green: int
    blue: int
    alpha: int = 255

    model_config = ConfigDict(frozen=True, extra="ignore")  # ignore legacy "name"

    @model_validator(mode="after")
    def _clamp(self):
        def clamp(v: int) -> int:
            return 0 if v < 0 else 255 if v > 255 else v

        object.__setattr__(self, "red", clamp(self.red))
        object.__setattr__(self, "green", clamp(self.green))
        object.__setattr__(self, "blue", clamp(self.blue))
        object.__setattr__(self, "alpha", clamp(self.alpha))
        return self

    @property
    def rgb(self) -> tuple[int, int, int]:
        return self.red, self.green, self.blue

    @property
    def rgba(self) -> tuple[int, int, int, int]:
        return self.red, self.green, self.blue, self.alpha

    @property
    def hex(self) -> str:
        return f"#{self.red:02X}{self.green:02X}{self.blue:02X}"

    @property
    def hexa(self) -> str:
        return f"#{self.red:02X}{self.green:02X}{self.blue:02X}{self.alpha:02X}"

    @computed_field
    @property
    def name(self) -> str | None:
        return PALETTE_BY_RGBA.get(self.rgba)

    @computed_field
    @property
    def name_str(self) -> str:
        return PALETTE_BY_RGBA.get(self.rgba, f"Unknown: {self.rgba}")

    def with_alpha(self, a: int) -> "Colour":
        return Colour(red=self.red, green=self.green, blue=self.blue, alpha=a)


Colour_Name = Literal[
    "white",
    "black",
    "transparent",
    "red",
    "green",
    "blue",
    "cyan",
    "magenta",
    "yellow",
    "gray",
    "light_gray",
    "dark_gray",
    "sky",
]


@lru_cache(maxsize=256)
def nearest_name(col: Colour, *, include_alpha: bool = False) -> str | None:
    # simple Euclidean distance in RGB or RGBA space
    target = col.rgba if include_alpha else col.rgb
    best_name: str | None = None
    best_d = 10**9
    for name, c in PALETTE.items():
        v = c.rgba if include_alpha else c.rgb
        d = sum((a - b) * (a - b) for a, b in zip(target, v))
        if d < best_d:
            best_d = d
            best_name = name
    return best_name


class Colours:
    white: ClassVar[Colour] = Colour(red=255, green=255, blue=255)
    black: ClassVar[Colour] = Colour(red=0, green=0, blue=0)
    transparent: ClassVar[Colour] = Colour(red=0, green=0, blue=0, alpha=0)
    red: ClassVar[Colour] = Colour(red=255, green=0, blue=0)
    green: ClassVar[Colour] = Colour(red=0, green=255, blue=0)
    blue: ClassVar[Colour] = Colour(red=0, green=0, blue=255)
    cyan: ClassVar[Colour] = Colour(red=0, green=255, blue=255)
    magenta: ClassVar[Colour] = Colour(red=255, green=0, blue=255)
    yellow: ClassVar[Colour] = Colour(red=255, green=255, blue=0)
    gray: ClassVar[Colour] = Colour(red=128, green=128, blue=128)

    class sys:
        light_gray: ClassVar[Colour] = Colour(red=200, green=200, blue=200)
        dark_gray: ClassVar[Colour] = Colour(red=60, green=60, blue=60)
        sky: ClassVar[Colour] = Colour(red=30, green=200, blue=255)

    # ---------- internals ----------
    @classmethod
    def _iter(cls, *, include_sys: bool = False) -> Iterator[tuple[str, Colour]]:
        # top-level colours
        for k, v in vars(cls).items():
            if isinstance(v, Colour):
                yield k, v
        # optional sys subgroup
        if include_sys and hasattr(cls, "sys"):
            for k, v in vars(cls.sys).items():
                if isinstance(v, Colour):
                    yield k, v

    @classmethod
    def _map(cls, *, include_sys: bool = False, min_alpha: int = 0) -> Mapping[str, Colour]:
        items = ((k, c) for k, c in cls._iter(include_sys=include_sys) if c.alpha >= min_alpha)
        # return a read-only, name-sorted mapping
        return MappingProxyType(dict(items))

    # ---------- public helpers ----------
    @classmethod
    def names(cls, *, include_sys: bool = False, min_alpha: int = 0) -> list[str]:
        return list(cls._map(include_sys=include_sys, min_alpha=min_alpha).keys())

    @classmethod
    def list(cls, *, include_sys: bool = False, min_alpha: int = 0) -> list[Colour]:
        return list(cls._map(include_sys=include_sys, min_alpha=min_alpha).values())

    @classmethod
    def items(cls, *, include_sys: bool = False, min_alpha: int = 0) -> list[tuple[str, Colour]]:
        m = cls._map(include_sys=include_sys, min_alpha=min_alpha)
        return list(m.items())

    @property
    def all(self) -> Mapping[str, Colour]:  # read-only view
        return PALETTE

    _HEX_RE = re.compile(r"^#?(?P<hex>[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")

    @classmethod
    def parse_colour(cls, value: str | tuple[int, int, int] | tuple[int, int, int, int] | Colour) -> Colour:
        if isinstance(value, Colour):
            return value
        if isinstance(value, tuple):
            r, g, b, *rest = value
            a = rest[0] if rest else 255
            return Colour(red=r, green=g, blue=b, alpha=a)
        if isinstance(value, str):
            if c := get_colour(value):
                return c
            m = cls._HEX_RE.match(value.strip())
            if m:
                hx = m.group("hex")
                if len(hx) == 6:
                    r, g, b = int(hx[0:2], 16), int(hx[2:4], 16), int(hx[4:6], 16)
                    return Colour(red=r, green=g, blue=b)
                else:
                    r, g, b, a = (int(hx[i : i + 2], 16) for i in (0, 2, 4, 6))
                    return Colour(red=r, green=g, blue=b, alpha=a)
        raise ValueError(f"Unrecognized colour: {value!r}")

    @staticmethod
    def name_for(col: Colour) -> str | None:
        return PALETTE_BY_RGBA.get(col.rgba)


def _collect_palette() -> dict[str, Colour]:
    base = {k: v for k, v in vars(Colours).items() if isinstance(v, Colour)}
    sysd = {f"{k}": v for k, v in vars(Colours.sys).items() if isinstance(v, Colour)}
    base.update(sysd)
    return base


PALETTE: Final[Mapping[str, Colour]] = _collect_palette()
PALETTE_BY_RGBA: Final[Mapping[tuple[int, int, int, int], str]] = {c.rgba: n for n, c in PALETTE.items()}


# Convenience
def get_colour(name: Colour_Name | str) -> Colour | None:
    return PALETTE.get(name.lower())


def get_colour_or(name: str, fallback: Colour | None = None) -> Colour:
    return get_colour(name) or fallback or Colours.white


class TkCursor(StrEnum):
    X_CURSOR = "X_cursor"
    ARROW = "arrow"
    BASED_ARROW_DOWN = "based_arrow_down"
    BASED_ARROW_UP = "based_arrow_up"
    BOAT = "boat"
    BOGOSITY = "bogosity"
    BOTTOM_LEFT_CORNER = "bottom_left_corner"
    BOTTOM_RIGHT_CORNER = "bottom_right_corner"
    BOTTOM_SIDE = "bottom_side"
    BOTTOM_TEE = "bottom_tee"
    BOX_SPIRAL = "box_spiral"
    CENTRE_PTR = "center_ptr"
    CIRCLE = "circle"
    CLOCK = "clock"
    COFFEE_MUG = "coffee_mug"
    CROSS = "cross"
    CROSS_REVERSE = "cross_reverse"
    CROSSHAIR = "crosshair"
    DIAMOND_CROSS = "diamond_cross"
    DOT = "dot"
    DOTBOX = "dotbox"
    DOUBLE_ARROW = "double_arrow"
    DRAFT_LARGE = "draft_large"
    DRAFT_SMALL = "draft_small"
    DRAPED_BOX = "draped_box"
    EXCHANGE = "exchange"
    FLEUR = "fleur"
    GOBBLER = "gobbler"
    GUMBY = "gumby"
    HAND1 = "hand1"
    HAND2 = "hand2"
    HEART = "heart"
    ICON = "icon"
    IRON_CROSS = "iron_cross"
    LEFT_PTR = "left_ptr"
    LEFT_SIDE = "left_side"
    LEFT_TEE = "left_tee"
    LEFTBUTTON = "leftbutton"
    LL_ANGLE = "ll_angle"
    LR_ANGLE = "lr_angle"
    MAN = "man"
    MIDDLEBUTTON = "middlebutton"
    MOUSE = "mouse"
    NONE = "none"  # hide the cursor entirely
    PENCIL = "pencil"
    PIRATE = "pirate"
    PLUS = "plus"
    QUESTION_ARROW = "question_arrow"
    RIGHT_PTR = "right_ptr"
    RIGHT_SIDE = "right_side"
    RIGHT_TEE = "right_tee"
    RIGHTBUTTON = "rightbutton"
    RTL_LOGO = "rtl_logo"
    SAILBOAT = "sailboat"
    SB_DOWN_ARROW = "sb_down_arrow"
    SB_H_DOUBLE_ARROW = "sb_h_double_arrow"
    SB_LEFT_ARROW = "sb_left_arrow"
    SB_RIGHT_ARROW = "sb_right_arrow"
    SB_UP_ARROW = "sb_up_arrow"
    SB_V_DOUBLE_ARROW = "sb_v_double_arrow"
    SHUTTLE = "shuttle"
    SIZING = "sizing"
    SPIDER = "spider"
    SPRAYCAN = "spraycan"
    STAR = "star"
    TARGET = "target"
    TCROSS = "tcross"
    TOP_LEFT_ARROW = "top_left_arrow"
    TOP_LEFT_CORNER = "top_left_corner"
    TOP_RIGHT_CORNER = "top_right_corner"
    TOP_SIDE = "top_side"
    TOP_TEE = "top_tee"
    TREK = "trek"
    UL_ANGLE = "ul_angle"
    UMBRELLA = "umbrella"
    UR_ANGLE = "ur_angle"
    WATCH = "watch"
    XTERM = "xterm"

# models/linestyle.py
from __future__ import annotations

import enum
from collections.abc import Iterable


class LineStyle(enum.StrEnum):
    SOLID = "solid"
    DASH = "dash"
    LONG = "long"
    SHORT = "short"
    DOT = "dot"
    DASH_DOT = "dashdot"
    DASH_DOT_DOT = "dashdotdot"


class CapStyle(enum.StrEnum):
    ROUND = "round"
    BUTT = "butt"
    PROJECTING = "projecting"


# Base patterns defined in *stroke-width units*
# (i.e., multiply by actual width in px to get real pixel pattern)
_BASE: dict[LineStyle | None, tuple[float, ...]] = {
    None: (),  # solid
    LineStyle.SOLID: (),
    LineStyle.DASH: (3, 2),
    LineStyle.LONG: (6, 3),
    LineStyle.SHORT: (2, 2),
    LineStyle.DOT: (0.1, 1.9),  # tiny on, bigger off → dots
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
        if v < 0:
            arr[i] = 0
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
    w = max(1, int(width_px))
    # scale each segment by width; clamp to at least 1px so it remains visible
    scaled = [max(1, int(round(seg * w))) for seg in base]
    return _normalise_pairs(scaled)


def svg_dasharray(style: LineStyle | None, width_px: int) -> str | None:
    """
    SVG stroke-dasharray string scaled by width, or None for solid.
    """
    pat = scaled_pattern(style, width_px)
    if not pat:
        return None
    return ",".join(str(x) for x in pat)

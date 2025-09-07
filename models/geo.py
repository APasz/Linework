from dataclasses import dataclass

from models.colour import Colour
from models.linestyle import LineStyle, CapStyle


@dataclass(slots=True)
class Line:
    x1: int
    y1: int
    x2: int
    y2: int
    col: Colour
    width: int
    capstyle: CapStyle = CapStyle.ROUND
    style: LineStyle = LineStyle.SOLID
    dash_offset: int = 0


@dataclass(slots=True)
class Point:
    x: int
    y: int
    capstyle: CapStyle = CapStyle.ROUND

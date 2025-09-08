from dataclasses import dataclass

from models.colour import Colour
from models.linestyle import CapStyle, LineStyle


@dataclass(slots=True)
class Point:
    x: int
    y: int
    capstyle: CapStyle = CapStyle.ROUND


@dataclass(slots=True)
class Line:
    a: Point
    b: Point
    col: Colour
    width: int
    capstyle: CapStyle = CapStyle.ROUND
    style: LineStyle = LineStyle.SOLID
    dash_offset: int = 0

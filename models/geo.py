from enum import StrEnum

from models.styling import Anchor, CapStyle, Colour, LineStyle, Model


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


class Label(Model):
    p: Point
    text: str
    col: Colour
    anchor: Anchor = Anchor.NW
    size: int = 12
    rotation: int = 0
    snap: bool = True


class IconName(StrEnum):
    SIGNAL = "signal"
    SWITCH = "switch"
    BUFFER = "buffer"
    CROSSING = "crossing"


class Icon(Model):
    p: Point
    name: IconName
    col: Colour
    anchor: Anchor = Anchor.SE
    size: int = 16
    rotation: int = 0
    snap: bool = True

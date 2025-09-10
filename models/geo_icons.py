from enum import StrEnum
from typing import NamedTuple


class Icon_Name(StrEnum):
    SIGNAL = "signal"
    SWITCH = "switch"
    BUFFER = "buffer"
    CROSSING = "crossing"


class Circle(NamedTuple):
    cx: int
    cy: int
    r: int


class LineSeg(NamedTuple):
    x1: int
    y1: int
    x2: int
    y2: int


class Rect(NamedTuple):
    x: int
    y: int
    w: int
    h: int
    stroke: int
    filled: bool


Primitive = Circle | LineSeg | Rect


def icon_primitives(name: Icon_Name, size: int) -> list[Primitive]: ...

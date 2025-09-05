from dataclasses import dataclass
from typing import Literal

from models.colour import Colour


@dataclass(slots=True, frozen=True)
class Line:
    x1: int
    y1: int
    x2: int
    y2: int
    col: Colour
    width: int
    capstyle: Literal["round", "projecting", "butt"] = "round"


@dataclass(slots=True, frozen=True)
class Point:
    x: int
    y: int
    capstyle: Literal["round", "projecting", "butt"] = "round"

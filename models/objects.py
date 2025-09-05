from dataclasses import dataclass
from typing import Literal

from models.colour import Colour


@dataclass(slots=True, frozen=True)
class Label:
    x: int
    y: int
    text: str
    col: Colour
    anchor: Literal["nw", "n", "ne", "w", "center", "e", "sw", "s", "se"] = "nw"
    size: int = 12  # px


@dataclass(slots=True, frozen=True)
class Icon:
    x: int
    y: int
    name: Literal["signal", "switch", "buffer", "crossing"]  # start simple; add more later
    col: Colour
    size: int = 16
    rotation: int = 0  # degrees

from dataclasses import dataclass
from typing import Literal

from models.anchors import Anchor
from models.colour import Colour


@dataclass(slots=True, frozen=True)
class Label:
    x: int
    y: int
    text: str
    col: Colour
    anchor: Anchor = Anchor.NW
    size: int = 12
    rotation: int = 0


@dataclass(slots=True, frozen=True)
class Icon:
    x: int
    y: int
    name: Literal["signal", "switch", "buffer", "crossing"]
    col: Colour
    anchor: Anchor = Anchor.SE
    size: int = 16
    rotation: int = 0

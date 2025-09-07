# models/anchor.py
from __future__ import annotations

from enum import Enum
from typing import Literal


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
        for a in cls:
            if a.value == v:
                return a
        return cls.C

    # ---- targets ----
    @property
    def tk(self) -> Literal["nw", "n", "ne", "w", "center", "e", "sw", "s", "se"]:
        """Tkinter Canvas.create_text(anchor=...)"""
        return self.value

    @property
    def pil(self) -> Literal["lt", "mt", "rt", "lm", "mm", "rm", "lb", "mb", "rm"] | str | None:
        """Pillow ImageDraw.text(anchor=...) — None means let Pillow default."""
        _PIL = {
            "nw": "lt",
            "n": "mt",
            "ne": "rt",
            "w": "lm",
            "center": "mm",
            "e": "rm",
            "sw": "lb",
            "s": "mb",
            "se": "rb",
        }
        return _PIL.get(self.value)

    @property
    def svg(
        self,
    ) -> tuple[
        Literal["start", "middle", "end", "start", "middle", "end", "start", "middle", "end"] | str,
        Literal[
            "hanging",
            "hanging",
            "hanging",
            "middle",
            "middle",
            "middle",
            "text-after-edge",
            "text-after-edge",
            "text-after-edge",
        ]
        | str,
    ]:
        """(text-anchor, dominant-baseline)"""
        _SVG = {
            "nw": ("start", "hanging"),
            "n": ("middle", "hanging"),
            "ne": ("end", "hanging"),
            "w": ("start", "middle"),
            "center": ("middle", "middle"),
            "e": ("end", "middle"),
            "sw": ("start", "text-after-edge"),
            "s": ("middle", "text-after-edge"),
            "se": ("end", "text-after-edge"),
        }
        return _SVG[self.value]

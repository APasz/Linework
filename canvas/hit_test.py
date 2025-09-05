from dataclasses import dataclass
from typing import Any, Literal
import tkinter as tk


@dataclass
class Hit:
    kind: Literal["label", "icon", "line"]
    token: Any  # canvas id for label/line; icon index for "icon"


def hit_under_cursor(canvas: tk.Canvas, x: int, y: int) -> Hit | None:
    items = canvas.find_overlapping(x, y, x, y)
    if not items:
        return None
    # prefer labels
    for item in items:
        if "label" in canvas.gettags(item):
            return Hit("label", item)
    # then icons (look for icon:<idx>)
    for item in items:
        for t in canvas.gettags(item):
            if t.startswith("icon:"):
                return Hit("icon", int(t.split(":", 1)[1]))
    # finally lines
    for item in items:
        if "line" in canvas.gettags(item):
            return Hit("line", item)
    return None

import tkinter as tk
from dataclasses import dataclass
from typing import Literal


@dataclass
class Hit:
    kind: Literal["label", "icon", "line"]
    canvas_idx: int
    tag_idx: int


def _find_hit(canvas: tk.Canvas, cid: int, prefix: Literal["label", "icon", "line"]) -> Hit | None:
    """Find a {prefix}:{index} tag on this item and return a Hit with that index.
    IMPORTANT: index 0 is valid, so check `is not None` not truthiness."""
    tag_idx: int | None = None
    want = prefix + ":"
    for t in canvas.gettags(cid):
        if t.startswith(want):
            try:
                tag_idx = int(t.split(":", 1)[1])
                break
            except ValueError:
                continue
    if tag_idx is None:
        return None
    return Hit(prefix, cid, tag_idx)


def test_hit(canvas: tk.Canvas, x: int, y: int) -> Hit | None:
    items = canvas.find_overlapping(x, y, x, y)
    if not items:
        return None
    for item in items:
        if hit := _find_hit(canvas, item, "label"):
            return hit
    for item in items:
        if hit := _find_hit(canvas, item, "icon"):
            return hit
    for item in items:
        if hit := _find_hit(canvas, item, "line"):
            return hit
    return None

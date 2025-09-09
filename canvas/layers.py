from __future__ import annotations

import tkinter as tk
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class Hit_Kind(StrEnum):
    label = "label"
    icon = "icon"
    line = "line"
    miss = ""


@dataclass
class Hit:
    kind: Hit_Kind
    canvas_idx: int
    tag_idx: int


def _find_hit(canvas: tk.Canvas, cid: int, prefix: Hit_Kind) -> Hit | None:
    """Find a {prefix}:{index} tag on this item and return a Hit with that index.
    IMPORTANT: index 0 is valid, so check `is not None` not truthiness."""
    tag_idx: int | None = None
    want = prefix.value + ":"
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
        if hit := _find_hit(canvas, item, Hit_Kind.label):
            return hit
    for item in items:
        if hit := _find_hit(canvas, item, Hit_Kind.icon):
            return hit
    for item in items:
        if hit := _find_hit(canvas, item, Hit_Kind.line):
            return hit
    return None


class Layer_Name(StrEnum):
    grid = "grid"
    lines = "lines"
    labels = "labels"
    icons = "icons"
    preview = "preview"


LAYER_TAGS = {
    Layer_Name.grid: f"layer:{Layer_Name.grid.value}",
    Layer_Name.lines: f"layer:{Layer_Name.lines.value}",
    Layer_Name.labels: f"layer:{Layer_Name.labels.value}",
    Layer_Name.icons: f"layer:{Layer_Name.icons.value}",
    Layer_Name.preview: f"layer:{Layer_Name.preview.value}",
}


def item_tag(kind: Hit_Kind, idx: int) -> str:
    return f"{kind.value}:{idx}"


def layer_tag(layer: Layer_Name) -> str:
    return LAYER_TAGS[layer]


def tag_tuple(kind: Hit_Kind, idx: int, layer: Layer_Name) -> tuple[str, str, str]:
    # order matters for your selection code
    return (kind.value, layer_tag(layer), item_tag(kind, idx))


class Painters(Protocol):
    def paint_grid(self, canvas: tk.Canvas, /): ...
    def paint_lines(self, canvas: tk.Canvas, /): ...
    def paint_labels(self, canvas: tk.Canvas, /): ...
    def paint_icons(self, canvas: tk.Canvas, /): ...


class Layer_Manager:
    """Thin wrapper around canvas tags for per-layer operations."""

    def __init__(self, canvas: tk.Canvas, painters: Painters):
        self.canvas = canvas
        self.painters = painters

    def _enforce_z(self):
        self.canvas.tag_lower(layer_tag(Layer_Name.grid))
        self.canvas.tag_raise(layer_tag(Layer_Name.lines))
        self.canvas.tag_raise(layer_tag(Layer_Name.icons))
        self.canvas.tag_raise(layer_tag(Layer_Name.labels))
        self.canvas.tag_raise(layer_tag(Layer_Name.preview))

    # --- clears ---
    def clear(self, layer: Layer_Name):
        if not layer:
            return
        self.canvas.delete(layer_tag(layer))

    def clear_many(self, layers: Iterable[Layer_Name]):
        for layer in layers:
            self.clear(layer)

    def clear_all(self):
        # nukes all known layers; don’t use canvas.delete("all") so you can keep temp overlays if you want
        for layer in Layer_Name:
            self.clear(layer)

    def clear_preview(self):
        self.canvas.delete(layer_tag(Layer_Name.preview))

    # --- redraws ---
    def redraw(self, layer: Layer_Name):
        if not layer:
            return
        self.clear(layer)
        self._paint(layer)
        self._enforce_z()

    def redraw_many(self, layers: Iterable[Layer_Name]):
        for layer in layers:
            self.redraw(layer)

    def redraw_all(self):
        self.clear_all()
        for layer in Layer_Name:
            self._paint(layer)
        self._enforce_z()

    # --- internals ---
    def _paint(self, layer: Layer_Name):
        if layer == Layer_Name.lines:
            self.painters.paint_lines(self.canvas)
        elif layer == Layer_Name.labels:
            self.painters.paint_labels(self.canvas)
        elif layer == Layer_Name.icons:
            self.painters.paint_icons(self.canvas)
        elif layer == Layer_Name.grid:
            self.painters.paint_grid(self.canvas)

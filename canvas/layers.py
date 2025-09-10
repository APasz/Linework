from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.geo import CanvasLW


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


def _find_hit(canvas: "CanvasLW", cid: int, prefix: Hit_Kind) -> Hit | None:
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


def test_hit(canvas: "CanvasLW", x: int, y: int) -> Hit | None:
    items = canvas.find_overlapping(x, y, x, y)
    if not items:
        return None
    for item in reversed(items):
        if hit := _find_hit(canvas, item, Hit_Kind.label):
            return hit
    for item in reversed(items):
        if hit := _find_hit(canvas, item, Hit_Kind.icon):
            return hit
    for item in reversed(items):
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


def tag_list(kind: Hit_Kind, idx: int, layer: Layer_Name) -> list[str]:
    # order matters for your selection code
    return [kind.value, layer_tag(layer), item_tag(kind, idx)]


if TYPE_CHECKING:
    from canvas.painters import Painters


class Layer_Manager:
    """Thin wrapper around canvas tags for per-layer operations."""

    _PROTECTED: set[Layer_Name] = {Layer_Name.grid}

    def __init__(self, canvas: CanvasLW, painters: Painters):
        self.canvas = canvas
        self.painters = painters

    def _enforce_z(self):
        self.canvas.tag_lower_l(Layer_Name.grid)
        self.canvas.tag_raise_l(Layer_Name.lines)
        self.canvas.tag_raise_l(Layer_Name.icons)
        self.canvas.tag_raise_l(Layer_Name.labels)
        self.canvas.tag_raise_l(Layer_Name.preview)

    # --- clears ---
    def clear(self, layer: Layer_Name, force: bool = False):
        if not layer:
            return
        if layer in self._PROTECTED and not force:
            return
        self.canvas.delete(layer_tag(layer))

    def clear_many(self, layers: Iterable[Layer_Name]):
        for layer in layers:
            self.clear(layer)

    def clear_all(self):
        # nukes all known layers; don’t use canvas.delete("all") so you can keep temp overlays if you want
        for layer in Layer_Name:
            self.clear(layer)
        known = set(LAYER_TAGS.values())
        for iid in self.canvas.find_all():
            tags = set(self.canvas.gettags(iid))
            if not tags.intersection(known):
                self.canvas.delete(iid)

    def clear_preview(self):
        self.clear(Layer_Name.preview)

    # --- redraws ---
    def redraw(self, layer: Layer_Name, force: bool = False):
        if not layer:
            return
        self.clear(layer, force)
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
        self._enforce_z()

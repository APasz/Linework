from __future__ import annotations
import tkinter as tk
from typing import Iterable, Literal, Protocol

L_GRID: str = "layer:grid"
L_LINES: str = "layer:lines"
L_LABELS: str = "layer:labels"
L_ICONS: str = "layer:icons"
L_PREV: str = "layer:preview"

LayerName = Literal["grid", "lines", "labels", "icons"]


class Painters(Protocol):
    def paint_grid(self, canvas: tk.Canvas, /) -> None: ...
    def paint_lines(self, canvas: tk.Canvas, /) -> None: ...
    def paint_labels(self, canvas: tk.Canvas, /) -> None: ...
    def paint_icons(self, canvas: tk.Canvas, /) -> None: ...


class LayerManager:
    """Thin wrapper around canvas tags for per-layer operations."""

    ORDER: tuple[LayerName, ...] = ("grid", "lines", "icons", "labels")

    def __init__(self, canvas: tk.Canvas, painters: Painters):
        self.canvas = canvas
        self.painters = painters

    def _enforce_z(self):
        self.canvas.tag_lower(self._tag("grid"))
        self.canvas.tag_raise(self._tag("lines"))
        self.canvas.tag_raise(self._tag("icons"))
        self.canvas.tag_raise(self._tag("labels"))
        self.canvas.tag_raise(L_PREV)

    # --- clears ---
    def clear(self, layer: LayerName) -> None:
        if not layer:
            return
        self.canvas.delete(self._tag(layer))

    def clear_many(self, layers: Iterable[LayerName]) -> None:
        for layer in layers:
            self.clear(layer)

    def clear_all(self) -> None:
        # nukes all known layers; don’t use canvas.delete("all") so you can keep temp overlays if you want
        for layer in self.ORDER:
            self.clear(layer)

    def clear_preview(self) -> None:
        self.canvas.delete(L_PREV)

    # --- redraws ---
    def redraw(self, layer: LayerName) -> None:
        if not layer:
            return
        self.clear(layer)
        self._paint(layer)
        self._enforce_z()

    def redraw_many(self, layers: Iterable[LayerName]) -> None:
        for layer in layers:
            self.redraw(layer)

    def redraw_all(self) -> None:
        # draw in z-order
        self.clear_all()
        for layer in self.ORDER:
            self._paint(layer)
        self._enforce_z()

    # --- internals ---
    def _tag(self, layer: LayerName) -> str:
        return {
            "lines": L_LINES,
            "labels": L_LABELS,
            "icons": L_ICONS,
            "grid": L_GRID,
        }[layer]

    def _paint(self, layer: LayerName) -> None:
        if layer == "lines":
            self.painters.paint_lines(self.canvas)
        elif layer == "labels":
            self.painters.paint_labels(self.canvas)
        elif layer == "icons":
            self.painters.paint_icons(self.canvas)
        elif layer == "grid":
            self.painters.paint_grid(self.canvas)

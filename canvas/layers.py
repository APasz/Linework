from __future__ import annotations
import tkinter as tk
from typing import Iterable, Literal, Protocol

# Canonical layer tags — keep these stable
L_GRID: str = "layer:grid"
L_LINES: str = "layer:lines"
L_LABELS: str = "layer:labels"
L_ICONS: str = "layer:icons"

LayerName = Literal["grid", "lines", "labels", "icons"]


class Painters(Protocol):
    def paint_grid(self, c: tk.Canvas) -> None: ...
    def paint_lines(self, c: tk.Canvas) -> None: ...
    def paint_labels(self, c: tk.Canvas) -> None: ...
    def paint_icons(self, c: tk.Canvas) -> None: ...


class LayerManager:
    """Thin wrapper around canvas tags for per-layer operations."""

    ORDER: tuple[LayerName, ...] = ("grid", "lines", "icons", "labels")

    def __init__(self, canvas: tk.Canvas, painters: Painters):
        self.c = canvas
        self.p = painters

    # --- clears ---
    def clear(self, layer: LayerName) -> None:
        if not layer:
            return
        self.c.delete(self._tag(layer))

    def clear_many(self, layers: Iterable[LayerName]) -> None:
        for layer in layers:
            self.clear(layer)

    def clear_all(self) -> None:
        # nukes all known layers; don’t use canvas.delete("all") so you can keep temp overlays if you want
        for layer in self.ORDER:
            self.clear(layer)

    # --- redraws ---
    def redraw(self, layer: LayerName) -> None:
        if not layer:
            return
        self.clear(layer)
        self._paint(layer)

    def redraw_many(self, layers: Iterable[LayerName]) -> None:
        for layer in layers:
            self.redraw(layer)

    def redraw_all(self) -> None:
        # draw in z-order
        self.clear_all()
        for layer in self.ORDER:
            self._paint(layer)

    # --- internals ---
    def _tag(self, layer: LayerName) -> str:
        return {
            "grid": L_GRID,
            "lines": L_LINES,
            "labels": L_LABELS,
            "icons": L_ICONS,
        }[layer]

    def _paint(self, layer: LayerName) -> None:
        if layer == "grid":
            self.p.paint_grid(self.c)
        elif layer == "lines":
            self.p.paint_lines(self.c)
        elif layer == "labels":
            self.p.paint_labels(self.c)
        elif layer == "icons":
            self.p.paint_icons(self.c)

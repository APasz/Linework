from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from tkinter import ttk

from models.colour import Colour
from models.colour import Colours as Cols


@dataclass
class Palette_Handles:
    frame: ttk.Frame
    set_selected: Callable[[str], None]  # call with colour name


class Colour_Palette(ttk.Frame):
    def __init__(
        self,
        master,
        colours: Iterable[Colour],
        on_select: Callable[[str], None],
        on_set_bg: Callable[[str], None],
        selected_name: str | None = None,
    ):
        super().__init__(master)
        self._on_select = on_select
        self._on_set_bg = on_set_bg
        self._swatches: list[tuple[tk.Canvas, str]] = []

        # label (optional)
        ttk.Label(self).pack(side="left", padx=(0, 6))

        for col in colours:
            sw = tk.Canvas(self, width=18, height=18, highlightthickness=0)
            sw.configure(highlightbackground=Cols.sys.dark_gray.hex, highlightcolor=Cols.sys.dark_gray.hex)
            sw.create_rectangle(0, 0, 18, 18, outline=Cols.black.hex, fill=col.hex)
            sw.pack(side="left", padx=2)

            sw.bind("<Button-1>", lambda _e, name=col.name: self._select(name))
            sw.bind("<Button-3>", lambda _e, name=col.name: self._set_bg(name))
            self._swatches.append((sw, col.name))

        if selected_name:
            self._update_highlight(selected_name)

    def _select(self, name: str):
        self._on_select(name)
        self._update_highlight(name)

    def _set_bg(self, name: str):
        if name != "transparent":
            self._on_set_bg(name)

    def _update_highlight(self, selected: str):
        for canvas, name in self._swatches:
            if name == selected:
                canvas.configure(highlightthickness=3)
            else:
                canvas.configure(highlightthickness=0)


def create_palette(
    master,
    colours: Iterable[Colour],
    on_select: Callable[[str], None],
    on_set_bg: Callable[[str], None],
    selected_name: str,
) -> Palette_Handles:
    pal = Colour_Palette(master, colours, on_select, on_set_bg, selected_name)
    pal.pack(side="right", padx=8)
    return Palette_Handles(frame=pal, set_selected=pal._update_highlight)

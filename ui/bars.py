from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from tkinter import ttk

from models.geo import CanvasLW
from models.styling import Colour, Colours, LineStyle
from ui.widgets.composite_spinbox import Composite_Spinbox


class Tool_Name(StrEnum):
    draw = "draw"
    label = "label"
    icon = "icon"
    select = "select"


@dataclass
class Palette_Handles:
    frame: ttk.Frame
    set_selected: Callable[[str], None]
    "call with colour name"


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
        self._swatches: list[tuple[CanvasLW, str]] = []

        # label (optional)
        ttk.Label(self).pack(side="left", padx=(0, 6))

        for col in colours:
            sw = CanvasLW(self, width=18, height=18, highlightthickness=0)
            sw.configure(highlightbackground=Colours.sys.dark_gray.hex, highlightcolor=Colours.sys.dark_gray.hex)
            sw.create_rectangle(0, 0, 18, 18, outline=Colours.black.hex, fill=col.hex)
            sw.pack(side="left", padx=2)

            sw.bind("<Button-1>", lambda _e, name=col.name_str: self._select(name))
            sw.bind("<Button-3>", lambda _e, name=col.name_str: self._set_bg(name))
            self._swatches.append((sw, col.name_str))

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


@dataclass
class Header_Handles:
    frame: ttk.Frame


@dataclass
class Toolbar_Handles:
    frame: ttk.Frame
    spin_grid: Composite_Spinbox
    spin_brush: Composite_Spinbox
    spin_w: Composite_Spinbox
    spin_h: Composite_Spinbox
    cb_bg: ttk.Combobox
    cb_dtd: ttk.Checkbutton
    cb_cardinal: ttk.Checkbutton
    cb_style: ttk.Combobox
    palette: Palette_Handles


class Side(StrEnum):
    left = "left"
    centre = "centre"
    right = "right"


@dataclass(order=True)
class _Overlay:
    sort_key: tuple[int, int] = field(init=False, repr=False)
    key: str
    text: str
    priority: int = 0
    side: Side = Side.left
    seq: int = 0

    def __post_init__(self):
        self.sort_key = (-self.priority, self.seq)


class Status_Handles(ttk.Frame):
    def __init__(self, master, status: "Bars.Status"):
        super().__init__(master)
        self.frame = self

        # three lanes: left | centre | right
        self.lbl_left = ttk.Label(self, textvariable=status.var_left, anchor="w")
        self.lbl_centre = ttk.Label(self, textvariable=status.var_centre, anchor="center")
        self.lbl_right = ttk.Label(self, textvariable=status.var_right, anchor="e")

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=1)

        self.lbl_left.grid(row=0, column=0, sticky="w", padx=6)
        self.lbl_right.grid(row=0, column=2, sticky="e", padx=6)
        self.lbl_centre.place(relx=0.5, rely=0.5, anchor="center")
        self.lbl_centre.lower()


class Bars:
    @classmethod
    def create_status(cls, master, status: "Bars.Status") -> Status_Handles:
        strip = Status_Handles(master, status)
        strip.pack(fill="x", side="bottom")
        return strip

    @staticmethod
    def _add_labeled(master: ttk.Frame, make_widget, text: str = "", right_label: bool = False):
        f = ttk.Frame(master)
        if not right_label and text:
            ttk.Label(f, text=text).pack(side="left")
        w = make_widget(f)
        w.pack(side="left")
        if right_label and text:
            ttk.Label(f, text=text).pack(side="left")
        f.pack(side="left", padx=4)
        return w

    @classmethod
    def create_palette(
        cls,
        master,
        colours: Iterable[Colour],
        on_select: Callable[[str], None],
        on_set_bg: Callable[[str], None],
        selected_name: str,
    ) -> Palette_Handles:
        pal = Colour_Palette(master, colours, on_select, on_set_bg, selected_name)
        pal.pack(side="right", padx=8)
        return Palette_Handles(frame=pal, set_selected=pal._update_highlight)

    @classmethod
    def create_header(
        cls,
        master,
        mode_var: tk.StringVar,
        on_toggle_grid,
        on_undo,
        on_redo,
        on_clear,
        on_save,
        on_export,
        on_new,
        on_open,
        on_save_as,
        icon_label_var: tk.StringVar | None = None,
    ):
        """Builds the header strip and returns handles."""
        frame = ttk.Frame(master)
        frame.pack(fill="x", side="top")

        # Actions
        cls._add_labeled(frame, lambda p: ttk.Button(p, text="Grid (G)", command=on_toggle_grid))
        cls._add_labeled(frame, lambda p: ttk.Button(p, text="Undo (Z)", command=on_undo))
        cls._add_labeled(frame, lambda p: ttk.Button(p, text="Redo (Y)", command=on_redo))
        cls._add_labeled(frame, lambda p: ttk.Button(p, text="Clear (C)", command=on_clear))
        cls._add_labeled(frame, lambda p: ttk.Button(p, text="Export…", command=on_export))
        cls._add_labeled(frame, lambda p: ttk.Button(p, text="New", command=on_new))
        cls._add_labeled(frame, lambda p: ttk.Button(p, text="Open…", command=on_open))
        cls._add_labeled(frame, lambda p: ttk.Button(p, text="Save", command=on_save))
        cls._add_labeled(frame, lambda p: ttk.Button(p, text="Save As…", command=on_save_as))

        # Modes
        cls._add_labeled(frame, lambda p: ttk.Radiobutton(p, text="Select", value=Tool_Name.select, variable=mode_var))
        cls._add_labeled(frame, lambda p: ttk.Radiobutton(p, text="Draw", value=Tool_Name.draw, variable=mode_var))
        cls._add_labeled(frame, lambda p: ttk.Radiobutton(p, text="Label", value=Tool_Name.label, variable=mode_var))
        cls._add_labeled(frame, lambda p: ttk.Radiobutton(p, text="Icon", value=Tool_Name.icon, variable=mode_var))

        if icon_label_var is not None:
            cls._add_labeled(frame, lambda p: ttk.Label(p, textvariable=icon_label_var), "")

        return Header_Handles(frame=frame)

    @classmethod
    def create_toolbar(
        cls,
        master,
        grid_var: tk.IntVar,
        brush_var: tk.IntVar,
        width_var: tk.IntVar,
        height_var: tk.IntVar,
        bg_var: tk.StringVar,
        drag_to_draw_var: tk.BooleanVar,
        cardinal_var: tk.BooleanVar,
        style_var: tk.StringVar,
        on_grid_change,
        on_brush_change,
        on_canvas_size_change,
        on_palette_select,
        on_palette_set_bg,
        on_style_change,
        selected_colour_name: str,
    ):
        """Builds the toolbar strip and returns widget handles."""
        frame = ttk.Frame(master)
        frame.pack(fill="x", side="top")

        sbox_grid = cls._add_labeled(
            frame,
            lambda p: Composite_Spinbox(
                p, from_=0, to=200, increment=5, width=3, textvariable=grid_var, command=on_grid_change
            ),
            "Grid:",
        )
        sbox_brush = cls._add_labeled(
            frame,
            lambda p: Composite_Spinbox(
                p, from_=1, to=50, increment=1, width=3, textvariable=brush_var, command=on_brush_change
            ),
            "Line:",
        )
        sbox_w = cls._add_labeled(
            frame,
            lambda p: Composite_Spinbox(
                p, from_=100, to=10000, increment=50, width=4, textvariable=width_var, command=on_canvas_size_change
            ),
            "W:",
        )
        sbox_h = cls._add_labeled(
            frame,
            lambda p: Composite_Spinbox(
                p, from_=100, to=10000, increment=50, width=4, textvariable=height_var, command=on_canvas_size_change
            ),
            "H:",
        )

        cbox_bg = cls._add_labeled(
            frame,
            lambda p: ttk.Combobox(
                p,
                textvariable=bg_var,
                values=Colours.names(),  # include transparent
                state="readonly",
                width=10,
            ),
            "BG:",
        )
        cbut_dtd = cls._add_labeled(
            frame,
            lambda p: ttk.Checkbutton(
                p,
                variable=drag_to_draw_var,
            ),
            "Drag to draw:",
        )
        cbut_cardinal = cls._add_labeled(
            frame,
            lambda p: ttk.Checkbutton(
                p,
                variable=cardinal_var,
            ),
            "Cardinal:",
        )
        styles = [s.value for s in LineStyle]
        cb_style = cls._add_labeled(
            frame,
            lambda p: ttk.Combobox(p, values=styles, state="readonly", width=9, textvariable=style_var),
            "Style:",
        )
        cb_style.bind("<<ComboboxSelected>>", lambda _e: on_style_change())
        pal = cls.create_palette(
            frame,
            colours=Colours.list(min_alpha=25),
            on_select=on_palette_select,
            on_set_bg=on_palette_set_bg,
            selected_name=selected_colour_name,
        )

        sbox_grid.bind("<Return>", lambda _e: on_grid_change())
        sbox_brush.bind("<Return>", lambda _e: on_brush_change())
        sbox_w.bind("<Return>", lambda _e: on_canvas_size_change())
        sbox_h.bind("<Return>", lambda _e: on_canvas_size_change())

        return Toolbar_Handles(
            frame=frame,
            spin_grid=sbox_grid,
            spin_brush=sbox_brush,
            spin_w=sbox_w,
            spin_h=sbox_h,
            cb_bg=cbox_bg,
            cb_dtd=cbut_dtd,
            cb_cardinal=cbut_cardinal,
            cb_style=cb_style,
            palette=pal,
        )

    class Status:
        def __init__(self, root: tk.Misc):
            self.var_left = tk.StringVar(value="Ready")
            self.var_centre = tk.StringVar(value="")
            self.var_right = tk.StringVar(value="")
            self._root = root

            self._base_left: str = ""
            self._seq = 0

            self._held: dict[str, _Overlay] = {}
            self._temp_key: str | None = None
            self._temp_after: str | None = None

            self._centre_key = "__centre__"

        # ---- base ----
        def set(self, text: str):
            self._base_left = text
            self._render()

        # ---- centre sugar ----
        def set_centre(self, text: str):
            if text:
                self.hold(self._centre_key, text, priority=-10, side=Side.centre)
            else:
                self.release(self._centre_key)

        def clear_centre(self):
            self.release(self._centre_key)

        # ---- held overlays (persistent until release) ----
        def hold(self, key: str, text: str, *, priority: int = 0, side: Side = Side.left):
            self._seq += 1
            self._held[key] = _Overlay(key=key, text=text, priority=priority, side=side, seq=self._seq)
            self._render()

        def release(self, key: str):
            if key in self._held:
                del self._held[key]
                if self._temp_key == key:
                    self._temp_key = None
                self._render()

        # ---- temporary overlays (auto-clear) ----
        def temp(self, text: str, ms: int = 7500, *, priority: int = 50, side: Side = Side.centre):
            # cancel previous timer
            if self._temp_after:
                try:
                    self._root.after_cancel(self._temp_after)
                except Exception:
                    pass
                self._temp_after = None

            # temp overlay is just a special held
            key = "__temp__"
            self.hold(key, text, priority=priority, side=side)
            self._temp_key = key
            self._temp_after = self._root.after(ms, self._clear_temp)

        def _clear_temp(self):
            if self._temp_key:
                self.release(self._temp_key)
            self._temp_after = None

        # ---- clear all ----
        def clear(self):
            self._base_left = ""
            self._held.clear()
            if self._temp_after:
                try:
                    self._root.after_cancel(self._temp_after)
                except Exception:
                    pass
                self._temp_after = None
            self._temp_key = None
            self._render()

        # ---- render ----
        def _render(self):
            self.var_left.set(self._pick_side(Side.left) or self._base_left)
            self.var_centre.set(self._pick_side(Side.centre) or "")
            self.var_right.set(self._pick_side(Side.right) or "")

        def _pick_side(self, side: Side) -> str:
            # choose the highest-priority overlay on this side
            items = [ov for ov in self._held.values() if ov.side == side]
            if not items:
                return ""
            top = sorted(items)[0]  # because sort_key is (-priority, seq)
            return top.text

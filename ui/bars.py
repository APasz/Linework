from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from tkinter import ttk
from tkinter import colorchooser

from models.geo import CanvasLW
from models.styling import Colour, Colours, LineStyle
from ui.composite_spinbox import Composite_Spinbox


class Tool_Name(StrEnum):
    draw = "draw"
    label = "label"
    icon = "icon"
    select = "select"


@dataclass
class Palette_Handles:
    frame: ttk.Frame
    set_selected: Callable[[str], None]
    "call with colour hexa"


class Colour_Palette(ttk.Frame):
    _open_owner: "Colour_Palette | None" = None

    def __init__(
        self,
        master,
        colours: Iterable[Colour],
        on_select: Callable[[str], None],
        custom: list[Colour | None] | None = None,
        on_update_custom: Callable[[int, Colour | None], None] | None = None,
    ):
        super().__init__(master)
        self._on_select = on_select
        self._colours = list(colours)
        self._swatches: list[tuple[CanvasLW, str]] = []
        self._popup: tk.Toplevel | None = None
        self._custom: list[Colour | None] = custom if custom is not None else [None] * len(Colours.list())
        self._on_update_custom = on_update_custom

        self._btn = CanvasLW(self, width=22, height=22, highlightthickness=1)
        self._btn.configure(
            highlightbackground=Colours.sys.dark_gray.hexh,
            highlightcolor=Colours.sys.dark_gray.hexh,
        )
        self._rect_id = self._btn.create_rectangle(1, 1, 21, 21, outline=Colours.black.hexh, fill=Colours.black.hexh)
        self._btn.pack(side="left", padx=4)
        self._btn.bind("<Button-1>", self._toggle_popup)

    # ------- popup -------
    def _toggle_popup(self, _evt=None):
        if self._popup:
            self._close_popup()
        else:
            if Colour_Palette._open_owner and Colour_Palette._open_owner is not self:
                try:
                    Colour_Palette._open_owner._close_popup()
                except Exception:
                    pass
            self._open_popup()

    def _open_popup(self, _evt=None):
        self._close_popup()
        Colour_Palette._open_owner = self
        top = tk.Toplevel(self)
        top.wm_overrideredirect(True)
        top.transient(self.winfo_toplevel())

        bx = self._btn.winfo_rootx()
        by = self._btn.winfo_rooty() + self._btn.winfo_height()
        top.geometry(f"+{bx}+{by}")

        frame = ttk.Frame(top, borderwidth=1, relief="solid")
        frame.pack(fill="both", expand=True)

        left = ttk.Frame(frame)
        left.pack(side="left", padx=6, pady=6)
        right = ttk.Frame(frame)
        right.pack(side="left", padx=(0, 6), pady=6)
        ttk.Label(right, text="Custom").pack(anchor="w", padx=2, pady=(0, 4))

        self._swatches.clear()
        # Built-ins (left)
        for col in self._colours:
            c = CanvasLW(left, width=22, height=22, highlightthickness=0)
            fill = Colours.sys.dark_gray.hexh if col.alpha == 0 else col.hexh
            c.create_rectangle(1, 1, 21, 21, outline=Colours.sys.dark_gray.hexh, fill=fill)
            c.bind("<Button-1>", lambda _e, hexa=col.hexah: (self._select(hexa), self._close_popup()))
            c.pack(side="top", pady=2)
            self._swatches.append((c, col.hexah))

        # Custom (right)
        for i, val in enumerate(self._custom):
            c = CanvasLW(right, width=22, height=22, highlightthickness=0)
            fill = Colours.white.hexh if val is None else (Colours.sys.dark_gray.hexh if val.alpha == 0 else val.hexh)
            c.create_rectangle(1, 1, 21, 21, outline=Colours.sys.dark_gray.hexh, fill=fill)
            if val is None:
                c.bind("<Button-1>", lambda _e, i=i: self._edit_custom(i, None))
            else:
                c.bind("<Button-1>", lambda _e, hexa=val.hexah: (self._select(hexa), self._close_popup()))
                c.bind("<Shift-Button-1>", lambda _e, i=i, init=val: self._edit_custom(i, init))
            c.bind("<Button-3>", lambda _e, i=i: self._clear_custom(i))
            c.pack(side="top", pady=2)
            self._swatches.append((c, val.hexah if val else ""))

        top.focus_force()
        try:
            top.grab_set()
        except Exception:
            pass

        self._popup = top
        top.after_idle(self._arm_outside_handlers)

    def _close_popup(self):
        if self._popup is not None:
            try:
                self._popup.unbind_all("<Escape>")
                self._popup.unbind_all("<ButtonRelease-1>")
                self._popup.grab_release()
            except Exception:
                pass
            try:
                self._popup.destroy()
            except Exception:
                pass
            self._popup = None
            self._swatches.clear()
            if Colour_Palette._open_owner is self:
                Colour_Palette._open_owner = None

    def _arm_outside_handlers(self):
        if not self._popup:
            return
        self._popup.update_idletasks()
        self._popup.bind_all("<Escape>", lambda _e: self._close_popup(), add="+")
        self._popup.bind_all("<ButtonRelease-1>", self._maybe_close_on_click, add="+")

    def _edit_custom(self, idx: int, initial: Colour | None):
        _rgb, hx = colorchooser.askcolor(color=initial.hexh if initial else None, parent=self)
        if not hx:
            return
        col = Colours.parse_colour(hx)
        self._custom[idx] = col
        if self._on_update_custom:
            self._on_update_custom(idx, col)
        self._select(col.hexah)
        self._close_popup()

    def _clear_custom(self, idx: int):
        self._custom[idx] = None
        if self._on_update_custom:
            self._on_update_custom(idx, None)
        self._close_popup()

    def _maybe_close_on_click(self, e):
        if not self._popup:
            return
        x, y = e.x_root, e.y_root
        px, py = self._popup.winfo_rootx(), self._popup.winfo_rooty()
        pw, ph = self._popup.winfo_width(), self._popup.winfo_height()
        inside = (px <= x < px + pw) and (py <= y < py + ph)
        if inside:
            return

        bx, by = self._btn.winfo_rootx(), self._btn.winfo_rooty()
        bw, bh = self._btn.winfo_width(), self._btn.winfo_height()
        on_btn = (bx <= x < bx + bw) and (by <= y < by + bh)
        if on_btn:
            return

        self._close_popup()

    # ------- selection -------
    def _select(self, name: str):
        self._on_select(name)
        self._update_highlight(name)

    def _update_highlight(self, selected: str):
        try:
            col = next((c for c in self._colours if c.hexah == selected), None)
            if col is None:
                col = Colours.parse_colour(selected)
            fill = Colours.sys.dark_gray.hexh if col.alpha == 0 else col.hexh
            self._btn.itemconfigure(self._rect_id, fill=fill)
        except Exception:
            pass


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
    cb_dtd: ttk.Checkbutton
    cb_cardinal: ttk.Checkbutton
    cb_style: ttk.Combobox
    palette_brush: Palette_Handles
    palette_bg: Palette_Handles
    palette_label: Palette_Handles
    palette_icon: Palette_Handles


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
    ) -> Palette_Handles:
        pal = Colour_Palette(master, colours, on_select)
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
        cls._add_labeled(frame, lambda p: ttk.Button(p, text="Undo (Ctrl+Z)", command=on_undo))
        cls._add_labeled(frame, lambda p: ttk.Button(p, text="Redo (Ctrl+Y)", command=on_redo))
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
        drag_to_draw_var: tk.BooleanVar,
        cardinal_var: tk.BooleanVar,
        style_var: tk.StringVar,
        on_grid_change,
        on_brush_change,
        on_canvas_size_change,
        on_style_change,
        on_palette_select_brush,
        on_palette_select_bg,
        on_palette_select_label,
        on_palette_select_icon,
        custom_palette: list[Colour | None] | None = None,
        on_update_custom: Callable[[int, Colour | None], None] | None = None,
    ):
        """Builds the toolbar strip and returns widget handles."""
        frame = ttk.Frame(master)
        frame.pack(fill="x", side="top")

        sbox_grid = cls._add_labeled(
            frame,
            lambda p: Composite_Spinbox(
                p,
                from_=0,
                to=200,
                increment=5,
                width=3,
                textvariable=grid_var,
                command=on_grid_change,
            ),
            "Grid:",
        )
        sbox_brush = cls._add_labeled(
            frame,
            lambda p: Composite_Spinbox(
                p,
                from_=1,
                to=50,
                increment=1,
                width=3,
                textvariable=brush_var,
                command=on_brush_change,
            ),
            "Line:",
        )
        sbox_w = cls._add_labeled(
            frame,
            lambda p: Composite_Spinbox(
                p,
                from_=100,
                to=10000,
                increment=50,
                width=4,
                textvariable=width_var,
                command=on_canvas_size_change,
            ),
            "W:",
        )
        sbox_h = cls._add_labeled(
            frame,
            lambda p: Composite_Spinbox(
                p,
                from_=100,
                to=10000,
                increment=50,
                width=4,
                textvariable=height_var,
                command=on_canvas_size_change,
            ),
            "H:",
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
            lambda p: ttk.Combobox(
                p,
                values=sorted(styles, key=str.lower),
                state="readonly",
                width=9,
                textvariable=style_var,
                height=16,
            ),
            "Style:",
        )
        style_var.trace_add("write", lambda *_: on_style_change())

        def _make_brush(p):
            return Colour_Palette(
                p,
                Colours.list(min_alpha=25),
                on_select=on_palette_select_brush,
                custom=custom_palette,
                on_update_custom=on_update_custom,
            )

        brush_widget = cls._add_labeled(frame, _make_brush, "Brush:")
        pal_brush = Palette_Handles(frame=brush_widget, set_selected=brush_widget._update_highlight)

        def _make_bg(p):
            return Colour_Palette(
                p,
                Colours.list(),
                on_select=on_palette_select_bg,
                custom=custom_palette,
                on_update_custom=on_update_custom,
            )

        bg_widget = cls._add_labeled(frame, _make_bg, "BG:")
        pal_bg = Palette_Handles(frame=bg_widget, set_selected=bg_widget._update_highlight)

        def _make_label(p):
            return Colour_Palette(
                p,
                Colours.list(min_alpha=25),
                on_select=on_palette_select_label,
                custom=custom_palette,
                on_update_custom=on_update_custom,
            )

        lb_widget = cls._add_labeled(frame, _make_label, "Label:")
        pal_label = Palette_Handles(frame=lb_widget, set_selected=lb_widget._update_highlight)

        def _make_icon(p):
            return Colour_Palette(
                p,
                Colours.list(min_alpha=25),
                on_select=on_palette_select_icon,
                custom=custom_palette,
                on_update_custom=on_update_custom,
            )

        ic_widget = cls._add_labeled(frame, _make_icon, "Icon:")
        pal_icon = Palette_Handles(frame=ic_widget, set_selected=ic_widget._update_highlight)

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
            cb_dtd=cbut_dtd,
            cb_cardinal=cbut_cardinal,
            cb_style=cb_style,
            palette_brush=pal_brush,
            palette_bg=pal_bg,
            palette_label=pal_label,
            palette_icon=pal_icon,
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
        def temp(self, text: str, ms: int = 1500, *, priority: int = 50, side: Side = Side.centre):
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

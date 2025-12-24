from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

try:
    import sv_ttk
except Exception:
    sv_ttk = None

from canvas.layers import Hit_Kind, Layer_Manager, Layer_Type, test_hit
from canvas.painters import Painters, Scene
from canvas.selection import SelectionOverlay
from controllers.commands import (
    Command_Stack,
    Delete_Icon,
    Delete_Label,
    Delete_Line,
    Multi,
)
from controllers.editors import Editors
from controllers.tools.draw import Draw_Tool
from controllers.tools.icon import Icon_Tool
from controllers.tools.label import Label_Tool
from controllers.tools.select import Select_Tool
from controllers.tools_base import Tool, Tool_Manager
from disk.export import Exporter
from disk.storage import IO, default_settings_path
from models.assets import Formats, Icon_Name, get_asset_library
from models.geo import CanvasLW, Icon_Source, Icon_Type, Point
from models.params import Params
from models.schemas import settings_schema
from models.styling import Anchor, Colour, Colours, LineStyle
from ui import input as input_mod
from ui.bars import Bars, Side, Tool_Name
from ui.settings_dialog import SettingsDialog


class App:
    def __init__(self, root: tk.Tk, project_path: Path | None = None):
        self.root = root
        self.root.title("Linework")

        # ---------- settings / project ----------
        self.project_path: Path = project_path or Path("untitled.linework")
        self.defaults_path = default_settings_path()
        try:
            self.defaults_profile = IO.load_defaults(self.defaults_path)
        except Exception as exc:
            self.defaults_profile = Params()
            self._safe_tk_call(messagebox.showwarning, "Settings load failed", str(exc))

        if self.project_path.exists():
            self.params = IO.load_params(self.project_path)
        else:
            self.params = Params()
            self.params.apply_profile(self.defaults_profile, inplace_palette=True)
        self.asset_lib = get_asset_library(self.project_path)
        self.dirty = False
        self.autosave_every = 10
        self._actions_since_autosave = 0

        # ---------- theme ----------
        if sv_ttk:
            sv_ttk.set_theme("dark")
        else:
            ttk.Style().theme_use("alt")

        # ---------- UI state ----------
        self.mode = tk.StringVar(value=Tool_Name.draw)
        self.var_grid = tk.IntVar(value=self.params.grid_size)
        self.var_width_px = tk.IntVar(value=self.params.width)
        self.var_height_px = tk.IntVar(value=self.params.height)
        self.var_brush_w = tk.IntVar(value=self.params.brush_width)
        self.var_line_style = tk.StringVar(value=self.params.line_style.value)

        self.var_brush_colour = tk.StringVar(value=self.params.brush_colour.hexah)
        self.var_bg_colour = tk.StringVar(value=self.params.bg_colour.hexah)
        self.var_label_colour = tk.StringVar(value=self.params.label_colour.hexah)
        self.var_icon_colour = tk.StringVar(value=self.params.icon_colour.hexah)

        self.var_drag_to_draw = tk.BooleanVar(value=self.params.drag_to_draw)
        self.var_cardinal = tk.BooleanVar(value=self.params.cardinal_snap)
        self.var_icon = tk.StringVar(value=Icon_Name.SIGNAL.value)
        self.var_icon_label = tk.StringVar(value=self.var_icon.get())

        self.current_icon = Icon_Source.builtin(Icon_Name.SIGNAL)
        self._apply_default_icon_source(self.params.default_icon)

        # ---------- header / toolbar / status ----------
        self.hbar = Bars.create_header(
            self.root,
            mode_var=self.mode,
            on_toggle_grid=self.toggle_grid,
            on_undo=self.on_undo,
            on_redo=self.on_redo,
            on_new=self.new_project,
            on_open=self.open_project,
            on_save=self.save_project,
            on_save_as=self.save_project_as,
            on_settings=self.open_settings,
            on_export=self.export_image,
            icon_label_var=self.var_icon_label,
        )
        self.tbar = Bars.create_toolbar(
            self.root,
            grid_var=self.var_grid,
            brush_var=self.var_brush_w,
            width_var=self.var_width_px,
            height_var=self.var_height_px,
            drag_to_draw_var=self.var_drag_to_draw,
            cardinal_var=self.var_cardinal,
            style_var=self.var_line_style,
            on_grid_change=self.on_grid_change,
            on_brush_change=self.on_brush_change,
            on_canvas_size_change=self.on_canvas_size_change,
            on_style_change=self.on_style_change,
            on_palette_select_brush=lambda name: self.var_brush_colour.set(name),
            on_palette_select_bg=lambda name: self.var_bg_colour.set(name),
            on_palette_select_label=lambda name: self.var_label_colour.set(name),
            on_palette_select_icon=lambda name: self.var_icon_colour.set(name),
            custom_palette=self.params.custom_palette,
            on_update_custom=self._set_custom_colour,
        )

        self.status = Bars.Status(self.root)
        self.status_bar = Bars.create_status(self.root, self.status)

        # ---------- canvas ----------
        self.canvas = CanvasLW(
            self.root,
            width=self.params.width,
            height=self.params.height,
            bg=self.params.bg_colour.hexh,
        )
        self.canvas.pack(fill="both", expand=False)

        # ---------- editors ----------
        self.editors = Editors(self)

        # ---------- scene / paint / layers ----------
        self.scene = Scene(self.params)
        self.painters = Painters(self)
        self.layers = Layer_Manager(self)

        # ---------- selection ----------
        self.selection = SelectionOverlay(self)
        self.selection_kind: Hit_Kind | None = None
        self.selection_index: int | None = None
        self.multi_sel: list[tuple[Hit_Kind, int]] = []

        # ---------- tools ----------
        self.tools: dict[Tool_Name, Tool] = {
            Tool_Name.select: Select_Tool(),
            Tool_Name.draw: Draw_Tool(),
            Tool_Name.icon: Icon_Tool(),
            Tool_Name.label: Label_Tool(),
        }
        self.tool_mgr = Tool_Manager(self, self.tools)
        # event routing (single source of truth)
        self.canvas.bind("<ButtonPress-1>", lambda e: (self.tool_mgr.on_press(e), "break")[-1])
        self.canvas.bind("<B1-Motion>", lambda e: (self.tool_mgr.on_motion(e), "break")[-1])
        self.canvas.bind(
            "<Motion>",
            lambda e: (
                self.tool_mgr.on_motion(e),
                self.status.hold("pos", f"({e.x},{e.y})", priority=-100, side=Side.centre),
                "break",
            )[-1],
        )
        self.canvas.bind("<ButtonRelease-1>", lambda e: (self.tool_mgr.on_release(e), "break")[-1])
        self.canvas.bind("<Double-Button-1>", lambda e: (self.on_double_click(e), "break")[-1])
        self.canvas.bind("<Leave>", lambda e: self.status.clear_centre())
        self.root.bind("<Escape>", lambda e: self.tool_mgr.cancel())
        self.root.bind("<Control-a>", self._on_select_all)
        self.root.bind("<Command-a>", self._on_select_all)

        # global keys
        self.root.bind("<Delete>", self._on_delete_key)
        self.root.bind("<BackSpace>", self._on_delete_key)
        self.root.bind("<Command-BackSpace>", self._on_delete_key)
        self.root.bind("<Control-z>", self._on_undo_key)
        self.root.bind("<Command-z>", self._on_undo_key)
        self.root.bind("<Control-y>", self._on_redo_key)
        self.root.bind("<Control-Shift-Z>", self._on_redo_key)
        self.root.bind("<Command-y>", self._on_redo_key)
        self.root.bind("<Command-Shift-Z>", self._on_redo_key)
        self.root.bind("<Control-s>", self._on_save_key)
        self.root.bind("<Control-S>", self._on_save_as_key)
        self.root.bind("<Command-s>", self._on_save_key)
        self.root.bind("<Command-S>", self._on_save_as_key)
        self.root.bind("<KeyPress-g>", self._on_toggle_grid_key)
        self.root.bind("<KeyPress-G>", self._on_toggle_grid_key)
        self.root.bind("<KeyPress>", self._on_any_key)
        self.root.bind("<KeyRelease>", self._on_any_key)
        self.root.bind("<KeyPress>", input_mod.handle_key_event, add="+")
        self.root.bind("<KeyRelease>", input_mod.handle_key_event, add="+")
        self.root.bind("<FocusOut>", lambda _e: input_mod.reset_mods(), add="+")

        # mode activation
        self.mode.trace_add("write", self._on_mode_change)
        self._on_mode_change()

        # palette sync
        self.var_brush_colour.trace_add("write", self.apply_brush_colour)
        self.var_bg_colour.trace_add("write", self.apply_bg_colour)
        self.var_label_colour.trace_add("write", self.apply_label_colour)
        self.var_icon_colour.trace_add("write", self.apply_icon_colour)

        # window close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # initial draw
        self._apply_size_increments(self.params.grid_size)
        self.layers.redraw_all()
        self._update_title()
        self.apply_brush_colour()
        self.apply_bg_colour()
        self.apply_label_colour()
        self.apply_icon_colour()

        self.var_icon.trace_add("write", self._sync_icon_from_combo)
        self.var_drag_to_draw.trace_add("write", self._on_drag_to_draw_change)
        self.var_cardinal.trace_add("write", self._on_cardinal_change)

        self._status_hints_set()
        self.mark_clean()
        self.status.set("Ready")

    # ========= small app API used by tools =========
    @staticmethod
    def _safe_tk_call(func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except tk.TclError as exc:
            if "application has been destroyed" in str(exc):
                return None
            raise

    def prompt_text(self, title: str, prompt: str) -> str | None:
        import tkinter.simpledialog as sd

        return self._safe_tk_call(sd.askstring, title, prompt, parent=self.root)

    def layers_redraw(self, *names: Layer_Type):
        if names:
            for n in names:
                self.layers.redraw(n)
        else:
            self.layers.redraw_all()

    def snap(self, p: Point, *, ignore_grid: bool = False) -> Point:
        W, H = self.params.width, self.params.height
        if ignore_grid or self.params.grid_size <= 0:
            x = 0 if p.x < 0 else min(p.x, W)
            y = 0 if p.y < 0 else min(p.y, H)
            return Point(x=x, y=y)
        g = self.params.grid_size
        sx, sy = round(p.x / g) * g, round(p.y / g) * g
        sx = 0 if sx < 0 else min(sx, (W // g) * g)
        sy = 0 if sy < 0 else min(sy, (H // g) * g)
        return Point(x=sx, y=sy)

    # ========= selection =========
    def _selected(self) -> tuple[Hit_Kind | None, int | None]:
        return self.selection_kind, self.selection_index

    def is_selected(self, kind: Hit_Kind, idx: int) -> bool:
        return (kind, idx) in self.multi_sel

    def select_clear(self):
        self.multi_sel.clear()
        self._set_selected(None, None)
        self.selection.clear()

    def select_set(self, items: list[tuple[Hit_Kind, int]]):
        items = [(k, i) for k, i in items if k and i is not None]
        self.multi_sel = []
        # make the first item primary if any
        if items:
            k0, i0 = items[0]
            self._set_selected(k0, i0)
            for k, i in items:
                if (k, i) not in self.multi_sel:
                    self.multi_sel.append((k, i))
        else:
            self._set_selected(None, None)
        primary = (
            (self.selection_kind, self.selection_index)
            if self.selection_index is not None and self.selection_kind
            else None
        )
        self.selection.show_many(self.multi_sel, primary=primary)
        self._status_selected_hint()

    def select_merge(self, items: list[tuple[Hit_Kind, int]]):
        changed = False
        for k, i in items:
            if (k, i) not in self.multi_sel:
                self.multi_sel.append((k, i))
                changed = True
        if changed:
            if self.selection_kind and self.multi_sel:
                self.selection_kind, self.selection_index = self.multi_sel[0]
            primary = (
                (self.selection_kind, self.selection_index)
                if self.selection_index is not None and self.selection_kind
                else None
            )
            self.selection.show_many(self.multi_sel, primary=primary)
            self._status_selected_hint()

    def select_add(self, kind: Hit_Kind, idx: int, make_primary: bool = False):
        if (kind, idx) not in self.multi_sel:
            self.multi_sel.append((kind, idx))
        if make_primary:
            self._set_selected(kind, idx)
        primary = (
            (self.selection_kind, self.selection_index)
            if self.selection_index is not None and self.selection_kind
            else None
        )
        self.selection.show_many(self.multi_sel, primary=primary)
        self._status_selected_hint()

    def select_remove(self, kind: Hit_Kind, idx: int):
        try:
            self.multi_sel.remove((kind, idx))
        except ValueError:
            pass
        if self.selection_kind == kind and self.selection_index == idx:
            # promote first remaining as primary
            if self.multi_sel:
                self.selection_kind, self.selection_index = self.multi_sel[0]
            else:
                self.selection_kind, self.selection_index = None, None
        primary = (
            (self.selection_kind, self.selection_index)
            if self.selection_index is not None and self.selection_kind
            else None
        )
        self.selection.show_many(self.multi_sel, primary=primary)
        self._status_selected_hint()

    def _set_selected(self, kind: Hit_Kind | None, idx: int | None):
        self.selection_kind, self.selection_index = kind, idx
        if kind and kind and idx is not None:
            self.multi_sel = [(kind, idx)]
            self.selection.show_many(self.multi_sel, primary=(kind, idx))
            if kind == Hit_Kind.line and idx is not None:
                lin = self.params.lines[idx]
                _, _, L = lin.unit()
                self.status.hold(
                    "sel",
                    f"Line {idx}: {int(L)}px | width {lin.width} | {lin.style.value}",
                    priority=10,
                    side=Side.centre,
                )
            elif kind == Hit_Kind.label and idx is not None:
                lab = self.params.labels[idx]
                preview = (lab.text[:20] + "…") if len(lab.text) > 20 else lab.text
                self.status.hold(
                    "sel",
                    f'Label {idx}: "{preview}"  |  size {lab.size} | rot {lab.rotation}°',
                    priority=10,
                    side=Side.centre,
                )
            elif kind == Hit_Kind.icon and idx is not None:
                ico = self.params.icons[idx]
                self.status.hold(
                    "sel",
                    f"Icon {idx}: size {ico.size} | rot {ico.rotation}°",
                    priority=10,
                    side=Side.centre,
                )
            else:
                self.multi_sel.clear()
                self.selection.show_many([])
                self.selection.clear_marquee()
                self.status.release("sel")
        else:
            self.selection.clear()

    # ========= UI callbacks =========
    def on_delete(self, _evt=None):
        self.tool_mgr.cancel()
        kind, idx = self._selected()
        targets = list(self.multi_sel) if self.multi_sel else ([(kind, idx)] if kind and idx is not None else [])
        if not targets:
            self.status.temp("Nothing selected to delete", 1500)
            return

        subs = []
        for k, i in sorted(targets, key=lambda t: (t[0].value, -t[1])):
            if k == Hit_Kind.line:
                subs.append(Delete_Line(self.params, i, on_after=lambda: self.layers_redraw(Layer_Type.lines)))
            elif k == Hit_Kind.label:
                subs.append(Delete_Label(self.params, i, on_after=lambda: self.layers_redraw(Layer_Type.labels)))
            elif k == Hit_Kind.icon:
                subs.append(Delete_Icon(self.params, i, on_after=lambda: self.layers_redraw(Layer_Type.icons)))
        self.cmd.push_and_do(Multi(subs))
        self.status.temp(f"Deleted {len(subs)} item(s)")
        self.select_clear()
        self.mark_dirty()

    def on_style_change(self, *_):
        try:
            self.params.line_style = LineStyle(self.var_line_style.get())
        except Exception:
            self.params.line_style = LineStyle.SOLID
        self.layers_redraw(Layer_Type.lines)
        self.status.temp(f"Line style: {self.params.line_style.value}")

    def _on_mode_change(self, *_):
        name = Tool_Name(self.mode.get())
        self.status.clear_centre()
        self.tool_mgr.activate(name)
        self.status.temp(f"Tool: {name.value.title()}", 1500, priority=-50)
        self._status_hints_set()

    @staticmethod
    def _is_text_input_widget(widget: tk.Widget | None) -> bool:
        if widget is None:
            return False
        if isinstance(widget, (tk.Entry, tk.Text, tk.Spinbox)):
            return True
        if isinstance(widget, (ttk.Entry, ttk.Spinbox, ttk.Combobox)):
            return True
        return widget.winfo_class() in {"Entry", "Text", "Spinbox", "TEntry", "TSpinbox", "TCombobox"}

    def _should_handle_global_key(self, evt: tk.Event | None) -> bool:
        if evt is None:
            return True
        return not self._is_text_input_widget(getattr(evt, "widget", None))

    def _on_any_key(self, evt):
        if not self._should_handle_global_key(evt):
            return
        self.tool_mgr.on_key(evt)

    def _on_delete_key(self, evt=None):
        if not self._should_handle_global_key(evt):
            return
        self.on_delete(evt)

    def _on_undo_key(self, evt=None):
        if not self._should_handle_global_key(evt):
            return
        self.on_undo(evt)

    def _on_redo_key(self, evt=None):
        if not self._should_handle_global_key(evt):
            return
        self.on_redo(evt)

    def _on_toggle_grid_key(self, evt=None):
        if not self._should_handle_global_key(evt):
            return
        self.toggle_grid(evt)

    def _on_save_key(self, evt=None):
        if not self._should_handle_global_key(evt):
            return
        if evt is not None and input_mod.get_mods(evt).shift:
            return
        self.save_project()

    def _on_save_as_key(self, evt=None):
        if not self._should_handle_global_key(evt):
            return
        self.save_project_as()

    def toggle_grid(self, *_):
        self.params.grid_visible = not self.params.grid_visible
        if self.params.grid_visible:
            self.layers.redraw(Layer_Type.grid, True)
        else:
            self.layers.clear(Layer_Type.grid, force=True)
        self.status.temp("Grid ON" if self.params.grid_visible else "Grid OFF")
        self.mark_dirty()

    def on_grid_change(self, *_):
        try:
            self.params.grid_size = max(0, int(self.var_grid.get()))
        except ValueError:
            return
        self.params.grid_visible = self.params.grid_size > 0
        self._apply_size_increments(self.params.grid_size)
        self.layers.redraw(Layer_Type.grid, True)
        self.canvas.cache.checker_bg = None
        self.mark_dirty()

    def on_brush_change(self, *_):
        try:
            self.params.brush_width = max(1, int(self.var_brush_w.get()))
        except ValueError:
            return
        self.status.temp(f"Line width: {self.params.brush_width}")
        self.mark_dirty()

    def on_canvas_size_change(self, *_):
        try:
            g = self.params.grid_size
            w = int(self.var_width_px.get())
            h = int(self.var_height_px.get())
        except ValueError:
            return
        w = self._snap_dim_to_grid(max(1, w), g)
        h = self._snap_dim_to_grid(max(1, h), g)
        self.var_width_px.set(w)
        self.var_height_px.set(h)
        self.params.width, self.params.height = w, h
        self.canvas.config(width=w, height=h)
        self.layers.redraw(Layer_Type.grid, True)
        self.status.temp(f"Canvas {w}×{h}")
        self.mark_dirty()

    def apply_brush_colour(self, *_):
        raw = (self.var_brush_colour.get().strip() if self.var_brush_colour else "") or "black"
        try:
            col = Colours.parse_colour(raw)
        except ValueError:
            col = Colours.black
        self.params.brush_colour = col
        self.mark_dirty()
        try:
            self.tbar.palette_brush.set_selected(col.hexah)
        except Exception:
            pass

    def apply_bg_colour(self, *_):
        raw = (self.var_bg_colour.get().strip() if self.var_bg_colour else "") or "white"
        try:
            col = Colours.parse_colour(raw)
        except ValueError:
            col = Colours.white
        self.params.bg_colour = col
        self.mark_dirty()
        self.canvas.config(bg=(col.hexh if col.alpha else Colours.white.hexh))
        try:
            self.tbar.palette_bg.set_selected(col.hexah)
        except Exception:
            pass
        self.layers.redraw(Layer_Type.grid, force=True)

    def apply_label_colour(self, *_):
        raw = (self.var_label_colour.get().strip() if self.var_label_colour else "") or self.var_brush_colour.get()
        try:
            col = Colours.parse_colour(raw)
        except ValueError:
            col = self.params.brush_colour
        self.params.label_colour = col
        self.mark_dirty()
        try:
            self.tbar.palette_label.set_selected(col.hexah)
        except Exception:
            pass

    def apply_icon_colour(self, *_):
        raw = (self.var_icon_colour.get().strip() if self.var_icon_colour else "") or self.var_brush_colour.get()
        try:
            col = Colours.parse_colour(raw)
        except ValueError:
            col = self.params.brush_colour
        self.params.icon_colour = col
        self.mark_dirty()
        try:
            self.tbar.palette_icon.set_selected(col.hexah)
        except Exception:
            pass

    def _set_custom_colour(self, idx: int, col: Colour | None):
        self.params.custom_palette[idx] = col
        self.mark_dirty()

    def on_double_click(self, evt):
        self.tool_mgr.cancel()

        hit = test_hit(self.canvas, int(evt.x), int(evt.y))
        if not hit or hit.tag_idx is None or not hit.kind:
            return

        if hit.kind == Hit_Kind.line:
            obj = self.params.lines[hit.tag_idx]
            layer = Layer_Type.lines
        elif hit.kind == Hit_Kind.label:
            obj = self.params.labels[hit.tag_idx]
            layer = Layer_Type.labels
        elif hit.kind == Hit_Kind.icon:
            obj = self.params.icons[hit.tag_idx]
            layer = Layer_Type.icons
        else:
            return

        self._set_selected(hit.kind, hit.tag_idx)
        if self.editors.edit(self, obj):
            self.layers.redraw(layer, True)
            self.selection.update_bbox()
            self.mark_dirty()
            self._set_selected(hit.kind, hit.tag_idx)
            self.status.temp("Updated", 1200)

    # ========= undo/redo/clear =========
    @property
    def cmd(self) -> Command_Stack:
        if not hasattr(self, "_cmd"):
            self._cmd = Command_Stack()
        return self._cmd

    def on_undo(self, _evt=None):
        self.tool_mgr.cancel()
        self.cmd.undo()
        self.repair_snap_flags(self.params)
        self.layers.redraw_all()
        self.selection.update_bbox()
        self.mark_dirty()
        self.status.temp("Undo")
        self._set_selected(self.selection_kind, self.selection_index)

    def on_redo(self, _evt=None):
        self.tool_mgr.cancel()
        self.cmd.redo()
        self.repair_snap_flags(self.params)
        self.layers.redraw_all()
        self.selection.update_bbox()
        self.mark_dirty()
        self.status.temp("Redo")
        self._set_selected(self.selection_kind, self.selection_index)

    def on_clear(self, _evt=None):  # unwired but kept just in case
        self.tool_mgr.cancel()
        self.params.lines.clear()
        self.params.labels.clear()
        self.params.icons.clear()
        self.layers.redraw_all()
        self._set_selected(None, None)
        self.mark_dirty()
        self.status.temp("Cleared")

    def on_file_opened(self, path: Path):
        self.status.set(f"Opened: {path.name}")

    def on_file_saved(self, path: Path):
        self.status.set(f"Saved: {path.name}")

    def on_ready(self):
        self.status.set("Ready")

    def on_hover_xy(self, x: int, y: int):
        self.status.set_centre(f"({x}, {y})")

    def on_move_element(self, old_xy: tuple[int, int], new_xy: tuple[int, int]):
        ox, oy = old_xy
        nx, ny = new_xy
        self.status.temp(f"({ox},{oy}) → ({nx},{ny})", ms=2000)

    def _status_hints_set(self):
        # use a stable key so you update instead of stacking
        self.status.hold("hints", self.tool_mgr.current.tool_hints, side=Side.right, priority=0)
        self._status_selected_hint()

    def _status_selected_hint(self):
        n = len(self.multi_sel)
        if n <= 1:
            self.status.release("sel_count")
        else:
            self.status.hold("sel_count", f"{n} selected", side=Side.centre, priority=5)

    def on_icon_selected(self, icon_name: str):
        self.status.temp(f"Icon: {icon_name}", ms=1500)

    # ---- keys ----
    def _on_select_all(self, _evt=None):
        if not self._should_handle_global_key(_evt):
            return
        items: list[tuple[Hit_Kind, int]] = []
        items += [(Hit_Kind.line, i) for i in range(len(self.params.lines))]
        items += [(Hit_Kind.label, i) for i in range(len(self.params.labels))]
        items += [(Hit_Kind.icon, i) for i in range(len(self.params.icons))]
        self.select_set(items)

    # ========= export / persistence =========
    @property
    def _autosave_path(self) -> Path:
        return self.project_path.with_suffix(f"{self.project_path.suffix}.autosave")

    def _maybe_autosave(self):
        if self.project_path.name.startswith("untitled"):
            return
        if self.autosave_every <= 0:
            return
        self._actions_since_autosave += 1
        if self._actions_since_autosave % self.autosave_every == 0:
            try:
                IO.save_params(self.params, self._autosave_path)
                self.status.temp(f"Autosaved: {self._autosave_path.name}")
            except Exception:
                pass

    def export_image(self):
        initialfile = self.params.output_file.name
        path = self._safe_tk_call(
            filedialog.asksaveasfilename,
            parent=self.root,
            title="Export",
            defaultextension=self.params.output_file.suffix,
            filetypes=[(t.upper(), f"*.{t.lower()}") for t in Formats],
            initialdir=self.params.output_file.parent,
            initialfile=initialfile,
        )
        if not path:
            return

        out = Path(path)
        if not Formats.check(out):
            self._safe_tk_call(
                messagebox.showerror,
                "Invalid filetype",
                f"Choose one of: {', '.join(Formats)}",
            )
            return

        self.params.output_file = out
        try:
            Exporter.output(self.params)
        except Exception as e:
            self._safe_tk_call(messagebox.showerror, "Export failed", str(e))
            return

        try:
            IO.save_params(self.params, self.project_path)
        except Exception:
            pass
        self.status.set(f"Exported: {out}")

    def save_project(self) -> bool:
        if not self.project_path or self.project_path.name.startswith("untitled"):
            return self.save_project_as()
        try:
            IO.save_params(self.params, self.project_path)
        except Exception as e:
            self._safe_tk_call(messagebox.showerror, "Save failed", str(e))
            return False
        self.mark_clean()
        self.on_file_saved(self.project_path)
        self._actions_since_autosave = 0
        self._autosave_path.unlink(missing_ok=True)
        return True

    def save_project_as(self) -> bool:
        previous_path = self.project_path
        path = self._safe_tk_call(
            filedialog.asksaveasfilename,
            parent=self.root,
            title="Save As",
            defaultextension=".linework",
            filetypes=[("Linework Projects", "*.linework"), ("JSON", "*.json")],
            initialdir=self.project_path.parent if self.project_path else None,
            initialfile=(self.project_path.name if self.project_path else "untitled.linework"),
        )
        if not path:
            return False
        self.project_path = Path(path)
        ok = self.save_project()
        if ok:
            self._update_title()
            if previous_path != self.project_path:
                previous_path.with_suffix(f"{previous_path.suffix}.autosave").unlink(missing_ok=True)
        return ok

    def new_project(self):
        if not self._maybe_proceed():
            return
        self.project_path = Path("untitled.linework")
        self._actions_since_autosave = 0
        if hasattr(self, "_cmd"):
            self._cmd = Command_Stack()
        self.params = Params()
        self.params.apply_profile(self.defaults_profile, inplace_palette=True)
        self.scene = Scene(self.params)
        self.painters = Painters(self)
        self.layers = Layer_Manager(self)
        self._reset_canvas_caches()
        self.asset_lib = get_asset_library(self.project_path)
        self._set_selected(None, None)
        self._sync_vars_from_params()
        self._apply_size_increments(self.params.grid_size)
        self.layers.redraw_all()
        self.mark_clean()
        self.status.set("New Project")

    def open_project(self):
        if not self._maybe_proceed():
            return
        path = self._safe_tk_call(
            filedialog.askopenfilename,
            parent=self.root,
            title="Open Project",
            filetypes=[("Linework Projects", "*.linework"), ("JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            params = IO.load_params(Path(path))
        except Exception as e:
            self._safe_tk_call(messagebox.showerror, "Open failed", str(e))
            return
        self.project_path = Path(path)
        self.params = params
        self._actions_since_autosave = 0
        if hasattr(self, "_cmd"):
            self._cmd = Command_Stack()
        self.scene = Scene(self.params)
        self.painters = Painters(self)
        self.layers = Layer_Manager(self)
        self._reset_canvas_caches()
        self._sync_vars_from_params()
        self.layers.redraw_all()
        self._update_title()
        self.mark_clean()
        self.on_file_opened(self.project_path)
        self.asset_lib = get_asset_library(self.project_path)

    # ========= helpers =========

    def _reset_canvas_caches(self):
        self.canvas.cache.checker_bg = None
        self.canvas.cache.checker_ref = None
        self.canvas.cache.imgs.clear()
        if hasattr(self.canvas, "_picture_cache"):
            self.canvas._picture_cache.clear()
        if hasattr(self.canvas, "_item_images"):
            self.canvas._item_images.clear()

    def _snap_dim_to_grid(self, var: int, grid: int) -> int:
        if grid <= 0:
            return max(1, var)
        return max(grid, round(var / grid) * grid)

    @staticmethod
    def repair_snap_flags(params):
        g = params.grid_size
        for lb in params.labels:
            if g > 0 and ((lb.p.x % g) or (lb.p.y % g)):
                lb.snap = False
        for ic in params.icons:
            if g > 0 and ((ic.p.x % g) or (ic.p.y % g)):
                ic.snap = False

    def _sync_icon_from_combo(self, *_):
        try:
            src = Icon_Source.builtin(Icon_Name(self.var_icon.get()))
        except Exception:
            src = Icon_Source.builtin(Icon_Name.SIGNAL)
        self.current_icon = src
        self.var_icon_label.set(src.name.value if src.name else "Unknown")
        if getattr(self.params, "default_icon", None) != src:
            self.params.default_icon = src
            self.mark_dirty()

    def _apply_default_icon_source(self, src: Icon_Source | None):
        if not src:
            src = Icon_Source.builtin(Icon_Name.SIGNAL)
        self.current_icon = src
        if src.kind == Icon_Type.builtin and src.name:
            self.var_icon.set(src.name.value)
            self.var_icon_label.set(src.name.value)
        elif src.kind == Icon_Type.picture and src.src:
            self.var_icon_label.set(src.src.name)
        else:
            self.var_icon_label.set("Unknown")

    def _sync_vars_from_params(self):
        self.repair_snap_flags(self.params)
        self.var_grid.set(self.params.grid_size)
        self.var_width_px.set(self.params.width)
        self.var_height_px.set(self.params.height)
        self.var_brush_w.set(self.params.brush_width)
        self.var_brush_colour.set(self.params.brush_colour.hexah)
        self.var_bg_colour.set(self.params.bg_colour.hexah)
        self.var_label_colour.set(self.params.label_colour.hexah)
        self.var_icon_colour.set(self.params.icon_colour.hexah)
        self.var_line_style.set(self.params.line_style.value)
        self.var_drag_to_draw.set(self.params.drag_to_draw)
        self.var_cardinal.set(self.params.cardinal_snap)
        self._apply_default_icon_source(self.params.default_icon)
        self.canvas.config(width=self.params.width, height=self.params.height, bg=self.params.bg_colour.hexh)

    def open_settings(self):
        schema = settings_schema()
        values = self._settings_values_from_params(self.params)
        base_profile = self.params.model_copy()

        def _save_defaults(data: dict[str, Any]) -> bool:
            new_profile = self._settings_from_dialog(data, base_profile)
            try:
                IO.save_defaults(new_profile, self.defaults_path)
            except Exception as exc:
                self._safe_tk_call(messagebox.showerror, "Settings save failed", str(exc))
                return False
            self.defaults_profile = new_profile
            self.status.temp("Defaults saved", 1500)
            return True

        def _apply_now(data: dict[str, Any]) -> None:
            temp_profile = self._settings_from_dialog(data, base_profile)
            self._apply_defaults_to_current(temp_profile)
            self.status.temp("Defaults applied", 1500)

        dlg = self._safe_tk_call(
            SettingsDialog,
            self,
            "Default Project Settings",
            schema,
            values,
            on_save=_save_defaults,
            on_apply=_apply_now,
        )
        if dlg is None:
            return

    @staticmethod
    def _settings_values_from_params(params: Params) -> dict[str, Any]:
        default_icon_kind = params.default_icon.kind.value if params.default_icon else Icon_Type.builtin.value
        default_icon_builtin = ""
        default_icon_picture = ""
        if params.default_icon:
            if params.default_icon.kind == Icon_Type.builtin and params.default_icon.name:
                default_icon_builtin = params.default_icon.name.value
            elif params.default_icon.kind == Icon_Type.picture and params.default_icon.src:
                default_icon_picture = str(params.default_icon.src)
        return dict(
            width=params.width,
            height=params.height,
            grid_size=params.grid_size,
            grid_visible=params.grid_visible,
            drag_to_draw=params.drag_to_draw,
            cardinal_snap=params.cardinal_snap,
            brush_width=params.brush_width,
            line_style=params.line_style.value,
            line_dash_offset=params.line_dash_offset,
            label_size=params.label_size,
            label_rotation=params.label_rotation,
            label_anchor=params.label_anchor.value,
            label_snap=params.label_snap,
            icon_size=params.icon_size,
            picture_size=params.picture_size,
            icon_rotation=params.icon_rotation,
            icon_anchor=params.icon_anchor.value,
            icon_snap=params.icon_snap,
            default_icon_kind=default_icon_kind,
            default_icon_builtin=default_icon_builtin,
            default_icon_picture=default_icon_picture,
            brush_colour=params.brush_colour.hexah,
            bg_colour=params.bg_colour.hexah,
            label_colour=params.label_colour.hexah,
            icon_colour=params.icon_colour.hexah,
            grid_colour=params.grid_colour.hexah,
        )

    def _settings_from_dialog(self, data: dict[str, Any], base: Params) -> Params:
        def _parse_colour(key: str, fallback: Colour) -> Colour:
            raw = str(data.get(key, "")).strip()
            if not raw:
                return fallback
            try:
                return Colours.parse_colour(raw)
            except Exception:
                return fallback

        try:
            style = LineStyle(data.get("line_style", base.line_style.value))
        except Exception:
            style = base.line_style
        try:
            label_anchor = Anchor.parse(data.get("label_anchor", base.label_anchor))
        except Exception:
            label_anchor = base.label_anchor
        try:
            icon_anchor = Anchor.parse(data.get("icon_anchor", base.icon_anchor))
        except Exception:
            icon_anchor = base.icon_anchor
        icon_kind = str(data.get("default_icon_kind", Icon_Type.builtin.value)).strip().lower()
        default_icon = base.default_icon
        if icon_kind == Icon_Type.picture.value:
            pic = str(data.get("default_icon_picture", "")).strip()
            if pic:
                default_icon = Icon_Source.picture(pic)
        else:
            name = str(data.get("default_icon_builtin", "")).strip()
            if name:
                try:
                    default_icon = Icon_Source.builtin(name)
                except Exception:
                    default_icon = base.default_icon

        grid_size = max(0, int(data["grid_size"]))
        width = self._snap_dim_to_grid(max(1, int(data["width"])), grid_size)
        height = self._snap_dim_to_grid(max(1, int(data["height"])), grid_size)
        updates = {
            "width": width,
            "height": height,
            "grid_size": grid_size,
            "grid_visible": bool(data.get("grid_visible")),
            "drag_to_draw": bool(data.get("drag_to_draw")),
            "cardinal_snap": bool(data.get("cardinal_snap")),
            "brush_width": max(1, int(data["brush_width"])),
            "line_style": style,
            "line_dash_offset": max(0, int(data.get("line_dash_offset", 0))),
            "label_size": max(1, int(data.get("label_size", base.label_size))),
            "label_rotation": int(data.get("label_rotation", base.label_rotation)),
            "label_anchor": label_anchor,
            "label_snap": bool(data.get("label_snap", base.label_snap)),
            "icon_size": max(1, int(data.get("icon_size", base.icon_size))),
            "picture_size": max(1, int(data.get("picture_size", base.picture_size))),
            "icon_rotation": int(data.get("icon_rotation", base.icon_rotation)),
            "icon_anchor": icon_anchor,
            "icon_snap": bool(data.get("icon_snap", base.icon_snap)),
            "default_icon": default_icon,
            "brush_colour": _parse_colour("brush_colour", base.brush_colour),
            "bg_colour": _parse_colour("bg_colour", base.bg_colour),
            "label_colour": _parse_colour("label_colour", base.label_colour),
            "icon_colour": _parse_colour("icon_colour", base.icon_colour),
            "grid_colour": _parse_colour("grid_colour", base.grid_colour),
        }
        return base.model_copy(update=updates)

    def _apply_defaults_to_current(self, profile: Params):
        self.params.apply_profile(profile, inplace_palette=True)
        self._sync_vars_from_params()
        self._apply_size_increments(self.params.grid_size)
        self.canvas.config(width=self.params.width, height=self.params.height, bg=self.params.bg_colour.hexh)
        if self.params.grid_visible:
            self.layers.redraw(Layer_Type.grid, True)
        else:
            self.layers.clear(Layer_Type.grid, force=True)
        self.canvas.cache.checker_bg = None
        self.layers.redraw_all()
        self.selection.update_bbox()
        self.mark_dirty()

    def _apply_size_increments(self, g: int):
        step = max(1, g)
        self.tbar.spin_w.configure(increment=step, from_=step)
        self.tbar.spin_h.configure(increment=step, from_=step)

        w = self._snap_dim_to_grid(self.params.width, g)
        h = self._snap_dim_to_grid(self.params.height, g)
        if (w, h) != (self.params.width, self.params.height):
            self.params.width, self.params.height = w, h
            self.var_width_px.set(w)
            self.var_height_px.set(h)
            self.canvas.config(width=w, height=h)
            self.layers.redraw(Layer_Type.grid, True)

    def _maybe_proceed(self) -> bool:
        if not self.dirty:
            return True
        ans = self._safe_tk_call(
            messagebox.askyesnocancel,
            "Save changes?",
            "Save your changes before continuing?",
        )
        if ans is None:
            return False
        if ans is True:
            return self.save_project()
        return True

    def _on_drag_to_draw_change(self, *_):
        self.tool_mgr.cancel()
        try:
            v = self.var_drag_to_draw.get()
            on = bool(int(v)) if not isinstance(v, bool) else v
        except Exception:
            on = bool(self.var_drag_to_draw.get())
        if getattr(self.params, "drag_to_draw", on) != on:
            self.params.drag_to_draw = on
            self.mark_dirty()
        self.status.set_centre("Draw: drag to draw" if on else "Draw: click-click mode")

    def _on_cardinal_change(self, *_):
        self.tool_mgr.cancel()
        try:
            v = self.var_cardinal.get()
            on = bool(int(v)) if not isinstance(v, bool) else v
        except Exception:
            on = bool(self.var_cardinal.get())
        if getattr(self.params, "cardinal_snap", on) != on:
            self.params.cardinal_snap = on
            self.mark_dirty()
        self.status.set_centre("Draw: Cardinal Snap" if on else "Draw: Grid Snap")

    def _on_close(self):
        if self._maybe_proceed():
            self.root.destroy()

    def _update_title(self):
        name = self.project_path.name if self.project_path else "Untitled"
        star = " *" if self.dirty else ""
        self.root.title(f"Linework — {name}{star}")

    def mark_dirty(self, _reason: str = ""):
        self.dirty = True
        self._update_title()
        self._maybe_autosave()

    def mark_clean(self):
        self.dirty = False
        self._update_title()

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    import sv_ttk
except Exception:
    sv_ttk = None

from canvas.layers import Hit_Kind, Layer_Manager, Layer_Name, test_hit
from canvas.painters import Painters, Scene
from canvas.selection import SelectionOverlay
from controllers.commands import (
    Command_Stack,
    Delete_Icon,
    Delete_Label,
    Delete_Line,
)
from controllers.editors import Editors
from controllers.tools.draw import Draw_Tool
from controllers.tools.icon import Icon_Tool
from controllers.tools.label import Label_Tool
from controllers.tools.select import Select_Tool
from controllers.tools_base import Tool, ToolManager
from disk.export import Exporter
from disk.storage import IO
from models.assets import Formats, Icon_Name, get_asset_library
from models.geo import CanvasLW, Icon_Source, Point
from models.params import Params
from models.styling import Colours, LineStyle
from ui.bars import Bars, Side, Tool_Name


class App:
    def __init__(self, root: tk.Tk, project_path: Path | None = None):
        self.root = root
        self.root.title("Linework")

        # ---------- project / params ----------
        self.project_path: Path = project_path or Path("untitled.linework")
        self.params: Params = IO.load_params(self.project_path) if self.project_path.exists() else Params()
        self.asset_lib = get_asset_library(self.project_path)
        self.dirty = False

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
        self.var_bg = tk.StringVar(value=self.params.bg_mode.name)
        self.var_colour = tk.StringVar(value=self.params.brush_colour.name)
        self.var_line_style = tk.StringVar(value=self.params.line_style.value)
        self.var_drag_to_draw = tk.BooleanVar(value=True)
        self.var_cardinal = tk.BooleanVar(value=True)
        self.var_icon = tk.StringVar(value=Icon_Name.SIGNAL.value)
        self.var_icon_label = tk.StringVar(value=self.var_icon.get())
        self.current_icon = Icon_Source.builtin(Icon_Name.SIGNAL)

        # ---------- header / toolbar ----------
        self.hbar = Bars.create_header(
            self.root,
            mode_var=self.mode,
            on_toggle_grid=self.toggle_grid,
            on_undo=self.on_undo,
            on_redo=self.on_redo,
            on_clear=self.on_clear,
            on_new=self.new_project,
            on_open=self.open_project,
            on_save=self.save_project,
            on_save_as=self.save_project_as,
            on_export=self.export_image,
            icon_label_var=self.var_icon_label,
        )
        self.tbar = Bars.create_toolbar(
            self.root,
            grid_var=self.var_grid,
            brush_var=self.var_brush_w,
            width_var=self.var_width_px,
            height_var=self.var_height_px,
            bg_var=self.var_bg,
            drag_to_draw_var=self.var_drag_to_draw,
            cardinal_var=self.var_cardinal,
            style_var=self.var_line_style,
            on_style_change=self.on_style_change,
            on_grid_change=self.on_grid_change,
            on_brush_change=self.on_brush_change,
            on_canvas_size_change=self.on_canvas_size_change,
            on_palette_select=lambda name: self.var_colour.set(name),
            on_palette_set_bg=lambda name: self.var_bg.set(name),
            selected_colour_name=self.var_colour.get(),
        )

        # ---------- canvas ----------
        display_bg = Colours.sys.dark_gray.hex if self.params.bg_mode.alpha == 0 else self.params.bg_mode.hex
        self.canvas = CanvasLW(self.root, width=self.params.width, height=self.params.height, bg=display_bg)
        self.canvas.pack(fill="both", expand=False)

        # ---------- editors ----------
        self.editors = Editors(self)

        # ---------- status ----------
        self.status = Bars.Status(self.root)
        self.status_bar = Bars.create_status(self.root, self.status)

        self.status.set("Ready")

        # ---------- scene / paint / layers ----------
        self.scene = Scene(self.params)
        self.painters = Painters(self.scene)
        self.layers = Layer_Manager(self.canvas, self.painters)

        # ---------- selection ----------
        self.selection = SelectionOverlay(self)
        self.selection_kind: Hit_Kind = Hit_Kind.miss
        self.selection_index: int | None = None

        # ---------- tools ----------
        self.tools: dict[Tool_Name, Tool] = {
            Tool_Name.select: Select_Tool(),
            Tool_Name.draw: Draw_Tool(),
            Tool_Name.icon: Icon_Tool(),
            Tool_Name.label: Label_Tool(),
        }
        self.tool_mgr = ToolManager(self, self.tools)

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
        self.root.bind("<Key>", lambda e: self.tool_mgr.on_key(e))
        self.root.bind("<Escape>", lambda e: self.tool_mgr.cancel())
        self.canvas.bind("<Leave>", lambda e: self.status.clear_centre())

        # global keys
        self.root.bind("<Delete>", self.on_delete)
        self.root.bind("<KeyPress-z>", self.on_undo)
        self.root.bind("<KeyPress-y>", self.on_redo)
        self.root.bind("<KeyPress>", self._on_any_key)
        self.root.bind("<KeyRelease>", self._on_any_key)

        # mode activation
        self.mode.trace_add("write", self._on_mode_change)
        self._on_mode_change()

        # palette sync
        self.var_colour.trace_add("write", self.apply_colour)
        self.var_bg.trace_add("write", self.apply_bg)

        # window close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # initial draw
        self._apply_size_increments(self.params.grid_size)
        self.layers.redraw_all()
        self._update_title()
        self.apply_colour()

        self.var_icon.trace_add("write", self._sync_icon_from_combo)
        self.var_drag_to_draw.trace_add("write", self._on_drag_to_draw_change)

        self._status_hints_set()

    # ========= small app API used by tools =========
    def prompt_text(self, title: str, prompt: str) -> str | None:
        import tkinter.simpledialog as sd

        return sd.askstring(title, prompt, parent=self.root)

    def layers_redraw(self, *names: Layer_Name):
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
    def _selected(self) -> tuple[Hit_Kind, int | None]:
        return self.selection_kind, self.selection_index

    def _set_selected(self, kind: Hit_Kind, idx: int | None):
        self.selection_kind, self.selection_index = kind, idx
        if kind and kind != Hit_Kind.miss and idx is not None:
            self.selection.show(kind, idx)
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
                self.status.release("sel")
        else:
            self.selection.clear()

    # ========= UI callbacks =========
    def on_delete(self, _evt=None):
        self.tool_mgr.cancel()
        kind, idx = self._selected()
        if idx is None or not kind or str(kind.value) == "":
            self.status.temp("Nothing selected to delete", 1500)
            return

        if kind == Hit_Kind.line:
            self.cmd.push_and_do(Delete_Line(self.params, idx, on_after=lambda: self.layers_redraw(Layer_Name.lines)))
        elif kind == Hit_Kind.label:
            self.cmd.push_and_do(Delete_Label(self.params, idx, on_after=lambda: self.layers_redraw(Layer_Name.labels)))
        elif kind == Hit_Kind.icon:
            self.cmd.push_and_do(Delete_Icon(self.params, idx, on_after=lambda: self.layers_redraw(Layer_Name.icons)))

        if kind.name:
            self.status.temp(f"Deleted {kind.name}")

        self._set_selected(Hit_Kind.miss, None)
        self.mark_dirty()

    def on_style_change(self, *_):
        try:
            self.params.line_style = LineStyle(self.var_line_style.get())
        except Exception:
            self.params.line_style = LineStyle.SOLID
        self.status.temp(f"Line style: {self.params.line_style.value}")

    def _on_mode_change(self, *_):
        name = Tool_Name(self.mode.get())
        self.status.clear_centre()
        self.tool_mgr.activate(name)
        self.status.temp(f"Tool: {name.value}", 1500, priority=-50)
        self._status_hints_set()

    def _on_any_key(self, evt):
        self.tool_mgr.on_key(evt)

    def toggle_grid(self, *_):
        self.params.grid_visible = not self.params.grid_visible
        if self.params.grid_visible:
            self.layers.redraw(Layer_Name.grid, True)
        else:
            self.layers.clear(Layer_Name.grid, force=True)
        self.status.temp("Grid ON" if self.params.grid_visible else "Grid OFF")
        self.mark_dirty()

    def on_grid_change(self, *_):
        try:
            self.params.grid_size = max(0, int(self.var_grid.get()))
        except ValueError:
            return
        self.params.grid_visible = self.params.grid_size > 0
        self._apply_size_increments(self.params.grid_size)
        self.layers.redraw(Layer_Name.grid, True)

    def on_brush_change(self, *_):
        try:
            self.params.brush_width = max(1, int(self.var_brush_w.get()))
        except ValueError:
            return
        self.status.temp(f"Line width: {self.params.brush_width}")
        self.mark_dirty()

    def on_canvas_size_change(self, *_):
        try:
            w = max(self.params.grid_size, int(self.var_width_px.get()))
            h = max(self.params.grid_size, int(self.var_height_px.get()))
        except ValueError:
            return
        self.params.width, self.params.height = w, h
        self.canvas.config(width=w, height=h)
        self.layers.redraw_all()
        self.status.temp(f"Canvas {w}×{h}")
        self.mark_dirty()

    def apply_bg(self, *_):
        raw = (self.var_bg.get().strip() if self.var_bg else "") or "white"
        try:
            col = Colours.parse_colour(raw)
        except ValueError:
            col = Colours.white
        self.params.bg_mode = col
        display_bg = Colours.sys.dark_gray if col.alpha == 0 else col
        self.canvas.config(bg=display_bg.hex)
        self.layers.redraw(Layer_Name.grid)

    def apply_colour(self, *_):
        raw = (self.var_colour.get().strip() if self.var_colour else "") or "black"
        try:
            col = Colours.parse_colour(raw)
        except ValueError:
            col = Colours.black
        self.params.brush_colour = col
        self.status.temp(f"Brush: {Colours.name_for(col) or col.hexa}")

    def on_double_click(self, evt):
        self.tool_mgr.cancel()

        hit = test_hit(self.canvas, int(evt.x), int(evt.y))
        if not hit or hit.tag_idx is None or hit.kind == Hit_Kind.miss:
            return

        if hit.kind == Hit_Kind.line:
            obj = self.params.lines[hit.tag_idx]
            layer = Layer_Name.lines
        elif hit.kind == Hit_Kind.label:
            obj = self.params.labels[hit.tag_idx]
            layer = Layer_Name.labels
        elif hit.kind == Hit_Kind.icon:
            obj = self.params.icons[hit.tag_idx]
            layer = Layer_Name.icons
        else:
            return

        self._set_selected(hit.kind, hit.tag_idx)
        if self.editors.edit(self.root, obj):
            self.layers.redraw(layer, True)
            self.selection.update_bbox()
            self.mark_dirty()
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

    def on_redo(self, _evt=None):
        self.tool_mgr.cancel()
        self.cmd.redo()
        self.repair_snap_flags(self.params)
        self.layers.redraw_all()
        self.selection.update_bbox()
        self.mark_dirty()
        self.status.temp("Redo")

    def on_clear(self, _evt=None):
        self.tool_mgr.cancel()
        self.params.lines.clear()
        self.params.labels.clear()
        self.params.icons.clear()
        self.layers.redraw_all()
        self._set_selected(Hit_Kind.miss, None)
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

    def on_style_changed(self, style_name: str):
        self.status.temp(f"Line style: {style_name}", ms=1500)  # centre info

    def on_icon_selected(self, icon_name: str):
        self.status.temp(f"Icon: {icon_name}", ms=1500)

    # ========= export / persistence =========
    def export_image(self):
        initialfile = self.params.output_file.name
        path = filedialog.asksaveasfilename(
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
            messagebox.showerror("Invalid filetype", f"Choose one of: {', '.join(Formats)}")
            return

        self.params.output_file = out
        try:
            Exporter.output(self.params)
        except Exception as e:
            messagebox.showerror("Export failed", str(e))
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
            messagebox.showerror("Save failed", str(e))
            return False
        self.mark_clean()
        self.on_file_saved(self.project_path)
        return True

    def save_project_as(self) -> bool:
        path = filedialog.asksaveasfilename(
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
        return ok

    def new_project(self):
        if not self._maybe_proceed():
            return
        self.params = Params()
        self.scene = Scene(self.params)
        self.painters = Painters(self.scene)
        self.layers = Layer_Manager(self.canvas, self.painters)
        self._set_selected(Hit_Kind.miss, None)
        self.layers.redraw_all()
        self.mark_clean()
        self.status.set("New Project")

    def open_project(self):
        if not self._maybe_proceed():
            return
        path = filedialog.askopenfilename(
            parent=self.root,
            title="Open Project",
            filetypes=[("Linework Projects", "*.linework"), ("JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        self.project_path = Path(path)
        try:
            self.params = IO.load_params(self.project_path)
        except Exception as e:
            messagebox.showerror("Open failed", str(e))
            return
        self.scene = Scene(self.params)
        self.painters = Painters(self.scene)
        self.layers = Layer_Manager(self.canvas, self.painters)
        self._sync_vars_from_params()
        self.layers.redraw_all()
        self._update_title()
        self.mark_clean()
        self.on_file_opened(self.project_path)
        self.asset_lib = get_asset_library(self.project_path)

    # ========= helpers =========

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

    def _sync_vars_from_params(self):
        self.repair_snap_flags(self.params)
        self.var_grid.set(self.params.grid_size)
        self.var_width_px.set(self.params.width)
        self.var_height_px.set(self.params.height)
        self.var_brush_w.set(self.params.brush_width)
        self.var_bg.set(self.params.bg_mode.name or "Unknown")
        self.var_colour.set(self.params.brush_colour.name or "Unknown")
        self.var_line_style.set(self.params.line_style)
        display_bg = Colours.sys.dark_gray.hex if self.params.bg_mode.alpha == 0 else self.params.bg_mode.hex
        self.canvas.config(width=self.params.width, height=self.params.height, bg=display_bg)

    def _apply_size_increments(self, g: int):
        step = max(1, g)
        self.tbar.spin_w.configure(increment=step, from_=step)
        self.tbar.spin_h.configure(increment=step, from_=step)

    def _maybe_proceed(self) -> bool:
        if not self.dirty:
            return True
        ans = messagebox.askyesnocancel("Save changes?", "Save your changes before continuing?")
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
        self.status.set_centre("Draw: drag to draw" if on else "Draw: click-click mode")

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

    def mark_clean(self):
        self.dirty = False
        self._update_title()

"""Qt application window for Linework."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6 import QtCore, QtGui, QtWidgets

from core.commands import CommandStack, DeleteIcon, DeleteLabel, DeleteLine, Multi
from core.layers import HitKind
from disk.storage import IO, current_storage_mode, default_settings_path, set_storage_mode
from models.assets import get_asset_library
from models.geo import IconSource, IconType, Point
from models.params import Params
from models.schemas import settings_schema
from models.styling import Anchor, Colour, Colours, LineStyle
from qt.canvas_scene import QtCanvasScene
from qt.hit_test import hit_test
from qt.input import MotionEvent
from qt.renderer import QtSceneRenderer
from qt.selection import QtSelectionOverlay
from qt.tool_manager import QtToolManager
from qt.tools.base import ToolName
from qt.tools.draw import DrawTool
from qt.tools.eraser import EraserTool
from qt.tools.icon import IconTool
from qt.tools.label import LabelTool
from qt.tools.select import SelectTool
from qt.view import QtCanvasView
from ui.qt.editors import QtEditors
from ui.qt.icon_picker import QtIconPickerDialog
from ui.qt.settings_bar import QtSettingsBar
from ui.qt.settings_dialog import QtSettingsDialog
from ui.qt.status_bar import QtStatus, QtStatusStrip, Side

if TYPE_CHECKING:
    from models.geo import Point
    from ui.qt.properties import PropertiesPanel


def _sync_custom_palette(target: list[Colour | None], source: list[Colour | None]) -> None:
    target[:] = list(source)


def _load_params(project_path: Path | None) -> tuple[Params, Path | None]:
    """Load params and resolve the project path.

    Args;
        project_path: Optional project path.

    Returns;
        The params instance and resolved project path.
    """
    defaults_path = default_settings_path()
    try:
        defaults = IO.load_defaults(defaults_path)
    except Exception as xcp:
        defaults = Params()
        print(f"Defaults load failed; using built-ins: {xcp}", file=sys.stderr)

    _sync_custom_palette(Colours.custom_palette, defaults.custom_palette)
    default_project = getattr(defaults, "default_project", None)
    window_width = int(getattr(defaults, "window_width", 0) or 0)
    window_height = int(getattr(defaults, "window_height", 0) or 0)
    remember_window_size = bool(getattr(defaults, "remember_window_size", False))
    auto_expand_window = bool(getattr(defaults, "auto_expand_window", False))
    auto_shrink_window = bool(getattr(defaults, "auto_shrink_window", False))
    custom_palette_shared = bool(getattr(defaults, "custom_palette_shared", True))
    if auto_expand_window or auto_shrink_window:
        window_width = 0
        window_height = 0

    def _apply_palette_mode(params: Params) -> None:
        params.custom_palette_shared = custom_palette_shared
        palette_snapshot = list(params.custom_palette)
        if not custom_palette_shared:
            _sync_custom_palette(Colours.custom_palette, palette_snapshot)
        params.custom_palette = Colours.custom_palette
    if project_path is None and default_project:
        candidate = Path(default_project).expanduser()
        if candidate.suffix.lower() == ".linework" and candidate.is_file():
            try:
                params = IO.load_params(candidate)
            except Exception as xcp:
                print(f"Default project load failed; using defaults: {xcp}", file=sys.stderr)
            else:
                params.default_project = default_project
                params.window_width = window_width
                params.window_height = window_height
                params.remember_window_size = remember_window_size
                params.auto_expand_window = auto_expand_window
                params.auto_shrink_window = auto_shrink_window
                _apply_palette_mode(params)
                return params, candidate

    if project_path is None:
        params = Params()
        params.apply_profile(defaults, inplace_palette=True)
        _apply_palette_mode(params)
        return params, None

    project = project_path
    if project.exists():
        try:
            params = IO.load_params(project)
        except Exception as xcp:
            params = Params()
            params.apply_profile(defaults, inplace_palette=True)
            print(f"Project load failed; using defaults: {xcp}", file=sys.stderr)
    else:
        params = Params()
        params.apply_profile(defaults, inplace_palette=True)
    params.default_project = default_project
    params.window_width = window_width
    params.window_height = window_height
    params.remember_window_size = remember_window_size
    params.auto_expand_window = auto_expand_window
    params.auto_shrink_window = auto_shrink_window
    _apply_palette_mode(params)
    return params, project


class QtApp(QtWidgets.QMainWindow):
    """Main Qt window for Linework."""

    def __init__(self, project_path: Path | None = None) -> None:
        """Create the Qt application window.

        Args;
            project_path: Optional project path to load.
        """
        super().__init__()
        self.params, self.project_path = _load_params(project_path)
        self._normalize_canvas_params()
        self.dirty = False
        self.last_save_was_autosave = False
        self._set_last_save_autosave(self.project_path)
        self.asset_lib = get_asset_library(self._project_path_or_default())

        self.setWindowTitle("Linework (Qt)")
        self.scene = QtCanvasScene(self)
        self.view = QtCanvasView(self, self.scene)
        self.view.setRenderHints(
            QtGui.QPainter.RenderHint.Antialiasing
            | QtGui.QPainter.RenderHint.TextAntialiasing
            | QtGui.QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setCentralWidget(self.view)

        self.renderer = QtSceneRenderer(self.scene)
        self.preview_items: list[QtWidgets.QGraphicsItem] = []

        self.cmd = CommandStack()
        self.current_icon: IconSource = self.params.default_icon

        self.selection_kind: "HitKind | None" = None
        self.selection_index: int | None = None
        self.multi_sel: list[tuple[HitKind, int]] = []
        self.selection = QtSelectionOverlay(self)
        self.properties_panel: PropertiesPanel | None = None

        self.tools = {
            ToolName.select: SelectTool(),
            ToolName.draw: DrawTool(),
            ToolName.erase: EraserTool(),
            ToolName.label: LabelTool(),
            ToolName.icon: IconTool(),
        }
        self.tool_mgr = QtToolManager(self, self.tools)
        self.editors = QtEditors(self)
        self.tool_mgr.activate(ToolName.select)
        self.view.setFocus()

        self._build_actions()
        self._build_menu()
        self._build_tool_actions()
        self._build_settings_bar()
        self._build_status_bar()
        self._install_modifier_filter()
        self.renderer.render(self.params)
        self._sync_view_size()
        self._sync_view_size_after_layout()
        self._status_hints_set()
        self.status.set("Ready")

    def _sync_view_size(self) -> None:
        """Apply scene geometry to the view and window."""
        w, h = self.params.width, self.params.height
        self.view.setSceneRect(0, 0, w, h)
        window_w, window_h = self._resolve_window_size(w, h)
        self.resize(window_w, window_h)

    def _sync_view_size_after_layout(self) -> None:
        """Schedule a size sync after layout if auto sizing is enabled."""
        if not (
            getattr(self.params, "auto_expand_window", False) or getattr(self.params, "auto_shrink_window", False)
        ):
            return
        QtCore.QTimer.singleShot(15, self._sync_view_size)

    def _window_chrome_size(self) -> tuple[int, int]:
        """Return the extra window size needed around the canvas view.

        Returns;
            The extra width and height.
        """
        window_size = self.size()
        view_size = self.view.size()
        extra_w = window_size.width() - view_size.width()
        extra_h = window_size.height() - view_size.height()
        if (
            window_size.width() > 0
            and window_size.height() > 0
            and view_size.width() > 0
            and view_size.height() > 0
            and extra_w >= 0
            and extra_h >= 0
            and (extra_w > 0 or extra_h > 0)
        ):
            return int(extra_w), int(extra_h)

        hint = self.sizeHint()
        view_hint = self.view.sizeHint()
        extra_w = hint.width() - view_hint.width()
        extra_h = hint.height() - view_hint.height()
        if extra_w >= 0 and extra_h >= 0 and (extra_w > 0 or extra_h > 0):
            return int(extra_w), int(extra_h)

        extra_h = 0
        menu = self.menuBar()
        if menu is not None:
            extra_h += menu.sizeHint().height()
        toolbar = getattr(self, "settings_toolbar", None)
        if toolbar is not None:
            extra_h += toolbar.sizeHint().height()
        status = self.statusBar()
        if status is not None:
            extra_h += status.sizeHint().height()
        if extra_h <= 0:
            extra_h = 100
        return 0, int(extra_h)

    def _resolve_window_size(self, canvas_w: int, canvas_h: int) -> tuple[int, int]:
        """Resolve a window size from canvas size and preferences.

        Args;
            canvas_w: Canvas width.
            canvas_h: Canvas height.

        Returns;
            The window width and height.
        """
        extra_w, extra_h = self._window_chrome_size()
        base_w = max(640, canvas_w + extra_w)
        base_h = max(480, canvas_h + extra_h)
        pref_w = int(getattr(self.params, "window_width", 0) or 0)
        pref_h = int(getattr(self.params, "window_height", 0) or 0)
        window_w = pref_w if pref_w > 0 else base_w
        window_h = pref_h if pref_h > 0 else base_h
        if getattr(self.params, "auto_expand_window", False):
            window_w = max(window_w, base_w)
            window_h = max(window_h, base_h)
        if getattr(self.params, "auto_shrink_window", False):
            window_w = min(window_w, base_w)
            window_h = min(window_h, base_h)
        return self._clamp_window_size(window_w, window_h)

    def _clamp_window_size(self, window_w: int, window_h: int) -> tuple[int, int]:
        """Clamp window size to the current screen.

        Args;
            window_w: Proposed window width.
            window_h: Proposed window height.

        Returns;
            The clamped window size.
        """
        screen = self.screen() or QtGui.QGuiApplication.primaryScreen()
        if screen is None:
            return window_w, window_h
        available = screen.availableGeometry()
        max_w = int(available.width())
        max_h = int(available.height())
        if max_w > 0:
            window_w = min(window_w, max_w)
        if max_h > 0:
            window_h = min(window_h, max_h)
        return window_w, window_h

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # type: ignore[override]
        """Track window size when remember is enabled."""
        super().resizeEvent(event)
        if not self.params.remember_window_size:
            return
        if self.params.auto_expand_window or self.params.auto_shrink_window:
            self.params.window_width = 0
            self.params.window_height = 0
            return
        if self.windowState() & QtCore.Qt.WindowState.WindowMinimized:
            return
        size = event.size()
        self.params.window_width = int(size.width())
        self.params.window_height = int(size.height())

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # type: ignore[override]
        """Persist window size and close auxiliary windows."""
        if not self._confirm_close():
            event.ignore()
            return
        self._persist_window_size()
        super().closeEvent(event)
        if event.isAccepted():
            self._close_aux_windows()

    def _confirm_close(self) -> bool:
        """Prompt to save when closing with unsaved or autosaved work."""
        # Only bother the user when there are actual edits.
        if not self.dirty:
            return True
        unsaved = self.project_path is None

        parts = []
        if unsaved:
            parts.append("This project hasn't been saved yet.")
        if self.dirty:
            parts.append("You have unsaved changes.")
        if self.last_save_was_autosave:
            parts.append("The last save was an autosave.")
        message = "\n".join(parts) or "Save the project before closing?"

        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        box.setWindowTitle("Save project?")
        box.setText(message)
        box.setInformativeText("Save the project before closing?")
        box.setStandardButtons(
            QtWidgets.QMessageBox.StandardButton.Save
            | QtWidgets.QMessageBox.StandardButton.Discard
            | QtWidgets.QMessageBox.StandardButton.Cancel
        )
        box.setDefaultButton(QtWidgets.QMessageBox.StandardButton.Save)

        choice = box.exec()
        if choice == QtWidgets.QMessageBox.StandardButton.Save:
            if unsaved or (self.last_save_was_autosave and self._is_autosave_path(self.project_path)):
                self.on_save_as()
            else:
                self.on_save()
            return not self.dirty
        if choice == QtWidgets.QMessageBox.StandardButton.Discard:
            return True
        return False

    @staticmethod
    def _is_autosave_path(path: Path | None) -> bool:
        """Return True when the path looks like an autosave file."""
        if path is None:
            return False
        suffixes = path.suffixes
        return suffixes[-1:] == [".autosave"] or path.name.endswith(".linework.autosave")

    def _set_last_save_autosave(self, path: Path | None) -> None:
        """Update autosave tracking based on the current path."""
        self.last_save_was_autosave = self._is_autosave_path(path)

    def _persist_window_size(self) -> None:
        """Persist the current window size to defaults."""
        try:
            defaults = IO.load_defaults()
        except Exception as xcp:
            print(f"Defaults load failed; window size not saved: {xcp}", file=sys.stderr)
            return
        if not getattr(defaults, "remember_window_size", False):
            return
        if self.params.auto_expand_window or self.params.auto_shrink_window:
            defaults.window_width = 0
            defaults.window_height = 0
            try:
                IO.save_defaults(defaults)
            except Exception as xcp:
                print(f"Default window size save failed: {xcp}", file=sys.stderr)
            return
        size = self.size()
        if self.windowState() & QtCore.Qt.WindowState.WindowMinimized:
            size = self.normalGeometry().size()
        defaults.window_width = int(size.width())
        defaults.window_height = int(size.height())
        try:
            IO.save_defaults(defaults)
        except Exception as xcp:
            print(f"Default window size save failed: {xcp}", file=sys.stderr)

    def _close_aux_windows(self) -> None:
        for widget in QtWidgets.QApplication.topLevelWidgets():
            if widget is self:
                continue
            self._safe_close_window(widget)

    @staticmethod
    def _safe_close_window(widget: QtWidgets.QWidget) -> None:
        try:
            widget.close()
        except RuntimeError:
            return

    # ---------- rendering ----------
    def redraw(self) -> None:
        """Redraw the scene and selection overlays."""
        self.clear_preview()
        self.renderer.render(self.params)
        self.scene.invalidate(self.scene.sceneRect(), QtWidgets.QGraphicsScene.SceneLayer.BackgroundLayer)
        self.selection.refresh()
        if self.properties_panel is not None:
            self.properties_panel.refresh()

    def clear_preview(self) -> None:
        """Clear preview items from the scene."""
        for item in self.preview_items:
            self.scene.removeItem(item)
        self.preview_items.clear()

    def add_preview_item(self, item: QtWidgets.QGraphicsItem) -> None:
        """Track a preview item for cleanup."""
        if item.scene() is None:
            self.scene.addItem(item)
        self.preview_items.append(item)

    def add_preview_items(self, items: list[QtWidgets.QGraphicsItem]) -> None:
        """Track multiple preview items for cleanup."""
        for item in items:
            self.add_preview_item(item)

    def preview_bbox(self) -> QtCore.QRectF | None:
        """Return a bounding box for all preview items."""
        rect: QtCore.QRectF | None = None
        for item in self.preview_items:
            ib = item.sceneBoundingRect()
            rect = ib if rect is None else rect.united(ib)
        return rect

    # ---------- input helpers ----------
    def prompt_text(self, title: str, prompt: str) -> str | None:
        """Prompt for text using a simple dialog."""
        text, ok = QtWidgets.QInputDialog.getText(self, title, prompt)
        if not ok:
            return None
        value = text.strip()
        return value if value else None

    def pick_icon_source(self) -> IconSource | None:
        """Pick a builtin or picture icon.

        Returns;
            The selected icon source, or None if cancelled.
        """
        dlg = QtIconPickerDialog(self, initial=self.current_icon or self.params.default_icon)
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return None
        return dlg.selected_source()

    # ---------- edit helpers ----------
    def on_double_click(self, evt: "MotionEvent") -> None:
        """Open the modal editor for the hit item."""
        if getattr(self.tool_mgr.current, "name", None) != ToolName.select:
            return
        hit = hit_test(self.scene, evt.x, evt.y)
        if not hit or hit.tag_idx is None:
            return
        obj = self._object_for_hit(hit.kind, hit.tag_idx)
        if obj is None:
            return
        self.select_set([(hit.kind, hit.tag_idx)])
        if self.editors.edit(self, obj):
            self._sync_selection_index(hit.kind, obj)
            self.redraw()
            self.mark_dirty()
            if hasattr(self, "status"):
                self.status.temp("Updated", 1200)

    def _object_for_hit(self, hit_kind: HitKind, idx: int) -> object | None:
        """Return the model object for a hit reference.

        Args;
            hit_kind: The hit kind.
            idx: The hit index.

        Returns;
            The model object, or None if unavailable.
        """
        if hit_kind == HitKind.line and 0 <= idx < len(self.params.lines):
            return self.params.lines[idx]
        if hit_kind == HitKind.label and 0 <= idx < len(self.params.labels):
            return self.params.labels[idx]
        if hit_kind == HitKind.icon and 0 <= idx < len(self.params.icons):
            return self.params.icons[idx]
        return None

    @staticmethod
    def _index_for_item(items: Sequence[object], target: object) -> int | None:
        """Return the index of a target by identity.

        Args;
            items: The sequence to search.
            target: The target object.

        Returns;
            The index, or None if not found.
        """
        for idx, item in enumerate(items):
            if item is target:
                return idx
        return None

    def _sync_selection_index(self, hit_kind: HitKind, obj: object) -> None:
        """Sync selection indices after edits.

        Args;
            hit_kind: The selection kind.
            obj: The edited object.
        """
        if hit_kind == HitKind.line:
            idx = self._index_for_item(self.params.lines, obj)
        elif hit_kind == HitKind.label:
            idx = self._index_for_item(self.params.labels, obj)
        elif hit_kind == HitKind.icon:
            idx = self._index_for_item(self.params.icons, obj)
        else:
            return
        if idx is None:
            return
        if self.selection_kind == hit_kind and self.selection_index == idx:
            return
        self.select_set([(hit_kind, idx)])

    # ---------- snapping ----------
    def snap(self, point: Point, *, ignore_grid: bool = False) -> Point:
        """Clamp or snap a point to grid and bounds."""
        width, height = self.params.width, self.params.height
        if ignore_grid or self.params.grid_size <= 0:
            clamped_x = 0 if point.x < 0 else min(point.x, width)
            clamped_y = 0 if point.y < 0 else min(point.y, height)
            return Point(x=clamped_x, y=clamped_y)
        grid_size = self.params.grid_size
        snapped_x = round(point.x / grid_size) * grid_size
        snapped_y = round(point.y / grid_size) * grid_size
        snapped_x = 0 if snapped_x < 0 else min(snapped_x, (width // grid_size) * grid_size)
        snapped_y = 0 if snapped_y < 0 else min(snapped_y, (height // grid_size) * grid_size)
        return Point(x=snapped_x, y=snapped_y)

    @staticmethod
    def _round_to_multiple(value: int, step: int) -> int:
        """Round a value to the nearest multiple.

        Args;
            value: The input value.
            step: The step size.

        Returns;
            The rounded value.
        """
        return int((value + step / 2) // step) * step

    @staticmethod
    def _clamp_int(value: int, min_value: int | None = None, max_value: int | None = None) -> int:
        """Clamp an integer to optional bounds.

        Args;
            value: The input value.
            min_value: Optional minimum.
            max_value: Optional maximum.

        Returns;
            The clamped value.
        """
        if min_value is not None:
            value = max(min_value, value)
        if max_value is not None:
            value = min(max_value, value)
        return value

    @staticmethod
    def _coerce_step(value: int | None) -> int:
        """Coerce a step value to a positive integer.

        Args;
            value: The input value.

        Returns;
            The coerced step.
        """
        try:
            step = int(value) if value is not None else 1
        except (TypeError, ValueError):
            step = 1
        return max(1, step)

    def _snap_grid_size_value(self, value: int, *, step: int | None = None) -> int:
        """Snap grid size to the configured step.

        Args;
            value: The raw grid size.
            step: Optional step override.

        Returns;
            The snapped grid size.
        """
        step_value = self._coerce_step(self.params.grid_step if step is None else step)
        if value <= 0:
            return 0
        snapped = self._round_to_multiple(int(value), step_value)
        return step_value if snapped <= 0 else snapped

    def _snap_canvas_dimension(
        self,
        value: int,
        *,
        grid_size: int | None = None,
        min_value: int | None = None,
        max_value: int | None = None,
    ) -> int:
        """Snap a canvas dimension to the grid and bounds.

        Args;
            value: The raw dimension value.
            grid_size: Optional grid size override.
            min_value: Optional minimum.
            max_value: Optional maximum.

        Returns;
            The snapped dimension.
        """
        grid = int(self.params.grid_size if grid_size is None else grid_size)
        if grid <= 0:
            return self._clamp_int(int(value), min_value, max_value)
        snapped = self._round_to_multiple(int(value), grid)
        if snapped <= 0:
            snapped = grid
        if min_value is not None and snapped < min_value:
            snapped = ((min_value + grid - 1) // grid) * grid
        if max_value is not None and snapped > max_value:
            snapped = (max_value // grid) * grid
            if snapped <= 0:
                snapped = grid
        return snapped

    def _normalize_canvas_params(self) -> None:
        """Normalise grid and canvas dimensions."""
        self.params.grid_step = self._coerce_step(self.params.grid_step)
        self.params.grid_size = self._snap_grid_size_value(self.params.grid_size, step=self.params.grid_step)
        self.params.width = self._snap_canvas_dimension(self.params.width, grid_size=self.params.grid_size, min_value=1)
        self.params.height = self._snap_canvas_dimension(
            self.params.height, grid_size=self.params.grid_size, min_value=1
        )

    # ---------- selection ----------
    def is_selected(self, kind: HitKind, idx: int) -> bool:
        """Return True if an item is selected."""
        return (kind, idx) in self.multi_sel

    def select_clear(self) -> None:
        """Clear the current selection."""
        self.multi_sel.clear()
        self._set_selected(None, None)
        self._status_selected_hint()

    def select_set(self, items: list[tuple[HitKind, int]]) -> None:
        """Replace the selection with the given items."""
        filtered_items = [(hit_kind, index) for hit_kind, index in items if hit_kind and index is not None]
        unique: list[tuple[HitKind, int]] = []
        for hit_kind, index in filtered_items:
            if (hit_kind, index) not in unique:
                unique.append((hit_kind, index))
        self.multi_sel = unique
        if len(self.multi_sel) == 1:
            primary_kind, primary_index = self.multi_sel[0]
            self._set_selected(primary_kind, primary_index)
        else:
            self._set_selected(None, None)
            if self.multi_sel:
                self.selection.show_many(self.multi_sel, primary=None)
        self._status_selected_hint()

    def select_merge(self, items: list[tuple[HitKind, int]]) -> None:
        """Merge items into the current selection."""
        changed = False
        for hit_kind, index in items:
            if (hit_kind, index) not in self.multi_sel:
                self.multi_sel.append((hit_kind, index))
                changed = True
        if changed:
            if len(self.multi_sel) == 1:
                primary_kind, primary_index = self.multi_sel[0]
                self._set_selected(primary_kind, primary_index)
            else:
                self._set_selected(None, None)
                self.selection.show_many(self.multi_sel, primary=None)
        self._status_selected_hint()

    def select_add(self, kind: HitKind, idx: int, make_primary: bool = False) -> None:
        """Add an item to the selection."""
        if (kind, idx) not in self.multi_sel:
            self.multi_sel.append((kind, idx))
        if make_primary and len(self.multi_sel) == 1:
            self._set_selected(kind, idx)
        elif len(self.multi_sel) == 1:
            self._set_selected(kind, idx)
        else:
            self._set_selected(None, None)
            self.selection.show_many(self.multi_sel, primary=None)
        self._status_selected_hint()

    def select_remove(self, kind: HitKind, idx: int) -> None:
        """Remove an item from the selection."""
        try:
            self.multi_sel.remove((kind, idx))
        except ValueError:
            pass
        if len(self.multi_sel) == 1:
            primary_kind, primary_index = self.multi_sel[0]
            self._set_selected(primary_kind, primary_index)
        elif self.multi_sel:
            self._set_selected(None, None)
            self.selection.show_many(self.multi_sel, primary=None)
        else:
            self._set_selected(None, None)
        self._status_selected_hint()

    def _set_selected(self, hit_kind: "HitKind | None", index: int | None) -> None:
        """Update selection state and related UI.

        Args;
            hit_kind: The selected kind, or None.
            index: The selected index, or None.
        """
        self.selection_kind, self.selection_index = hit_kind, index
        if hit_kind and index is not None:
            self.multi_sel = [(hit_kind, index)]
            self.selection.show_many(self.multi_sel, primary=(hit_kind, index))
            if hasattr(self, "status"):
                if hit_kind == HitKind.line and 0 <= index < len(self.params.lines):
                    line = self.params.lines[index]
                    _, _, line_length = line.unit()
                    self.status.hold(
                        "sel",
                        f"Line {index}: {int(line_length)}px | width {line.width} | {line.style.value}",
                        priority=10,
                        side=Side.centre,
                    )
                elif hit_kind == HitKind.label and 0 <= index < len(self.params.labels):
                    label = self.params.labels[index]
                    preview = (label.text[:20] + "...") if len(label.text) > 20 else label.text
                    self.status.hold(
                        "sel",
                        f'Label {index}: "{preview}" | size {label.size} | rot {label.rotation}deg',
                        priority=10,
                        side=Side.centre,
                    )
                elif hit_kind == HitKind.icon and 0 <= index < len(self.params.icons):
                    icon = self.params.icons[index]
                    self.status.hold(
                        "sel",
                        f"Icon {index}: size {icon.size} | rot {icon.rotation}deg",
                        priority=10,
                        side=Side.centre,
                    )
                else:
                    self.status.release("sel")
        else:
            self.selection.clear()
            if hasattr(self, "status"):
                self.status.release("sel")
        if self.properties_panel is not None:
            self.properties_panel.set_target(hit_kind, index)

    def on_select_all(self) -> None:
        """Select all items in the scene."""
        items: list[tuple[HitKind, int]] = []
        items.extend((HitKind.line, idx) for idx in range(len(self.params.lines)))
        items.extend((HitKind.label, idx) for idx in range(len(self.params.labels)))
        items.extend((HitKind.icon, idx) for idx in range(len(self.params.icons)))
        if items:
            self.select_set(items)
        else:
            self.select_clear()

    # ---------- actions ----------
    def _build_actions(self) -> None:
        """Create core actions and shortcuts."""
        self.new_action = QtGui.QAction("New", self)
        self.new_action.setShortcut(QtGui.QKeySequence.StandardKey.New)
        self.new_action.triggered.connect(self.on_new)
        self.addAction(self.new_action)

        self.open_action = QtGui.QAction("Open...", self)
        self.open_action.setShortcut(QtGui.QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self.on_open)
        self.addAction(self.open_action)

        self.open_quick_action = QtGui.QAction("Open/New", self)
        self.open_quick_action.setToolTip("Open project (Shift: New)")
        self.open_quick_action.triggered.connect(self.on_quick_open)
        self.addAction(self.open_quick_action)

        self.save_action = QtGui.QAction("Save", self)
        self.save_action.setShortcut(QtGui.QKeySequence.StandardKey.Save)
        self.save_action.triggered.connect(self.on_save)
        self.addAction(self.save_action)

        self.save_quick_action = QtGui.QAction("Save/As", self)
        self.save_quick_action.setToolTip("Save project (Shift: Save As)")
        self.save_quick_action.triggered.connect(self.on_quick_save)
        self.addAction(self.save_quick_action)

        self.save_as_action = QtGui.QAction("Save As...", self)
        self.save_as_action.setShortcut(QtGui.QKeySequence.StandardKey.SaveAs)
        self.save_as_action.triggered.connect(self.on_save_as)
        self.addAction(self.save_as_action)

        self.export_action = QtGui.QAction("Export...", self)
        self.export_action.setShortcut(QtGui.QKeySequence("Ctrl+E"))
        self.export_action.triggered.connect(self.on_export)
        self.addAction(self.export_action)

        self.export_quick_action = QtGui.QAction("Export/Overwrite", self)
        self.export_quick_action.setToolTip("Export image (Shift: Overwrite last export)")
        self.export_quick_action.triggered.connect(self.on_quick_export)
        self.addAction(self.export_quick_action)

        self.settings_action = QtGui.QAction("Settings...", self)
        self.settings_action.setShortcut(QtGui.QKeySequence("Ctrl+,"))
        self.settings_action.triggered.connect(self.open_settings)
        self.addAction(self.settings_action)

        self.undo_action = QtGui.QAction("Undo", self)
        self.undo_action.setShortcut(QtGui.QKeySequence.StandardKey.Undo)
        self.undo_action.triggered.connect(self.on_undo)
        self.addAction(self.undo_action)

        self.redo_action = QtGui.QAction("Redo", self)
        self.redo_action.setShortcut(QtGui.QKeySequence.StandardKey.Redo)
        self.redo_action.triggered.connect(self.on_redo)
        self.addAction(self.redo_action)

        self.select_all_action = QtGui.QAction("Select All", self)
        self.select_all_action.setShortcut(QtGui.QKeySequence.StandardKey.SelectAll)
        self.select_all_action.triggered.connect(self.on_select_all)
        self.addAction(self.select_all_action)

        self.delete_action = QtGui.QAction("Delete", self)
        self.delete_action.setShortcuts(
            [QtGui.QKeySequence(QtCore.Qt.Key.Key_Delete), QtGui.QKeySequence(QtCore.Qt.Key.Key_Backspace)]
        )
        self.delete_action.triggered.connect(self.on_delete)
        self.addAction(self.delete_action)

    def _build_tool_actions(self) -> None:
        """Create tool actions and shortcuts."""
        self.tool_action_group = QtGui.QActionGroup(self)
        self.tool_action_group.setExclusive(True)
        self.tool_actions = {}

        def _add_tool(name: ToolName, label: str, shortcut: str | None) -> None:
            action = QtGui.QAction(label, self)
            action.setCheckable(True)
            if shortcut:
                action.setShortcut(QtGui.QKeySequence(shortcut))
            action.triggered.connect(lambda _checked, n=name: self.tool_mgr.activate(n))
            self.tool_action_group.addAction(action)
            self.addAction(action)
            self.tool_actions[name] = action
            if name == ToolName.select:
                action.setChecked(True)

        _add_tool(ToolName.select, "Select", "V")
        _add_tool(ToolName.draw, "Draw", "L")
        _add_tool(ToolName.erase, "Eraser", None)  # toggled via E hotkey in tool manager
        _add_tool(ToolName.label, "Label", "T")
        _add_tool(ToolName.icon, "Icon", "I")

    def _build_settings_bar(self) -> None:
        """Create the settings toolbar and bar."""
        if not hasattr(self, "settings_toolbar"):
            toolbar = QtWidgets.QToolBar("Settings", self)
            toolbar.setMovable(False)
            toolbar.setFloatable(False)
            toolbar.setAllowedAreas(QtCore.Qt.ToolBarArea.TopToolBarArea)
            toolbar.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Minimum)
            toolbar.setContentsMargins(0, 0, 0, 0)
            toolbar.setStyleSheet("QToolBar { padding: 0px; spacing: 0px; }")
            layout = toolbar.layout()
            if layout is not None:
                layout.setContentsMargins(0, 0, 0, 0)
                layout.setSpacing(0)
            self.addToolBar(QtCore.Qt.ToolBarArea.TopToolBarArea, toolbar)
            self.settings_toolbar = toolbar
        self._rebuild_settings_bar()

    def _build_status_bar(self) -> None:
        """Create the status bar widget and manager."""
        bar = QtWidgets.QStatusBar(self)
        bar.setSizeGripEnabled(False)
        bar.setContentsMargins(0, 0, 0, 0)

        strip = QtStatusStrip(bar)
        bar.addWidget(strip, 1)
        self.setStatusBar(bar)

        self.status_bar = bar
        self.status_strip = strip
        self.status = QtStatus(strip)

        zoom_widget = QtWidgets.QWidget(bar)
        zoom_widget.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        zoom_layout = QtWidgets.QHBoxLayout(zoom_widget)
        zoom_layout.setContentsMargins(6, 0, 6, 0)
        zoom_layout.setSpacing(4)

        self.zoom_label = QtWidgets.QLabel("Zoom 100%")
        self.zoom_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignVCenter)
        self.zoom_label.setToolTip("Canvas zoom level")
        self.zoom_reset = QtWidgets.QToolButton()
        self.zoom_reset.setText("Reset")
        self.zoom_reset.setToolTip("Reset zoom to 100%")
        self.zoom_reset.setAutoRaise(True)
        self.zoom_reset.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.zoom_reset.clicked.connect(self.reset_zoom)

        zoom_layout.addWidget(self.zoom_label)
        zoom_layout.addWidget(self.zoom_reset)
        bar.addPermanentWidget(zoom_widget)
        self.on_zoom_changed(self.view.zoom_level())

    def _rebuild_settings_bar(self) -> None:
        """Rebuild the settings bar widget."""
        if hasattr(self, "settings_bar_action"):
            try:
                self.settings_toolbar.removeAction(self.settings_bar_action)
            except RuntimeError:
                # Ignore stale Qt objects during toolbar rebuilds.
                pass
        if hasattr(self, "settings_bar"):
            self.settings_bar.deleteLater()
        self.settings_bar = QtSettingsBar(self)
        self.settings_bar_action = self.settings_toolbar.addWidget(self.settings_bar)
        self.on_tool_changed(getattr(self.tool_mgr.current, "name", ToolName.select))
        self._sync_snap_overrides()

    def _install_modifier_filter(self) -> None:
        """Install the global modifier filter."""
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def _sync_snap_overrides(self, mods: QtCore.Qt.KeyboardModifier | None = None) -> None:
        """Update snap toggles to reflect modifier overrides."""
        if not hasattr(self, "settings_bar"):
            return
        if mods is None:
            self.settings_bar.sync_snap_overrides()
            return
        alt_down = bool(mods & QtCore.Qt.KeyboardModifier.AltModifier)
        self.settings_bar.sync_snap_overrides(alt_down=alt_down)

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:  # type: ignore[override]
        """Handle modifier changes for snap toggle updates."""
        event_type = event.type()
        if event_type in (QtCore.QEvent.Type.KeyPress, QtCore.QEvent.Type.KeyRelease):
            if isinstance(event, QtGui.QInputEvent):
                self._sync_snap_overrides(event.modifiers())
            else:
                self._sync_snap_overrides()
        elif event_type in (QtCore.QEvent.Type.WindowActivate, QtCore.QEvent.Type.WindowDeactivate):
            self._sync_snap_overrides()
        return super().eventFilter(obj, event)

    def _build_menu(self) -> None:
        """Build the main menu bar."""
        menu = self.menuBar()
        file_menu = menu.addMenu("File")
        file_menu.addAction(self.new_action)
        file_menu.addAction(self.open_action)
        file_menu.addSeparator()
        file_menu.addAction(self.save_action)
        file_menu.addAction(self.save_as_action)
        file_menu.addSeparator()
        file_menu.addAction(self.export_action)
        file_menu.addSeparator()
        file_menu.addAction("Quit", self.close, QtGui.QKeySequence.StandardKey.Quit)
        menu.addAction(self.open_quick_action)
        menu.addAction(self.save_quick_action)
        menu.addAction(self.export_quick_action)
        menu.addAction(self.settings_action)

    def on_undo(self) -> None:
        """Undo the last action."""
        self.cmd.undo()
        if hasattr(self, "status"):
            self.status.temp("Undo")

    def on_redo(self) -> None:
        """Redo the last undone action."""
        self.cmd.redo()
        if hasattr(self, "status"):
            self.status.temp("Redo")

    def on_delete(self) -> None:
        """Delete the current selection."""
        hit_kind, hit_index = self.selection_kind, self.selection_index
        if self.multi_sel:
            targets = list(self.multi_sel)
        elif hit_kind and hit_index is not None:
            targets = [(hit_kind, hit_index)]
        else:
            if hasattr(self, "status"):
                self.status.temp("Nothing selected to delete", 1500)
            return

        subcommands = []

        def _noop() -> None:
            return None

        for target_kind, target_index in sorted(targets, key=lambda target: (target[0].value, -target[1])):
            if target_kind == HitKind.line:
                subcommands.append(DeleteLine(self.params, target_index, on_after=_noop))
            elif target_kind == HitKind.label:
                subcommands.append(DeleteLabel(self.params, target_index, on_after=_noop))
            elif target_kind == HitKind.icon:
                subcommands.append(DeleteIcon(self.params, target_index, on_after=_noop))

        if subcommands:
            self.cmd.push_and_do(Multi(subcommands, on_after=self.redraw))
            self.select_clear()
            self.mark_dirty()
            if hasattr(self, "status"):
                self.status.temp(f"Deleted {len(subcommands)} item(s)")

    def on_new(self) -> None:
        """Create a new project."""
        defaults_path = default_settings_path()
        try:
            defaults = IO.load_defaults(defaults_path)
        except Exception:
            # Fall back to built-in defaults when settings cannot be read.
            defaults = Params()
        params = Params()
        params.apply_profile(defaults, inplace_palette=True)
        self.project_path = None
        self._load_params_into_app(params)
        if hasattr(self, "status"):
            self.status.set("New Project")

    @staticmethod
    def _shift_pressed() -> bool:
        """Return True when Shift is pressed.

        Returns;
            True if Shift is held.
        """
        return bool(QtGui.QGuiApplication.keyboardModifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier)

    def on_quick_open(self) -> None:
        """Open a project, or create new when Shift is held."""
        if self._shift_pressed():
            self.on_new()
        else:
            self.on_open()

    def on_open(self) -> None:
        """Open a Linework project."""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Open Linework project",
            str(self.project_dir()),
            "Linework (*.linework)",
        )
        if not path:
            return
        self.project_path = Path(path)
        try:
            params = IO.load_params(self.project_path)
        except Exception as xcp:
            QtWidgets.QMessageBox.warning(self, "Open failed", str(xcp))
            return
        self._load_params_into_app(params)
        self.on_file_opened(self.project_path)

    def on_quick_save(self) -> None:
        """Save a project, or save-as when Shift is held."""
        if self._shift_pressed():
            self.on_save_as()
        else:
            self.on_save()

    def on_save(self) -> None:
        """Save the current project."""
        if self.project_path is None:
            self.on_save_as()
            return
        try:
            IO.save_params(self.params, self.project_path)
        except Exception as xcp:
            QtWidgets.QMessageBox.warning(self, "Save failed", str(xcp))
            return
        self.dirty = False
        self.last_save_was_autosave = self._is_autosave_path(self.project_path)
        self._update_title()
        self.on_file_saved(self.project_path)

    def on_save_as(self) -> None:
        """Save the project to a new path."""
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save Linework project",
            str(self._project_path_or_default()),
            "Linework (*.linework)",
        )
        if not path:
            return
        target = Path(path)
        if target.suffix.lower() != ".linework":
            target = target.with_suffix(".linework")
        self.project_path = target
        self.asset_lib = get_asset_library(self.project_path)
        try:
            IO.save_params(self.params, self.project_path)
        except Exception as xcp:
            QtWidgets.QMessageBox.warning(self, "Save failed", str(xcp))
            return
        self.dirty = False
        self.last_save_was_autosave = self._is_autosave_path(self.project_path)
        self._update_title()
        self.on_file_saved(self.project_path)

    def on_quick_export(self) -> None:
        """Export a project, or overwrite the last export when Shift is held."""
        if self._shift_pressed():
            self.on_export_again()
        else:
            self.on_export()

    def on_export(self) -> None:
        """Export the current project to an image file."""
        from disk.export import Exporter

        default_path = self._project_path_or_default().with_suffix(".webp")
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Export image",
            str(default_path),
            "Images (*.png *.webp *.jpg *.jpeg *.bmp *.svg)",
        )
        if not path:
            return
        self.params.output_file = Path(path)
        try:
            Exporter.output(self.params)
        except Exception as xcp:
            QtWidgets.QMessageBox.warning(self, "Export failed", str(xcp))
            return
        QtWidgets.QMessageBox.information(self, "Export complete", f"Saved to {self.params.output_file}")
        if hasattr(self, "status"):
            self.status.set(f"Exported: {self.params.output_file}")

    def on_export_again(self) -> None:
        """Export the current project using the last output path."""
        from disk.export import Exporter

        if not getattr(self.params.output_file, "suffix", ""):
            self.on_export()
            return
        try:
            Exporter.output(self.params)
        except Exception as xcp:
            QtWidgets.QMessageBox.warning(self, "Export failed", str(xcp))
            return
        QtWidgets.QMessageBox.information(self, "Export complete", f"Saved to {self.params.output_file}")
        if hasattr(self, "status"):
            self.status.set(f"Exported: {self.params.output_file}")

    def on_file_opened(self, path: Path) -> None:
        """Update status after opening a file.

        Args;
            path: The opened file path.
        """
        if hasattr(self, "status"):
            self.status.set(f"Opened: {path.name}")

    def on_file_saved(self, path: Path) -> None:
        """Update status after saving a file.

        Args;
            path: The saved file path.
        """
        if hasattr(self, "status"):
            self.status.set(f"Saved: {path.name}")

    def on_ready(self) -> None:
        """Set status to ready."""
        if hasattr(self, "status"):
            self.status.set("Ready")

    def on_hover_xy(self, pos_x: int, pos_y: int) -> None:
        """Update hover status with coordinates.

        Args;
            pos_x: X coordinate.
            pos_y: Y coordinate.
        """
        if hasattr(self, "status"):
            self.status.hold("pos", f"({pos_x},{pos_y})", priority=-100, side=Side.centre)

    def on_hover_motion(self, evt: MotionEvent) -> None:
        """Update hover status using the tool-aware endpoint.

        Args;
            evt: The motion event.
        """
        if isinstance(self.tool_mgr.current, DrawTool):
            p = self.snap(Point(x=evt.x, y=evt.y), ignore_grid=evt.mods.alt)
            start = getattr(self.tool_mgr.current, "_start", None)
            dragging = getattr(self.tool_mgr.current, "_dragging", False)
            if start is not None and (not self.params.drag_to_draw or dragging or self.params.continuous_draw):
                p = DrawTool._maybe_cardinal(self, start, p, invert=evt.mods.ctrl)
            self.on_hover_xy(int(p.x), int(p.y))
            return
        self.on_hover_xy(evt.x, evt.y)

    def on_hover_leave(self) -> None:
        """Clear hover status when leaving the canvas."""
        if hasattr(self, "status"):
            self.status.clear_centre()

    def on_zoom_changed(self, zoom: float) -> None:
        """Update the zoom indicator."""
        if not hasattr(self, "zoom_label"):
            return
        pct = int(round(zoom * 100))
        self.zoom_label.setText(f"Zoom {pct}%")
        if hasattr(self, "zoom_reset"):
            self.zoom_reset.setEnabled(abs(zoom - 1.0) > 1e-3)

    def reset_zoom(self) -> None:
        """Reset the canvas zoom back to 100%."""
        self.view.reset_zoom()
        self.view.setFocus()

    def _status_hints_set(self) -> None:
        """Update status hints for the active tool."""
        if not hasattr(self, "status"):
            return
        hints = getattr(self.tool_mgr.current, "tool_hints", "")
        if hints:
            self.status.hold("hints", hints, side=Side.right, priority=0)
        else:
            self.status.release("hints")
        self._status_selected_hint()

    def _status_selected_hint(self) -> None:
        """Update the selection count hint."""
        if not hasattr(self, "status"):
            return
        selection_count = len(self.multi_sel)
        if selection_count <= 1:
            self.status.release("sel_count")
        else:
            self.status.hold(
                "sel_count",
                f"{selection_count} selected",
                side=Side.centre,
                priority=5,
            )

    # ---------- settings ----------
    def open_settings(self) -> None:
        """Open the settings dialog."""
        schema = settings_schema()
        values = self._settings_values_from_params(self.params)
        base_profile = self.params.model_copy()
        try:
            default_params = IO.load_defaults()
        except Exception:
            # Fall back to built-in defaults when settings cannot be read.
            default_params = Params()
        default_values = self._settings_values_from_params(default_params)
        default_base = default_params.model_copy()

        def _apply(data: dict[str, object]) -> bool:
            nonlocal base_profile
            new_profile = self._settings_from_dialog(data, base_profile)
            mark_dirty = self._settings_touch_project(base_profile, new_profile)
            base_profile = new_profile.model_copy()
            self._apply_settings_profile(new_profile, mark_dirty=mark_dirty)
            return True

        def _save_defaults(data: dict[str, object]) -> dict[str, object] | None:
            nonlocal default_base
            default_profile = self._settings_from_dialog(data, default_base)
            if getattr(default_profile, "custom_palette_shared", True):
                default_profile.custom_palette = list(self.params.custom_palette)
            target_path: Path | None = None
            requested_mode = str(data.get("storage_mode", "")).strip()
            if requested_mode:
                try:
                    target_path = set_storage_mode(requested_mode)
                except Exception as xcp:
                    QtWidgets.QMessageBox.warning(self, "Storage mode unavailable", str(xcp))
                    default_profile.storage_mode = current_storage_mode()
            try:
                IO.save_defaults(default_profile, path=target_path)
            except Exception as xcp:
                QtWidgets.QMessageBox.warning(self, "Save defaults failed", str(xcp))
                return None
            default_base = default_profile.model_copy()
            return self._settings_values_from_params(default_profile)

        dlg = QtSettingsDialog(
            self,
            schema,
            values,
            default_values=default_values,
            on_apply=_apply,
            on_save=_save_defaults,
        )
        dlg.exec()

    @staticmethod
    def _settings_values_from_params(params: Params) -> dict[str, object]:
        """Extract dialog values from params.

        Args;
            params: The params to convert.

        Returns;
            The dialog value mapping.
        """
        default_icon_kind = params.default_icon.kind.value if params.default_icon else IconType.builtin.value
        default_icon_builtin = ""
        default_icon_picture = ""
        if params.default_icon:
            if params.default_icon.kind == IconType.builtin and params.default_icon.name:
                default_icon_builtin = params.default_icon.name.value
            elif params.default_icon.kind == IconType.picture and params.default_icon.src:
                default_icon_picture = str(params.default_icon.src)
        default_project = str(params.default_project) if params.default_project else ""
        storage_mode = "Portable" if current_storage_mode() == "portable" else "Standard"
        window_width = params.window_width
        window_height = params.window_height
        if params.auto_expand_window or params.auto_shrink_window:
            window_width = 0
            window_height = 0
        return dict(
            default_project=default_project,
            storage_mode=storage_mode,
            custom_palette_shared=getattr(params, "custom_palette_shared", True),
            window_width=window_width,
            window_height=window_height,
            remember_window_size=params.remember_window_size,
            auto_expand_window=params.auto_expand_window,
            auto_shrink_window=params.auto_shrink_window,
            width=params.width,
            height=params.height,
            grid_size=params.grid_size,
            grid_step=params.grid_step,
            grid_visible=params.grid_visible,
            drag_to_draw=params.drag_to_draw,
            continuous_draw=params.continuous_draw,
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

    def _settings_from_dialog(self, data: dict[str, object], base: Params) -> Params:
        """Build a params profile from dialog data.

        Args;
            data: The dialog data.
            base: The base params profile.

        Returns;
            The updated params profile.
        """
        def _parse_colour(key: str, fallback: Colour) -> Colour:
            raw = str(data.get(key, "")).strip()
            if not raw:
                return fallback
            try:
                return Colours.parse_colour(raw)
            except ValueError:
                return fallback

        def _int_from_data(key: str, fallback: int, *, min_value: int | None = None) -> int:
            raw = data.get(key, fallback)
            if isinstance(raw, bool):
                value = fallback
            elif isinstance(raw, int):
                value = raw
            elif isinstance(raw, float):
                value = int(raw)
            elif isinstance(raw, str):
                cleaned = raw.strip()
                if not cleaned:
                    value = fallback
                else:
                    try:
                        value = int(cleaned)
                    except ValueError:
                        value = fallback
            else:
                value = fallback
            if min_value is not None:
                value = max(min_value, value)
            return value

        def _path_from_data(key: str, fallback: Path | None = None) -> Path | None:
            raw = data.get(key, fallback)
            if isinstance(raw, Path):
                return raw
            if raw is None:
                return None
            cleaned = str(raw).strip()
            if not cleaned:
                return None
            return Path(cleaned).expanduser()

        def _storage_mode_from_data(key: str, fallback: str) -> str:
            raw = str(data.get(key, fallback)).strip().lower()
            if raw.startswith("port"):
                return "portable"
            if raw in {"standard", "installed", "normal", "default"}:
                return "standard"
            return fallback

        grid_step = _int_from_data("grid_step", getattr(base, "grid_step", 5), min_value=1)
        grid_size = self._snap_grid_size_value(_int_from_data("grid_size", base.grid_size, min_value=0), step=grid_step)
        width = self._snap_canvas_dimension(
            _int_from_data("width", base.width, min_value=1), grid_size=grid_size, min_value=1
        )
        height = self._snap_canvas_dimension(
            _int_from_data("height", base.height, min_value=1), grid_size=grid_size, min_value=1
        )

        try:
            style = LineStyle(str(data.get("line_style", base.line_style.value)))
        except ValueError:
            style = base.line_style
        try:
            label_anchor = Anchor.parse(str(data.get("label_anchor", base.label_anchor.value)))
        except ValueError:
            label_anchor = base.label_anchor
        try:
            icon_anchor = Anchor.parse(str(data.get("icon_anchor", base.icon_anchor.value)))
        except ValueError:
            icon_anchor = base.icon_anchor

        icon_kind = str(data.get("default_icon_kind", IconType.builtin.value)).strip().lower()
        default_icon = base.default_icon
        if icon_kind == IconType.picture.value:
            pic = str(data.get("default_icon_picture", "")).strip()
            if pic:
                default_icon = IconSource.picture(pic)
        else:
            name = str(data.get("default_icon_builtin", "")).strip()
            if name:
                try:
                    default_icon = IconSource.builtin(name)
                except ValueError:
                    default_icon = base.default_icon

        updates = {
            "default_project": _path_from_data("default_project", base.default_project),
            "storage_mode": _storage_mode_from_data("storage_mode", getattr(base, "storage_mode", "portable")),
            "custom_palette_shared": bool(data.get("custom_palette_shared", base.custom_palette_shared)),
            "window_width": _int_from_data("window_width", base.window_width, min_value=0),
            "window_height": _int_from_data("window_height", base.window_height, min_value=0),
            "remember_window_size": bool(data.get("remember_window_size", base.remember_window_size)),
            "auto_expand_window": bool(data.get("auto_expand_window", base.auto_expand_window)),
            "auto_shrink_window": bool(data.get("auto_shrink_window", base.auto_shrink_window)),
            "width": width,
            "height": height,
            "grid_size": grid_size,
            "grid_step": grid_step,
            "grid_visible": bool(data.get("grid_visible", base.grid_visible)),
            "drag_to_draw": bool(data.get("drag_to_draw", base.drag_to_draw)),
            "continuous_draw": bool(data.get("continuous_draw", base.continuous_draw)),
            "cardinal_snap": bool(data.get("cardinal_snap", base.cardinal_snap)),
            "brush_width": _int_from_data("brush_width", base.brush_width, min_value=1),
            "line_style": style,
            "line_dash_offset": _int_from_data("line_dash_offset", base.line_dash_offset, min_value=0),
            "label_size": _int_from_data("label_size", base.label_size, min_value=1),
            "label_rotation": _int_from_data("label_rotation", base.label_rotation),
            "label_anchor": label_anchor,
            "label_snap": bool(data.get("label_snap", base.label_snap)),
            "icon_size": _int_from_data("icon_size", base.icon_size, min_value=1),
            "picture_size": _int_from_data("picture_size", base.picture_size, min_value=1),
            "icon_rotation": _int_from_data("icon_rotation", base.icon_rotation),
            "icon_anchor": icon_anchor,
            "icon_snap": bool(data.get("icon_snap", base.icon_snap)),
            "default_icon": default_icon,
            "brush_colour": _parse_colour("brush_colour", base.brush_colour),
            "bg_colour": _parse_colour("bg_colour", base.bg_colour),
            "label_colour": _parse_colour("label_colour", base.label_colour),
            "icon_colour": _parse_colour("icon_colour", base.icon_colour),
            "grid_colour": _parse_colour("grid_colour", base.grid_colour),
        }
        if updates["auto_expand_window"] or updates["auto_shrink_window"]:
            updates["window_width"] = 0
            updates["window_height"] = 0
        return base.model_copy(update=updates)

    @staticmethod
    def _settings_touch_project(before: Params, after: Params) -> bool:
        """Return True if changes affect project data.

        Args;
            before: The original params.
            after: The updated params.

        Returns;
            True if the project should be marked dirty.
        """
        for name in type(before).model_fields:
            if name in {
                "default_project",
                "storage_mode",
                "window_width",
                "window_height",
                "remember_window_size",
                "auto_expand_window",
                "auto_shrink_window",
                "custom_palette_shared",
            }:
                continue
            if getattr(before, name) != getattr(after, name):
                return True
        return False

    def _apply_settings_profile(self, profile: Params, *, mark_dirty: bool = True) -> None:
        """Apply a settings profile and refresh UI.

        Args;
            profile: The profile to apply.
            mark_dirty: Whether to mark the document dirty.
        """
        self.params.apply_profile(profile, inplace_palette=True)
        self._apply_custom_palette_sharing()
        self._normalize_canvas_params()
        self.current_icon = self.params.default_icon
        self._sync_view_size()
        self.redraw()
        self._rebuild_settings_bar()
        self._sync_view_size_after_layout()
        if mark_dirty:
            self.mark_dirty()

    def _apply_custom_palette_sharing(self) -> None:
        if self.params.custom_palette is not Colours.custom_palette:
            _sync_custom_palette(Colours.custom_palette, self.params.custom_palette)
            self.params.custom_palette = Colours.custom_palette
        if bool(getattr(self.params, "custom_palette_shared", True)):
            self._persist_shared_palette()

    def update_custom_palette(self, idx: int, col: Colour | None) -> None:
        if idx < 0:
            return
        palette = self.params.custom_palette
        if idx >= len(palette):
            palette.extend([None] * (idx - len(palette) + 1))
        palette[idx] = col
        if palette is not Colours.custom_palette:
            _sync_custom_palette(Colours.custom_palette, palette)
        if getattr(self.params, "custom_palette_shared", True):
            self._persist_shared_palette()
        else:
            self.mark_dirty()

    def _persist_shared_palette(self) -> None:
        if not getattr(self.params, "custom_palette_shared", True):
            return
        try:
            defaults = IO.load_defaults()
        except Exception as xcp:
            defaults = Params()
            print(f"Defaults load failed; custom palette not persisted: {xcp}", file=sys.stderr)
        defaults.custom_palette_shared = True
        defaults.custom_palette = list(self.params.custom_palette)
        try:
            IO.save_defaults(defaults)
        except Exception as xcp:
            print(f"Defaults save failed; custom palette not persisted: {xcp}", file=sys.stderr)

    def on_tool_changed(self, name: ToolName) -> None:
        """Sync the settings tab and status to the active tool."""
        if hasattr(self, "settings_bar"):
            self.settings_bar.set_active_tool(name)
        if hasattr(self, "status"):
            self.status.clear_centre()
            self.status.temp(f"Tool: {name.value.title()}", 1500, priority=-50)
            self._status_hints_set()

    # ---------- dirty state ----------
    def mark_dirty(self) -> None:
        """Mark the document dirty."""
        if not self.dirty:
            self.dirty = True
            self._update_title()

    def _update_title(self) -> None:
        """Update the window title based on dirty state."""
        suffix = "*" if self.dirty else ""
        self.setWindowTitle(f"Linework (Qt){suffix}")

    def _project_path_or_default(self) -> Path:
        """Return the project path or a placeholder.

        Returns;
            The project path.
        """
        return self.project_path or Path("untitled.linework")

    def project_dir(self) -> Path:
        """Return the project directory or cwd.

        Returns;
            The project directory.
        """
        if self.project_path is None:
            return Path.cwd()
        return self.project_path.parent

    def project_display_path(self) -> str:
        """Return the display path for the current project.

        Returns;
            The display path string.
        """
        return str(self.project_path) if self.project_path is not None else "Unsaved project"

    def _load_params_into_app(self, params: Params) -> None:
        """Replace params and refresh the scene/UI."""
        default_project = getattr(self.params, "default_project", None)
        storage_mode = getattr(self.params, "storage_mode", "portable")
        window_width = getattr(self.params, "window_width", 0)
        window_height = getattr(self.params, "window_height", 0)
        remember_window_size = getattr(self.params, "remember_window_size", False)
        auto_expand_window = getattr(self.params, "auto_expand_window", False)
        auto_shrink_window = getattr(self.params, "auto_shrink_window", False)
        custom_palette_shared = bool(getattr(self.params, "custom_palette_shared", True))
        self.params = params
        self.params.default_project = default_project
        self.params.storage_mode = storage_mode
        self.params.window_width = window_width
        self.params.window_height = window_height
        self.params.remember_window_size = remember_window_size
        self.params.auto_expand_window = auto_expand_window
        self.params.auto_shrink_window = auto_shrink_window
        self.params.custom_palette_shared = custom_palette_shared
        palette_snapshot = list(self.params.custom_palette)
        if not self.params.custom_palette_shared:
            _sync_custom_palette(Colours.custom_palette, palette_snapshot)
        self.params.custom_palette = Colours.custom_palette
        self._normalize_canvas_params()
        self.asset_lib = get_asset_library(self._project_path_or_default())
        self.current_icon = self.params.default_icon
        self.selection_kind = None
        self.selection_index = None
        self.multi_sel.clear()
        self.selection.clear()
        if hasattr(self, "status"):
            self.status.release("sel")
            self._status_selected_hint()
        self.clear_preview()
        self.renderer.render(self.params)
        self._sync_view_size()
        self._rebuild_settings_bar()
        self._sync_view_size_after_layout()
        self.dirty = False
        self._set_last_save_autosave(self.project_path)
        self._update_title()
        if self.properties_panel is not None:
            self.properties_panel.set_target(None, None, force=True)

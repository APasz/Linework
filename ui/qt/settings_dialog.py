"""Tabbed settings dialog for the Qt frontend."""

from __future__ import annotations

import os
import shutil
import sys
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import PySide6
from PySide6 import QtCore, QtGui, QtWidgets

from disk.storage import (
    can_use_portable,
    clear_installed_marker,
    current_storage_mode,
    default_settings_path,
    installed_marker_path,
    mark_installed,
    portable_settings_path,
    standard_settings_path,
)
from models.assets import IconName
from models.styling import Colours
from models.version import get_app_version
from ui.qt.palette import ColourPaletteButton

if TYPE_CHECKING:
    from qt.app import QtApp


class _PicturePicker(QtWidgets.QWidget):
    """Widget for picking picture icon files."""

    changed = QtCore.Signal(str)

    def __init__(self, app: QtApp, initial: Any) -> None:
        """Create the picture picker widget.

        Args;
            app: The parent Qt app.
            initial: The initial value.
        """
        super().__init__()
        self._app = app
        self._path = str(initial or "")

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._edit = QtWidgets.QLineEdit()
        self._edit.setReadOnly(True)
        self._edit.setText(self._display_name(self._path))
        browse = QtWidgets.QPushButton("Browse...")
        browse.clicked.connect(self._choose)

        layout.addWidget(self._edit)
        layout.addWidget(browse)

    @staticmethod
    def _display_name(path: str) -> str:
        """Return the display name for a file path.

        Args;
            path: The input path.

        Returns;
            The display label.
        """
        if not path:
            return ""
        return Path(path).name

    def _choose(self) -> None:
        """Open a file dialog and update the selection."""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Choose picture icon",
            str(self._app.project_dir()),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp *.svg)",
        )
        if not path:
            return
        if hasattr(self._app, "asset_lib"):
            try:
                imported = self._app.asset_lib.import_files([Path(path)])
                if imported:
                    path = str(imported[0])
            except OSError:
                # Best-effort import; fall back to the raw file path.
                pass
        self._path = path
        self._edit.setText(self._display_name(self._path))
        self.changed.emit(self._path)

    def value(self) -> str:
        """Return the selected path.

        Returns;
            The selected path.
        """
        return self._path

    def set_value(self, path: str) -> None:
        """Set the selected path and emit the change signal.

        Args;
            path: The new path.
        """
        self._path = str(path or "")
        self._edit.setText(self._display_name(self._path))
        self.changed.emit(self._path)


class _ProjectPicker(QtWidgets.QWidget):
    """Widget for picking a default project path."""

    changed = QtCore.Signal(str)

    def __init__(self, app: QtApp, initial: Any) -> None:
        """Create the project picker widget.

        Args;
            app: The parent Qt app.
            initial: The initial value.
        """
        super().__init__()
        self._app = app
        self._path = str(initial or "")

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._edit = QtWidgets.QLineEdit()
        self._edit.setReadOnly(True)
        self._edit.setPlaceholderText("Not set")
        self._edit.setText(self._path)
        browse = QtWidgets.QPushButton("Browse...")
        browse.clicked.connect(self._choose)
        clear = QtWidgets.QPushButton("Clear")
        clear.clicked.connect(self._clear)

        layout.addWidget(self._edit)
        layout.addWidget(browse)
        layout.addWidget(clear)

    def _choose(self) -> None:
        """Open a file dialog and update the project path."""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Choose default project",
            str(self._app.project_dir()),
            "Linework (*.linework)",
        )
        if not path:
            return
        self._set_path(path)

    def _clear(self) -> None:
        """Clear the current project path."""
        self._set_path("")

    def _set_path(self, path: str) -> None:
        """Set the project path and emit the change signal.

        Args;
            path: The new path.
        """
        self._path = str(path or "")
        self._edit.setText(self._path)
        self.changed.emit(self._path)

    def value(self) -> str:
        """Return the selected project path.

        Returns;
            The selected path.
        """
        return self._path

    def set_value(self, path: str) -> None:
        """Set the project path from external values.

        Args;
            path: The new path.
        """
        self._set_path(path)


class QtSettingsDialog(QtWidgets.QDialog):
    """Settings dialog with tabbed sections."""

    def __init__(
        self,
        app: QtApp,
        schema: list[dict[str, Any]],
        values: dict[str, Any] | None,
        *,
        default_values: dict[str, Any] | None = None,
        on_apply: Callable[[dict[str, Any]], bool | None] | None = None,
        on_save: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None,
    ) -> None:
        """Create the settings dialog.

        Args;
            app: The parent Qt app.
            schema: The settings schema.
            values: Initial values for the settings.
            default_values: Optional default values for highlighting changes.
            on_apply: Optional callback for applying changes.
            on_save: Optional callback for saving defaults.
        """
        super().__init__(app)
        self.app = app
        self.schema = list(schema)
        self.values = dict(values or {})
        self._default_values = dict(default_values or {})
        self._on_apply = on_apply
        self._on_save = on_save
        self._widgets: dict[str, QtWidgets.QWidget] = {}
        self._labels: dict[str, QtWidgets.QLabel] = {}
        self._info_labels: list[QtWidgets.QLabel] = []
        self._icon_rows: dict[str, tuple[QtWidgets.QLabel, QtWidgets.QWidget]] = {}
        self._icon_kind_combo: QtWidgets.QComboBox | None = None
        self._multiple_of: list[tuple[str, str]] = []
        self._desktop_button: QtWidgets.QPushButton | None = None

        self.setWindowTitle("Settings")
        self._build()
        hint = self.sizeHint()
        self.resize(int(hint.width() * 1.1), int(hint.height() * 1.2))

    def _build(self) -> None:
        """Build the dialog layout and controls."""
        layout = QtWidgets.QVBoxLayout(self)
        tabs = QtWidgets.QTabWidget(self)
        layout.addWidget(tabs)

        sections: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
        for fld in self.schema:
            section = str(fld.get("section", "General"))
            sections.setdefault(section, []).append(fld)

        for title, fields in sections.items():
            tab = QtWidgets.QWidget()
            form = QtWidgets.QFormLayout(tab)
            form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

            for fld in fields:
                name = str(fld.get("name", ""))
                if not name:
                    continue
                kind = str(fld.get("kind", "str")).lower()
                label = QtWidgets.QLabel(str(fld.get("label", name)))
                widget = self._build_widget(fld, self.values.get(name))
                form.addRow(label, widget)
                self._labels[name] = label
                self._widgets[name] = widget
                self._wire_default_marker(name, widget, kind)
                multiple_of = str(fld.get("multiple_of", "")).strip()
                if multiple_of:
                    self._multiple_of.append((name, multiple_of))
                if name in ("default_icon_builtin", "default_icon_picture"):
                    self._icon_rows[name] = (label, widget)
            if title == "General":
                settings_label = QtWidgets.QLabel("Settings file")
                self._info_labels.append(settings_label)
                settings_button = QtWidgets.QPushButton("Open settings")
                settings_button.setToolTip(str(default_settings_path()))
                settings_button.clicked.connect(self._open_settings_file)
                form.addRow(settings_label, settings_button)
                install_label = QtWidgets.QLabel("Desktop integration")
                self._info_labels.append(install_label)
                self._desktop_button = QtWidgets.QPushButton()
                self._desktop_button.clicked.connect(self._toggle_desktop_entry)
                form.addRow(install_label, self._desktop_button)
                self._sync_desktop_button()
            tabs.addTab(tab, title)

        info_tab = QtWidgets.QWidget()
        info_layout = QtWidgets.QVBoxLayout(info_tab)
        info_form = QtWidgets.QFormLayout()
        info_form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        info_form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        params = self.app.params
        line_count = len(params.lines)
        label_count = len(params.labels)
        icon_count = len(params.icons)
        total_count = line_count + label_count + icon_count

        def _info_row(label_text: str, value_widget: QtWidgets.QWidget) -> None:
            label = QtWidgets.QLabel(label_text)
            self._info_labels.append(label)
            info_form.addRow(label, value_widget)

        _info_row(
            "Project",
            QtWidgets.QLabel(self.app.project_display_path()),
        )
        _info_row(
            "Unsaved changes",
            QtWidgets.QLabel("Yes" if self.app.dirty else "No"),
        )
        _info_row(
            "Canvas size",
            QtWidgets.QLabel(f"{params.width} x {params.height}"),
        )
        grid_txt = f"{params.grid_size}px (step {params.grid_step}){' | visible' if params.grid_visible else ''}"
        _info_row(
            "Grid",
            QtWidgets.QLabel(grid_txt),
        )
        _info_row(
            "Lines",
            QtWidgets.QLabel(str(line_count)),
        )
        _info_row(
            "Labels",
            QtWidgets.QLabel(str(label_count)),
        )
        _info_row(
            "Icons",
            QtWidgets.QLabel(str(icon_count)),
        )
        _info_row(
            "Total items",
            QtWidgets.QLabel(str(total_count)),
        )
        _info_row(
            "App version",
            QtWidgets.QLabel(get_app_version()),
        )
        _info_row(
            "Qt version",
            QtWidgets.QLabel(QtCore.qVersion()),
        )
        _info_row(
            "PySide6",
            QtWidgets.QLabel(getattr(PySide6, "__version__", "unknown")),
        )
        _info_row(
            "Python",
            QtWidgets.QLabel(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"),
        )
        info_layout.addLayout(info_form)
        info_layout.addStretch(1)
        tabs.addTab(info_tab, "Info")

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Save
            | QtWidgets.QDialogButtonBox.StandardButton.Reset
            | QtWidgets.QDialogButtonBox.StandardButton.Apply
            | QtWidgets.QDialogButtonBox.StandardButton.Close
        )
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Save).clicked.connect(self._save)
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Reset).clicked.connect(self._reset_to_defaults)
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Apply).clicked.connect(self._apply)
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Close).clicked.connect(self.reject)
        layout.addWidget(buttons)

        self._bind_multiple_of()
        self._sync_icon_kind_visibility()
        self._sync_default_diff_markers()
        self._lock_label_widths()

    @staticmethod
    def _snap_to_multiple(
        value: int,
        step: int,
        *,
        allow_zero: bool = False,
        min_value: int | None = None,
        max_value: int | None = None,
    ) -> int:
        """Snap a value to the nearest allowed multiple.

        Args;
            value: The input value.
            step: The step size to snap to.
            allow_zero: Whether zero is a valid result.
            min_value: Optional minimum bound.
            max_value: Optional maximum bound.

        Returns;
            The snapped value.
        """
        step_value = max(1, int(step))
        if allow_zero and value <= 0:
            return 0
        snapped = int((value + step_value / 2) // step_value) * step_value
        if snapped <= 0:
            snapped = step_value
        if min_value is not None and snapped < min_value:
            snapped = ((min_value + step_value - 1) // step_value) * step_value
        if max_value is not None and snapped > max_value:
            snapped = (max_value // step_value) * step_value
            if snapped <= 0:
                snapped = step_value
        return snapped

    def _bind_multiple_of(self) -> None:
        """Wire up fields that must track a multiple-of constraint."""
        for name, target in self._multiple_of:
            widget = self._widgets.get(name)
            target_widget = self._widgets.get(target)
            if not isinstance(widget, QtWidgets.QSpinBox) or not isinstance(target_widget, QtWidgets.QSpinBox):
                continue

            def _sync(
                _value: int | None = None,
                *,
                w: QtWidgets.QSpinBox = widget,
                t: QtWidgets.QSpinBox = target_widget,
            ) -> None:
                step = max(1, int(t.value()))
                w.setSingleStep(step)
                snapped = self._snap_to_multiple(
                    int(w.value()),
                    step,
                    allow_zero=w.minimum() <= 0,
                    min_value=w.minimum(),
                    max_value=w.maximum(),
                )
                if snapped != w.value():
                    w.setValue(snapped)

            _sync()
            widget.valueChanged.connect(_sync)
            target_widget.valueChanged.connect(_sync)

    def _build_widget(self, fld: dict[str, Any], init_val: Any) -> QtWidgets.QWidget:
        """Create a widget for a schema field.

        Args;
            fld: The schema field data.
            init_val: The initial value.

        Returns;
            The configured widget.
        """
        kind = str(fld.get("kind", "str")).lower()
        name = str(fld.get("name", ""))

        if kind == "bool":
            chk = QtWidgets.QCheckBox()
            chk.setChecked(bool(init_val))
            return chk

        if kind == "int":
            spin = QtWidgets.QSpinBox()
            lo = int(fld.get("min", -1000000))
            hi = int(fld.get("max", 1000000))
            spin.setRange(lo, hi)
            spin.setKeyboardTracking(False)
            if init_val is not None:
                spin.setValue(int(init_val))
            return spin

        if kind == "float":
            spin = QtWidgets.QDoubleSpinBox()
            lo = float(fld.get("min", -1000000.0))
            hi = float(fld.get("max", 1000000.0))
            spin.setRange(lo, hi)
            spin.setKeyboardTracking(False)
            if init_val is not None:
                spin.setValue(float(init_val))
            return spin

        if kind == "choice":
            combo = QtWidgets.QComboBox()
            choices = fld.get("choices") or []
            for choice in choices:
                combo.addItem(str(choice))
            if init_val is not None:
                idx = combo.findText(str(init_val))
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            if name == "default_icon_kind":
                self._icon_kind_combo = combo
                combo.currentIndexChanged.connect(self._sync_icon_kind_visibility)
            return combo

        if kind == "colour":
            pal = ColourPaletteButton(
                self,
                Colours.list(min_alpha=25),
                selected=str(init_val) if init_val is not None else None,
                on_select=self._on_colour_selected,
                custom=self.app.params.custom_palette,
                on_update_custom=self._on_update_custom_palette,
            )
            return pal

        if kind == "icon_builtin":
            combo = QtWidgets.QComboBox()
            for name in IconName:
                combo.addItem(name.value)
            if init_val is not None:
                idx = combo.findText(str(init_val))
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            return combo

        if kind == "icon_picture":
            picker = _PicturePicker(self.app, init_val)
            return picker

        if kind == "project_path":
            picker = _ProjectPicker(self.app, init_val)
            return picker

        edit = QtWidgets.QLineEdit()
        edit.setText("" if init_val is None else str(init_val))
        return edit

    def _sync_icon_kind_visibility(self) -> None:
        """Show or hide icon rows based on the current icon kind."""
        if self._icon_kind_combo is None:
            return
        kind = str(self._icon_kind_combo.currentText()).lower()
        for name in ("default_icon_builtin", "default_icon_picture"):
            label, widget = self._icon_rows.get(name, (None, None))
            if label is None or widget is None:
                continue
            should_show = (name == "default_icon_builtin" and kind == "builtin") or (
                name == "default_icon_picture" and kind == "picture"
            )
            label.setVisible(should_show)
            widget.setVisible(should_show)
        self._sync_default_diff_markers()

    def _lock_label_widths(self) -> None:
        """Set uniform label widths for consistent alignment."""
        labels = list(self._labels.values()) + self._info_labels
        if not labels:
            return
        max_width = 0
        padding_width = 0
        for label in labels:
            text = label.text()
            font = label.font()
            metrics = QtGui.QFontMetrics(font)
            max_width = max(max_width, metrics.horizontalAdvance(text))
            italic_font = QtGui.QFont(font)
            italic_font.setItalic(True)
            italic_metrics = QtGui.QFontMetrics(italic_font)
            max_width = max(max_width, italic_metrics.horizontalAdvance(text))
            padding_width = max(
                padding_width,
                metrics.horizontalAdvance("  "),
                italic_metrics.horizontalAdvance("  "),
            )
        max_width += padding_width
        for label in labels:
            label.setMinimumWidth(max_width)

    def _normalize_default_value(self, value: Any) -> Any:
        """Normalise values for default comparisons.

        Args;
            value: The input value.

        Returns;
            The normalised value.
        """
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned.startswith("#"):
                return cleaned.lower()
            return cleaned
        return value

    def _sync_default_diff_markers(self) -> None:
        """Update label styling for values that differ from defaults."""
        if not self._default_values:
            return
        current = self._collect_values()
        for name, label in self._labels.items():
            if name not in self._default_values:
                continue
            default_value = self._normalize_default_value(self._default_values.get(name))
            current_value = self._normalize_default_value(current.get(name))
            is_default = current_value == default_value
            font = label.font()
            if font.italic() == (not is_default):
                continue
            font.setItalic(not is_default)
            label.setFont(font)

    def _wire_default_marker(self, name: str, widget: QtWidgets.QWidget, kind: str) -> None:
        """Connect widget changes to the default-diff marker.

        Args;
            name: The field name.
            widget: The widget to watch.
            kind: The schema field kind.
        """
        if name not in self._default_values:
            return

        def _sync(_value: object | None = None) -> None:
            self._sync_default_diff_markers()

        if kind == "bool" and isinstance(widget, QtWidgets.QCheckBox):
            widget.toggled.connect(_sync)
        elif kind == "int" and isinstance(widget, QtWidgets.QSpinBox):
            widget.valueChanged.connect(_sync)
        elif kind == "float" and isinstance(widget, QtWidgets.QDoubleSpinBox):
            widget.valueChanged.connect(_sync)
        elif kind in ("choice", "icon_builtin") and isinstance(widget, QtWidgets.QComboBox):
            widget.currentIndexChanged.connect(_sync)
        elif kind == "icon_picture" and isinstance(widget, _PicturePicker):
            widget.changed.connect(_sync)
        elif kind == "project_path" and isinstance(widget, _ProjectPicker):
            widget.changed.connect(_sync)
        elif isinstance(widget, QtWidgets.QLineEdit):
            widget.textChanged.connect(_sync)

    def _on_colour_selected(self, _hex: str) -> None:
        """Sync default markers after a colour selection."""
        self._sync_default_diff_markers()

    def _open_settings_file(self) -> None:
        """Open the settings file or its folder."""
        path = default_settings_path()
        if not (QtGui.QGuiApplication.keyboardModifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier):
            file_url = QtCore.QUrl.fromLocalFile(str(path))
            if QtGui.QDesktopServices.openUrl(file_url):
                return
        folder_url = QtCore.QUrl.fromLocalFile(str(path.parent))
        if QtGui.QDesktopServices.openUrl(folder_url):
            return
        QtWidgets.QMessageBox.information(
            self,
            "Settings file",
            f"Settings file is located at:\n{path}",
        )

    def _toggle_desktop_entry(self) -> None:
        """Install or uninstall desktop integration."""
        if not sys.platform.startswith("linux"):
            QtWidgets.QMessageBox.information(
                self,
                "Desktop integration",
                "Desktop integration is only supported on Linux for now.",
            )
            return
        if self._is_desktop_installed():
            self._uninstall_desktop_entry()
        else:
            self._install_desktop_entry()
        self._sync_desktop_button()

    def _install_desktop_entry(self) -> None:
        """Install the desktop entry and migrate settings."""
        if not sys.platform.startswith("linux"):
            QtWidgets.QMessageBox.information(
                self,
                "Desktop install",
                "Desktop install is only supported on Linux for now.",
            )
            return
        try:
            desktop_path = self._write_linux_desktop_entry()
            settings_path = self._migrate_settings_to_standard()
            mark_installed()
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Desktop install failed", str(exc))
            return
        self._sync_storage_mode_widget()
        QtWidgets.QMessageBox.information(
            self,
            "Desktop install",
            f"Installed desktop entry:\n{desktop_path}\n\nSettings path:\n{settings_path}",
        )

    def _uninstall_desktop_entry(self) -> None:
        """Remove the desktop entry and migrate settings."""
        if not sys.platform.startswith("linux"):
            QtWidgets.QMessageBox.information(
                self,
                "Desktop integration",
                "Desktop integration is only supported on Linux for now.",
            )
            return
        desktop_path = self._desktop_entry_path()
        icon_paths = self._installed_icon_paths()
        removed = []
        if desktop_path.exists():
            try:
                desktop_path.unlink()
                removed.append(str(desktop_path))
            except OSError:
                # Best-effort cleanup; ignore locked/permission errors.
                pass
        for icon_path in icon_paths:
            if icon_path.exists():
                try:
                    icon_path.unlink()
                    removed.append(str(icon_path))
                except OSError:
                    # Best-effort cleanup; ignore locked/permission errors.
                    pass
        portable_path = self._migrate_settings_to_portable()
        clear_installed_marker()
        self._sync_storage_mode_widget()
        message = "Desktop entry removed."
        if removed:
            message = "Removed:\n" + "\n".join(removed)
        if portable_path is None:
            message += "\n\nPortable mode unavailable; settings remain in the standard location."
        else:
            message += f"\n\nSettings path:\n{portable_path}"
        QtWidgets.QMessageBox.information(self, "Desktop uninstall", message)

    def _migrate_settings_to_standard(self) -> Path:
        """Copy settings into the standard storage location.

        Returns;
            The standard settings path.
        """
        source = default_settings_path()
        target = standard_settings_path()
        if source.resolve() == target.resolve():
            return target
        if source.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        return target

    def _migrate_settings_to_portable(self) -> Path | None:
        """Copy settings into the portable storage location.

        Returns;
            The portable settings path, or None when unavailable.
        """
        if not can_use_portable():
            return None
        source = standard_settings_path()
        if not source.exists():
            source = default_settings_path()
        target = portable_settings_path()
        try:
            if source.resolve() == target.resolve():
                return target
        except OSError:
            if str(source) == str(target):
                return target
        if source.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        return target

    def _write_linux_desktop_entry(self) -> Path:
        """Write a Linux desktop entry file.

        Returns;
            The desktop entry path.
        """
        data_home = self._xdg_data_home()
        applications_dir = data_home / "applications"
        applications_dir.mkdir(parents=True, exist_ok=True)
        icon_name = ""
        icon_source = self._find_app_icon()
        if icon_source is not None:
            icon_name = self._install_icon(icon_source, data_home)
        lines = [
            "[Desktop Entry]",
            "Type=Application",
            "Name=Linework",
            f"Exec={self._desktop_exec()}",
            "Terminal=false",
            "Categories=Graphics;",
        ]
        if icon_name:
            lines.append(f"Icon={icon_name}")
        desktop_path = applications_dir / "linework.desktop"
        desktop_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return desktop_path

    def _desktop_entry_path(self) -> Path:
        """Return the desktop entry path.

        Returns;
            The desktop entry path.
        """
        return self._xdg_data_home() / "applications" / "linework.desktop"

    def _installed_icon_paths(self) -> list[Path]:
        """Return the installed icon paths.

        Returns;
            The icon paths.
        """
        data_home = self._xdg_data_home()
        return [
            data_home / "icons" / "hicolor" / "scalable" / "apps" / "linework.svg",
            data_home / "icons" / "hicolor" / "256x256" / "apps" / "linework.png",
        ]

    def _is_desktop_installed(self) -> bool:
        """Return True if desktop integration is installed.

        Returns;
            True when desktop integration is installed.
        """
        if installed_marker_path().exists():
            return True
        return self._desktop_entry_path().exists()

    def _sync_storage_mode_widget(self) -> None:
        """Sync the storage mode combo to the current mode."""
        storage_widget = self._widgets.get("storage_mode")
        if not isinstance(storage_widget, QtWidgets.QComboBox):
            return
        target_text = "Portable" if current_storage_mode() == "portable" else "Standard"
        idx = storage_widget.findText(target_text)
        if idx >= 0:
            storage_widget.setCurrentIndex(idx)

    def _sync_desktop_button(self) -> None:
        """Update the desktop integration button state."""
        if self._desktop_button is None:
            return
        if not sys.platform.startswith("linux"):
            self._desktop_button.setText("Install Desktop")
            self._desktop_button.setEnabled(False)
            self._desktop_button.setToolTip("Desktop integration is only supported on Linux for now.")
            return
        if self._is_desktop_installed():
            self._desktop_button.setText("Uninstall Desktop")
            self._desktop_button.setToolTip("Remove the desktop entry and switch to portable mode.")
        else:
            self._desktop_button.setText("Install Desktop")
            self._desktop_button.setToolTip("Install a desktop entry and use standard settings storage.")

    @staticmethod
    def _desktop_exec() -> str:
        """Build the Exec value for the desktop entry.

        Returns;
            The Exec string.
        """
        if getattr(sys, "frozen", False):
            exe = Path(sys.executable).resolve()
            return f'"{exe}" %U'
        script = Path(sys.argv[0]).resolve()
        python = Path(sys.executable).resolve()
        return f'"{python}" "{script}" %U'

    @staticmethod
    def _xdg_data_home() -> Path:
        """Return the XDG data home path.

        Returns;
            The XDG data home path.
        """
        raw = os.environ.get("XDG_DATA_HOME", "").strip()
        if raw:
            return Path(raw).expanduser()
        return Path.home() / ".local" / "share"

    @staticmethod
    def _runtime_dir() -> Path:
        """Return the runtime directory for portable assets.

        Returns;
            The runtime directory.
        """
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent
        if sys.argv and sys.argv[0]:
            return Path(sys.argv[0]).resolve().parent
        return Path.cwd()

    def _find_app_icon(self) -> Path | None:
        """Find the application icon in the runtime tree.

        Returns;
            The icon path, or None when missing.
        """
        root = self._runtime_dir()
        candidates = [
            root / "assets" / "app" / "linework.svg",
            root / "assets" / "app" / "linework.png",
        ]
        for path in candidates:
            if path.exists():
                return path
        return None

    @staticmethod
    def _install_icon(source: Path, data_home: Path) -> str:
        """Install an icon into the data directory.

        Args;
            source: The source icon path.
            data_home: The target data directory.

        Returns;
            The icon name to reference.
        """
        if source.suffix.lower() == ".svg":
            target_dir = data_home / "icons" / "hicolor" / "scalable" / "apps"
            target_name = "linework.svg"
        else:
            target_dir = data_home / "icons" / "hicolor" / "256x256" / "apps"
            target_name = "linework.png"
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target_dir / target_name)
        return "linework"

    def _collect_values(self) -> dict[str, Any]:
        """Collect the current widget values.

        Returns;
            The collected values.
        """
        data: dict[str, Any] = {}
        for fld in self.schema:
            name = str(fld.get("name", ""))
            if not name:
                continue
            kind = str(fld.get("kind", "str")).lower()
            widget = self._widgets.get(name)
            if widget is None:
                continue
            if kind == "bool" and isinstance(widget, QtWidgets.QCheckBox):
                data[name] = bool(widget.isChecked())
            elif kind == "int" and isinstance(widget, QtWidgets.QSpinBox):
                widget.interpretText()
                data[name] = int(widget.value())
            elif kind == "float" and isinstance(widget, QtWidgets.QDoubleSpinBox):
                widget.interpretText()
                data[name] = float(widget.value())
            elif kind in ("choice", "icon_builtin") and isinstance(widget, QtWidgets.QComboBox):
                data[name] = str(widget.currentText())
            elif kind == "icon_picture" and isinstance(widget, _PicturePicker):
                data[name] = widget.value()
            elif kind == "project_path" and isinstance(widget, _ProjectPicker):
                data[name] = widget.value()
            elif kind == "colour" and isinstance(widget, ColourPaletteButton):
                data[name] = widget.selected_hex()
            elif isinstance(widget, QtWidgets.QLineEdit):
                data[name] = widget.text().strip()
        return data

    def _apply(self) -> None:
        """Apply the current values via the callback."""
        if not self._on_apply:
            return
        data = self._collect_values()
        ok = self._on_apply(data)
        if ok is False:
            return

    def current_values(self) -> dict[str, Any]:
        """Return the current dialog values.

        Returns;
            The current values.
        """
        return self._collect_values()

    def _apply_values(self, values: dict[str, Any]) -> None:
        """Apply values to the dialog widgets.

        Args;
            values: The values to apply.
        """
        for fld in self.schema:
            name = str(fld.get("name", ""))
            if not name or name not in values:
                continue
            kind = str(fld.get("kind", "str")).lower()
            widget = self._widgets.get(name)
            if widget is None:
                continue
            value = values.get(name)
            was_blocked = widget.blockSignals(True)
            try:
                if kind == "bool" and isinstance(widget, QtWidgets.QCheckBox):
                    widget.setChecked(bool(value))
                elif kind == "int" and isinstance(widget, QtWidgets.QSpinBox) and value is not None:
                    widget.setValue(int(value))
                elif kind == "float" and isinstance(widget, QtWidgets.QDoubleSpinBox) and value is not None:
                    widget.setValue(float(value))
                elif kind in ("choice", "icon_builtin") and isinstance(widget, QtWidgets.QComboBox):
                    idx = widget.findText(str(value))
                    if idx >= 0:
                        widget.setCurrentIndex(idx)
                elif kind == "icon_picture" and isinstance(widget, _PicturePicker):
                    widget.set_value(str(value or ""))
                elif kind == "project_path" and isinstance(widget, _ProjectPicker):
                    widget.set_value(str(value or ""))
                elif kind == "colour" and isinstance(widget, ColourPaletteButton):
                    if value:
                        widget.set_selected(str(value))
                elif isinstance(widget, QtWidgets.QLineEdit):
                    widget.setText("" if value is None else str(value))
            finally:
                widget.blockSignals(was_blocked)

    def _reset_to_defaults(self) -> None:
        """Reset the dialog to default values."""
        if not self._default_values:
            return
        self._apply_values(self._default_values)
        self._sync_icon_kind_visibility()
        self._sync_default_diff_markers()

    def _save(self) -> None:
        """Save defaults via the callback."""
        if not self._on_save:
            return
        data = self._collect_values()
        defaults = self._on_save(data)
        if defaults is not None:
            self._default_values = dict(defaults)
            self._sync_default_diff_markers()

    def _on_update_custom_palette(self, idx: int, col: Any) -> None:
        """Update a custom palette entry.

        Args;
            idx: The palette index.
            col: The new colour value.
        """
        if idx < 0:
            return
        if idx >= len(self.app.params.custom_palette):
            self.app.params.custom_palette.extend([None] * (idx - len(self.app.params.custom_palette) + 1))
        self.app.params.custom_palette[idx] = col
        self.app.mark_dirty()

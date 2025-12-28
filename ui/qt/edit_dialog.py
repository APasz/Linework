"""Qt edit dialog helpers for Linework."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6 import QtCore, QtGui, QtWidgets

from models.assets import IconName
from models.styling import Colours, LineStyle
from ui.qt.line_style_icons import line_style_icon
from ui.qt.palette import ColourPaletteButton

if TYPE_CHECKING:
    from qt.app import QtApp


def _coerce_schema_item(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise TypeError(f"Schema entries must be dict, got {type(item)}")
    d = dict(item)
    k = d.get("kind", "str")
    d["kind"] = str(k).lower()
    d.setdefault("label", d.get("label", d.get("name")))
    return d


def _resolve_choices_seq(val: Any) -> list[str]:
    if val is None:
        return []
    if callable(val):
        val = val()
    if isinstance(val, (list, tuple)):
        return [str(x) for x in val]
    raise TypeError("choices must be Sequence[str] or a callable returning Sequence[str]")


def _resolve_choices_map(val: Any) -> dict[str, Any]:
    if val is None:
        return {}
    if callable(val):
        val = val()
    if isinstance(val, dict):
        return dict(val)
    raise TypeError("choices must be Mapping[str, Any] or a callable returning Mapping[str, Any]")


class _PicturePicker(QtWidgets.QWidget):
    def __init__(self, app: QtApp, initial: Any) -> None:
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
        if not path:
            return ""
        return Path(path).name

    def _choose(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Choose picture icon",
            str(self._app.project_dir()),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp *.svg)",
        )
        if not path:
            return
        try:
            imported = self._app.asset_lib.import_files([Path(path)])
            if imported:
                path = str(imported[0])
        except OSError:
            # Best-effort import; fall back to the raw file path.
            pass
        self._path = path
        self._edit.setText(self._display_name(self._path))

    def value(self) -> str:
        return self._path


class QtGenericEditDialog(QtWidgets.QDialog):
    """Schema-driven edit dialog with typed field support."""

    def __init__(
        self,
        app: QtApp,
        title: str,
        schema: list[dict[str, Any]],
        values: dict[str, Any] | None,
    ) -> None:
        """Create the edit dialog.

        Args;
            app: The parent Qt app.
            title: Dialog title.
            schema: Field schema for the dialog.
            values: Initial field values.
        """
        super().__init__(app)
        self.app = app
        self.schema = [_coerce_schema_item(s) for s in list(schema)]
        self.values = dict(values or {})
        self.widgets: dict[str, QtWidgets.QWidget] = {}
        self._meta: dict[str, dict[str, Any]] = {}
        self.result_data: dict[str, Any] | None = None

        self.setWindowTitle(title)
        self._build()

    def _build(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        for fld in self.schema:
            name = fld["name"]
            label = fld.get("label", name)
            widget = self._build_widget(fld, self.values.get(name))
            form.addRow(label, widget)

        layout.addLayout(form)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self) -> None:
        """Validate input and accept the dialog."""
        out: dict[str, Any] = {}
        try:
            for fld in self.schema:
                name = fld["name"]
                kind = str(fld.get("kind", "str")).lower()
                raw = self._read_value(name, kind, fld)
                if kind in ("int", "float"):
                    if "min" in fld and raw < fld["min"]:
                        raise ValueError(f"{fld.get('label', name)} must be >= {fld['min']}")
                    if "max" in fld and raw > fld["max"]:
                        raise ValueError(f"{fld.get('label', name)} must be <= {fld['max']}")
                out[name] = raw
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Invalid input", str(exc))
            return
        self.result_data = out
        super().accept()

    # ---- builders ----
    def _build_widget(self, fld: dict[str, Any], init_val: Any) -> QtWidgets.QWidget:
        kind = str(fld.get("kind", "str")).lower()
        name = fld["name"]
        self._meta[name] = {}

        builders: dict[str, Callable[[dict[str, Any], Any], QtWidgets.QWidget]] = {
            "bool": self._build_bool,
            "int": self._build_int,
            "float": self._build_float,
            "str": self._build_str,
            "text": self._build_text,
            "choice": self._build_choice,
            "choice_dict": self._build_choice_dict,
            "colour": self._build_colour,
            "icon_builtin": self._build_icon_builtin,
            "icon_picture": self._build_icon_picture,
        }
        widget = builders.get(kind, self._build_str)(fld, init_val)
        self.widgets[name] = widget
        return widget

    def _build_bool(self, fld: dict[str, Any], init_val: Any) -> QtWidgets.QWidget:
        chk = QtWidgets.QCheckBox()
        chk.setChecked(bool(init_val))
        return chk

    def _build_int(self, fld: dict[str, Any], init_val: Any) -> QtWidgets.QWidget:
        spin = QtWidgets.QSpinBox()
        lo = int(fld.get("min", -1000000))
        hi = int(fld.get("max", 1000000))
        spin.setRange(lo, hi)
        if init_val is not None:
            spin.setValue(int(init_val))
        return spin

    def _build_float(self, fld: dict[str, Any], init_val: Any) -> QtWidgets.QWidget:
        spin = QtWidgets.QDoubleSpinBox()
        lo = float(fld.get("min", -1000000.0))
        hi = float(fld.get("max", 1000000.0))
        spin.setDecimals(3)
        spin.setRange(lo, hi)
        if init_val is not None:
            spin.setValue(float(init_val))
        return spin

    def _build_str(self, _fld: dict[str, Any], init_val: Any) -> QtWidgets.QWidget:
        edit = QtWidgets.QLineEdit()
        edit.setText("" if init_val is None else str(init_val))
        return edit

    def _build_text(self, _fld: dict[str, Any], init_val: Any) -> QtWidgets.QWidget:
        edit = QtWidgets.QPlainTextEdit()
        if init_val:
            edit.setPlainText(str(init_val))
        edit.setFixedHeight(80)
        return edit

    def _build_choice(self, fld: dict[str, Any], init_val: Any) -> QtWidgets.QWidget:
        combo = QtWidgets.QComboBox()
        keys = _resolve_choices_seq(fld.get("choices"))
        if fld.get("sort", True):
            keys = sorted(keys, key=str.casefold)
        line_values = {s.value for s in LineStyle}
        name = str(fld.get("name", ""))
        use_line_icons = bool(keys) and name in {"style", "line_style"} and set(keys).issubset(line_values)
        if use_line_icons:
            icon_size = QtCore.QSize(60, 12)
            combo.setIconSize(icon_size)
            combo.setMinimumContentsLength(10)
            combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            colour = combo.palette().color(QtGui.QPalette.ColorRole.Text)
        for key in keys:
            label = str(key)
            if use_line_icons:
                try:
                    style = LineStyle(label)
                except ValueError:
                    combo.addItem(label)
                else:
                    combo.addItem(line_style_icon(style, icon_size, colour), label)
            else:
                combo.addItem(label)
        init_key = str(init_val) if init_val is not None else (keys[0] if keys else "")
        idx = combo.findText(init_key)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        if use_line_icons:
            combo.view().setMinimumWidth(combo.sizeHint().width())
        return combo

    def _build_choice_dict(self, fld: dict[str, Any], init_val: Any) -> QtWidgets.QWidget:
        combo = QtWidgets.QComboBox()
        mapping = _resolve_choices_map(fld.get("choices"))
        keys = list(mapping.keys())
        if fld.get("sort", True):
            keys = sorted(keys, key=str.casefold)
        for key in keys:
            combo.addItem(str(key))
        init_key = keys[0] if keys else ""
        for k, v in mapping.items():
            if v == init_val or (isinstance(v, Path) and str(v) == str(init_val)):
                init_key = k
                break
        idx = combo.findText(init_key)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        self._meta[fld["name"]]["map"] = mapping
        return combo

    def _build_colour(self, _fld: dict[str, Any], init_val: Any) -> QtWidgets.QWidget:
        pal = ColourPaletteButton(
            self,
            Colours.list(min_alpha=25),
            selected=str(init_val) if init_val is not None else None,
            custom=self.app.params.custom_palette,
            on_update_custom=self._on_update_custom_palette,
        )
        return pal

    def _build_icon_builtin(self, _fld: dict[str, Any], init_val: Any) -> QtWidgets.QWidget:
        combo = QtWidgets.QComboBox()
        names = [n.value for n in IconName]
        for name in names:
            combo.addItem(name)
        init_key = str(init_val) if init_val is not None else (names[0] if names else "")
        idx = combo.findText(init_key)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        return combo

    def _build_icon_picture(self, _fld: dict[str, Any], init_val: Any) -> QtWidgets.QWidget:
        return _PicturePicker(self.app, init_val)

    # ---- readers ----
    def _read_value(self, name: str, kind: str, fld: dict[str, Any]) -> Any:
        widget = self.widgets.get(name)
        if kind == "bool" and isinstance(widget, QtWidgets.QCheckBox):
            return bool(widget.isChecked())
        if kind == "text" and isinstance(widget, QtWidgets.QPlainTextEdit):
            return widget.toPlainText()
        if kind == "choice" and isinstance(widget, QtWidgets.QComboBox):
            return str(widget.currentText()).strip()
        if kind == "choice_dict" and isinstance(widget, QtWidgets.QComboBox):
            key = str(widget.currentText())
            mapping = self._meta.get(name, {}).get("map", {})
            if key not in mapping:
                raise ValueError(f"{fld.get('label', name)}: unknown option '{key}'")
            return mapping[key]
        if kind == "int" and isinstance(widget, QtWidgets.QSpinBox):
            return int(widget.value())
        if kind == "float" and isinstance(widget, QtWidgets.QDoubleSpinBox):
            return float(widget.value())
        if kind == "colour" and isinstance(widget, ColourPaletteButton):
            return widget.selected_hex()
        if kind == "icon_builtin" and isinstance(widget, QtWidgets.QComboBox):
            return str(widget.currentText())
        if kind == "icon_picture" and isinstance(widget, _PicturePicker):
            return widget.value()
        if isinstance(widget, QtWidgets.QLineEdit):
            return str(widget.text()).strip()
        return ""

    def _on_update_custom_palette(self, idx: int, col: Any) -> None:
        self.app.update_custom_palette(idx, col)

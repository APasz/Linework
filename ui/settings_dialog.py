"""Settings dialog with diff tracking and validation."""

from __future__ import annotations

import sys
import tkinter as tk
import tkinter.font as tkfont
from collections import OrderedDict
from collections.abc import Callable, Sequence
from pathlib import Path
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING, Any

from models.geo import Icon_Type
from models.version import get_app_version
from ui.edit_dialog import GenericEditDialog

if TYPE_CHECKING:
    from controllers.app import App


class SettingsDialog(GenericEditDialog):
    """Settings dialog with save/apply/reset helpers."""

    def __init__(
        self,
        app: App,
        title: str,
        schema: Sequence[dict[str, Any]],
        values: dict[str, Any] | None,
        *,
        on_save: Callable[[dict[str, Any]], bool | None],
        on_apply: Callable[[dict[str, Any]], bool | None] | None = None,
        on_reset: Callable[[], dict[str, Any] | None] | None = None,
        saved_values: dict[str, Any] | None = None,
    ) -> None:
        """Create a settings dialog.

        Args;
            app: The application instance.
            title: Dialog title.
            schema: Settings schema fields.
            values: Initial values.
            on_save: Callback for saving defaults.
            on_apply: Callback for applying changes.
            on_reset: Callback for reset.
            saved_values: Previously saved values for diff tracking.
        """
        self.apply_now = False
        self._on_save_cb = on_save
        self._on_apply_cb = on_apply
        self._on_reset_cb = on_reset
        self._saved_values = dict(saved_values or {})
        self._field_labels: dict[str, ttk.Label] = {}
        self._label_fonts: dict[ttk.Label, tuple[tkfont.Font, tkfont.Font]] = {}
        self._default_icon_label: ttk.Label | None = None
        self._diff_tracking_ready = False
        self._dim_widgets: dict[str, ttk.Entry] = {}
        self._num_widgets: dict[str, ttk.Entry] = {}
        self._entry_base_styles: dict[ttk.Entry, str] = {}
        self._schema_by_name: dict[str, dict] = {}
        self._multiple_of: dict[str, str] = {}
        self._multiple_bases: set[str] = set()
        self._icon_picker_widgets: dict[str, tk.Widget] = {}
        self._icon_picker_container: ttk.Frame | None = None
        self._icon_hint_popup: tk.Toplevel | None = None
        self._icon_hint_after: str | None = None
        self._icon_kind_var = None
        super().__init__(app, title, schema, values)

    def body(self, master: tk.Frame) -> tk.Widget:
        """Build the dialog body.

        Args;
            master: The parent frame.

        Returns;
            The initial focus widget.
        """
        master.grid_columnconfigure(0, weight=1)
        # header = ttk.Label(master, text="")
        # header.grid(row=0, column=0, sticky="w", padx=6, pady=(6, 6))
        # disabled for now but might wanna use later

        master.grid_rowconfigure(1, weight=1)
        notebook = ttk.Notebook(master)
        notebook.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))

        self._schema_by_name = {str(fld.get("name")): fld for fld in self.schema if fld.get("name")}
        self._multiple_of = {
            name: str(fld.get("multiple_of")) for name, fld in self._schema_by_name.items() if fld.get("multiple_of")
        }
        self._multiple_bases = {base for base in self._multiple_of.values() if base}

        sections: OrderedDict[str, list[dict]] = OrderedDict()
        for fld in self.schema:
            section = str(fld.get("section", "General"))
            sections.setdefault(section, []).append(fld)

        first_widget = None

        def _add_fields(tab: ttk.Frame, fields: list[dict[str, Any]]) -> None:
            nonlocal first_widget
            tab.grid_columnconfigure(1, weight=1)
            row = 0
            for fld in fields:
                name = str(fld.get("name", ""))
                if not name:
                    continue
                if name in ("default_icon_builtin", "default_icon_picture"):
                    if self._icon_picker_container is None:
                        label = ttk.Label(tab, text="Default icon")
                        label.grid(row=row, column=0, sticky="w", padx=6, pady=4)
                        self._default_icon_label = label
                        self._register_label(name, label)
                        self._icon_picker_container = ttk.Frame(tab)
                        self._icon_picker_container.grid(row=row, column=1, sticky="ew", padx=6, pady=4)
                        self._icon_picker_container.grid_columnconfigure(0, weight=1)
                        row += 1
                    elif self._default_icon_label is not None:
                        self._register_label(name, self._default_icon_label)
                    widget = self._build_widget(self._icon_picker_container, fld, self.values.get(name))
                    widget.grid(row=0, column=0, sticky="ew")
                    widget.grid_remove()
                    self._icon_picker_widgets[name] = widget
                    if first_widget is None:
                        first_widget = widget
                    continue
                label = fld.get("label", name)
                label_widget = ttk.Label(tab, text=label)
                label_widget.grid(row=row, column=0, sticky="w", padx=6, pady=4)
                self._register_label(name, label_widget)
                widget = self._build_widget(tab, fld, self.values.get(name))
                widget.grid(row=row, column=1, sticky="ew", padx=6, pady=4)
                if first_widget is None:
                    first_widget = widget

                kind = str(fld.get("kind", "")).lower()
                if kind == "int" and isinstance(widget, ttk.Entry):
                    self._num_widgets[name] = widget
                    self._register_entry(widget)
                if name in self._multiple_of and isinstance(widget, ttk.Entry):
                    self._dim_widgets[name] = widget
                    self._attach_dim_validation(widget)
                if name in self._multiple_bases and isinstance(widget, ttk.Entry):
                    self._attach_grid_validation(widget)
                row += 1

        for title, fields in sections.items():
            tab = ttk.Frame(notebook)
            notebook.add(tab, text=title)
            _add_fields(tab, fields)

        self._add_about_tab(notebook)

        if first_widget is None:
            first_widget = notebook
        self._setup_default_icon_picker()
        self._setup_diff_tracking()
        return first_widget

    def buttonbox(self) -> None:
        """Build the dialog button box."""
        box = ttk.Frame(self)
        btn_save = ttk.Button(box, text="Save Defaults", command=self._on_save)
        btn_apply = ttk.Button(box, text="Apply Now", command=self._on_apply)
        btn_reset = ttk.Button(box, text="Reset", command=self._on_reset)
        btn_cancel = ttk.Button(box, text="Cancel", command=self.cancel)
        btn_save.pack(side="left", padx=5, pady=5)
        btn_apply.pack(side="left", padx=5, pady=5)
        btn_reset.pack(side="left", padx=5, pady=5)
        btn_cancel.pack(side="left", padx=5, pady=5)
        box.pack(fill="x")
        self.bind("<Return>", lambda e: self._on_save())
        self.bind("<Escape>", lambda e: self.cancel())

    def _on_save(self) -> None:
        self.apply_now = False
        if not self._validate_on_submit():
            return
        self._clear_entry_styles()
        if not self.validate():
            return
        self.apply()
        ok = True
        if self._on_save_cb:
            ok = self._on_save_cb(getattr(self, "result", {})) is not False
        if ok:
            try:
                self.withdraw()
                self.update_idletasks()
            except Exception:
                pass
            self.cancel()

    def _on_apply(self) -> None:
        self.apply_now = True
        if not self._validate_on_submit():
            return
        self._clear_entry_styles()
        if not self.validate():
            return
        self.apply()
        if self._on_apply_cb:
            self._on_apply_cb(getattr(self, "result", {}))

    def _on_reset(self) -> None:
        if not self._on_reset_cb:
            return
        ok = False
        try:
            ok = messagebox.askyesno(
                "Reset Defaults",
                "Delete the saved settings file and restore original defaults?\n"
                "This only updates the fields until you apply or save.",
                parent=self,
            )
        except tk.TclError as exc:
            if "application has been destroyed" in str(exc):
                return
            raise
        if not ok:
            return
        result = self._on_reset_cb()
        if isinstance(result, dict):
            self._saved_values = dict(result)
            self._apply_values(result)

    def _register_label(self, name: str, label: ttk.Label) -> None:
        self._field_labels[name] = label
        if label not in self._label_fonts:
            base_font = tkfont.Font(root=label, font=label.cget("font") or "TkDefaultFont")
            italic_font = tkfont.Font(root=label, font=base_font)
            italic_font.configure(slant="italic")
            self._label_fonts[label] = (base_font, italic_font)

    def _setup_diff_tracking(self) -> None:
        if self._diff_tracking_ready:
            return
        self._diff_tracking_ready = True

        def _trigger(*_args: object) -> None:
            self._update_diff_markers()

        for meta in self._meta.values():
            var = meta.get("var")
            if var:
                try:
                    var.trace_add("write", _trigger)
                except Exception:
                    pass

        for widget in self.widgets.values():
            if isinstance(widget, tk.Text):
                widget.bind("<<Modified>>", lambda _e, w=widget: self._on_text_modified(w), add="+")

        self._update_diff_markers()

    def _on_text_modified(self, widget: tk.Text) -> None:
        try:
            if widget.edit_modified():
                widget.edit_modified(False)
                self._update_diff_markers()
        except Exception:
            pass

    def _update_diff_markers(self) -> None:
        label_flags: dict[ttk.Label, bool] = {}
        icon_kind = self._read_raw_value("default_icon_kind", "choice")
        if not icon_kind:
            icon_kind = Icon_Type.builtin.value

        for fld in self.schema:
            name = str(fld.get("name", ""))
            if not name:
                continue
            kind = str(fld.get("kind", "str")).lower()

            if name in ("default_icon_builtin", "default_icon_picture"):
                if icon_kind == Icon_Type.builtin.value and name == "default_icon_picture":
                    continue
                if icon_kind == Icon_Type.picture.value and name == "default_icon_builtin":
                    continue

            current = self._normalize_for_compare(kind, self._read_raw_value(name, kind))
            saved = self._normalize_for_compare(kind, self._saved_values.get(name))
            diff = current != saved

            label = self._field_labels.get(name)
            if label is not None:
                label_flags[label] = label_flags.get(label, False) or diff

        for label, (base, italic) in self._label_fonts.items():
            if label_flags.get(label, False):
                try:
                    label.configure(font=italic)
                except Exception:
                    pass
            else:
                try:
                    label.configure(font=base)
                except Exception:
                    pass

    def _read_raw_value(self, name: str, kind: str) -> Any | None:
        if kind == "text":
            widget = self.widgets.get(name)
            if isinstance(widget, tk.Text):
                return widget.get("1.0", "end-1c")
            return ""
        meta = self._meta.get(name, {})
        var = meta.get("var")
        if not var:
            return None
        try:
            return var.get()
        except Exception:
            return None

    @staticmethod
    def _normalize_for_compare(kind: str, value: Any) -> bool | int | float | str | None:
        def _as_int(val: Any) -> int | None:
            if val is None:
                return None
            try:
                return int(float(str(val).strip()))
            except Exception:
                return None

        def _as_float(val: Any) -> float | None:
            if val is None:
                return None
            try:
                return float(str(val).strip())
            except Exception:
                return None

        if kind == "bool":
            return bool(value)
        if kind == "int":
            return _as_int(value)
        if kind == "float":
            return _as_float(value)
        if value is None:
            return ""
        return str(value).strip()

    def _apply_values(self, values: dict) -> None:
        self.values = dict(values)
        for fld in self.schema:
            name = str(fld.get("name", ""))
            if not name:
                continue
            kind = str(fld.get("kind", "str")).lower()
            raw = values.get(name)
            if kind == "text":
                widget = self.widgets.get(name)
                if isinstance(widget, tk.Text):
                    widget.delete("1.0", "end")
                    widget.insert("1.0", "" if raw is None else str(raw))
                continue

            meta = self._meta.get(name, {})
            var = meta.get("var")
            if not var:
                continue

            if kind == "bool":
                var.set(bool(raw))
            else:
                var.set("" if raw is None else str(raw))

            if kind == "colour":
                widget = self.widgets.get(name)
                update = getattr(widget, "_update_highlight", None)
                if callable(update):
                    try:
                        update(str(var.get()))
                    except Exception:
                        pass

            if kind in ("icon_builtin", "icon_picture"):
                display_var = meta.get("display_var")
                if display_var is not None:
                    if kind == "icon_picture":
                        display_val = Path(str(raw)).name if raw else ""
                    else:
                        display_val = "" if raw is None else str(raw)
                    display_var.set(display_val)

        self._clear_entry_styles()
        self._update_diff_markers()

    def _setup_default_icon_picker(self) -> None:
        if not self._icon_picker_widgets:
            return
        meta = self._meta.get("default_icon_kind", {})
        var = meta.get("var")
        if not var:
            return
        self._icon_kind_var = var
        self._icon_kind_var.trace_add("write", lambda *_: self._sync_default_icon_picker())
        self._sync_default_icon_picker()

    def _sync_default_icon_picker(self) -> None:
        if not self._icon_picker_widgets:
            return
        kind = (
            str(self._icon_kind_var.get()).strip().lower()
            if self._icon_kind_var is not None
            else Icon_Type.builtin.value
        )
        show_picture = kind == Icon_Type.picture.value
        builtin = self._icon_picker_widgets.get("default_icon_builtin")
        picture = self._icon_picker_widgets.get("default_icon_picture")
        if show_picture:
            if builtin is not None:
                builtin.grid_remove()
            if picture is not None:
                picture.grid()
            self._show_icon_hint()
        else:
            if picture is not None:
                picture.grid_remove()
            if builtin is not None:
                builtin.grid()
            self._hide_icon_hint()

    def _show_icon_hint(self) -> None:
        self._hide_icon_hint()
        if not self._icon_picker_container:
            return
        try:
            self.update_idletasks()
        except tk.TclError:
            return
        top = tk.Toplevel(self)
        top.wm_overrideredirect(True)
        top.transient(self)
        frame = ttk.Frame(top, borderwidth=1, relief="solid")
        ttk.Label(frame, text="Uses assets in */assets/icons").pack(padx=6, pady=4)
        frame.pack(fill="both", expand=True)
        x = self._icon_picker_container.winfo_rootx()
        y = self._icon_picker_container.winfo_rooty() + self._icon_picker_container.winfo_height() + 2
        top.geometry(f"+{x}+{y}")
        self._icon_hint_popup = top
        self._icon_hint_after = self.after(2500, self._hide_icon_hint)

    def _hide_icon_hint(self) -> None:
        if self._icon_hint_after:
            try:
                self.after_cancel(self._icon_hint_after)
            except Exception:
                pass
            self._icon_hint_after = None
        if self._icon_hint_popup:
            try:
                self._icon_hint_popup.destroy()
            except Exception:
                pass
            self._icon_hint_popup = None

    def _add_about_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="About")
        tab.grid_columnconfigure(0, weight=1)

        title = ttk.Label(tab, text="Linework", font=("TkDefaultFont", 14, "bold"))
        title.grid(row=0, column=0, sticky="w", padx=10, pady=(10, 4))

        description = "A small Tkinter app for drawing simple track diagrams and line drawings"
        wraplength = 350
        desc_label = ttk.Label(tab, text=description, wraplength=wraplength, justify="left")
        desc_label.grid(row=1, column=0, sticky="w", padx=10)

        ttk.Separator(tab, orient="horizontal").grid(row=2, column=0, sticky="ew", padx=10, pady=10)

        try:
            tk_version = str(self.tk.call("info", "patchlevel"))
        except Exception:
            tk_version = str(tk.TkVersion)

        info_text = "\n".join(
            [
                f"Version: {get_app_version()}",
                f"Python: {sys.version.split()[0]}",
                f"Tk: {tk_version}",
                "Project files: .linework",
                "Autosave: .linework.autosave",
            ]
        )
        info_label = ttk.Label(tab, text=info_text, justify="left", wraplength=wraplength)
        info_label.grid(row=3, column=0, sticky="w", padx=10, pady=(0, 10))

    def destroy(self) -> None:
        """Destroy the dialog and hint popups."""
        self._hide_icon_hint()
        super().destroy()

    def _attach_dim_validation(self, entry: ttk.Entry) -> None:
        entry.bind("<FocusOut>", lambda _e: self._validate_dimensions(), add="+")
        entry.bind("<Return>", lambda _e: self._validate_dimensions(), add="+")
        entry.bind("<KP_Enter>", lambda _e: self._validate_dimensions(), add="+")

    def _attach_grid_validation(self, entry: ttk.Entry) -> None:
        entry.bind("<FocusOut>", lambda _e: self._validate_dimensions(), add="+")
        entry.bind("<Return>", lambda _e: self._validate_dimensions(), add="+")
        entry.bind("<KP_Enter>", lambda _e: self._validate_dimensions(), add="+")

    def _validate_dimensions(self) -> None:
        base_values: dict[str, int | None] = {}
        for base in self._multiple_bases:
            base_val = self._read_int_field(base)
            base_values[base] = base_val
            base_field = self._schema_by_name.get(base, {})
            base_min = base_field.get("min")
            if base_val is None or (base_min is not None and base_val < base_min):
                base_entry = self._num_widgets.get(base)
                if base_entry is not None:
                    self._flash_entry(base_entry)

        for name, entry in self._dim_widgets.items():
            val = self._read_int_field(name)
            field = self._schema_by_name.get(name, {})
            min_val = field.get("min")
            if val is None or (min_val is not None and val < min_val):
                self._flash_entry(entry)
                continue

            base = self._multiple_of.get(name)
            if not base:
                continue
            base_val = base_values.get(base)
            base_field = self._schema_by_name.get(base, {})
            base_min = base_field.get("min")
            base_ok = base_val is not None and (base_min is None or base_val >= base_min)
            if base_ok and base_val and (val % base_val) != 0:
                self._flash_entry(entry)

    def _validate_on_submit(self) -> bool:
        invalid: set[str] = set()

        for fld in self.schema:
            kind = str(fld.get("kind", "")).lower()
            if kind != "int":
                continue
            name = str(fld.get("name", ""))
            if not name:
                continue
            val = self._read_int_field(name)
            if val is None:
                invalid.add(name)
                continue

            min_val = fld.get("min")
            if min_val is not None and val < min_val:
                invalid.add(name)

            base = fld.get("multiple_of")
            if base:
                base = str(base)
                base_val = self._read_int_field(base)
                base_field = self._schema_by_name.get(base, {})
                base_min = base_field.get("min")
                if base_val is None or (base_min is not None and base_val < base_min):
                    invalid.add(base)
                elif base_val > 0 and (val % base_val) != 0:
                    invalid.add(name)

        if invalid:
            for name in invalid:
                entry = self._num_widgets.get(name)
                if entry is not None:
                    self._flash_entry(entry)
            return False
        return True

    def _read_int_field(self, name: str) -> int | None:
        meta = self._meta.get(name, {})
        var = meta.get("var")
        if not var:
            return None
        try:
            return int(float(str(var.get()).strip()))
        except Exception:
            return None

    def _register_entry(self, entry: ttk.Entry) -> None:
        if entry not in self._entry_base_styles:
            self._entry_base_styles[entry] = entry.cget("style") or "TEntry"

    def _clear_entry_styles(self) -> None:
        for entry, style in self._entry_base_styles.items():
            try:
                entry.configure(style=style)
            except Exception:
                pass

    def _flash_entry(self, entry: ttk.Entry) -> None:
        style = ttk.Style(self)
        warn_style = "Warn.TEntry"
        try:
            style.configure(warn_style, foreground="#b00020")
            style.map(warn_style, fieldbackground=[("!disabled", "#ffe5e5")])
        except Exception:
            pass
        normal = self._entry_base_styles.get(entry) or entry.cget("style") or "TEntry"
        self._entry_base_styles.setdefault(entry, normal)

        def _toggle(on: bool) -> None:
            try:
                entry.configure(style=warn_style if on else normal)
            except Exception:
                pass

        _toggle(False)
        _toggle(True)
        entry.after(120, lambda: _toggle(False))
        entry.after(240, lambda: _toggle(True))
        entry.after(360, lambda: _toggle(False))

from __future__ import annotations

import sys
import tkinter as tk
from collections import OrderedDict
from collections.abc import Callable
from tkinter import ttk

from models.geo import Icon_Type
from ui.edit_dialog import GenericEditDialog


class SettingsDialog(GenericEditDialog):
    def __init__(self, app, title, schema, values, *, on_save: Callable[[dict], bool | None], on_apply=None):
        self.apply_now = False
        self._on_save_cb = on_save
        self._on_apply_cb = on_apply
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

    def body(self, master):
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

        def _add_fields(tab: ttk.Frame, fields: list[dict]) -> None:
            nonlocal first_widget
            tab.grid_columnconfigure(1, weight=1)
            row = 0
            for fld in fields:
                name = str(fld.get("name", ""))
                if not name:
                    continue
                if name in ("default_icon_builtin", "default_icon_picture"):
                    if self._icon_picker_container is None:
                        ttk.Label(tab, text="Default icon").grid(row=row, column=0, sticky="w", padx=6, pady=4)
                        self._icon_picker_container = ttk.Frame(tab)
                        self._icon_picker_container.grid(row=row, column=1, sticky="ew", padx=6, pady=4)
                        self._icon_picker_container.grid_columnconfigure(0, weight=1)
                        row += 1
                    widget = self._build_widget(self._icon_picker_container, fld, self.values.get(name))
                    widget.grid(row=0, column=0, sticky="ew")
                    widget.grid_remove()
                    self._icon_picker_widgets[name] = widget
                    if first_widget is None:
                        first_widget = widget
                    continue
                label = fld.get("label", name)
                ttk.Label(tab, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=4)
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
        return first_widget

    def buttonbox(self):
        box = ttk.Frame(self)
        btn_save = ttk.Button(box, text="Save Defaults", command=self._on_save)
        btn_apply = ttk.Button(box, text="Apply Now", command=self._on_apply)
        btn_cancel = ttk.Button(box, text="Cancel", command=self.cancel)
        btn_save.pack(side="left", padx=5, pady=5)
        btn_apply.pack(side="left", padx=5, pady=5)
        btn_cancel.pack(side="left", padx=5, pady=5)
        box.pack(fill="x")
        self.bind("<Return>", lambda e: self._on_save())
        self.bind("<Escape>", lambda e: self.cancel())

    def _on_save(self):
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

    def _on_apply(self):
        self.apply_now = True
        if not self._validate_on_submit():
            return
        self._clear_entry_styles()
        if not self.validate():
            return
        self.apply()
        if self._on_apply_cb:
            self._on_apply_cb(getattr(self, "result", {}))

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
                f"Python: {sys.version.split()[0]}",
                f"Tk: {tk_version}",
                "Project files: .linework",
                "Autosave: .linework.autosave",
            ]
        )
        info_label = ttk.Label(tab, text=info_text, justify="left", wraplength=wraplength)
        info_label.grid(row=3, column=0, sticky="w", padx=10, pady=(0, 10))

    def destroy(self):
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

        def _toggle(on: bool):
            try:
                entry.configure(style=warn_style if on else normal)
            except Exception:
                pass

        _toggle(False)
        _toggle(True)
        entry.after(120, lambda: _toggle(False))
        entry.after(240, lambda: _toggle(True))
        entry.after(360, lambda: _toggle(False))

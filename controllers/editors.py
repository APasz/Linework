from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Generic, TypeVar

from models.assets import Icon_Name
from models.geo import Builtin_Icon, Label, Line, Picture_Icon, Point
from models.styling import Anchor, CapStyle, Colours, LineStyle
from ui.edit_dialog import GenericEditDialog

if TYPE_CHECKING:
    from controllers.app import App

M = TypeVar("M")


class EKind(StrEnum):
    INT = "int"
    FLOAT = "float"
    TEXT = "text"
    CHOICE = "choice"
    CHOICE_DICT = "choice_dict"
    BOOL = "bool"


@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: str
    kind: EKind
    min: int | float | None = None
    max: int | float | None = None
    choices: Callable[[], list[str]] | None = None
    choices_dict: Callable[[], dict[str, Any]] | None = None


@dataclass
class EditPlan(Generic[M]):
    title: str
    fields: list[FieldSpec]
    init: Callable[[M], dict[str, Any]]
    apply: Callable[[M, dict[str, Any]], None]


class Editors:
    def __init__(self, app: App) -> None:
        self.app = app
        self._registry: dict[type, Callable[[Any], EditPlan[Any]]] = {
            Label: self._plan_label,
            Line: self._plan_line,
            Builtin_Icon: self._plan_builtin_icon,
            Picture_Icon: self._plan_picture_icon,
        }

    def _colour_choices(self) -> list[str]:
        return Colours.names(min_alpha=25)

    def _cap_choices(self) -> list[str]:
        return [s.value for s in CapStyle]

    def _style_choices(self) -> list[str]:
        return [s.value for s in LineStyle]

    def _anchor_choices_tk(self) -> list[str]:
        return [s.value for s in Anchor]

    def _icon_choices(self) -> list[str]:
        return [n.value for n in Icon_Name]

    def _picture_choices(self) -> dict[str, Path]:
        return {p.name: p for p in self.app.asset_lib.list_pictures()}

    # ---------- single public entry point ----------
    def edit(self, parent: tk.Misc, obj: Any) -> bool:
        plan = self._resolve_plan(obj)
        schema = [self._field_to_schema(f) for f in plan.fields]
        dlg = GenericEditDialog(parent, plan.title, schema, plan.init(obj))
        result = getattr(dlg, "result", None)
        if not result:
            return False
        plan.apply(obj, result)
        return True

    # Convert our typed FieldSpec into the dialog’s schema dict just once
    def _field_to_schema(self, f: FieldSpec) -> dict[str, Any]:
        d: dict[str, Any] = {"name": f.name, "label": f.label, "kind": f.kind.value}
        if f.min is not None:
            d["min"] = f.min
        if f.max is not None:
            d["max"] = f.max
        if f.kind is EKind.CHOICE and f.choices:
            d["choices"] = f.choices()
        if f.kind is EKind.CHOICE_DICT and f.choices_dict:
            d["choices"] = f.choices_dict()
        return d

    def _resolve_plan(self, obj: Any) -> EditPlan[Any]:
        for ty, builder in self._registry.items():
            if isinstance(obj, ty):
                return builder(obj)
        raise TypeError(f"No editor registered for {type(obj)}")

    # =================== Plans (one per model type) ===================
    # --- Label ---
    def _plan_label(self, lab: Label) -> EditPlan[Label]:
        fields = [
            FieldSpec("text", "Text", EKind.TEXT),
            FieldSpec("x", "X", EKind.INT, min=0),
            FieldSpec("y", "Y", EKind.INT, min=0),
            FieldSpec("snap_to_grid", "Snap X/Y to grid now", EKind.BOOL),
            FieldSpec("snap_flag", "Keep snapped when dragging", EKind.BOOL),
            FieldSpec("size", "Size", EKind.INT, min=1),
            FieldSpec("rotation", "Rotation (deg)", EKind.INT),
            FieldSpec("anchor", "Anchor", EKind.CHOICE, choices=self._anchor_choices_tk),
            FieldSpec("colour", "Colour", EKind.CHOICE, choices=self._colour_choices),
        ]

        def init(lab: Label) -> dict[str, Any]:
            return dict(
                text=lab.text,
                x=lab.p.x,
                y=lab.p.y,
                snap_to_grid=False,
                snap_flag=lab.snap,
                size=lab.size,
                rotation=lab.rotation,
                anchor=lab.anchor.tk,
                colour=lab.col.name,
            )

        def apply(lab: Label, data: dict[str, Any]) -> None:
            p = Point(x=int(data["x"]), y=int(data["y"]))
            if data.get("snap_to_grid"):
                p = self.app.snap(p)
            lab.text = data["text"]
            lab.p = p
            lab.snap = bool(data.get("snap_flag", lab.snap))
            lab.size = int(data["size"])
            lab.rotation = int(data.get("rotation", 0))
            lab.anchor = Anchor.parse(data["anchor"]) or lab.anchor
            lab.col = Colours.parse_colour(data["colour"]) if data.get("colour") else lab.col

        return EditPlan(title="Edit Label", fields=fields, init=init, apply=apply)

    # --- Line ---
    def _plan_line(self, lin: Line) -> EditPlan[Line]:
        fields = [
            FieldSpec("x1", "X1", EKind.INT, min=0),
            FieldSpec("y1", "Y1", EKind.INT, min=0),
            FieldSpec("x2", "X2", EKind.INT, min=0),
            FieldSpec("y2", "Y2", EKind.INT, min=0),
            FieldSpec("snap_to_grid", "Snap endpoints to grid", EKind.BOOL),
            FieldSpec("width", "Width", EKind.INT, min=1),
            FieldSpec("capstyle", "Cap", EKind.CHOICE, choices=self._cap_choices),
            FieldSpec("style", "Dash", EKind.CHOICE, choices=self._style_choices),
            FieldSpec("colour", "Colour", EKind.CHOICE, choices=self._colour_choices),
            FieldSpec("dash_offset", "Dash offset", EKind.INT, min=0),
        ]

        def init(lin: Line) -> dict[str, Any]:
            return dict(
                x1=lin.a.x,
                y1=lin.a.y,
                x2=lin.b.x,
                y2=lin.b.y,
                snap_to_grid=False,
                width=lin.width,
                capstyle=lin.capstyle,
                style=lin.style,
                colour=lin.col.name,
                dash_offset=lin.dash_offset,
            )

        def apply(lin: Line, data: dict[str, Any]) -> None:
            a = Point(x=int(data["x1"]), y=int(data["y1"]))
            b = Point(x=int(data["x2"]), y=int(data["y2"]))
            if data.get("snap_to_grid"):
                a, b = self.app.snap(a), self.app.snap(b)
            lin.a, lin.b = a, b
            lin.width = int(data["width"])
            lin.capstyle = CapStyle(data["capstyle"])
            lin.style = LineStyle(data["style"])
            lin.col = Colours.parse_colour(data["colour"]) if data.get("colour") else lin.col
            lin.dash_offset = int(data.get("dash_offset", 0))

        return EditPlan(title="Edit Line", fields=fields, init=init, apply=apply)

    # --- Built-in Icon ---
    def _plan_builtin_icon(self, ico: Builtin_Icon) -> EditPlan[Builtin_Icon]:
        fields_common = self._icon_common_fields()
        fields = [
            FieldSpec("name", "Icon", EKind.CHOICE, choices=self._icon_choices),
            FieldSpec("colour", "Colour", EKind.CHOICE, choices=self._colour_choices),
            *fields_common,
        ]

        def init(ico: Builtin_Icon) -> dict[str, Any]:
            return dict(
                name=ico.name.value,
                colour=ico.col.name,
                x=ico.p.x,
                y=ico.p.y,
                snap_to_grid=False,
                snap_flag=ico.snap,
                size=ico.size,
                rotation=ico.rotation,
                anchor=ico.anchor.tk,
            )

        def apply(ico: Builtin_Icon, data: dict[str, Any]) -> None:
            p = Point(x=int(data["x"]), y=int(data["y"]))
            if data.get("snap_to_grid"):
                p = self.app.snap(p)
            ico.name = Icon_Name(data["name"])
            ico.p = p
            ico.snap = bool(data.get("snap_flag", ico.snap))
            ico.size = int(data["size"])
            ico.rotation = int(data.get("rotation", 0))
            ico.anchor = Anchor.parse(data["anchor"]) or ico.anchor
            if data.get("colour"):
                ico.col = Colours.parse_colour(data["colour"])

        return EditPlan(title="Edit Icon", fields=fields, init=init, apply=apply)

    def _plan_picture_icon(self, pic: Picture_Icon) -> EditPlan[Picture_Icon]:
        fields_common = self._icon_common_fields()
        fields = [
            FieldSpec("src", "Picture", EKind.CHOICE_DICT, choices_dict=self._picture_choices),
            *fields_common,
        ]

        def init(pic: Picture_Icon) -> dict[str, Any]:
            return dict(
                src=Path(pic.src).name,
                x=pic.p.x,
                y=pic.p.y,
                snap_to_grid=False,
                snap_flag=pic.snap,
                size=pic.size,
                rotation=pic.rotation,
                anchor=pic.anchor.tk,
            )

        def apply(pic: Picture_Icon, data: dict[str, Any]) -> None:
            p = Point(x=int(data["x"]), y=int(data["y"]))
            if data.get("snap_to_grid"):
                p = self.app.snap(p)
            cand = data["src"]
            pic.src = Path(cand) if Path(cand).exists() else self._picture_choices().get(cand, pic.src)
            pic.p = p
            pic.snap = bool(data.get("snap_flag", pic.snap))
            pic.size = int(data["size"])
            pic.rotation = int(data.get("rotation", 0))
            pic.anchor = Anchor.parse(data["anchor"]) or pic.anchor

        return EditPlan(title="Edit Picture", fields=fields, init=init, apply=apply)

    # --- shared icon fields ---
    def _icon_common_fields(self) -> list[FieldSpec]:
        return [
            FieldSpec("x", "X", EKind.INT, min=0),
            FieldSpec("y", "Y", EKind.INT, min=0),
            FieldSpec("snap_to_grid", "Snap X/Y to grid now", EKind.BOOL),
            FieldSpec("snap_flag", "Keep snapped when dragging", EKind.BOOL),
            FieldSpec("size", "Size", EKind.INT, min=1),
            FieldSpec("rotation", "Rotation (deg)", EKind.INT),
            FieldSpec("anchor", "Anchor", EKind.CHOICE, choices=self._anchor_choices_tk),
        ]

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from models.assets import Icon_Name
from models.geo import Builtin_Icon, Label, Line, Picture_Icon, Point
from models.styling import Anchor, CapStyle, Colours, LineStyle
from ui.edit_dialog import GenericEditDialog

if TYPE_CHECKING:
    from controllers.app import App

M = TypeVar("M")


class EKind(StrEnum):
    STR = "str"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    TEXT = "text"
    CHOICE = "choice"
    CHOICE_DICT = "choice_dict"
    COLOUR = "colour"
    ICON_BUILTIN = "icon_builtin"
    ICON_PICTURE = "icon_picture"


MASTER = [
    "src",
    "text",
    "name",
    "x",
    "y",
    "x1",
    "y1",
    "x2",
    "y2",
    "colour",
    "size",
    "width",
    "rotation",
    "anchor",
    "capstyle",
    "style",
    "dash_offset",
    "snap_to_grid",
    "snap_flag",
    "remember_defaults",
]


def make_order_key(names):
    pos = {n: i for i, n in enumerate(names)}

    def key(f):  # f: FieldSpec
        return (0, pos[f.name]) if f.name in pos else (1, f.label.lower())

    return key


_order_key = make_order_key(MASTER)


@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: str
    kind: EKind
    min: int | float | None = None
    max: int | float | None = None
    choices: Callable[[], list[str]] | None = None
    choices_dict: Callable[[], dict[str, Any]] | None = None
    sort: bool = False


@dataclass
class EditPlan(Generic[M]):
    title: str
    fields: list[FieldSpec]
    init: Callable[[M], dict[str, Any]]
    apply: Callable[[M, dict[str, Any]], None]
    override_sort: bool | Callable[[FieldSpec], Any] = True

    def __post_init__(self):
        if not self.fields:
            raise ValueError("EditPlan must have at least one field")
        if not callable(self.init):
            raise TypeError("init must be callable")
        if not callable(self.apply):
            raise TypeError("apply must be callable")
        if self.override_sort:
            key = self.override_sort if callable(self.override_sort) else (lambda f: f.label.lower())
            self.fields.sort(key=key)


class Editors:
    def __init__(self, app: App):
        self.app = app
        self._registry: dict[type, Callable[[Any], EditPlan[Any]]] = {
            Label: self._plan_label,
            Line: self._plan_line,
            Builtin_Icon: self._plan_builtin_icon,
            Picture_Icon: self._plan_picture_icon,
        }
        # per-session sticky defaults (not persisted)
        self._label_defaults: dict[str, Any] | None = None
        self._icon_defaults: dict[str, Any] | None = None

    # ---------- apply session defaults ----------
    def apply_label_defaults(self, lab: Label):
        d = self._label_defaults or {}
        lab.size = int(d.get("size", self.app.params.label_size))
        lab.rotation = int(d.get("rotation", self.app.params.label_rotation))
        lab.anchor = Anchor.parse(d.get("anchor", self.app.params.label_anchor)) or lab.anchor

    def apply_icon_defaults(self, ico):
        d = self._icon_defaults or {}
        default_size = self.app.params.picture_size if isinstance(ico, Picture_Icon) else self.app.params.icon_size
        ico.size = int(d.get("size", default_size))
        ico.rotation = int(d.get("rotation", self.app.params.icon_rotation))
        ico.anchor = Anchor.parse(d.get("anchor", self.app.params.icon_anchor)) or ico.anchor

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
    def edit(self, app: App, obj: Any) -> bool:
        plan = self._resolve_plan(obj)
        schema = [self._field_to_schema(f) for f in plan.fields]
        dlg = app._safe_tk_call(GenericEditDialog, app, plan.title, schema, plan.init(obj))
        if dlg is None:
            return False
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
        d["sort"] = f.sort
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
            FieldSpec("anchor", "Anchor", EKind.CHOICE, choices=self._anchor_choices_tk, sort=False),
            FieldSpec("colour", "Colour", EKind.COLOUR),
            FieldSpec("remember_defaults", "Remember for this session;\nsize/rotation/anchor", EKind.BOOL),
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
                colour=lab.col.hexah,
                remember_defaults=False,
            )

        def apply(lab: Label, data: dict[str, Any]):
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
            if data.get("remember_defaults"):
                self._label_defaults = {
                    "size": int(data["size"]),
                    "rotation": int(data.get("rotation", 0)),
                    "anchor": data["anchor"],
                }

        return EditPlan(title="Edit Label", fields=fields, init=init, apply=apply, override_sort=_order_key)

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
            FieldSpec("colour", "Colour", EKind.COLOUR),
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
                colour=lin.col.hexah,
                dash_offset=lin.dash_offset,
            )

        def apply(lin: Line, data: dict[str, Any]):
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

        return EditPlan(title="Edit Line", fields=fields, init=init, apply=apply, override_sort=_order_key)

    # --- Built-in Icon ---
    def _plan_builtin_icon(self, ico: Builtin_Icon) -> EditPlan[Builtin_Icon]:
        fields_common = self._icon_common_fields()
        fields = [
            FieldSpec("name", "Icon", EKind.ICON_BUILTIN),
            FieldSpec("colour", "Colour", EKind.COLOUR),
            *fields_common,
        ]

        def init(ico: Builtin_Icon) -> dict[str, Any]:
            return dict(
                name=ico.name.value,
                colour=ico.col.hexah,
                x=ico.p.x,
                y=ico.p.y,
                snap_to_grid=False,
                snap_flag=ico.snap,
                size=ico.size,
                rotation=ico.rotation,
                anchor=ico.anchor.tk,
                remember_defaults=False,
            )

        def apply(ico: Builtin_Icon, data: dict[str, Any]):
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
            if data.get("remember_defaults"):
                self._icon_defaults = {
                    "size": int(data["size"]),
                    "rotation": int(data.get("rotation", 0)),
                    "anchor": data["anchor"],
                }

        return EditPlan(title="Edit Icon", fields=fields, init=init, apply=apply, override_sort=_order_key)

    def _plan_picture_icon(self, pic: Picture_Icon) -> EditPlan[Picture_Icon]:
        fields_common = self._icon_common_fields()
        fields = [
            FieldSpec("src", "Picture", EKind.ICON_PICTURE),
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
                remember_defaults=False,
            )

        def apply(pic: Picture_Icon, data: dict[str, Any]):
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
            if data.get("remember_defaults"):
                self._icon_defaults = {
                    "size": int(data["size"]),
                    "rotation": int(data.get("rotation", 0)),
                    "anchor": data["anchor"],
                }

        return EditPlan(title="Edit Picture", fields=fields, init=init, apply=apply, override_sort=_order_key)

    # --- shared icon fields ---
    def _icon_common_fields(self) -> list[FieldSpec]:
        return [
            FieldSpec("x", "X", EKind.INT, min=0),
            FieldSpec("y", "Y", EKind.INT, min=0),
            FieldSpec("snap_to_grid", "Snap X/Y to grid now", EKind.BOOL),
            FieldSpec("snap_flag", "Keep snapped when dragging", EKind.BOOL),
            FieldSpec("size", "Size", EKind.INT, min=1),
            FieldSpec("rotation", "Rotation (deg)", EKind.INT),
            FieldSpec("anchor", "Anchor", EKind.CHOICE, choices=self._anchor_choices_tk, sort=False),
            FieldSpec("remember_defaults", "Remember for this session;\nsize/rotation/anchor", EKind.BOOL),
        ]

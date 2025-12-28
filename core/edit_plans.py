"""Edit plan definitions for model editing."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Generic, Protocol, TypeVar

from models.assets import AssetLibrary, IconName
from models.geo import BuiltinIcon, Label, Line, PictureIcon, Point
from models.params import Params
from models.styling import Anchor, CapStyle, Colours, LineStyle

M = TypeVar("M")


class EditPlanHost(Protocol):
    """Interface required to build and apply edit plans."""

    @property
    def params(self) -> Params:
        """Access to application parameters."""
        ...

    @property
    def asset_lib(self) -> AssetLibrary | None:
        """Access to the asset library if available."""
        ...

    def snap(self, point: Point, *, ignore_grid: bool = False) -> Point:
        """Snap a point to grid/bounds."""
        ...


class EKind(StrEnum):
    """Field kinds for editor schema."""

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
    "index",
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


def make_order_key(names: list[str]) -> Callable[["FieldSpec"], tuple[int, str] | tuple[int, int]]:
    """Build a sorting key for field ordering."""
    pos = {n: i for i, n in enumerate(names)}

    def key(f: "FieldSpec") -> tuple[int, str] | tuple[int, int]:
        return (0, pos[f.name]) if f.name in pos else (1, f.label.lower())

    return key


_order_key = make_order_key(MASTER)


@dataclass(frozen=True)
class FieldSpec:
    """Field specification for a dialog."""

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
    """Edit plan for a model type."""

    title: str
    fields: list[FieldSpec]
    init: Callable[[M], dict[str, Any]]
    apply: Callable[[M, dict[str, Any]], None]
    override_sort: bool | Callable[[FieldSpec], Any] = True

    def __post_init__(self) -> None:
        """Validate the plan and apply field ordering."""
        if not self.fields:
            raise ValueError("EditPlan must have at least one field")
        if not callable(self.init):
            raise TypeError("init must be callable")
        if not callable(self.apply):
            raise TypeError("apply must be callable")
        if self.override_sort:
            key = self.override_sort if callable(self.override_sort) else (lambda f: f.label.lower())
            self.fields.sort(key=key)


class EditPlans:
    """Registry of edit plans for model types."""

    def __init__(self, app: EditPlanHost) -> None:
        """Create the edit plan registry.

        Args;
            app: The host application.
        """
        self.app = app
        self._registry: dict[type, Callable[[Any], EditPlan[Any]]] = {
            Label: self._plan_label,
            Line: self._plan_line,
            BuiltinIcon: self._plan_builtin_icon,
            PictureIcon: self._plan_picture_icon,
        }
        self._label_defaults: dict[str, Any] | None = None
        self._icon_defaults: dict[str, Any] | None = None

    @staticmethod
    def _index_for_item(items: list[Any], target: Any) -> int | None:
        """Return the index of an item by identity.

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

    @staticmethod
    def _swap_items(items: list[Any], a: int, b: int) -> None:
        """Swap two items in-place when indices are valid.

        Args;
            items: The list to mutate.
            a: First index.
            b: Second index.
        """
        if a == b:
            return
        if not (0 <= a < len(items) and 0 <= b < len(items)):
            return
        items[a], items[b] = items[b], items[a]

    def _index_field(self, idx: int | None, count: int) -> FieldSpec | None:
        """Create an index field for reordering.

        Args;
            idx: The current index.
            count: The total number of items.

        Returns;
            The field spec, or None if reordering is not applicable.
        """
        if idx is None or count <= 1:
            return None
        return FieldSpec("index", "Index", EKind.INT, min=0, max=count - 1)

    def _apply_index_swap(self, items: list[Any], target: Any, data: dict[str, Any]) -> None:
        """Apply any index change from submitted data.

        Args;
            items: The list to reorder.
            target: The target item.
            data: The submitted field data.
        """
        if "index" not in data:
            return
        current = self._index_for_item(items, target)
        if current is None:
            return
        desired = int(data.get("index", current))
        if desired == current:
            return
        if 0 <= desired < len(items):
            self._swap_items(items, current, desired)

    # ---------- apply session defaults ----------
    def apply_label_defaults(self, lab: Label) -> None:
        """Apply session defaults to a label.

        Args;
            lab: The label to update.
        """
        d = self._label_defaults or {}
        lab.size = int(d.get("size", self.app.params.label_size))
        lab.rotation = int(d.get("rotation", self.app.params.label_rotation))
        lab.anchor = Anchor.parse(d.get("anchor", self.app.params.label_anchor)) or lab.anchor

    def apply_icon_defaults(self, ico: BuiltinIcon | PictureIcon) -> None:
        """Apply session defaults to an icon.

        Args;
            ico: The icon to update.
        """
        d = self._icon_defaults or {}
        default_size = self.app.params.picture_size if isinstance(ico, PictureIcon) else self.app.params.icon_size
        ico.size = int(d.get("size", default_size))
        ico.rotation = int(d.get("rotation", self.app.params.icon_rotation))
        ico.anchor = Anchor.parse(d.get("anchor", self.app.params.icon_anchor)) or ico.anchor

    # ---------- choices ----------
    def _colour_choices(self) -> list[str]:
        """Return the available colour choices.

        Returns;
            The colour names.
        """
        return Colours.names(min_alpha=25)

    def _cap_choices(self) -> list[str]:
        """Return available cap style choices.

        Returns;
            The cap style values.
        """
        return [s.value for s in CapStyle]

    def _style_choices(self) -> list[str]:
        """Return available line style choices.

        Returns;
            The line style values.
        """
        return [s.value for s in LineStyle]

    def _anchor_choices(self) -> list[str]:
        """Return available anchor choices.

        Returns;
            The anchor values.
        """
        return [s.value for s in Anchor]

    def _icon_choices(self) -> list[str]:
        """Return available builtin icon choices.

        Returns;
            The icon names.
        """
        return [n.value for n in IconName]

    def _picture_choices(self) -> dict[str, Path]:
        """Return available picture choices from the asset library.

        Returns;
            Mapping of display names to paths.
        """
        lib = getattr(self.app, "asset_lib", None)
        if lib is None:
            return {}
        return {p.name: p for p in lib.list_pictures()}

    # ---------- public helpers ----------
    def plan_for(self, obj: Any) -> EditPlan[Any]:
        """Return the edit plan for a given object."""
        for ty, builder in self._registry.items():
            if isinstance(obj, ty):
                return builder(obj)
        raise TypeError(f"No editor registered for {type(obj)}")

    def schema_for_plan(self, plan: EditPlan[Any]) -> list[dict[str, Any]]:
        """Return a dialog schema dict for a plan."""
        return [self._field_to_schema(f) for f in plan.fields]

    # ---------- schema ----------
    def _field_to_schema(self, f: FieldSpec) -> dict[str, Any]:
        """Convert a field spec into a schema dictionary.

        Args;
            f: The field specification.

        Returns;
            The schema dictionary.
        """
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

    # =================== Plans (one per model type) ===================
    def _plan_label(self, lab: Label) -> EditPlan[Label]:
        """Build the edit plan for a label.

        Args;
            lab: The label to edit.

        Returns;
            The edit plan.
        """
        idx = self._index_for_item(self.app.params.labels, lab)
        fields = []
        index_field = self._index_field(idx, len(self.app.params.labels))
        if index_field is not None:
            fields.append(index_field)
        fields.extend(
            [
            FieldSpec("text", "Text", EKind.TEXT),
            FieldSpec("x", "X", EKind.INT, min=0),
            FieldSpec("y", "Y", EKind.INT, min=0),
            FieldSpec("snap_to_grid", "Snap X/Y to grid now", EKind.BOOL),
            FieldSpec("snap_flag", "Keep snapped when dragging", EKind.BOOL),
            FieldSpec("size", "Size", EKind.INT, min=1),
            FieldSpec("rotation", "Rotation (deg)", EKind.INT),
            FieldSpec("anchor", "Anchor", EKind.CHOICE, choices=self._anchor_choices, sort=False),
            FieldSpec("colour", "Colour", EKind.COLOUR),
            FieldSpec("remember_defaults", "Remember for this session;\nsize/rotation/anchor", EKind.BOOL),
            ]
        )

        def init(lab: Label) -> dict[str, Any]:
            return dict(
                index=idx,
                text=lab.text,
                x=lab.p.x,
                y=lab.p.y,
                snap_to_grid=False,
                snap_flag=lab.snap,
                size=lab.size,
                rotation=lab.rotation,
                anchor=lab.anchor.value,
                colour=lab.col.hexah,
                remember_defaults=False,
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
            self._apply_index_swap(self.app.params.labels, lab, data)
            if data.get("remember_defaults"):
                self._label_defaults = {
                    "size": int(data["size"]),
                    "rotation": int(data.get("rotation", 0)),
                    "anchor": data["anchor"],
                }

        return EditPlan(title="Edit Label", fields=fields, init=init, apply=apply, override_sort=_order_key)

    def _plan_line(self, lin: Line) -> EditPlan[Line]:
        """Build the edit plan for a line.

        Args;
            lin: The line to edit.

        Returns;
            The edit plan.
        """
        idx = self._index_for_item(self.app.params.lines, lin)
        fields = []
        index_field = self._index_field(idx, len(self.app.params.lines))
        if index_field is not None:
            fields.append(index_field)
        fields.extend(
            [
            FieldSpec("x1", "X1", EKind.INT, min=0),
            FieldSpec("y1", "Y1", EKind.INT, min=0),
            FieldSpec("x2", "X2", EKind.INT, min=0),
            FieldSpec("y2", "Y2", EKind.INT, min=0),
            FieldSpec("snap_to_grid", "Snap endpoints to grid", EKind.BOOL),
            FieldSpec("snap_flag", "Keep snapped", EKind.BOOL),
            FieldSpec("width", "Width", EKind.INT, min=1),
            FieldSpec("capstyle", "Cap", EKind.CHOICE, choices=self._cap_choices),
            FieldSpec("style", "Dash", EKind.CHOICE, choices=self._style_choices),
            FieldSpec("colour", "Colour", EKind.COLOUR),
            FieldSpec("dash_offset", "Dash offset", EKind.INT, min=0),
            ]
        )

        def init(lin: Line) -> dict[str, Any]:
            return dict(
                index=idx,
                x1=lin.a.x,
                y1=lin.a.y,
                x2=lin.b.x,
                y2=lin.b.y,
                snap_to_grid=False,
                snap_flag=lin.snap,
                width=lin.width,
                capstyle=lin.capstyle.value,
                style=lin.style.value,
                colour=lin.col.hexah,
                dash_offset=lin.dash_offset,
            )

        def apply(lin: Line, data: dict[str, Any]) -> None:
            a = Point(x=int(data["x1"]), y=int(data["y1"]))
            b = Point(x=int(data["x2"]), y=int(data["y2"]))
            if data.get("snap_to_grid"):
                a, b = self.app.snap(a), self.app.snap(b)
            lin.a, lin.b = a, b
            lin.snap = bool(data.get("snap_flag", lin.snap))
            lin.width = int(data["width"])
            lin.capstyle = CapStyle(data["capstyle"])
            lin.style = LineStyle(data["style"])
            lin.col = Colours.parse_colour(data["colour"]) if data.get("colour") else lin.col
            lin.dash_offset = int(data.get("dash_offset", 0))
            self._apply_index_swap(self.app.params.lines, lin, data)

        return EditPlan(title="Edit Line", fields=fields, init=init, apply=apply, override_sort=_order_key)

    def _plan_builtin_icon(self, ico: BuiltinIcon) -> EditPlan[BuiltinIcon]:
        """Build the edit plan for a builtin icon.

        Args;
            ico: The builtin icon to edit.

        Returns;
            The edit plan.
        """
        idx = self._index_for_item(self.app.params.icons, ico)
        fields = []
        index_field = self._index_field(idx, len(self.app.params.icons))
        if index_field is not None:
            fields.append(index_field)
        fields_common = self._icon_common_fields()
        fields.extend(
            [
            FieldSpec("name", "Icon", EKind.ICON_BUILTIN),
            FieldSpec("colour", "Colour", EKind.COLOUR),
            *fields_common,
            ]
        )

        def init(ico: BuiltinIcon) -> dict[str, Any]:
            return dict(
                index=idx,
                name=ico.name.value,
                colour=ico.col.hexah,
                x=ico.p.x,
                y=ico.p.y,
                snap_to_grid=False,
                snap_flag=ico.snap,
                size=ico.size,
                rotation=ico.rotation,
                anchor=ico.anchor.value,
                remember_defaults=False,
            )

        def apply(ico: BuiltinIcon, data: dict[str, Any]) -> None:
            p = Point(x=int(data["x"]), y=int(data["y"]))
            if data.get("snap_to_grid"):
                p = self.app.snap(p)
            ico.name = IconName(data["name"])
            ico.p = p
            ico.snap = bool(data.get("snap_flag", ico.snap))
            ico.size = int(data["size"])
            ico.rotation = int(data.get("rotation", 0))
            ico.anchor = Anchor.parse(data["anchor"]) or ico.anchor
            if data.get("colour"):
                ico.col = Colours.parse_colour(data["colour"])
            self._apply_index_swap(self.app.params.icons, ico, data)
            if data.get("remember_defaults"):
                self._icon_defaults = {
                    "size": int(data["size"]),
                    "rotation": int(data.get("rotation", 0)),
                    "anchor": data["anchor"],
                }

        return EditPlan(title="Edit Icon", fields=fields, init=init, apply=apply, override_sort=_order_key)

    def _plan_picture_icon(self, pic: PictureIcon) -> EditPlan[PictureIcon]:
        """Build the edit plan for a picture icon.

        Args;
            pic: The picture icon to edit.

        Returns;
            The edit plan.
        """
        idx = self._index_for_item(self.app.params.icons, pic)
        fields = []
        index_field = self._index_field(idx, len(self.app.params.icons))
        if index_field is not None:
            fields.append(index_field)
        fields_common = self._icon_common_fields()
        fields.extend(
            [
            FieldSpec("src", "Picture", EKind.ICON_PICTURE),
            *fields_common,
            ]
        )

        def init(pic: PictureIcon) -> dict[str, Any]:
            return dict(
                index=idx,
                src=Path(pic.src).name,
                x=pic.p.x,
                y=pic.p.y,
                snap_to_grid=False,
                snap_flag=pic.snap,
                size=pic.size,
                rotation=pic.rotation,
                anchor=pic.anchor.value,
                remember_defaults=False,
            )

        def apply(pic: PictureIcon, data: dict[str, Any]) -> None:
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
            self._apply_index_swap(self.app.params.icons, pic, data)
            if data.get("remember_defaults"):
                self._icon_defaults = {
                    "size": int(data["size"]),
                    "rotation": int(data.get("rotation", 0)),
                    "anchor": data["anchor"],
                }

        return EditPlan(title="Edit Picture", fields=fields, init=init, apply=apply, override_sort=_order_key)

    def _icon_common_fields(self) -> list[FieldSpec]:
        """Return the shared icon fields.

        Returns;
            The common icon field specs.
        """
        return [
            FieldSpec("x", "X", EKind.INT, min=0),
            FieldSpec("y", "Y", EKind.INT, min=0),
            FieldSpec("snap_to_grid", "Snap X/Y to grid now", EKind.BOOL),
            FieldSpec("snap_flag", "Keep snapped when dragging", EKind.BOOL),
            FieldSpec("size", "Size", EKind.INT, min=1),
            FieldSpec("rotation", "Rotation (deg)", EKind.INT),
            FieldSpec("anchor", "Anchor", EKind.CHOICE, choices=self._anchor_choices, sort=False),
            FieldSpec("remember_defaults", "Remember for this session;\nsize/rotation/anchor", EKind.BOOL),
        ]

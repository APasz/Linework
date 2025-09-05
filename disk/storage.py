from __future__ import annotations
from pathlib import Path
from typing import Any, TypedDict, Literal

import json

from models.params import Params
from models.colour import Colour, Colours as Cols
from models.geo import Line, Point
from models.objects import Label, Icon
from enums import OUT_TYPES

SCHEMA_VERSION = 1  # bump when you change shape

# ---------- Encoders ----------


def _enc_colour(c: Colour) -> dict[str, Any]:
    return {"name": c.name, "r": c.red, "g": c.green, "b": c.blue, "a": c.alpha}


def _enc_line(l: Line) -> dict[str, Any]:
    return {
        "x1": l.x1,
        "y1": l.y1,
        "x2": l.x2,
        "y2": l.y2,
        "col": _enc_colour(l.col),
        "width": l.width,
        "cap": l.capstyle,
    }


def _enc_label(lb: Label) -> dict[str, Any]:
    return {"x": lb.x, "y": lb.y, "text": lb.text, "col": _enc_colour(lb.col), "anchor": lb.anchor, "size": lb.size}


def _enc_icon(ic: Icon) -> dict[str, Any]:
    return {"x": ic.x, "y": ic.y, "name": ic.name, "col": _enc_colour(ic.col), "size": ic.size, "rotation": ic.rotation}


def params_to_dict(p: Params) -> dict[str, Any]:
    return {
        "version": SCHEMA_VERSION,
        "width": p.width,
        "height": p.height,
        "bg_mode": _enc_colour(p.bg_mode),
        "brush_width": p.brush_width,
        "brush_color": _enc_colour(p.brush_color),
        "grid_size": p.grid_size,
        "grid_colour": _enc_colour(p.grid_colour),
        "grid_visible": p.grid_visible,
        "output_file": str(p.output_file),
        "output_type": str(p.output_type),
        "lines": [_enc_line(l) for l in p.lines],
        "labels": [_enc_label(lb) for lb in getattr(p, "labels", [])],
        "icons": [_enc_icon(ic) for ic in getattr(p, "icons", [])],
    }


# ---------- Decoders ----------


def _dec_colour(d: dict[str, Any]) -> Colour:
    # allow either {"name": "..."} or full rgba dicts
    if isinstance(d, str):
        return Cols.get(d) or Cols.white
    return Colour(d.get("name", "custom"), int(d["r"]), int(d["g"]), int(d["b"]), int(d.get("a", 255)))


def _dec_line(d: dict[str, Any]) -> Line:
    return Line(d["x1"], d["y1"], d["x2"], d["y2"], _dec_colour(d["col"]), int(d["width"]), d.get("cap", "round"))


def _dec_label(d: dict[str, Any]) -> Label:
    return Label(
        int(d["x"]),
        int(d["y"]),
        d.get("text", ""),
        _dec_colour(d["col"]),
        d.get("anchor", "nw"),
        int(d.get("size", 12)),
    )


def _dec_icon(d: dict[str, Any]) -> Icon:
    return Icon(
        int(d["x"]),
        int(d["y"]),
        d.get("name", "signal"),
        _dec_colour(d["col"]),
        int(d.get("size", 16)),
        int(d.get("rotation", 0)),
    )


def dict_to_params(data: dict[str, Any]) -> Params:
    v = int(data.get("version", 0))
    if v != SCHEMA_VERSION:
        data = _migrate(data, v)

    from models.params import Params  # avoid cycles

    p = Params(
        width=int(data["width"]),
        height=int(data["height"]),
        bg_mode=_dec_colour(data["bg_mode"]),
        brush_width=int(data["brush_width"]),
        brush_color=_dec_colour(data["brush_color"]),
        grid_size=int(data["grid_size"]),
        grid_colour=_dec_colour(data["grid_colour"]),
        grid_visible=bool(data["grid_visible"]),
        output_file=Path(data.get("output_file", "output")),
        output_type=OUT_TYPES[data.get("output_type", "webp")],
        lines=[_dec_line(x) for x in data.get("lines", [])],
    )
    # optional fields in older files
    if "labels" in data:
        p.labels = [_dec_label(x) for x in data["labels"]]
    if "icons" in data:
        p.icons = [_dec_icon(x) for x in data["icons"]]
    return p


# ---------- Public API ----------


class IO:
    @staticmethod
    def save_params(p: Params, path: Path) -> None:
        path.write_text(json.dumps(params_to_dict(p), indent=4))

    @staticmethod
    def load_params(path: Path) -> Params:
        raw = json.loads(path.read_text()) if path.exists() else {"version": SCHEMA_VERSION}
        return dict_to_params(raw)


# ---------- Migration hook ----------


def _migrate(data: dict[str, Any], from_version: int) -> dict[str, Any]:
    """Migrate older payloads to current schema."""
    d = dict(data)
    v = int(from_version)

    # example future migrations:
    # if v < 1:
    #     ...
    #     v = 1
    # if v < 2:
    #     ...
    #     v = 2

    d["version"] = SCHEMA_VERSION
    return d

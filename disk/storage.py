from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from disk.formats import Formats
from models.anchors import Anchor
from models.colour import Colour
from models.colour import Colours as Cols
from models.geo import Line
from models.linestyle import CapStyle, LineStyle
from models.objects import Icon, Label
from models.params import Params

SCHEMA_VERSION = 1


# ---------- Encoders ----------
def _enc_colour(colour: Colour) -> dict[str, Any]:
    return {"name": colour.name, "r": colour.red, "g": colour.green, "b": colour.blue, "a": colour.alpha}


def _enc_anchor(anchor: Anchor) -> dict[str, Any]:
    return {"value": anchor.value}


def _enc_line(lin: Line) -> dict[str, Any]:
    return {
        "x1": lin.x1,
        "y1": lin.y1,
        "x2": lin.x2,
        "y2": lin.y2,
        "col": _enc_colour(lin.col),
        "width": lin.width,
        "cap": lin.capstyle.value,
        "style": str(getattr(lin, "style", "solid")),
        "dash_offset": int(getattr(lin, "dash_offset", 0)),
    }


def _enc_label(lab: Label) -> dict[str, Any]:
    return {
        "x": lab.x,
        "y": lab.y,
        "text": lab.text,
        "col": _enc_colour(lab.col),
        "anchor": _enc_anchor(lab.anchor),
        "size": lab.size,
        "rotation": lab.rotation,
        "snap": lab.snap,
    }


def _enc_icon(ico: Icon) -> dict[str, Any]:
    return {
        "x": ico.x,
        "y": ico.y,
        "name": ico.name,
        "col": _enc_colour(ico.col),
        "anchor": _enc_anchor(ico.anchor),
        "size": ico.size,
        "rotation": ico.rotation,
        "snap": ico.snap,
    }


def params_to_dict(params: Params) -> dict[str, Any]:
    return {
        "version": SCHEMA_VERSION,
        "width": params.width,
        "height": params.height,
        "bg_mode": _enc_colour(params.bg_mode),
        "brush_width": params.brush_width,
        "brush_colour": _enc_colour(params.brush_colour),
        "line_style": str(params.line_style),
        "line_dash_offset": int(params.line_dash_offset),
        "grid_size": params.grid_size,
        "grid_colour": _enc_colour(params.grid_colour),
        "grid_visible": params.grid_visible,
        "output_file": str(params.output_file),
        "lines": [_enc_line(lin) for lin in params.lines],
        "labels": [_enc_label(lab) for lab in params.labels],
        "icons": [_enc_icon(ico) for ico in params.icons],
    }


# ---------- Decoders ----------


def _dec_colour(dic: dict[str, Any]) -> Colour:
    # allow either {"name": "..."} or full rgba dicts
    if isinstance(dic, str):
        return Cols.get(dic) or Cols.white
    return Colour(dic.get("name", "custom"), int(dic["r"]), int(dic["g"]), int(dic["b"]), int(dic.get("a", 255)))


def _dec_anchor(val: Any) -> Anchor:
    if isinstance(val, str):
        return Anchor.parse(val) or Anchor.C
    if isinstance(val, dict):
        return Anchor(val.get("value", "center"))
    return Anchor.C


def _dec_line(dic: dict[str, Any]) -> Line:
    from models.linestyle import LineStyle

    style_raw = dic.get("style", "solid")
    try:
        style = LineStyle(style_raw)
    except Exception:
        style = LineStyle.SOLID
    return Line(
        dic["x1"],
        dic["y1"],
        dic["x2"],
        dic["y2"],
        _dec_colour(dic["col"]),
        int(dic["width"]),
        CapStyle(dic.get("cap", "round")),
        style=style,
        dash_offset=int(dic.get("dash_offset", 0)),
    )


def _dec_label(dic: dict[str, Any]) -> Label:
    return Label(
        int(dic["x"]),
        int(dic["y"]),
        dic.get("text", ""),
        _dec_colour(dic["col"]),
        _dec_anchor(dic.get("anchor", Anchor.NW)),
        int(dic.get("size", 12)),
        int(dic.get("rotation", 0)),
        bool(dic.get("snap", True)),
    )


def _dec_icon(dic: dict[str, Any]) -> Icon:
    return Icon(
        int(dic["x"]),
        int(dic["y"]),
        dic.get("name", "signal"),
        _dec_colour(dic["col"]),
        _dec_anchor(dic.get("anchor", Anchor.SE)),
        int(dic.get("size", 16)),
        int(dic.get("rotation", 0)),
        bool(dic.get("snap", True)),
    )


def dict_to_params(dic: dict[str, Any]) -> Params:
    v = int(dic.get("version", 0))
    if v != SCHEMA_VERSION:
        dic = _migrate(dic, v)

    from models.params import Params  # avoid cycles

    style_raw = dic.get("line_style", "solid")
    try:
        line_style = LineStyle(style_raw)
    except Exception:
        line_style = LineStyle.SOLID

    params = Params(
        width=int(dic["width"]),
        height=int(dic["height"]),
        bg_mode=_dec_colour(dic["bg_mode"]),
        brush_width=int(dic["brush_width"]),
        brush_colour=_dec_colour(dic["brush_colour"]),
        line_style=line_style,
        line_dash_offset=int(dic.get("line_dash_offset", 0)),
        grid_size=int(dic["grid_size"]),
        grid_colour=_dec_colour(dic["grid_colour"]),
        grid_visible=bool(dic["grid_visible"]),
        output_file=Path(dic.get("output_file", "output")),
        lines=[_dec_line(lin) for lin in dic.get("lines", [])],
        labels=[_dec_label(lab) for lab in dic.get("labels", [])],
        icons=[_dec_icon(ico) for ico in dic.get("icons", [])],
    )
    return params


# ---------- Public API ----------


class IO:
    @staticmethod
    def save_params(params: Params, path: Path):
        path.write_text(json.dumps(params_to_dict(params), indent=4))

    @staticmethod
    def load_params(path: Path) -> Params:
        raw = json.loads(path.read_text()) if path.exists() else {"version": SCHEMA_VERSION}
        return dict_to_params(raw)


# ---------- Migration hook ----------


def _migrate(data: dict[str, Any], from_version: int) -> dict[str, Any]:
    """Migrate older payloads to current schema."""
    dic = dict(data)
    # ver = int(from_version)

    # example future migrations:
    # if v < 1:
    #     ...
    #     v = 1
    # if v < 2:
    #     ...
    #     v = 2

    dic["version"] = SCHEMA_VERSION
    return dic

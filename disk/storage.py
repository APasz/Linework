from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from models.params import SCHEMA_VERSION, Params


def dict_to_params(dic: dict[str, Any]) -> Params:
    v = int(dic.get("version", 0))
    if v != SCHEMA_VERSION:
        dic = _migrate(dic, v)
    return Params.model_validate(dic)


class IO:
    @staticmethod
    def save_params(params: Params, path: Path):
        path.write_text(params.model_dump_json(indent=4, exclude_none=True), encoding="utf-8")

    @staticmethod
    def load_params(path: Path) -> Params:
        raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"version": SCHEMA_VERSION}
        return dict_to_params(raw)


def _migrate(data: dict[str, Any], from_version: int) -> dict[str, Any]:
    dic = dict(data)
    dic["version"] = SCHEMA_VERSION
    return dic

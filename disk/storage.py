"""Persistence helpers for Linework settings and projects."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from models.params import SCHEMA_VERSION, Params
from models.version import get_app_version

DEFAULT_SETTINGS_NAME = "linework.settings"


def default_settings_path() -> Path:
    """Return the default per-user settings path."""
    return Path.home() / DEFAULT_SETTINGS_NAME


def dict_to_params(dic: dict[str, Any]) -> Params:
    """Coerce a settings dictionary into Params, migrating if needed."""
    v = int(dic.get("version", 0))
    if v != SCHEMA_VERSION:
        dic = _migrate(dic, v)
    return Params.model_validate(dic)


class IO:
    """Read/write Params and defaults to disk."""

    @staticmethod
    def save_params(params: Params, path: Path) -> None:
        """Write params to disk at the given path."""
        payload = params.model_copy(update={"app_version": get_app_version()})
        path.write_text(payload.model_dump_json(indent=4, exclude_none=True), encoding="utf-8")

    @staticmethod
    def load_params(path: Path) -> Params:
        """Load params from disk, returning defaults when missing."""
        raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"version": SCHEMA_VERSION}
        return dict_to_params(raw)

    @staticmethod
    def save_defaults(params: Params, path: Path | None = None) -> Path:
        """Write defaults to disk and return the written path."""
        target = path or default_settings_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(params.profile_dump_json(), encoding="utf-8")
        return target

    @staticmethod
    def load_defaults(path: Path | None = None) -> Params:
        """Load defaults from disk, falling back to defaults path."""
        target = path or default_settings_path()
        return IO.load_params(target)


def _migrate(data: dict[str, Any], from_version: int) -> dict[str, Any]:
    dic = dict(data)
    dic["version"] = SCHEMA_VERSION
    return dic

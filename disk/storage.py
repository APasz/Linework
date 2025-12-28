"""Persistence helpers for Linework settings and projects."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from models.params import SCHEMA_VERSION, Params
from models.version import get_app_version

DEFAULT_SETTINGS_NAME = "linework.settings"
SETTINGS_ENV_VAR = "LINEWORK_SETTINGS_PATH"
INSTALLED_MARKER_NAME = "linework.installed"
_SETTINGS_OVERRIDE: Path | None = None


def set_default_settings_path(path: str | Path | None) -> None:
    """Override the default settings path for this session."""
    global _SETTINGS_OVERRIDE
    _SETTINGS_OVERRIDE = _coerce_settings_path(path) if path else None


def default_settings_path() -> Path:
    """Return the default per-user settings path."""
    if _SETTINGS_OVERRIDE is not None:
        return _SETTINGS_OVERRIDE
    env_path = os.environ.get(SETTINGS_ENV_VAR, "").strip()
    if env_path:
        return _coerce_settings_path(env_path)
    standard = _standard_settings_path()
    legacy = _legacy_settings_path()
    if _installed_marker_path(standard).exists():
        if standard.exists():
            return standard
        if legacy.exists():
            return legacy
        return standard
    portable = _portable_settings_path()
    if portable is not None:
        return portable
    if not standard.exists() and legacy.exists():
        return legacy
    return standard


def _coerce_settings_path(value: str | Path) -> Path:
    """Coerce a settings path into a file path.

    Args;
        value: The input path or directory.

    Returns;
        The resolved settings file path.
    """
    path = Path(value).expanduser()
    raw = str(value)
    if path.exists() and path.is_dir():
        return path / DEFAULT_SETTINGS_NAME
    if raw.endswith(("/", "\\")):
        return path / DEFAULT_SETTINGS_NAME
    return path


def _legacy_settings_path() -> Path:
    """Return the legacy settings path.

    Returns;
        The legacy settings file path.
    """
    return Path.home() / DEFAULT_SETTINGS_NAME


def _portable_settings_path() -> Path | None:
    """Return the portable settings path when available.

    Returns;
        The portable settings path, or None when unavailable.
    """
    root = _runtime_dir()
    if not _dir_writable(root):
        return None
    return root / DEFAULT_SETTINGS_NAME


def _normalize_storage_mode(mode: str) -> str:
    """Normalise storage mode strings.

    Args;
        mode: The input mode string.

    Returns;
        The normalised mode.
    """
    cleaned = str(mode or "").strip().lower()
    if cleaned.startswith("port"):
        return "portable"
    if cleaned in {"standard", "installed", "normal", "default"}:
        return "standard"
    return "standard"


def standard_settings_path() -> Path:
    """Return the platform-standard settings path."""
    return _standard_settings_path()


def portable_settings_path() -> Path:
    """Return the runtime-folder portable settings path."""
    return _runtime_dir() / DEFAULT_SETTINGS_NAME


def installed_marker_path() -> Path:
    """Return the path to the installed marker file."""
    return _installed_marker_path(_standard_settings_path())


def mark_installed() -> Path:
    """Create the installed marker file."""
    target = installed_marker_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("installed\n", encoding="utf-8")
    return target


def clear_installed_marker() -> None:
    """Remove the installed marker file if present."""
    marker = installed_marker_path()
    try:
        marker.unlink()
    except FileNotFoundError:
        return
    except OSError:
        # Best-effort cleanup: ignore permissions or locked files.
        return


def can_use_portable() -> bool:
    """Return True when the runtime dir is writable for portable settings."""
    return _dir_writable(_runtime_dir())


def current_storage_mode() -> str:
    """Return the active storage mode."""
    current = default_settings_path()
    portable = portable_settings_path()
    try:
        if current.resolve() == portable.resolve():
            return "portable"
    except OSError:
        if str(current) == str(portable):
            return "portable"
    return "standard"


def set_storage_mode(mode: str) -> Path:
    """Set storage mode and return the target settings path."""
    normalized = _normalize_storage_mode(mode)
    if normalized == "portable":
        if not can_use_portable():
            raise RuntimeError("Portable mode is unavailable: app folder is not writable.")
        clear_installed_marker()
        return portable_settings_path()
    mark_installed()
    return standard_settings_path()


def _dir_writable(path: Path) -> bool:
    """Return True if a directory is writable.

    Args;
        path: The directory path.

    Returns;
        True if the directory is writable.
    """
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    return os.access(path, os.W_OK)


def _runtime_dir() -> Path:
    """Return the runtime directory for portable storage.

    Returns;
        The runtime directory path.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    if sys.argv and sys.argv[0]:
        return Path(sys.argv[0]).resolve().parent
    return Path.cwd()


def _standard_settings_path() -> Path:
    """Return the platform-standard settings path.

    Returns;
        The standard settings file path.
    """
    try:
        from PySide6 import QtCore
    except ImportError:
        return _legacy_settings_path()
    base = QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.StandardLocation.AppConfigLocation)
    if not base:
        return _legacy_settings_path()
    return Path(base) / DEFAULT_SETTINGS_NAME


def _installed_marker_path(standard_path: Path) -> Path:
    """Return the installed marker path for a settings directory.

    Args;
        standard_path: The standard settings path.

    Returns;
        The marker file path.
    """
    return standard_path.parent / INSTALLED_MARKER_NAME


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
        path.write_text(
            payload.model_dump_json(
                indent=4,
                exclude_none=True,
                exclude={
                    "default_project",
                    "storage_mode",
                    "window_width",
                    "window_height",
                    "remember_window_size",
                    "auto_expand_window",
                    "auto_shrink_window",
                },
            ),
            encoding="utf-8",
        )

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
    """Migrate settings data to the current schema version.

    Args;
        data: The input settings data.
        from_version: The source schema version.

    Returns;
        The migrated settings data.
    """
    dic = dict(data)
    dic["version"] = SCHEMA_VERSION
    return dic

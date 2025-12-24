from __future__ import annotations

import os
import subprocess
from pathlib import Path

_VERSION: str | None = None


def get_app_version() -> str:
    global _VERSION
    if _VERSION is not None:
        return _VERSION

    env_version = os.getenv("LINEWORK_VERSION", "").strip()
    if env_version:
        _VERSION = env_version
        return _VERSION

    try:
        from models._version import __version__  # type: ignore[import-not-found]

        file_version = str(__version__).strip()
        if file_version:
            _VERSION = file_version
            return _VERSION
    except Exception:
        pass

    git_version = _version_from_git()
    if git_version:
        _VERSION = git_version
        return _VERSION

    _VERSION = "dev"
    return _VERSION


def _version_from_git() -> str | None:
    repo_root = _find_repo_root(Path(__file__).resolve())
    if not repo_root:
        return None

    def _run_git(args: list[str]) -> str | None:
        try:
            output = subprocess.check_output(
                ["git", *args],
                cwd=repo_root,
                stderr=subprocess.DEVNULL,
                text=True,
            )
        except Exception:
            return None
        return output.strip()

    tag = _run_git(["describe", "--tags", "--abbrev=0"])
    if tag:
        return tag

    count = _run_git(["rev-list", "--count", "HEAD"])
    if count:
        return f"v0.{count}"

    return None


def _find_repo_root(path: Path) -> Path | None:
    for parent in path.parents:
        if (parent / ".git").exists():
            return parent
    return None

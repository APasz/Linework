"""Entry point for Linework."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from disk.storage import set_default_settings_path
from qt.app import QtApp

MIN_PYTHON: tuple[int, int] = (3, 13)


def _pick_project_path(args: list[str]) -> Path | None:
    candidates = [arg for arg in args if arg and not arg.startswith("-")]
    for raw in reversed(candidates):
        path = Path(raw)
        if path.suffix.lower() == ".linework" or path.exists():
            return path
    return None


def _parse_args(argv: list[str]) -> tuple[Path | None, Path | None, list[str]]:
    settings_path: Path | None = None
    qt_args = [argv[0]] if argv else ["linework"]
    it = iter(argv[1:])
    for arg in it:
        if arg in ("--settings", "--settings-path"):
            try:
                settings_path = Path(next(it))
            except StopIteration:
                break
        elif arg.startswith("--settings="):
            value = arg.split("=", 1)[1]
            if value:
                settings_path = Path(value)
        else:
            qt_args.append(arg)
    project_path = _pick_project_path(qt_args[1:])
    return settings_path, project_path, qt_args


def main() -> None:
    """Run Linework"""
    if sys.version_info < MIN_PYTHON:
        raise RuntimeError("Linework requires Python 3.13+")

    settings_path, project_path, qt_args = _parse_args(sys.argv)
    if settings_path is not None:
        set_default_settings_path(settings_path)
    app = QtWidgets.QApplication(qt_args)
    QtCore.QCoreApplication.setOrganizationName("Linework")
    QtCore.QCoreApplication.setApplicationName("Linework")
    QtGui.QGuiApplication.setDesktopFileName("linework")
    window = QtApp(project_path=project_path)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

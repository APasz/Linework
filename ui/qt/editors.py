"""Qt edit dialog wrapper for model edit plans."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6 import QtWidgets

from core.edit_plans import EditPlans
from models.geo import BuiltinIcon, Label, PictureIcon
from ui.qt.edit_dialog import QtGenericEditDialog

if TYPE_CHECKING:
    from qt.app import QtApp


class QtEditors:
    """Qt-facing editor entry point."""

    def __init__(self, app: QtApp) -> None:
        """Create the editors helper.

        Args;
            app: The parent Qt app.
        """
        self.app = app
        self._plans = EditPlans(app)

    def apply_label_defaults(self, lab: Label) -> None:
        """Apply label defaults for the current session.

        Args;
            lab: The label to update.
        """
        self._plans.apply_label_defaults(lab)

    def apply_icon_defaults(self, ico: BuiltinIcon | PictureIcon) -> None:
        """Apply icon defaults for the current session.

        Args;
            ico: The icon to update.
        """
        self._plans.apply_icon_defaults(ico)

    def edit(self, app: QtApp, obj: Any) -> bool:
        """Open an edit dialog for a model object.

        Args;
            app: The parent Qt app.
            obj: The object to edit.

        Returns;
            True if edits were applied.
        """
        plan = self._plans.plan_for(obj)
        schema = self._plans.schema_for_plan(plan)
        dlg = QtGenericEditDialog(app, plan.title, schema, plan.init(obj))
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return False
        result = getattr(dlg, "result_data", None)
        if not result:
            return False
        plan.apply(obj, result)
        return True

"""Hit testing helpers for Qt scenes."""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from core.layers import Hit, HitKind
from qt.scene_data import DATA_HANDLE, DATA_IDX, DATA_KIND


def _item_hit_data(item: QtWidgets.QGraphicsItem) -> tuple[str | None, int | None, str | None]:
    kind = item.data(DATA_KIND)
    idx = item.data(DATA_IDX)
    handle = item.data(DATA_HANDLE)
    return (kind, idx, handle)


def hit_test(scene: QtWidgets.QGraphicsScene, x: int, y: int, radius: int = 3) -> Hit | None:
    """Pick the nearest valid hit around a coordinate.

    Args;
        scene: The scene to test.
        x: The x coordinate.
        y: The y coordinate.
        radius: Search radius.

    Returns;
        The hit result, or None.
    """
    rect = QtCore.QRectF(x - radius, y - radius, radius * 2, radius * 2)
    items = scene.items(rect, QtCore.Qt.ItemSelectionMode.IntersectsItemShape, QtCore.Qt.SortOrder.DescendingOrder)

    for item in items:
        kind, idx, handle = _item_hit_data(item)
        if kind is None or idx is None:
            parent = item.parentItem()
            if parent is not None:
                kind, idx, handle = _item_hit_data(parent)
        if kind is None or idx is None:
            continue
        try:
            hk = HitKind(kind)
        except ValueError:
            continue
        point = str(handle) if handle is not None else None
        return Hit(kind=hk, tag_idx=int(idx), point=point)

    return None

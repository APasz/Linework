"""Icon picker dialog for builtin and imported icons."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image
from PySide6 import QtCore, QtGui, QtWidgets

from models.assets import IconName, _builtin_icon_plan, _open_rgba, probe_wh
from models.geo import IconSource, IconType

if TYPE_CHECKING:
    from qt.app import QtApp


_CAP_STYLES = {
    "round": QtCore.Qt.PenCapStyle.RoundCap,
    "butt": QtCore.Qt.PenCapStyle.FlatCap,
    "projecting": QtCore.Qt.PenCapStyle.SquareCap,
}
_JOIN_STYLES = {
    "miter": QtCore.Qt.PenJoinStyle.MiterJoin,
    "round": QtCore.Qt.PenJoinStyle.RoundJoin,
    "bevel": QtCore.Qt.PenJoinStyle.BevelJoin,
}


def _qimage_from_pil(image: Image.Image) -> QtGui.QImage:
    """Convert a PIL image into a detached QImage.

    Args;
        image: The source PIL image.

    Returns;
        A copy-backed QImage.
    """
    rgba = image.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    qimage = QtGui.QImage(data, rgba.width, rgba.height, QtGui.QImage.Format.Format_RGBA8888)
    return qimage.copy()


def _pen_from_entry(entry: dict[str, Any]) -> QtGui.QPen:
    """Build a pen from a drawing plan entry.

    Args;
        entry: The plan entry containing stroke metadata.

    Returns;
        The configured pen, or a NoPen when stroke is missing.
    """
    stroke = entry.get("stroke")
    if not stroke:
        return QtGui.QPen(QtCore.Qt.PenStyle.NoPen)
    pen = QtGui.QPen(QtGui.QColor(str(stroke)))
    pen.setWidth(max(1, int(entry.get("width", 1))))
    cap = entry.get("cap")
    if cap:
        pen.setCapStyle(_CAP_STYLES.get(cap, QtCore.Qt.PenCapStyle.RoundCap))
    join = entry.get("join")
    if join:
        pen.setJoinStyle(_JOIN_STYLES.get(join, QtCore.Qt.PenJoinStyle.RoundJoin))
    dash = entry.get("dash")
    if dash:
        pen.setDashPattern([float(x) for x in dash])
    return pen


def _brush_from_entry(entry: dict[str, Any]) -> QtGui.QBrush:
    """Build a brush from a drawing plan entry.

    Args;
        entry: The plan entry containing fill metadata.

    Returns;
        The configured brush.
    """
    fill = entry.get("fill")
    if not fill:
        return QtGui.QBrush(QtCore.Qt.BrushStyle.NoBrush)
    return QtGui.QBrush(QtGui.QColor(str(fill)))


def _builtin_pixmap(name: IconName, size: int, colour: QtGui.QColor) -> QtGui.QPixmap:
    """Render a builtin icon preview pixmap.

    Args;
        name: The builtin icon name.
        size: The preview size in pixels.
        colour: The preview colour.

    Returns;
        The rendered pixmap.
    """
    plan = _builtin_icon_plan(name, size, colour.name())
    pixmap = QtGui.QPixmap(size, size)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
    centre = size / 2.0

    for kind, entry in plan:
        pen = _pen_from_entry(entry)
        brush = _brush_from_entry(entry)
        painter.setPen(pen)
        painter.setBrush(brush)
        if kind == "line":
            painter.drawLine(
                QtCore.QPointF(centre + entry["x1"], centre + entry["y1"]),
                QtCore.QPointF(centre + entry["x2"], centre + entry["y2"]),
            )
        elif kind == "circle":
            r = entry["r"]
            painter.drawEllipse(
                QtCore.QPointF(centre + entry["cx"], centre + entry["cy"]),
                r,
                r,
            )
        elif kind == "rect":
            painter.drawRect(
                QtCore.QRectF(
                    centre + entry["x"],
                    centre + entry["y"],
                    entry["w"],
                    entry["h"],
                )
            )
        elif kind == "polyline":
            points = [QtCore.QPointF(centre + x, centre + y) for x, y in entry["points"]]
            poly = QtGui.QPolygonF(points)
            if entry.get("closed"):
                painter.drawPolygon(poly)
            else:
                painter.drawPolyline(poly)

    painter.end()
    return pixmap


def _picture_pixmap(path: Path, size: int) -> QtGui.QPixmap:
    """Render a picture icon preview pixmap.

    Args;
        path: The image path.
        size: The preview size in pixels.

    Returns;
        The rendered pixmap.
    """
    w, h = probe_wh(path)
    if w <= 0 or h <= 0:
        w = h = size
    scale = min(size / w, size / h)
    tw = max(1, int(round(w * scale)))
    th = max(1, int(round(h * scale)))
    image = _open_rgba(path, tw, th)
    qimage = _qimage_from_pil(image)

    pixmap = QtGui.QPixmap(size, size)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)
    painter.drawImage(int((size - tw) / 2), int((size - th) / 2), qimage)
    painter.end()
    return pixmap


class QtIconPickerDialog(QtWidgets.QDialog):
    """Tabbed icon picker dialog."""

    def __init__(self, app: QtApp, initial: IconSource | None = None) -> None:
        """Create the icon picker dialog.

        Args;
            app: The parent Qt app.
            initial: Optional icon to preselect.
        """
        super().__init__(app)
        self._app = app
        self._selected: IconSource | None = None
        self._icon_px = 36

        self.setWindowTitle("Choose icon")
        self.setMinimumSize(520, 480)

        layout = QtWidgets.QVBoxLayout(self)
        self._tabs = QtWidgets.QTabWidget(self)
        layout.addWidget(self._tabs)

        self._builtin_list = self._make_icon_list()
        builtin_tab = QtWidgets.QWidget()
        builtin_layout = QtWidgets.QVBoxLayout(builtin_tab)
        builtin_layout.addWidget(self._builtin_list)
        self._tabs.addTab(builtin_tab, "Built-in")

        self._picture_list = self._make_icon_list()
        pic_tab = QtWidgets.QWidget()
        pic_layout = QtWidgets.QVBoxLayout(pic_tab)
        top_row = QtWidgets.QHBoxLayout()
        top_row.addStretch(1)
        self._import_btn = QtWidgets.QPushButton("Import...")
        self._import_btn.clicked.connect(self._import_pictures)
        top_row.addWidget(self._import_btn)
        pic_layout.addLayout(top_row)
        pic_layout.addWidget(self._picture_list)
        self._tabs.addTab(pic_tab, "Pictures")

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._ok_button = buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        if self._ok_button is not None:
            self._ok_button.setEnabled(False)

        self._builtin_list.itemSelectionChanged.connect(self._on_builtin_selected)
        self._picture_list.itemSelectionChanged.connect(self._on_picture_selected)
        self._builtin_list.itemDoubleClicked.connect(lambda _item: self.accept())
        self._picture_list.itemDoubleClicked.connect(lambda _item: self.accept())

        self._load_builtins()
        self._load_pictures()
        self._select_initial(initial)

    def selected_source(self) -> IconSource | None:
        return self._selected

    def _make_icon_list(self) -> QtWidgets.QListWidget:
        """Create the list widget configured for icon previews.

        Returns;
            The configured list widget.
        """
        lst = QtWidgets.QListWidget()
        lst.setViewMode(QtWidgets.QListView.ViewMode.IconMode)
        lst.setResizeMode(QtWidgets.QListView.ResizeMode.Adjust)
        lst.setMovement(QtWidgets.QListView.Movement.Static)
        lst.setIconSize(QtCore.QSize(self._icon_px, self._icon_px))
        lst.setGridSize(QtCore.QSize(self._icon_px + 28, self._icon_px + 32))
        lst.setSpacing(6)
        lst.setWordWrap(True)
        lst.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        return lst

    def _load_builtins(self) -> None:
        """Populate the builtin icon list."""
        self._builtin_list.clear()
        colour = self.palette().color(QtGui.QPalette.ColorRole.Text)
        for name in IconName:
            item = QtWidgets.QListWidgetItem(name.value)
            item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, name.value)
            item.setIcon(QtGui.QIcon(_builtin_pixmap(name, self._icon_px, colour)))
            self._builtin_list.addItem(item)

    def _load_pictures(self, *, select: list[Path] | None = None) -> None:
        """Populate the picture icon list.

        Args;
            select: Optional list of paths to select after loading.
        """
        self._picture_list.clear()
        pics = self._app.asset_lib.list_pictures() or []
        selected_names = {p.name for p in select or []}
        selected_item: QtWidgets.QListWidgetItem | None = None
        for path in pics:
            item = QtWidgets.QListWidgetItem(path.name)
            item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, str(path))
            item.setIcon(QtGui.QIcon(_picture_pixmap(path, self._icon_px)))
            self._picture_list.addItem(item)
            if path.name in selected_names:
                selected_item = item
        if selected_item is not None:
            selected_item.setSelected(True)
            self._picture_list.scrollToItem(selected_item)

    def _select_initial(self, initial: IconSource | None) -> None:
        """Select the initial icon in the picker UI.

        Args;
            initial: The icon source to preselect.
        """
        if initial is None:
            return
        if initial.kind is IconType.builtin and initial.name:
            name = initial.name.value
            for i in range(self._builtin_list.count()):
                item = self._builtin_list.item(i)
                if item and item.data(QtCore.Qt.ItemDataRole.UserRole) == name:
                    self._tabs.setCurrentIndex(0)
                    item.setSelected(True)
                    self._builtin_list.scrollToItem(item)
                    self._selected = IconSource.builtin(initial.name)
                    if self._ok_button is not None:
                        self._ok_button.setEnabled(True)
                    return
        if initial.kind is IconType.picture and initial.src:
            src = Path(initial.src)
            for i in range(self._picture_list.count()):
                item = self._picture_list.item(i)
                if item and Path(str(item.data(QtCore.Qt.ItemDataRole.UserRole))).name == src.name:
                    self._tabs.setCurrentIndex(1)
                    item.setSelected(True)
                    self._picture_list.scrollToItem(item)
                    self._selected = IconSource.picture(src)
                    if self._ok_button is not None:
                        self._ok_button.setEnabled(True)
                    return

    def _import_pictures(self) -> None:
        """Import picture files and refresh the list."""
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "Import pictures",
            str(self._app.project_dir()),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp *.svg)",
        )
        if not paths:
            return
        imported = self._app.asset_lib.import_files([Path(p) for p in paths])
        if imported:
            self._load_pictures(select=imported)
            self._tabs.setCurrentIndex(1)

    def _on_builtin_selected(self) -> None:
        """Handle builtin icon selection changes."""
        items = self._builtin_list.selectedItems()
        if not items:
            if self._ok_button is not None and not self._picture_list.selectedItems():
                self._ok_button.setEnabled(False)
            return
        self._picture_list.blockSignals(True)
        self._picture_list.clearSelection()
        self._picture_list.blockSignals(False)
        name = items[0].data(QtCore.Qt.ItemDataRole.UserRole)
        try:
            self._selected = IconSource.builtin(IconName(str(name)))
        except ValueError:
            self._selected = None
        if self._ok_button is not None:
            self._ok_button.setEnabled(self._selected is not None)

    def _on_picture_selected(self) -> None:
        """Handle picture icon selection changes."""
        items = self._picture_list.selectedItems()
        if not items:
            if self._ok_button is not None and not self._builtin_list.selectedItems():
                self._ok_button.setEnabled(False)
            return
        self._builtin_list.blockSignals(True)
        self._builtin_list.clearSelection()
        self._builtin_list.blockSignals(False)
        path = items[0].data(QtCore.Qt.ItemDataRole.UserRole)
        if path:
            self._selected = IconSource.picture(Path(str(path)))
        else:
            self._selected = None
        if self._ok_button is not None:
            self._ok_button.setEnabled(self._selected is not None)

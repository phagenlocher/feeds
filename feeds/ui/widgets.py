"""Reusable tree widget with hand cursor and font management."""

import logging
from enum import IntEnum, auto
from typing import assert_never

from PySide6 import QtCore, QtGui, QtWidgets

ItemTypeRole: int = QtCore.Qt.ItemDataRole.UserRole + 1
FeedIndexRole: int = QtCore.Qt.ItemDataRole.UserRole + 2
DataRole: int = QtCore.Qt.ItemDataRole.UserRole + 3
TagsRole: int = QtCore.Qt.ItemDataRole.UserRole + 4

log: logging.Logger = logging.getLogger(__name__)


class ItemType(IntEnum):
    """Item types in the tree widget."""

    FEED = auto()
    ENTRY = auto()


class FeedTreeWidget(QtWidgets.QTreeWidget):
    """Tree widget with hand cursor on items and font-scaling support."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Build tree widget with hand cursor and font management."""
        super().__init__(parent)
        self._font_size: int = 0
        self.setHeaderHidden(True)
        self.setStyleSheet(
            "QTreeWidget::item:selected { background-color: #3478bf; color: white; }"
        )
        self.setMouseTracking(True)
        self.viewport().installEventFilter(self)
        self.setAnimated(True)

    @staticmethod
    def _item_height(size: int, item_type: ItemType | None = None) -> int:
        match item_type:
            case ItemType.FEED:
                return max(28, size * 2 + 4)
            case ItemType.ENTRY | None:
                return max(46, size * 4)
            case _ as unreachable:
                assert_never(unreachable)

    def set_font_size(self, size: int) -> None:
        """Set font size and reapply with bold and height to all items."""
        self._font_size = size

        def _visit(item: QtWidgets.QTreeWidgetItem) -> None:
            bold = item.font(0).bold()
            item_type: ItemType | None = item.data(0, ItemTypeRole)
            item.setSizeHint(0, QtCore.QSize(0, self._item_height(size, item_type)))
            self.apply_font(item, bold)
            for i in range(item.childCount()):
                child: QtWidgets.QTreeWidgetItem | None = item.child(i)
                if child:
                    _visit(child)

        for i in range(self.topLevelItemCount()):
            item: QtWidgets.QTreeWidgetItem | None = self.topLevelItem(i)
            if item:
                _visit(item)
        self.doItemsLayout()

    @staticmethod
    def _make_font(font_size: int, bold: bool = False) -> QtGui.QFont:
        font = QtGui.QFont()
        font.setPointSize(
            font_size
            if font_size > 0
            else QtWidgets.QApplication.instance().font().pointSize()
        )
        font.setBold(bold)
        return font

    def apply_font(self, item: QtWidgets.QTreeWidgetItem, bold: bool) -> None:
        """Set the item's font to the configured size and the given bold state."""
        item.setFont(0, self._make_font(self._font_size, bold))

    def build_item(
        self,
        title: str,
        subtitle: str,
        bold: bool,
        item_type: ItemType | None = None,
    ) -> QtWidgets.QTreeWidgetItem:
        """Build QTreeWidgetItem with title, subtitle, bold, and size hint."""
        size = (
            self._font_size
            if self._font_size > 0
            else QtWidgets.QApplication.instance().font().pointSize()
        )
        item = QtWidgets.QTreeWidgetItem()
        item.setText(0, title)
        item.setSizeHint(0, QtCore.QSize(0, self._item_height(size, item_type)))
        item.setData(0, QtCore.Qt.ItemDataRole.UserRole, subtitle)
        self.apply_font(item, bold)
        return item

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:  # noqa: N802
        """Set PointingHandCursor over items, ArrowCursor over empty space."""
        if (
            event.type() == QtCore.QEvent.Type.MouseMove
            and isinstance(event, QtGui.QMouseEvent)
            and obj is self.viewport()
        ):
            item: QtWidgets.QTreeWidgetItem | None = self.itemAt(
                event.position().toPoint()
            )
            cursor = (
                QtCore.Qt.CursorShape.PointingHandCursor
                if item
                else QtCore.Qt.CursorShape.ArrowCursor
            )
            if self.viewport().cursor().shape() != cursor:
                self.viewport().setCursor(cursor)
        return super().eventFilter(obj, event)

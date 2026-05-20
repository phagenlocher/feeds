"""Reusable list widget with hand cursor and font management."""

from PySide6 import QtCore, QtGui, QtWidgets


class FeedListWidget(QtWidgets.QListWidget):
    """List widget with hand cursor on items and font-scaling support."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._font_size: int = 0
        self.setUniformItemSizes(True)
        self.setStyleSheet(
            "QListWidget::item:selected { background-color: #3478bf; color: white; }"
        )
        self.setMouseTracking(True)
        self.viewport().installEventFilter(self)

    def set_font_size(self, size: int) -> None:
        self._font_size = size
        for i in range(self.count()):
            item = self.item(i)
            if item is None:
                continue
            bold = item.font().bold()
            item.setSizeHint(QtCore.QSize(0, max(46, size * 4)))
            self.apply_font(item, bold)
        self.doItemsLayout()

    @staticmethod
    def _make_font(font_size: int, bold: bool = False) -> QtGui.QFont:
        font = QtGui.QFont()
        font.setPointSize(font_size if font_size > 0 else 12)
        font.setBold(bold)
        return font

    def apply_font(self, item: QtWidgets.QListWidgetItem, bold: bool) -> None:
        item.setFont(self._make_font(self._font_size, bold))

    def build_item(
        self, title: str, subtitle: str, bold: bool
    ) -> QtWidgets.QListWidgetItem:
        size = self._font_size if self._font_size > 0 else 12
        item = QtWidgets.QListWidgetItem(title)
        item.setSizeHint(QtCore.QSize(0, max(46, size * 4)))
        item.setData(QtCore.Qt.ItemDataRole.UserRole, subtitle)
        self.apply_font(item, bold)
        return item

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if (
            event.type() == QtCore.QEvent.Type.MouseMove
            and isinstance(event, QtGui.QMouseEvent)
            and obj is self.viewport()
        ):
            item = self.itemAt(event.position().toPoint())
            cursor = (
                QtCore.Qt.CursorShape.PointingHandCursor
                if item
                else QtCore.Qt.CursorShape.ArrowCursor
            )
            if self.viewport().cursor().shape() != cursor:
                self.viewport().setCursor(cursor)
        return super().eventFilter(obj, event)

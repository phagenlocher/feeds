"""Custom item delegate for two-line list items."""

from typing import assert_never

from PySide6 import QtCore, QtGui, QtWidgets

from feeds.ui.widgets import ItemType, ItemTypeRole


class TwoLineRenderer(QtWidgets.QStyledItemDelegate):
    """Renders each item as a bold/normal title with a gray subtitle below."""

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
    ) -> None:
        """Draw selection highlight, then render inline or two-line layout."""
        painter.save()

        if option.state & QtWidgets.QStyle.StateFlag.State_Selected:
            painter.fillRect(
                option.rect,
                option.palette.brush(QtGui.QPalette.ColorRole.Highlight),
            )

        title: str = index.data(QtCore.Qt.ItemDataRole.DisplayRole) or ""
        subtitle: str = index.data(QtCore.Qt.ItemDataRole.UserRole) or ""

        font: QtGui.QFont = index.data(QtCore.Qt.ItemDataRole.FontRole)
        if font is None:
            font = option.font

        selected = bool(option.state & QtWidgets.QStyle.StateFlag.State_Selected)
        text_color = (
            option.palette.color(QtGui.QPalette.ColorRole.HighlightedText)
            if selected
            else option.palette.color(QtGui.QPalette.ColorRole.WindowText)
        )
        muted_color = (
            option.palette.color(QtGui.QPalette.ColorRole.HighlightedText)
            if selected
            else QtGui.QColor("#888888")
        )

        item_type: ItemType | None = index.data(ItemTypeRole)

        match item_type:
            case ItemType.FEED:
                self._paint_inline(
                    painter, option, font, title, subtitle, text_color, muted_color
                )
            case ItemType.ENTRY | None:
                self._paint_two_line(
                    painter, option, font, title, subtitle, text_color, muted_color
                )
            case _ as unreachable:
                assert_never(unreachable)

        painter.restore()

    @staticmethod
    def _paint_inline(
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        font: QtGui.QFont,
        title: str,
        subtitle: str,
        text_color: QtGui.QColor,
        muted_color: QtGui.QColor,
    ) -> None:
        r = option.rect.adjusted(4, 0, -4, 0)

        painter.setFont(font)
        painter.setPen(text_color)
        painter.drawText(
            r,
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter,
            title,
        )

        if subtitle:
            sep = " \u00b7 "
            label = f"{sep}{subtitle}"
            tw = painter.fontMetrics().horizontalAdvance(title)
            sr = QtCore.QRect(
                r.x() + tw,
                r.y(),
                r.width() - tw,
                r.height(),
            )
            painter.setPen(muted_color)
            painter.drawText(
                sr,
                QtCore.Qt.AlignmentFlag.AlignLeft
                | QtCore.Qt.AlignmentFlag.AlignVCenter,
                label,
            )

    @staticmethod
    def _paint_two_line(
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        font: QtGui.QFont,
        title: str,
        subtitle: str,
        text_color: QtGui.QColor,
        muted_color: QtGui.QColor,
    ) -> None:
        half = option.rect.height() // 2
        painter.setFont(font)
        painter.setPen(text_color)
        painter.drawText(
            option.rect.adjusted(4, 3, -4, -(half)),
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignBottom,
            title,
        )

        if subtitle:
            sub_font = QtGui.QFont(font)
            sub_font.setPointSize(max(6, font.pointSize() - 3))
            painter.setFont(sub_font)
            painter.setPen(muted_color)
            painter.drawText(
                option.rect.adjusted(4, half, -4, -3),
                QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop,
                subtitle,
            )

    def sizeHint(  # noqa: N802
        self,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
    ) -> QtCore.QSize:
        """Return QSize with height based on font size and item type (feed vs entry)."""
        font: QtGui.QFont = index.data(QtCore.Qt.ItemDataRole.FontRole)
        if font is None:
            font = option.font
        item_type: ItemType | None = index.data(ItemTypeRole)
        match item_type:
            case ItemType.FEED:
                return QtCore.QSize(0, max(28, font.pointSize() * 2 + 4))
            case ItemType.ENTRY | None:
                return QtCore.QSize(0, max(46, font.pointSize() * 4))
            case _ as unreachable:
                assert_never(unreachable)

"""Custom item delegate for two-line list items with tag pill badges."""

import logging
from typing import assert_never

from PySide6 import QtCore, QtGui, QtWidgets

from feeds.ui.widgets import ItemType, ItemTypeRole, TagsRole

log: logging.Logger = logging.getLogger(__name__)

_TAG_PADDING_H: int = 8
_TAG_PADDING_V: int = 4
_TAG_MARGIN: int = 6
_TAG_RADIUS: int = 5
_DEFAULT_TAG_COLOR: str = "#888888"


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

        tags: list[tuple[str, str]] | None = index.data(TagsRole)

        item_type: ItemType | None = index.data(ItemTypeRole)

        match item_type:
            case ItemType.FEED:
                self._paint_inline(
                    painter,
                    option,
                    font,
                    title,
                    subtitle,
                    text_color,
                    muted_color,
                    tags,
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
        tags: list[tuple[str, str]] | None = None,
    ) -> None:
        r = option.rect.adjusted(4, 0, -4, 0)

        painter.setFont(font)
        painter.setPen(text_color)
        painter.drawText(
            r,
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter,
            title,
        )

        x_offset = r.x() + painter.fontMetrics().horizontalAdvance(title)

        if tags:
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
            tag_font = QtGui.QFont(font)
            tag_font.setPointSize(max(6, font.pointSize() - 2))
            tag_font.setWeight(QtGui.QFont.Weight.Normal)
            painter.setFont(tag_font)
            fm = painter.fontMetrics()
            tag_height = fm.height() + _TAG_PADDING_V * 2

            x_offset += _TAG_MARGIN
            remaining = r.right() - x_offset
            for tag_name, color_hex in tags:
                color = (
                    QtGui.QColor(color_hex)
                    if color_hex
                    else QtGui.QColor(_DEFAULT_TAG_COLOR)
                )
                tag_width = fm.horizontalAdvance(tag_name) + _TAG_PADDING_H * 2
                if tag_width > remaining:
                    ellipsis = "\u2026"
                    ellipsis_width = fm.horizontalAdvance(ellipsis) + _TAG_MARGIN
                    if ellipsis_width <= remaining:
                        painter.setPen(muted_color)
                        painter.drawText(
                            QtCore.QPoint(
                                x_offset, option.rect.center().y() + tag_height // 2 - 1
                            ),
                            ellipsis,
                        )
                    break

                tag_rect = QtCore.QRect(
                    x_offset,
                    option.rect.center().y() - tag_height // 2,
                    tag_width,
                    tag_height,
                )

                fill_color = QtGui.QColor(color)
                fill_color.setAlpha(50)
                border_pen = QtGui.QPen(color, 2.0)
                painter.setBrush(fill_color)
                painter.setPen(border_pen)
                painter.drawRoundedRect(tag_rect, _TAG_RADIUS, _TAG_RADIUS)

                text_color_pill = text_color
                painter.setPen(text_color_pill)
                painter.drawText(
                    tag_rect.adjusted(_TAG_PADDING_H, 0, -_TAG_PADDING_H, 0),
                    QtCore.Qt.AlignmentFlag.AlignLeft
                    | QtCore.Qt.AlignmentFlag.AlignVCenter,
                    tag_name,
                )

                x_offset += tag_width + _TAG_MARGIN
                remaining = r.right() - x_offset

            painter.setFont(font)

        if subtitle:
            sep = " \u00b7 "
            label = f"{sep}{subtitle}"
            subtitle_x = x_offset
            sr = QtCore.QRect(
                subtitle_x,
                r.y(),
                r.width() - (subtitle_x - r.x()),
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
        tags: list[tuple[str, str]] | None = index.data(TagsRole)
        has_tags = bool(tags)
        item_type: ItemType | None = index.data(ItemTypeRole)
        match item_type:
            case ItemType.FEED:
                base = max(28, font.pointSize() * 2 + 4)
                if has_tags:
                    tag_height = font.pointSize() + _TAG_PADDING_V * 2 + 4
                    base = max(base, tag_height + 12)
                return QtCore.QSize(0, base)
            case ItemType.ENTRY | None:
                return QtCore.QSize(0, max(46, font.pointSize() * 4))
            case _ as unreachable:
                assert_never(unreachable)

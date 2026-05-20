"""Custom item delegate for two-line list items."""

from PySide6 import QtCore, QtGui, QtWidgets


class TwoLineRenderer(QtWidgets.QStyledItemDelegate):
    """Renders each item as a bold/normal title with a gray subtitle below."""

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
    ) -> None:
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

        painter.restore()

    def sizeHint(
        self,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
    ) -> QtCore.QSize:
        font: QtGui.QFont = index.data(QtCore.Qt.ItemDataRole.FontRole)
        if font is None:
            font = option.font
        return QtCore.QSize(0, max(46, font.pointSize() * 4))

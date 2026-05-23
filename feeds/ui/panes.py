"""Left (FeedsPane) and right (EntriesPane) panes with context menus."""

import typing
import webbrowser
from dataclasses import replace
from enum import IntEnum, auto

from PySide6 import QtCore, QtWidgets

from feeds.models.feed import Entry, Feed, FeedReader
from feeds.ui.widgets import FeedListWidget


def _feed_label(feed: Feed, unread_count: int) -> str:
    return f"{feed.title} ({unread_count})" if unread_count else feed.title


class FeedMenuAction(IntEnum):
    COPY_URL = auto()
    READ_ALL = auto()
    REMOVE = auto()


class EntryMenuAction(IntEnum):
    MARK_READ = auto()
    MARK_UNREAD = auto()


class FeedsPane(QtWidgets.QWidget):
    """Left pane: list of feeds with context menu (Read All, Remove)."""

    feed_selected: QtCore.Signal = QtCore.Signal(int)
    read_all_requested: QtCore.Signal = QtCore.Signal(int)
    remove_feed_requested: QtCore.Signal = QtCore.Signal(int)

    def __init__(
        self,
        delegate: QtWidgets.QStyledItemDelegate,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.feeds: list[Feed] = []
        self.list: FeedListWidget

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QtWidgets.QLabel("Feeds"))

        self.list = FeedListWidget(self)
        self.list.setItemDelegate(delegate)
        self.list.itemClicked.connect(self._on_item_clicked)
        self.list.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self.list)

    def refresh(self, reader: FeedReader) -> None:
        self.feeds = list(reader.get_feeds())
        self.list.clear()
        for feed in self.feeds:
            unread = reader.get_unread_count(feed)
            title = _feed_label(feed, unread)
            ts = feed.last_updated.strftime("%Y-%m-%d") if feed.last_updated else ""
            self.list.addItem(self.list.build_item(title, ts, bool(unread)))

    def select(self, index: int | None) -> None:
        self.list.clearSelection()
        if index is not None:
            item = self.list.item(index)
            if item:
                self.list.setCurrentItem(item)

    def update_feed_font(self, index: int, reader: FeedReader) -> None:
        feed = self.feeds[index]
        unread = reader.get_unread_count(feed)
        item = self.list.item(index)
        if item is None:
            return
        item.setText(_feed_label(feed, unread))
        self.list.apply_font(item, bool(unread))

    def _on_item_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        self.feed_selected.emit(self.list.row(item))

    def _on_context_menu(self, pos: QtCore.QPoint) -> None:
        item = self.list.itemAt(pos)
        if item is None:
            return
        index = self.list.row(item)
        menu = QtWidgets.QMenu(self)

        act = menu.addAction("Mark all as read")
        act.setData(FeedMenuAction.READ_ALL)
        act = menu.addAction("Remove feed")
        act.setData(FeedMenuAction.REMOVE)
        act = menu.addAction("Copy URL")
        act.setData(FeedMenuAction.COPY_URL)

        action = menu.exec(self.list.viewport().mapToGlobal(pos))
        if action is None:
            return
        kind = FeedMenuAction(action.data())
        match kind:
            case FeedMenuAction.COPY_URL:
                QtWidgets.QApplication.clipboard().setText(self.feeds[index].id)
            case FeedMenuAction.READ_ALL:
                self.read_all_requested.emit(index)
            case FeedMenuAction.REMOVE:
                confirm = QtWidgets.QMessageBox.question(
                    self,
                    "Remove feed",
                    f"Remove '{self.feeds[index].title}'?",
                    QtWidgets.QMessageBox.StandardButton.Yes
                    | QtWidgets.QMessageBox.StandardButton.No,
                    QtWidgets.QMessageBox.StandardButton.No,
                )
                if confirm == QtWidgets.QMessageBox.StandardButton.Yes:
                    self.remove_feed_requested.emit(index)
            case _ as unreachable:
                typing.assert_never(unreachable)


class EntriesPane(QtWidgets.QWidget):
    """Right pane: list of entries for the selected feed."""

    entry_activated: QtCore.Signal = QtCore.Signal(int)
    entry_read_requested: QtCore.Signal = QtCore.Signal(int)
    entry_unread_requested: QtCore.Signal = QtCore.Signal(int)

    def __init__(
        self,
        delegate: QtWidgets.QStyledItemDelegate,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.entries: list[Entry] = []
        self.list: FeedListWidget

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QtWidgets.QLabel("Entries"))

        self.list = FeedListWidget(self)
        self.list.setItemDelegate(delegate)
        self.list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.list.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self.list)

    def show_entries(self, feed: Feed, reader: FeedReader) -> None:
        self.entries = list(reader.get_posts(feed))
        self.list.clear()
        for entry in self.entries:
            parts: list[str] = []
            if entry.author:
                parts.append(entry.author)
            if entry.last_updated:
                parts.append(entry.last_updated.strftime("%Y-%m-%d"))
            subtitle = " · ".join(parts)
            item = self.list.build_item(entry.title, subtitle, not entry.read)
            self.list.addItem(item)

    def clear(self) -> None:
        self.entries = []
        self.list.clear()

    def mark_read(self, index: int) -> None:
        self._set_read_state(index, True)

    def mark_unread(self, index: int) -> None:
        self._set_read_state(index, False)

    def _set_read_state(self, index: int, read: bool) -> None:
        if index < 0 or index >= len(self.entries):
            return
        self.entries[index] = replace(self.entries[index], read=read)
        item = self.list.item(index)
        if item:
            self.list.apply_font(item, not read)

    def _on_item_double_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        index = self.list.row(item)
        if index < 0 or index >= len(self.entries):
            return
        entry = self.entries[index]
        if not entry.read:
            self.entry_activated.emit(index)
        webbrowser.open(entry.url)

    def _on_context_menu(self, pos: QtCore.QPoint) -> None:
        item = self.list.itemAt(pos)
        if item is None:
            return
        index = self.list.row(item)
        entry = self.entries[index]
        menu = QtWidgets.QMenu(self)

        is_read = entry.read
        label = "Mark Unread" if is_read else "Mark Read"
        act_kind = EntryMenuAction.MARK_UNREAD if is_read else EntryMenuAction.MARK_READ
        act = menu.addAction(label)
        act.setData(act_kind)

        action = menu.exec(self.list.viewport().mapToGlobal(pos))
        if action is None:
            return
        kind = EntryMenuAction(action.data())
        match kind:
            case EntryMenuAction.MARK_READ:
                self.entry_read_requested.emit(index)
            case EntryMenuAction.MARK_UNREAD:
                self.entry_unread_requested.emit(index)
            case _ as unreachable:
                typing.assert_never(unreachable)

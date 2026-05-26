"""Single tree pane with feeds as top-level and entries as children."""

import logging
import webbrowser
from enum import IntEnum, auto
from typing import assert_never

from PySide6 import QtCore, QtWidgets

from feeds.models.feed import Entry, Feed, FeedReader
from feeds.ui.widgets import (
    DataRole,
    FeedIndexRole,
    FeedTreeWidget,
    ItemType,
    ItemTypeRole,
)

log: logging.Logger = logging.getLogger(__name__)


def _feed_label(feed: Feed, unread_count: int) -> str:
    return f"{feed.title} ({unread_count})" if unread_count else feed.title


class FeedMenuAction(IntEnum):
    """Actions available on the feed context menu."""

    COPY_URL = auto()
    READ_ALL = auto()
    REMOVE = auto()
    UPDATE = auto()


class EntryMenuAction(IntEnum):
    """Actions available on the entry context menu."""

    MARK_READ = auto()
    MARK_UNREAD = auto()


class FeedTreePane(QtWidgets.QWidget):
    """Single pane: feeds as top-level items, entries as children."""

    entry_activated: QtCore.Signal = QtCore.Signal(Entry)
    entry_read_requested: QtCore.Signal = QtCore.Signal(Entry)
    entry_unread_requested: QtCore.Signal = QtCore.Signal(Entry)
    read_all_requested: QtCore.Signal = QtCore.Signal(int)
    remove_feed_requested: QtCore.Signal = QtCore.Signal(int)
    update_feed_requested: QtCore.Signal = QtCore.Signal(int)

    def __init__(
        self,
        delegate: QtWidgets.QStyledItemDelegate,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Build the pane with a tree widget using the given delegate."""
        super().__init__(parent)
        self.feeds: list[Feed] = []
        self.tree: FeedTreeWidget

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tree = FeedTreeWidget(self)
        self.tree.setItemDelegate(delegate)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self.tree)

    def expand_feed_by_url(self, url: str) -> None:
        """Expand the feed node matching the given URL."""
        for i in range(self.tree.topLevelItemCount()):
            feed_item: QtWidgets.QTreeWidgetItem | None = self.tree.topLevelItem(i)
            if feed_item is None:
                continue
            feed: Feed | None = feed_item.data(0, DataRole)
            if feed and feed.id == url:
                self.tree.expandItem(feed_item)
                break

    def refresh(self, reader: FeedReader) -> None:
        """Clear and rebuild the tree from all feeds and entries."""
        self.feeds = list(reader.get_feeds())
        self.tree.clear()
        for feed_idx, feed in enumerate(self.feeds):
            feed_item = self._build_feed_item(feed, feed_idx, reader)
            self.tree.addTopLevelItem(feed_item)

    def mark_entry_read(self, item: QtWidgets.QTreeWidgetItem) -> None:
        """Remove bold from the item and decrement the parent feed's unread count."""
        self._set_item_bold(item, False)
        self._update_parent_unread(item.parent(), -1)

    def mark_entry_unread(self, item: QtWidgets.QTreeWidgetItem) -> None:
        """Apply bold to the item and increment the parent feed's unread count."""
        self._set_item_bold(item, True)
        self._update_parent_unread(item.parent(), 1)

    def _build_feed_item(
        self, feed: Feed, feed_idx: int, reader: FeedReader
    ) -> QtWidgets.QTreeWidgetItem:
        unread = reader.get_unread_count(feed)
        title = _feed_label(feed, unread)
        ts = feed.last_updated.strftime("%Y-%m-%d") if feed.last_updated else ""
        item = self.tree.build_item(title, ts, bool(unread), item_type=ItemType.FEED)
        item.setData(0, ItemTypeRole, ItemType.FEED)
        item.setData(0, FeedIndexRole, feed_idx)
        item.setData(0, DataRole, feed)

        for entry in reader.get_posts(feed):
            entry_item = self._build_entry_item(entry, feed_idx)
            item.addChild(entry_item)

        return item

    def _build_entry_item(
        self, entry: Entry, feed_idx: int
    ) -> QtWidgets.QTreeWidgetItem:
        parts: list[str] = []
        if entry.author:
            parts.append(entry.author)
        if entry.last_updated:
            parts.append(entry.last_updated.strftime("%Y-%m-%d"))
        subtitle = " · ".join(parts)
        item = self.tree.build_item(entry.title, subtitle, not entry.read)
        item.setData(0, ItemTypeRole, ItemType.ENTRY)
        item.setData(0, FeedIndexRole, feed_idx)
        item.setData(0, DataRole, entry)
        return item

    @staticmethod
    def _set_item_bold(item: QtWidgets.QTreeWidgetItem, bold: bool) -> None:
        font = item.font(0)
        font.setBold(bold)
        item.setFont(0, font)

    def _update_parent_unread(
        self, feed_item: QtWidgets.QTreeWidgetItem, delta: int
    ) -> None:
        if feed_item is None:
            return
        feed: Feed | None = feed_item.data(0, DataRole)
        if feed is None:
            return
        current_text: str = feed_item.text(0)
        unread = self._parse_unread(current_text, feed.title) + delta
        if unread < 0:
            unread = 0
        feed_item.setText(0, _feed_label(feed, unread))
        self.tree.apply_font(feed_item, bool(unread))

    @staticmethod
    def _parse_unread(text: str, title: str) -> int:
        prefix = f"{title} ("
        if text.startswith(prefix) and text.endswith(")"):
            inner = text[len(prefix) : -1]
            try:
                return int(inner)
            except ValueError:
                pass
        return 0

    def _on_item_double_clicked(self, item: QtWidgets.QTreeWidgetItem) -> None:
        item_type: ItemType | None = item.data(0, ItemTypeRole)
        match item_type:
            case ItemType.ENTRY:
                entry: Entry | None = item.data(0, DataRole)
                if entry is None:
                    return
                if not entry.read:
                    self.mark_entry_read(item)
                    self.entry_activated.emit(entry)
                log.info("opening entry in browser: %s", entry.url)
                webbrowser.open(entry.url)
            case ItemType.FEED | None:
                pass
            case _ as unreachable:
                assert_never(unreachable)

    def _on_context_menu(self, pos: QtCore.QPoint) -> None:
        item: QtWidgets.QTreeWidgetItem | None = self.tree.itemAt(pos)
        if item is None:
            return
        item_type: ItemType | None = item.data(0, ItemTypeRole)
        match item_type:
            case ItemType.FEED:
                self._show_feed_context_menu(item, pos)
            case ItemType.ENTRY:
                self._show_entry_context_menu(item, pos)
            case None:
                pass
            case _ as unreachable:
                assert_never(unreachable)

    def _show_feed_context_menu(
        self, item: QtWidgets.QTreeWidgetItem, pos: QtCore.QPoint
    ) -> None:
        feed_index: int | None = item.data(0, FeedIndexRole)
        if feed_index is None:
            return
        feed: Feed | None = item.data(0, DataRole)
        if feed is None:
            return
        menu = QtWidgets.QMenu(self)

        act = menu.addAction("Mark all as read")
        act.setData(FeedMenuAction.READ_ALL)
        act = menu.addAction("Remove feed")
        act.setData(FeedMenuAction.REMOVE)
        act = menu.addAction("Copy URL")
        act.setData(FeedMenuAction.COPY_URL)
        act = menu.addAction("Update feed")
        act.setData(FeedMenuAction.UPDATE)

        action = menu.exec(self.tree.viewport().mapToGlobal(pos))
        if action is None:
            return
        kind = FeedMenuAction(action.data())
        match kind:
            case FeedMenuAction.COPY_URL:
                log.info("copied feed URL: %s", feed.id)
                QtWidgets.QApplication.clipboard().setText(feed.id)
            case FeedMenuAction.READ_ALL:
                log.info("mark all as read requested for feed %s", feed.id)
                self.read_all_requested.emit(feed_index)
            case FeedMenuAction.REMOVE:
                confirm = QtWidgets.QMessageBox.question(
                    self,
                    "Remove feed",
                    f"Remove '{feed.title}'?",
                    QtWidgets.QMessageBox.StandardButton.Yes
                    | QtWidgets.QMessageBox.StandardButton.No,
                    QtWidgets.QMessageBox.StandardButton.No,
                )
                if confirm == QtWidgets.QMessageBox.StandardButton.Yes:
                    log.info("remove feed confirmed: %s", feed.id)
                    self.remove_feed_requested.emit(feed_index)
            case FeedMenuAction.UPDATE:
                log.info("update feed requested: %s", feed.id)
                self.update_feed_requested.emit(feed_index)
            case _ as unreachable:
                assert_never(unreachable)

    def _show_entry_context_menu(
        self, item: QtWidgets.QTreeWidgetItem, pos: QtCore.QPoint
    ) -> None:
        entry: Entry | None = item.data(0, DataRole)
        if entry is None:
            return
        menu = QtWidgets.QMenu(self)

        is_read = not item.font(0).bold()
        label = "Mark Unread" if is_read else "Mark Read"
        act_kind = EntryMenuAction.MARK_UNREAD if is_read else EntryMenuAction.MARK_READ
        act = menu.addAction(label)
        act.setData(act_kind)

        action = menu.exec(self.tree.viewport().mapToGlobal(pos))
        if action is None:
            return
        kind = EntryMenuAction(action.data())
        match kind:
            case EntryMenuAction.MARK_READ:
                log.info("mark read requested for entry %s", entry.url)
                self.mark_entry_read(item)
                self.entry_read_requested.emit(entry)
            case EntryMenuAction.MARK_UNREAD:
                log.info("mark unread requested for entry %s", entry.url)
                self.mark_entry_unread(item)
                self.entry_unread_requested.emit(entry)
            case _ as unreachable:
                assert_never(unreachable)

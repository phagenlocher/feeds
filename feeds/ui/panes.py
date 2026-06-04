"""Single tree pane with feeds as top-level and entries as children."""

import logging
import webbrowser
from dataclasses import dataclass
from enum import IntEnum, auto
from typing import assert_never

from PySide6 import QtCore, QtGui, QtWidgets
from rapidfuzz import fuzz

from feeds.models.feed import Entry, Feed, FeedReader
from feeds.ui.widgets import (
    DataRole,
    FeedIndexRole,
    FeedTreeWidget,
    ItemType,
    ItemTypeRole,
)

log: logging.Logger = logging.getLogger(__name__)

_FUZZY_THRESHOLD: int = 80


@dataclass(frozen=True, slots=True)
class TreeViewState:
    """Snapshot of expanded/selection/scroll state to preserve across tree rebuilds."""

    expanded_feed_urls: frozenset[str]
    selected_feed_url: str | None
    selected_entry_id: str | None
    scroll_position: int


def _feed_label(feed: Feed, unread_count: int) -> str:
    return f"{feed.title} ({unread_count})" if unread_count else feed.title


class FeedMenuAction(IntEnum):
    """Actions available on the feed context menu."""

    COPY_URL = auto()
    READ_ALL = auto()
    REMOVE = auto()
    RENAME = auto()
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
    rename_feed_requested: QtCore.Signal = QtCore.Signal(int)
    update_feed_requested: QtCore.Signal = QtCore.Signal(int)

    def __init__(
        self,
        delegate: QtWidgets.QStyledItemDelegate,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Build the pane with a tree widget using the given delegate."""
        super().__init__(parent)
        self.feeds: list[Feed] = []
        self._filter_text: str = ""
        self.tree: FeedTreeWidget
        self.search_bar: QtWidgets.QLineEdit

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.search_bar = QtWidgets.QLineEdit(self)
        self.search_bar.setVisible(False)
        self.search_bar.setPlaceholderText("Filter entries\u2026")
        self.search_bar.setClearButtonEnabled(True)
        self.search_bar.textChanged.connect(self._on_filter_changed)
        layout.addWidget(self.search_bar)

        escape_shortcut = QtGui.QShortcut(
            QtGui.QKeySequence(QtCore.Qt.Key.Key_Escape), self.search_bar
        )
        escape_shortcut.activated.connect(self._on_filter_escape)

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

    def _get_expanded_feed_urls(self) -> frozenset[str]:
        expanded_urls: list[str] = []
        for i in range(self.tree.topLevelItemCount()):
            item: QtWidgets.QTreeWidgetItem | None = self.tree.topLevelItem(i)
            if item is None:
                continue
            if item.isExpanded():
                feed: Feed | None = item.data(0, DataRole)
                if feed is not None:
                    expanded_urls.append(feed.id)

        return frozenset(expanded_urls)

    def _save_state(self) -> TreeViewState:
        selected_feed_url: str | None = None
        selected_entry_id: str | None = None
        selected_items: list[QtWidgets.QTreeWidgetItem] = self.tree.selectedItems()
        if selected_items:
            sel: QtWidgets.QTreeWidgetItem = selected_items[0]
            item_type: ItemType | None = sel.data(0, ItemTypeRole)
            match item_type:
                case ItemType.FEED:
                    sel_feed: Feed | None = sel.data(0, DataRole)
                    if sel_feed is not None:
                        selected_feed_url = sel_feed.id
                case ItemType.ENTRY:
                    sel_entry: Entry | None = sel.data(0, DataRole)
                    parent: QtWidgets.QTreeWidgetItem | None = sel.parent()
                    if sel_entry is not None and parent is not None:
                        parent_feed: Feed | None = parent.data(0, DataRole)
                        if parent_feed is not None:
                            selected_feed_url = parent_feed.id
                            selected_entry_id = sel_entry.entry_id
                case _:
                    log.warning(f"Unknown item type: {item_type}")

        scroll_pos: int = self.tree.verticalScrollBar().value()

        return TreeViewState(
            expanded_feed_urls=self._get_expanded_feed_urls(),
            selected_feed_url=selected_feed_url,
            selected_entry_id=selected_entry_id,
            scroll_position=scroll_pos,
        )

    def _restore_state(self, state: TreeViewState) -> None:
        for i in range(self.tree.topLevelItemCount()):
            item: QtWidgets.QTreeWidgetItem | None = self.tree.topLevelItem(i)
            if item is None:
                continue
            exp_feed: Feed | None = item.data(0, DataRole)
            if exp_feed is not None and exp_feed.id in state.expanded_feed_urls:
                item.setExpanded(True)

        sel_target: QtWidgets.QTreeWidgetItem | None = None
        if state.selected_feed_url is not None:
            for i in range(self.tree.topLevelItemCount()):
                feed_item: QtWidgets.QTreeWidgetItem | None = self.tree.topLevelItem(i)
                if feed_item is None:
                    continue
                feed: Feed | None = feed_item.data(0, DataRole)
                if feed is None or feed.id != state.selected_feed_url:
                    continue

                if state.selected_entry_id is None:
                    feed_item.setSelected(True)
                    self.tree.setCurrentItem(feed_item)
                    sel_target = feed_item
                else:
                    for j in range(feed_item.childCount()):
                        child: QtWidgets.QTreeWidgetItem | None = feed_item.child(j)
                        if child is None:
                            continue
                        entry: Entry | None = child.data(0, DataRole)
                        if (
                            entry is not None
                            and entry.entry_id == state.selected_entry_id
                        ):
                            child.setSelected(True)
                            self.tree.setCurrentItem(child)
                            sel_target = child
                            break
                break

        QtCore.QTimer.singleShot(0, lambda: self._finish_restore(state, sel_target))

    def _finish_restore(
        self,
        state: TreeViewState,
        sel_target: QtWidgets.QTreeWidgetItem | None,
    ) -> None:
        self.tree.verticalScrollBar().setValue(state.scroll_position)
        if sel_target is not None and not sel_target.isHidden():
            self.tree.scrollToItem(
                sel_target,
                QtWidgets.QAbstractItemView.ScrollHint.EnsureVisible,
            )

    def refresh(self, reader: FeedReader) -> None:
        """Clear and rebuild the tree from all feeds and entries."""
        prev_state: TreeViewState = self._save_state()
        self.feeds = list(reader.get_feeds())
        self.tree.clear()
        for feed_idx, feed in enumerate(self.feeds):
            feed_item = self._build_feed_item(feed, feed_idx, reader)
            self.tree.addTopLevelItem(feed_item)
        self._apply_filter()
        self._restore_state(prev_state)

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
        item.setToolTip(0, feed.id)
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
        menu.addSeparator()
        act = menu.addAction("Rename")
        act.setData(FeedMenuAction.RENAME)
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
            case FeedMenuAction.RENAME:
                log.info("rename feed requested: %s", feed.id)
                self.rename_feed_requested.emit(feed_index)
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

    def _on_filter_changed(self, text: str) -> None:
        self._filter_text = text
        self._apply_filter()

    def _apply_filter(self) -> None:
        query = self._filter_text.lower()
        for i in range(self.tree.topLevelItemCount()):
            feed_item: QtWidgets.QTreeWidgetItem | None = self.tree.topLevelItem(i)
            if feed_item is None:
                continue
            if not query:
                feed_item.setHidden(False)
                for j in range(feed_item.childCount()):
                    child: QtWidgets.QTreeWidgetItem | None = feed_item.child(j)
                    if child is not None:
                        child.setHidden(False)
            else:
                any_visible = False
                for j in range(feed_item.childCount()):
                    entry_child: QtWidgets.QTreeWidgetItem | None = feed_item.child(j)
                    if entry_child is None:
                        continue
                    entry: Entry | None = entry_child.data(0, DataRole)
                    match: bool = (
                        entry is not None
                        and fuzz.partial_ratio(query, entry.title.lower())
                        >= _FUZZY_THRESHOLD
                    )
                    entry_child.setHidden(not match)
                    if match:
                        any_visible = True
                feed_item.setHidden(not any_visible)

    def toggle_search(self) -> None:
        """Toggle the search bar visibility; hide clears the filter."""
        if self.search_bar.isVisible():
            self.search_bar.setVisible(False)
            self._on_filter_escape()
        else:
            self.search_bar.setVisible(True)
            self.search_bar.setFocus()
            self.search_bar.selectAll()

    def _on_filter_escape(self) -> None:
        if self.search_bar.text():
            self.search_bar.clear()
        self.search_bar.setVisible(False)
        self.tree.setFocus()

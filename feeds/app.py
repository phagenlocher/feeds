"""Main window orchestrating toolbar, panes, zoom, and async operations."""

import logging
import traceback
from collections.abc import Callable

from PySide6 import QtCore, QtGui, QtWidgets

from feeds.models.feed import FeedReader
from feeds.services.feed_service import FeedService
from feeds.ui.delegates import TwoLineRenderer
from feeds.ui.dialogs import AddFeedChoiceDialog, AddFeedDialog
from feeds.ui.panes import EntriesPane, FeedsPane

log: logging.Logger = logging.getLogger(__name__)


class FeedsApp(QtWidgets.QMainWindow):
    """Main window orchestrating toolbar, panes, zoom, and async operations."""

    def __init__(self, reader: FeedReader | None = None) -> None:
        super().__init__()
        self.reader: FeedReader | None = None
        self._service: FeedService | None = None
        self._font_size: int = 12
        self._selected_feed_index: int | None = None
        self._update_action: QtGui.QAction | None = None
        self.feeds_pane: FeedsPane
        self.entries_pane: EntriesPane

        self.setWindowTitle("Feeds")
        self.resize(800, 500)
        self.statusBar().showMessage("")

        delegate = TwoLineRenderer(self)
        self._build_toolbar()
        self._build_main_area(delegate)

        try:
            self.reader = reader or FeedReader()
            self._service = FeedService(self.reader)
        except Exception:
            log.exception("failed to initialize FeedReader")
            traceback.print_exc()
            self.statusBar().showMessage("Failed to open feed database", 0)
        else:
            self._apply_font_size()
            self._setup_zoom_shortcuts()
            try:
                self.feeds_pane.refresh(self.reader)
            except Exception:
                log.exception("failed to load feeds")
                traceback.print_exc()
                self.statusBar().showMessage("Failed to load feeds from database", 0)

    def _build_toolbar(self) -> None:
        toolbar = QtWidgets.QToolBar()
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        add_action = QtGui.QAction("Add Feed", self)
        add_action.triggered.connect(self._on_add_feed)
        toolbar.addAction(add_action)

        self._update_action = QtGui.QAction("Update Feeds", self)
        self._update_action.triggered.connect(self._on_update_feeds)
        toolbar.addAction(self._update_action)

    def _build_main_area(self, delegate: TwoLineRenderer) -> None:
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)

        self.feeds_pane = FeedsPane(delegate, self)
        self.feeds_pane.feed_selected.connect(self._on_feed_selected)
        self.feeds_pane.read_all_requested.connect(self._read_all_async)
        self.feeds_pane.remove_feed_requested.connect(self._remove_feed_async)
        splitter.addWidget(self.feeds_pane)

        self.entries_pane = EntriesPane(delegate, self)
        self.entries_pane.entry_activated.connect(self._on_entry_activated)
        self.entries_pane.entry_read_requested.connect(self._on_entry_read)
        self.entries_pane.entry_unread_requested.connect(self._on_entry_unread)
        splitter.addWidget(self.entries_pane)

        splitter.setSizes([240, 560])

    def _set_base_font(self) -> None:
        font = QtGui.QFont()
        font.setPointSize(self._font_size)
        app = QtWidgets.QApplication.instance()
        if isinstance(app, QtWidgets.QApplication):
            app.setFont(font)

    def _setup_zoom_shortcuts(self) -> None:
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl++"), self, self._zoom_in)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+="), self, self._zoom_in)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+-"), self, self._zoom_out)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+0"), self, self._zoom_reset)

    def _zoom_in(self) -> None:
        self._font_size += 1
        self._apply_font_size()

    def _zoom_out(self) -> None:
        self._font_size = max(6, self._font_size - 1)
        self._apply_font_size()

    def _zoom_reset(self) -> None:
        self._font_size = 12
        self._apply_font_size()

    def _apply_font_size(self) -> None:
        self._set_base_font()
        self.feeds_pane.list.set_font_size(self._font_size)
        self.entries_pane.list.set_font_size(self._font_size)

    def _set_busy(self, busy: bool) -> None:
        if self._update_action is None:
            return
        self._update_action.setEnabled(not busy)
        self._update_action.setText("Updating…" if busy else "Update Feeds")
        if not busy:
            self.statusBar().showMessage("")

    def _on_service_error(self, msg: str) -> None:
        self._set_busy(False)
        self.statusBar().showMessage(f"Error: {msg}", 5000)

    def _on_feed_selected(self, index: int) -> None:
        if self.reader is None:
            return
        self._selected_feed_index = index
        self.feeds_pane.select(index)
        feed = self.feeds_pane.feeds[index]
        self.entries_pane.show_entries(feed, self.reader)

    def _update_feed_font(self) -> None:
        reader = self.reader
        if reader is None:
            return
        idx = self._selected_feed_index
        if idx is not None:
            self.feeds_pane.update_feed_font(idx, reader)

    def _toggle_entry_read(self, index: int, read: bool) -> None:
        if self.reader is None:
            return
        entry = self.entries_pane.entries[index]
        if read:
            self.reader.mark_entry_as_read(entry)
            self.entries_pane.mark_read(index)
        else:
            self.reader.mark_entry_as_unread(entry)
            self.entries_pane.mark_unread(index)
        self._update_feed_font()

    def _on_entry_activated(self, index: int) -> None:
        self._toggle_entry_read(index, True)

    def _on_entry_read(self, index: int) -> None:
        self._toggle_entry_read(index, True)

    def _on_entry_unread(self, index: int) -> None:
        self._toggle_entry_read(index, False)

    def _on_add_feed(self) -> None:
        if self._service is None:
            return

        dialog = AddFeedDialog(self)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        url = dialog.url
        if not url:
            return

        _service = self._service

        def on_discovered(feeds: list[tuple[str, str]]) -> None:
            if not feeds:
                self._on_service_error("No feed found at this URL")
                return

            if len(feeds) == 1:
                feed_url, _ = feeds[0]
                self._add_discovered_feed(feed_url)
                return

            choice = AddFeedChoiceDialog(feeds, self)
            if choice.exec() != QtWidgets.QDialog.DialogCode.Accepted:
                self._set_busy(False)
                return

            selected = choice.selected_feeds
            if not selected:
                self._set_busy(False)
                return

            self._add_feeds_sequentially(selected, 0)

        self.statusBar().showMessage("Discovering feeds…")
        self._set_busy(True)
        self._service.discover_feeds(
            url, on_done=on_discovered, on_error=self._on_service_error
        )

    def _add_discovered_feed(self, feed_url: str) -> None:
        _service = self._service
        if _service is None:
            return

        def on_added() -> None:
            self.statusBar().showMessage("Updating feed…")
            self._set_busy(True)
            _service.update_feed(
                feed_url,
                on_done=lambda: self._on_add_feed_done(feed_url),
                on_error=self._on_service_error,
            )

        self.statusBar().showMessage("Adding feed…")
        self._set_busy(True)
        _service.add_feed(feed_url, on_done=on_added, on_error=self._on_service_error)

    def _add_feeds_sequentially(self, feeds: list[tuple[str, str]], index: int) -> None:
        if index >= len(feeds):
            if self.reader is None:
                return
            self._set_busy(False)
            self.feeds_pane.refresh(self.reader)
            self.statusBar().showMessage("Feeds added", 3000)
            return

        _service = self._service
        if _service is None:
            return

        feed_url, _ = feeds[index]
        total = len(feeds)

        def on_added() -> None:
            self.statusBar().showMessage(f"Updating feed {index + 1}/{total}…")
            self._set_busy(True)
            _service.update_feed(
                feed_url,
                on_done=lambda: self._on_add_feed_done(
                    feed_url,
                    on_next=lambda: self._add_feeds_sequentially(feeds, index + 1),
                ),
                on_error=self._on_service_error,
            )

        self.statusBar().showMessage(f"Adding feed {index + 1}/{total}…")
        self._set_busy(True)
        _service.add_feed(feed_url, on_done=on_added, on_error=self._on_service_error)

    def _on_add_feed_done(
        self, url: str, on_next: Callable[[], object] | None = None
    ) -> None:
        if self.reader is None:
            return
        self.feeds_pane.refresh(self.reader)
        for i, feed in enumerate(self.feeds_pane.feeds):
            if feed.id == url:
                self._on_feed_selected(i)
                break
        if on_next:
            on_next()
        else:
            self._set_busy(False)
            self.statusBar().showMessage("Feed added", 3000)

    def _on_update_feeds(self) -> None:
        if self._service is None:
            return
        self.statusBar().showMessage("Updating feeds…")
        self._set_busy(True)
        self._service.update_feeds(
            on_done=self._on_update_feeds_done,
            on_error=self._on_service_error,
        )

    def _on_update_feeds_done(self) -> None:
        if self.reader is None:
            return
        self._set_busy(False)
        self.feeds_pane.refresh(self.reader)
        if self._selected_feed_index is not None and self._selected_feed_index < len(
            self.feeds_pane.feeds
        ):
            feed = self.feeds_pane.feeds[self._selected_feed_index]
            self.entries_pane.show_entries(feed, self.reader)
            self.feeds_pane.select(self._selected_feed_index)
        else:
            self.entries_pane.clear()
        self.statusBar().showMessage("Feeds updated", 3000)

    def _remove_feed_async(self, index: int) -> None:
        if self._service is None:
            return
        feed = self.feeds_pane.feeds[index]
        self.statusBar().showMessage(f"Removing {feed.title}…")
        self._set_busy(True)
        self._service.delete_feed(
            feed,
            on_done=self._on_remove_feed_done,
            on_error=self._on_service_error,
        )

    def _on_remove_feed_done(self) -> None:
        if self.reader is None:
            return
        self._set_busy(False)
        self._selected_feed_index = None
        self.feeds_pane.refresh(self.reader)
        self.entries_pane.clear()
        self.statusBar().showMessage("Feed removed", 3000)

    def _read_all_async(self, index: int) -> None:
        if self._service is None:
            return
        feed = self.feeds_pane.feeds[index]
        self.statusBar().showMessage("Marking all as read…")
        self._set_busy(True)
        self._service.mark_all_as_read(
            feed,
            on_done=self._on_read_all_done,
            on_error=self._on_service_error,
        )

    def _on_read_all_done(self) -> None:
        if self.reader is None:
            return
        self._set_busy(False)
        self.feeds_pane.refresh(self.reader)
        if self._selected_feed_index is not None:
            feed = self.feeds_pane.feeds[self._selected_feed_index]
            self.entries_pane.show_entries(feed, self.reader)
        self.statusBar().showMessage("All marked as read", 3000)

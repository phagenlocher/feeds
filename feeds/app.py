"""Main window orchestrating menu bar, tree pane, zoom, and async operations."""

import logging
import webbrowser
from collections.abc import Callable

from PySide6 import QtGui, QtWidgets

from feeds.models.feed import Entry, FeedReader
from feeds.services.feed_service import FeedService
from feeds.ui.delegates import TwoLineRenderer
from feeds.ui.dialogs import (
    AboutDialog,
    AddFeedChoiceDialog,
    AddFeedDialog,
    RenameFeedDialog,
)
from feeds.ui.panes import FeedTreePane

log: logging.Logger = logging.getLogger(__name__)


class FeedsApp(QtWidgets.QMainWindow):
    """Main window orchestrating menu bar, tree pane, zoom, and async operations."""

    def __init__(self, reader: FeedReader | None = None) -> None:
        """Set up menu bar, pane, font, zoom, reader, service and load feeds."""
        super().__init__()
        self.reader: FeedReader | None = None
        self._service: FeedService | None = None
        self._font_size: int = 12
        self._update_action: QtGui.QAction | None = None
        self._searchbar_action: QtGui.QAction | None = None
        self._zoom_in_action: QtGui.QAction | None = None
        self._zoom_out_action: QtGui.QAction | None = None
        self._zoom_reset_action: QtGui.QAction | None = None
        self.pane: FeedTreePane

        self.setWindowTitle("Feeds")
        self.resize(800, 500)
        self.statusBar().showMessage("")

        delegate = TwoLineRenderer(self)
        self._build_menu_bar()
        self._build_main_area(delegate)

        try:
            self.reader = reader or FeedReader()
            self._service = FeedService(self.reader)
        except Exception:
            log.exception("failed to initialize FeedReader")
            self.statusBar().showMessage("Failed to open feed database", 0)
        else:
            self._apply_font_size()
            self._setup_zoom_shortcuts()
            try:
                self.pane.refresh(self.reader)
            except Exception:
                log.exception("failed to load feeds")
                self.statusBar().showMessage("Failed to load feeds from database", 0)
            self._update_all_feeds(scheduled=True)

    def _build_menu_bar(self) -> None:
        menubar = self.menuBar()

        feed_menu = menubar.addMenu("&Feed")
        add_action = QtGui.QAction("&Add Feed", self)
        add_action.triggered.connect(self._on_add_feed)
        feed_menu.addAction(add_action)

        self._update_action = QtGui.QAction("&Update Feeds", self)
        self._update_action.triggered.connect(self._on_update_feeds)
        feed_menu.addAction(self._update_action)

        feed_menu.addSeparator()

        export_action = QtGui.QAction("&Export URLs\u2026", self)
        export_action.triggered.connect(self._on_export_urls)
        feed_menu.addAction(export_action)

        import_action = QtGui.QAction("&Import URLs\u2026", self)
        import_action.triggered.connect(self._on_import_urls)
        feed_menu.addAction(import_action)

        display_menu = menubar.addMenu("&Display")

        self._searchbar_action = QtGui.QAction("Show &Searchbar", self)
        self._searchbar_action.setCheckable(True)
        self._searchbar_action.setChecked(False)
        self._searchbar_action.setShortcut(QtGui.QKeySequence("Ctrl+F"))
        self._searchbar_action.triggered.connect(self._toggle_search)
        display_menu.addAction(self._searchbar_action)

        display_menu.addSeparator()

        self._zoom_in_action = QtGui.QAction("Zoom &In", self)
        self._zoom_in_action.setShortcut(QtGui.QKeySequence("Ctrl++"))
        self._zoom_in_action.triggered.connect(self._zoom_in)
        display_menu.addAction(self._zoom_in_action)

        self._zoom_out_action = QtGui.QAction("Zoom &Out", self)
        self._zoom_out_action.setShortcut(QtGui.QKeySequence("Ctrl+-"))
        self._zoom_out_action.triggered.connect(self._zoom_out)
        display_menu.addAction(self._zoom_out_action)

        self._zoom_reset_action = QtGui.QAction("&Reset Zoom", self)
        self._zoom_reset_action.setShortcut(QtGui.QKeySequence("Ctrl+0"))
        self._zoom_reset_action.triggered.connect(self._zoom_reset)
        display_menu.addAction(self._zoom_reset_action)

        help_menu = menubar.addMenu("&Help")
        report_action = QtGui.QAction("&Report Issue", self)
        report_action.triggered.connect(self._on_report_issue)
        help_menu.addAction(report_action)

        help_menu.addSeparator()

        about_action = QtGui.QAction("&About", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    def _build_main_area(self, delegate: TwoLineRenderer) -> None:
        self.pane = FeedTreePane(delegate, self)
        self.pane.entry_activated.connect(self._on_entry_activated)
        self.pane.entry_read_requested.connect(self._on_entry_read)
        self.pane.entry_unread_requested.connect(self._on_entry_unread)
        self.pane.read_all_requested.connect(self._read_all_async)
        self.pane.remove_feed_requested.connect(self._remove_feed_async)
        self.pane.rename_feed_requested.connect(self._rename_feed)
        self.pane.update_feed_requested.connect(self._update_single_feed)
        self.pane.prune_feed_requested.connect(self._prune_feed_async)
        self.pane.search_visibility_changed.connect(self._on_search_visibility_changed)
        self.setCentralWidget(self.pane)

    def _set_base_font(self) -> None:
        font = QtGui.QFont()
        font.setPointSize(self._font_size)
        QtWidgets.QApplication.instance().setFont(font)

    def _setup_zoom_shortcuts(self) -> None:
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+="), self, self._zoom_in)

    def _zoom_in(self) -> None:
        self._font_size += 1
        self._apply_font_size()

    def _zoom_out(self) -> None:
        self._font_size = max(6, self._font_size - 1)
        self._apply_font_size()

    def _zoom_reset(self) -> None:
        self._font_size = 12
        self._apply_font_size()

    def _toggle_search(self) -> None:
        self.pane.toggle_search()

    def _on_search_visibility_changed(self, visible: bool) -> None:
        if self._searchbar_action is not None:
            self._searchbar_action.setChecked(visible)

    def _apply_font_size(self) -> None:
        self._set_base_font()
        self.pane.tree.set_font_size(self._font_size)

    def _set_busy(self, busy: bool) -> None:
        if self._update_action is None:
            return
        self._update_action.setEnabled(not busy)
        self._update_action.setText("Updating\u2026" if busy else "Update Feeds")
        if not busy:
            self.statusBar().showMessage("")

    def _on_service_error(self, msg: str) -> None:
        log.error("Service error: %s", msg)
        self._set_busy(False)
        self.statusBar().showMessage(f"Error: {msg}", 5000)

    def _toggle_entry_read(self, entry: Entry, read: bool) -> None:
        if self.reader is None:
            return
        if read:
            log.info("marking entry read: %s", entry.url)
            self.reader.mark_entry_as_read(entry)
        else:
            log.info("marking entry unread: %s", entry.url)
            self.reader.mark_entry_as_unread(entry)

    def _on_entry_activated(self, entry: Entry) -> None:
        log.info("entry activated: %s", entry.url)
        self._toggle_entry_read(entry, True)

    def _on_entry_read(self, entry: Entry) -> None:
        self._toggle_entry_read(entry, True)

    def _on_entry_unread(self, entry: Entry) -> None:
        self._toggle_entry_read(entry, False)

    def _on_add_feed(self) -> None:
        if self._service is None:
            return

        dialog = AddFeedDialog(self)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            log.info("add feed cancelled by user")
            return
        url = dialog.url
        if not url:
            return

        log.info("add feed button clicked: %s", url)
        _service = self._service

        def on_discovered(feeds: list[tuple[str, str]]) -> None:
            if not feeds:
                self._on_service_error("No feed found at this URL")
                return

            if len(feeds) == 1:
                feed_url, _ = feeds[0]
                log.info("single feed discovered, adding: %s", feed_url)
                self._add_discovered_feed(feed_url)
                return

            choice = AddFeedChoiceDialog(feeds, self)
            if choice.exec() != QtWidgets.QDialog.DialogCode.Accepted:
                log.info("feed choice cancelled by user")
                self._set_busy(False)
                return

            selected = choice.selected_feeds
            if not selected:
                self._set_busy(False)
                return

            self._add_feeds_sequentially(selected, 0)

        self.statusBar().showMessage("Discovering feeds\u2026")
        self._set_busy(True)
        self._service.discover_feeds(
            url, on_done=on_discovered, on_error=self._on_service_error
        )

    def _add_discovered_feed(self, feed_url: str) -> None:
        _service = self._service
        if _service is None:
            return

        def on_added() -> None:
            self.statusBar().showMessage("Updating feed\u2026")
            self._set_busy(True)
            _service.update_feed(
                feed_url,
                on_done=lambda: self._on_add_feed_done(feed_url),
                on_error=self._on_service_error,
            )

        self.statusBar().showMessage("Adding feed\u2026")
        self._set_busy(True)
        _service.add_feed(feed_url, on_done=on_added, on_error=self._on_service_error)

    def _add_feeds_sequentially(self, feeds: list[tuple[str, str]], index: int) -> None:
        if index >= len(feeds):
            if self.reader is None:
                return
            self._set_busy(False)
            self.pane.refresh(self.reader)
            self.statusBar().showMessage("Feeds added", 3000)
            return

        _service = self._service
        if _service is None:
            return

        feed_url, _ = feeds[index]
        total = len(feeds)

        def on_added() -> None:
            self.statusBar().showMessage(f"Updating feed {index + 1}/{total}\u2026")
            self._set_busy(True)
            _service.update_feed(
                feed_url,
                on_done=lambda: self._on_add_feed_done(
                    feed_url,
                    on_next=lambda: self._add_feeds_sequentially(feeds, index + 1),
                ),
                on_error=self._on_service_error,
            )

        self.statusBar().showMessage(f"Adding feed {index + 1}/{total}\u2026")
        self._set_busy(True)
        _service.add_feed(feed_url, on_done=on_added, on_error=self._on_service_error)

    def _on_add_feed_done(
        self,
        url: str,
        on_next: Callable[[], object] | None = None,
        expand: bool = True,
    ) -> None:
        if self.reader is None:
            return
        log.info("feed added: %s", url)
        self.pane.refresh(self.reader)
        if expand:
            self.pane.expand_feed_by_url(url)
        if on_next:
            on_next()
        else:
            self._set_busy(False)
            self.statusBar().showMessage("Feed added", 3000)

    def _on_export_urls(self) -> None:
        """Open save dialog to export all feed URLs to a text file."""
        if self.reader is None:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export Feed URLs", "", "Text files (*.txt)"
        )
        if not path:
            return
        if not path.endswith(".txt"):
            path += ".txt"
        try:
            urls: list[str] = [feed.id for feed in self.reader.get_feeds()]
            with open(path, "w") as f:
                for url in urls:
                    f.write(url + "\n")
            log.info("exported %d feed URLs to %s", len(urls), path)
            self.statusBar().showMessage(f"Exported {len(urls)} feed URLs", 3000)
        except Exception:
            log.exception("failed to export feed URLs")
            self.statusBar().showMessage("Failed to export feed URLs", 5000)

    def _on_import_urls(self) -> None:
        """Open file dialog to import feed URLs from a text file."""
        if self._service is None:
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Import Feed URLs", "", "Text files (*.txt)"
        )
        if not path:
            return
        try:
            with open(path) as f:
                urls: list[str] = [line.strip() for line in f if line.strip()]
        except Exception:
            log.exception("failed to read import file")
            self.statusBar().showMessage("Failed to read import file", 5000)
            return
        if not urls:
            self.statusBar().showMessage("No URLs found in file", 3000)
            return
        log.info("importing %d feed URLs from %s", len(urls), path)
        self.statusBar().showMessage(f"Importing {len(urls)} feeds\u2026")
        self._set_busy(True)
        self._import_urls_sequentially(urls, 0)

    def _import_urls_sequentially(self, urls: list[str], index: int) -> None:
        """Add and update one feed URL at a time, then recurse."""
        if index >= len(urls):
            if self.reader is None:
                return
            self._set_busy(False)
            self.statusBar().showMessage("Feeds imported", 3000)
            return

        _service = self._service
        if _service is None:
            return

        url = urls[index]
        total = len(urls)

        def on_added() -> None:
            self.statusBar().showMessage(f"Importing feed {index + 1}/{total}\u2026")
            self._set_busy(True)
            _service.update_feed(
                url,
                on_done=lambda: self._on_add_feed_done(
                    url,
                    on_next=lambda: self._import_urls_sequentially(urls, index + 1),
                    expand=False,
                ),
                on_error=self._on_service_error,
            )

        self.statusBar().showMessage(f"Adding feed {index + 1}/{total}\u2026")
        self._set_busy(True)
        _service.add_feed(url, on_done=on_added, on_error=self._on_service_error)

    def _update_all_feeds(self, scheduled: bool = False) -> None:
        """Update all feeds with status and busy feedback."""
        if self._service is None:
            return
        log.info("updating all feeds (scheduled=%s)", scheduled)
        self.statusBar().showMessage("Updating feeds\u2026")
        self._set_busy(True)
        self._service.update_feeds(
            scheduled=scheduled,
            on_done=self._on_update_feeds_done,
            on_error=self._on_service_error,
        )

    def _on_update_feeds(self) -> None:
        """Toolbar button handler — force-refresh all feeds."""
        self._update_all_feeds(scheduled=False)

    def _on_update_feeds_done(self) -> None:
        if self.reader is None:
            return
        log.info("feeds updated")
        self._set_busy(False)
        self.pane.refresh(self.reader)
        self.statusBar().showMessage("Feeds updated", 3000)

    def _on_report_issue(self) -> None:
        log.info("opening issue tracker")
        webbrowser.open("https://github.com/phagenlocher/feeds/issues")

    def _on_about(self) -> None:
        from feeds import __version__

        dialog = AboutDialog(__version__, self)
        dialog.exec()

    def _update_single_feed(self, feed_index: int) -> None:
        if self._service is None:
            return
        if feed_index >= len(self.pane.feeds):
            return
        feed = self.pane.feeds[feed_index]
        log.info("update single feed requested: %s", feed.id)
        self.statusBar().showMessage(f"Updating {feed.title}\u2026")
        self._set_busy(True)
        self._service.update_feed(
            feed.id,
            on_done=self._on_update_single_feed_done,
            on_error=self._on_service_error,
        )

    def _on_update_single_feed_done(self) -> None:
        if self.reader is None:
            return
        log.info("single feed updated")
        self._set_busy(False)
        self.pane.refresh(self.reader)
        self.statusBar().showMessage("Feed updated", 3000)

    def _remove_feed_async(self, feed_index: int) -> None:
        if self._service is None:
            return
        if feed_index >= len(self.pane.feeds):
            return
        feed = self.pane.feeds[feed_index]
        log.info("removing feed: %s", feed.id)
        self.statusBar().showMessage(f"Removing {feed.title}\u2026")
        self._set_busy(True)
        self._service.delete_feed(
            feed,
            on_done=self._on_remove_feed_done,
            on_error=self._on_service_error,
        )

    def _on_remove_feed_done(self) -> None:
        if self.reader is None:
            return
        log.info("feed removed")
        self._set_busy(False)
        self.pane.refresh(self.reader)
        self.statusBar().showMessage("Feed removed", 3000)

    def _rename_feed(self, feed_index: int) -> None:
        if self._service is None:
            return
        if feed_index >= len(self.pane.feeds):
            return
        feed = self.pane.feeds[feed_index]

        dialog = RenameFeedDialog(feed.title, self)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            log.info("rename feed cancelled by user")
            return
        title = dialog.title
        if not title:
            return

        log.info("renaming feed %s to '%s'", feed.id, title)
        self.statusBar().showMessage(f"Renaming {feed.title}\u2026")
        self._set_busy(True)
        self._service.set_feed_user_title(
            feed,
            title,
            on_done=self._on_rename_feed_done,
            on_error=self._on_service_error,
        )

    def _on_rename_feed_done(self) -> None:
        if self.reader is None:
            return
        log.info("feed renamed")
        self._set_busy(False)
        self.pane.refresh(self.reader)
        self.statusBar().showMessage("Feed renamed", 3000)

    def _read_all_async(self, feed_index: int) -> None:
        if self._service is None:
            return
        if feed_index >= len(self.pane.feeds):
            return
        feed = self.pane.feeds[feed_index]
        log.info("marking all as read in feed: %s", feed.id)
        self.statusBar().showMessage("Marking all as read\u2026")
        self._set_busy(True)
        self._service.mark_all_as_read(
            feed,
            on_done=self._on_read_all_done,
            on_error=self._on_service_error,
        )

    def _on_read_all_done(self) -> None:
        if self.reader is None:
            return
        log.info("all entries marked as read")
        self._set_busy(False)
        self.pane.refresh(self.reader)
        self.statusBar().showMessage("All marked as read", 3000)

    def _prune_feed_async(self, feed_index: int, n: int) -> None:
        if self._service is None:
            return
        if feed_index >= len(self.pane.feeds):
            return
        feed = self.pane.feeds[feed_index]
        log.info("pruning feed to %d entries: %s", n, feed.id)
        self.statusBar().showMessage(f"Pruning {feed.title}\u2026")
        self._set_busy(True)
        self._service.prune_feed(
            feed,
            n,
            on_done=lambda: self._on_prune_feed_done(feed.title),
            on_error=self._on_service_error,
        )

    def _on_prune_feed_done(self, feed_title: str) -> None:
        if self.reader is None:
            return
        log.info("feed pruned: %s", feed_title)
        self._set_busy(False)
        self.pane.refresh(self.reader)
        self.statusBar().showMessage(f"{feed_title} pruned", 3000)

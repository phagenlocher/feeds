"""Feed-related dialogs."""

import logging
from urllib.parse import urlparse

from PySide6 import QtCore, QtGui, QtWidgets

from feeds.models.feed import FeedReader

log: logging.Logger = logging.getLogger(__name__)

_DEFAULT_TAG_COLORS: list[str] = [
    "#e06c75",
    "#61afef",
    "#98c379",
    "#e5c07b",
    "#c678dd",
    "#56b6c2",
    "#d19a66",
    "#7ec8e3",
    "#b9e6a0",
    "#f0c674",
    "#b294bb",
    "#81a2be",
]


def _pick_tag_color(tag: str, tag_colors: dict[str, str]) -> str:
    """Return the color for *tag*, assigning a default if missing."""
    if tag in tag_colors:
        return tag_colors[tag]
    used = set(tag_colors.values())
    for c in _DEFAULT_TAG_COLORS:
        if c not in used:
            tag_colors[tag] = c
            return c
    idx = len(tag_colors) % len(_DEFAULT_TAG_COLORS)
    color = _DEFAULT_TAG_COLORS[idx]
    tag_colors[tag] = color
    return color


class AddFeedDialog(QtWidgets.QDialog):
    """Dialog for entering a feed URL with basic validation."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Modal dialog with a URL field and an Add button with validation."""
        super().__init__(parent)
        self.setWindowTitle("Add Feed")
        self.setFixedSize(400, 120)

        self.url_input: QtWidgets.QLineEdit = QtWidgets.QLineEdit()
        self.url_input.setFocus()

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel("Feed URL:"))
        layout.addWidget(self.url_input)

        self.add_btn: QtWidgets.QPushButton = QtWidgets.QPushButton("Add")
        self.add_btn.setEnabled(False)
        self.add_btn.clicked.connect(self._on_accepted)
        self.url_input.returnPressed.connect(self._on_accepted)
        self.url_input.textChanged.connect(self._validate)
        layout.addWidget(self.add_btn)

    def _on_accepted(self) -> None:
        log.info("add feed dialog accepted: %s", self.url)
        self.accept()

    def _validate(self, text: str) -> None:
        parsed = urlparse(text.strip())
        self.add_btn.setEnabled(bool(parsed.scheme and parsed.netloc))

    @property
    def url(self) -> str:
        """The trimmed URL text currently in the input field."""
        return self.url_input.text().strip()


class RenameFeedDialog(QtWidgets.QDialog):
    """Dialog for renaming a feed's display title."""

    def __init__(
        self, current_title: str, parent: QtWidgets.QWidget | None = None
    ) -> None:
        """Modal dialog with a pre-filled title field and a Rename button."""
        super().__init__(parent)
        self.setWindowTitle("Rename Feed")
        self.setFixedSize(400, 120)

        self.title_input: QtWidgets.QLineEdit = QtWidgets.QLineEdit()
        self.title_input.setText(current_title)
        self.title_input.selectAll()
        self.title_input.setFocus()

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel("Feed title:"))
        layout.addWidget(self.title_input)

        self.rename_btn: QtWidgets.QPushButton = QtWidgets.QPushButton("Rename")
        self.rename_btn.setEnabled(bool(current_title.strip()))
        self.rename_btn.clicked.connect(self._on_accepted)
        self.title_input.returnPressed.connect(self._on_accepted)
        self.title_input.textChanged.connect(self._validate)
        layout.addWidget(self.rename_btn)

    def _on_accepted(self) -> None:
        log.info("rename feed dialog accepted: %s", self.title)
        self.accept()

    def _validate(self, text: str) -> None:
        self.rename_btn.setEnabled(bool(text.strip()))

    @property
    def title(self) -> str:
        """The trimmed title text currently in the input field."""
        return self.title_input.text().strip()


class AddFeedChoiceDialog(QtWidgets.QDialog):
    """Dialog for choosing one or more feeds discovered from a URL."""

    def __init__(
        self,
        feeds: list[tuple[str, str]],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Modal dialog listing discovered feeds for multi-selection."""
        super().__init__(parent)
        self.setWindowTitle("Choose feeds")
        self.setMinimumSize(480, 300)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel("Multiple feeds found. Select which to add:"))

        self._list: QtWidgets.QListWidget = QtWidgets.QListWidget()
        self._list.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.MultiSelection
        )
        for url, title in feeds:
            item = QtWidgets.QListWidgetItem(f"{title}\n{url}")
            item.setData(QtWidgets.QListWidgetItem.ItemType.UserType, (url, title))
            item.setToolTip(url)
            self._list.addItem(item)
        layout.addWidget(self._list)

        btn_layout = QtWidgets.QHBoxLayout()
        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        add_btn = QtWidgets.QPushButton("Add Selected")
        add_btn.setDefault(True)
        add_btn.clicked.connect(self._on_accepted)
        btn_layout.addWidget(add_btn)
        layout.addLayout(btn_layout)

    def _on_accepted(self) -> None:
        selected = self.selected_feeds
        log.info(
            "feed choice dialog accepted: %d feed(s)",
            len(selected),
        )
        self.accept()

    @property
    def selected_feeds(self) -> list[tuple[str, str]]:
        """(url, title) tuples for every feed the user highlighted in the list."""
        return [
            (item.data(QtWidgets.QListWidgetItem.ItemType.UserType))
            for item in self._list.selectedItems()
        ]


class AboutDialog(QtWidgets.QDialog):
    """About dialog showing version and a GitHub link."""

    def __init__(self, version: str, parent: QtWidgets.QWidget | None = None) -> None:
        """Show version info and a clickable GitHub link."""
        super().__init__(parent)
        self.setWindowTitle("About feeds")
        self.setFixedSize(300, 150)

        layout = QtWidgets.QVBoxLayout(self)

        title = QtWidgets.QLabel(f"feeds {version}")
        title.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        font = title.font()
        font.setPointSize(14)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)

        link = QtWidgets.QLabel(
            '<a href="https://github.com/phagenlocher/feeds">Visit on GitHub</a>'
        )
        link.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        link.setOpenExternalLinks(True)
        layout.addWidget(link)

        layout.addStretch()

        btn = QtWidgets.QPushButton("OK")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)


class TagFeedDialog(QtWidgets.QDialog):
    """Dialog for assigning tags to a single feed."""

    def __init__(
        self,
        feed_title: str,
        feed_url: str,
        reader: FeedReader,
        tag_colors: dict[str, str],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Modal dialog with checkable tag list and new-tag input."""
        super().__init__(parent)
        self.setWindowTitle(f"Tag Feed \u2014 {feed_title}")
        self.setMinimumSize(360, 300)

        self._feed_url: str = feed_url
        self._reader = reader
        self._tag_colors: dict[str, str] = tag_colors
        self._all_tags: list[str] = reader.get_all_tag_keys()
        self._current_tags: set[str] = set(reader.get_feed_tags(feed_url))

        layout = QtWidgets.QVBoxLayout(self)

        layout.addWidget(QtWidgets.QLabel("Tags:"))

        self._tag_list: QtWidgets.QListWidget = QtWidgets.QListWidget()
        self._populate_list()
        layout.addWidget(self._tag_list)

        add_layout = QtWidgets.QHBoxLayout()
        self._new_tag_input: QtWidgets.QLineEdit = QtWidgets.QLineEdit()
        self._new_tag_input.setPlaceholderText("New tag name\u2026")
        add_layout.addWidget(self._new_tag_input)

        self._add_btn: QtWidgets.QPushButton = QtWidgets.QPushButton("Add")
        self._add_btn.setEnabled(False)
        add_layout.addWidget(self._add_btn)

        layout.addLayout(add_layout)

        btn_layout = QtWidgets.QHBoxLayout()
        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        ok_btn = QtWidgets.QPushButton("OK")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self._on_accept)
        btn_layout.addWidget(ok_btn)

        layout.addLayout(btn_layout)

        self._new_tag_input.textChanged.connect(self._validate_new_tag)
        self._new_tag_input.returnPressed.connect(self._add_new_tag)
        self._add_btn.clicked.connect(self._add_new_tag)

    def _populate_list(self) -> None:
        self._tag_list.clear()
        for tag in self._all_tags:
            item = QtWidgets.QListWidgetItem(tag)
            item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                QtCore.Qt.CheckState.Checked
                if tag in self._current_tags
                else QtCore.Qt.CheckState.Unchecked
            )
            color = self._tag_colors.get(tag)
            if color:
                pix = QtGui.QPixmap(12, 12)
                pix.fill(QtGui.QColor(color))
                item.setIcon(QtGui.QIcon(pix))
            self._tag_list.addItem(item)

    def _validate_new_tag(self, text: str) -> None:
        stripped = text.strip()
        self._add_btn.setEnabled(bool(stripped) and stripped not in self._all_tags)

    def _add_new_tag(self) -> None:
        tag = self._new_tag_input.text().strip()
        if not tag or tag in self._all_tags:
            return
        _pick_tag_color(tag, self._tag_colors)
        self._all_tags.append(tag)
        self._current_tags.add(tag)
        self._populate_list()
        self._new_tag_input.clear()

    def _on_accept(self) -> None:
        log.info("tag feed dialog accepted for %s", self._feed_url)
        self.accept()

    @property
    def selected_tags(self) -> list[str]:
        """Return the list of tag names the user checked."""
        result: list[str] = []
        for i in range(self._tag_list.count()):
            item = self._tag_list.item(i)
            if item is not None and item.checkState() == QtCore.Qt.CheckState.Checked:
                result.append(item.text())
        return result


class ManageTagsDialog(QtWidgets.QDialog):
    """Dialog for renaming, deleting, and recoloring tags globally."""

    def __init__(
        self,
        reader: FeedReader,
        tag_colors: dict[str, str],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Modal dialog with tag list and rename/delete/recolor actions."""
        super().__init__(parent)
        self.setWindowTitle("Manage Tags")
        self.setMinimumSize(400, 350)

        self._reader = reader
        self._tag_colors: dict[str, str] = tag_colors
        self._tags: list[str] = reader.get_all_tag_keys()

        layout = QtWidgets.QVBoxLayout(self)

        layout.addWidget(QtWidgets.QLabel("Tags:"))

        self._tag_list: QtWidgets.QListWidget = QtWidgets.QListWidget()
        self._populate_list()
        layout.addWidget(self._tag_list)

        btn_layout = QtWidgets.QHBoxLayout()

        rename_btn = QtWidgets.QPushButton("Rename\u2026")
        rename_btn.clicked.connect(self._on_rename)
        btn_layout.addWidget(rename_btn)

        delete_btn = QtWidgets.QPushButton("Delete")
        delete_btn.clicked.connect(self._on_delete)
        btn_layout.addWidget(delete_btn)

        recolor_btn = QtWidgets.QPushButton("Recolor\u2026")
        recolor_btn.clicked.connect(self._on_recolor)
        btn_layout.addWidget(recolor_btn)

        layout.addLayout(btn_layout)

        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

    def _populate_list(self) -> None:
        self._tag_list.clear()
        for tag in self._tags:
            item = QtWidgets.QListWidgetItem(tag)
            color = self._tag_colors.get(tag)
            if color:
                pix = QtGui.QPixmap(12, 12)
                pix.fill(QtGui.QColor(color))
                item.setIcon(QtGui.QIcon(pix))
            self._tag_list.addItem(item)

    def _refresh(self) -> None:
        self._tags = self._reader.get_all_tag_keys()
        self._populate_list()

    def _selected_tag(self) -> str | None:
        items = self._tag_list.selectedItems()
        if not items:
            return None
        return items[0].text()

    def _on_rename(self) -> None:
        old = self._selected_tag()
        if old is None:
            return
        new, ok = QtWidgets.QInputDialog.getText(
            self, "Rename Tag", f"Rename '{old}' to:", text=old
        )
        if not ok or not new.strip() or new.strip() == old:
            return
        new = new.strip()
        log.info("renaming tag '%s' to '%s'", old, new)
        self._reader.rename_tag(old, new)
        if old in self._tag_colors:
            self._tag_colors[new] = self._tag_colors.pop(old)
        self._refresh()

    def _on_delete(self) -> None:
        tag = self._selected_tag()
        if tag is None:
            return
        confirm = QtWidgets.QMessageBox.question(
            self,
            "Delete Tag",
            f"Remove tag '{tag}' from all feeds?",
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        if confirm != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        log.info("deleting tag '%s' from all feeds", tag)
        self._reader.delete_tag(tag)
        self._tag_colors.pop(tag, None)
        self._refresh()

    def _on_recolor(self) -> None:
        tag = self._selected_tag()
        if tag is None:
            return
        tag_color = self._tag_colors.get(tag)
        if tag_color is not None:
            current = QtGui.QColor(tag_color)
        else:
            current = self.palette().color(QtGui.QPalette.ColorRole.PlaceholderText)
        color = QtWidgets.QColorDialog.getColor(current, self, f"Color for '{tag}'")
        if not color.isValid():
            return
        self._tag_colors[tag] = color.name()
        self._refresh()

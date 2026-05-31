"""Feed-related dialogs."""

import logging
from urllib.parse import urlparse

from PySide6 import QtCore, QtWidgets

log: logging.Logger = logging.getLogger(__name__)


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

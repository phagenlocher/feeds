"""Feed-related dialogs."""

from urllib.parse import urlparse

from PySide6 import QtWidgets


class AddFeedDialog(QtWidgets.QDialog):
    """Dialog for entering a feed URL with basic validation."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
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
        self.add_btn.clicked.connect(self.accept)
        self.url_input.returnPressed.connect(self.accept)
        self.url_input.textChanged.connect(self._validate)
        layout.addWidget(self.add_btn)

    def _validate(self, text: str) -> None:
        parsed = urlparse(text.strip())
        self.add_btn.setEnabled(bool(parsed.scheme and parsed.netloc))

    @property
    def url(self) -> str:
        return self.url_input.text().strip()


class AddFeedChoiceDialog(QtWidgets.QDialog):
    """Dialog for choosing one or more feeds discovered from a URL."""

    def __init__(
        self,
        feeds: list[tuple[str, str]],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
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
        add_btn.clicked.connect(self.accept)
        btn_layout.addWidget(add_btn)
        layout.addLayout(btn_layout)

    @property
    def selected_feeds(self) -> list[tuple[str, str]]:
        return [
            (item.data(QtWidgets.QListWidgetItem.ItemType.UserType))
            for item in self._list.selectedItems()
        ]

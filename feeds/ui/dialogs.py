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

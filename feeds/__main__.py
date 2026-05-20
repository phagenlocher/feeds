"""Entry point: python -m feeds"""

import sys

from PySide6 import QtWidgets

from feeds.app import FeedsApp


def main() -> None:
    qapp = QtWidgets.QApplication(sys.argv)
    window = FeedsApp()
    window.show()
    sys.exit(qapp.exec())


if __name__ == "__main__":
    main()

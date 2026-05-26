"""Application entry point invoked via python -m feeds."""

import argparse
import logging
import sys

from PySide6 import QtWidgets

from feeds.app import FeedsApp


def main() -> None:
    """Parse CLI arguments, configure logging, and launch the FeedsApp main window."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging"
    )
    args, _ = parser.parse_known_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s:%(name)s:%(message)s",
    )

    qapp = QtWidgets.QApplication(sys.argv)
    window = FeedsApp()
    window.show()
    sys.exit(qapp.exec())


if __name__ == "__main__":
    main()

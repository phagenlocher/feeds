"""Application entry point invoked via python -m feeds."""

import argparse
import logging
import sys
from pathlib import Path

from PySide6 import QtWidgets

from feeds import __version__
from feeds._single_instance import SingleInstanceGuard
from feeds.app import FeedsApp


def main() -> None:
    """Parse CLI arguments, configure logging, and launch the FeedsApp main window."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging"
    )
    parser.add_argument(
        "-d",
        "--data-dir",
        type=Path,
        default=Path("~/.feeds").expanduser(),
        help="Data directory for feeds.db and settings.json (default: ~/.feeds)",
    )
    parser.add_argument("--version", action="version", version=__version__)
    args, _ = parser.parse_known_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s:%(name)s:%(message)s",
    )

    qapp: QtWidgets.QApplication = QtWidgets.QApplication(sys.argv)
    qapp.setPalette(qapp.style().standardPalette())

    window: FeedsApp | None = None

    def _focus_window() -> None:
        nonlocal window
        if window is not None:
            window.showNormal()
            window.raise_()
            window.activateWindow()
            qapp.alert(window, 3000)

    guard: SingleInstanceGuard = SingleInstanceGuard(on_focus=_focus_window)
    guard.assume_single_instance()

    window = FeedsApp(data_dir=args.data_dir)
    window.show()
    sys.exit(qapp.exec())


if __name__ == "__main__":
    main()

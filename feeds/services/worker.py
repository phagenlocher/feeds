"""Background-thread worker with done/error signals."""

import logging
from collections.abc import Callable

from PySide6 import QtCore

log: logging.Logger = logging.getLogger(__name__)


class WorkerThread(QtCore.QThread):
    """Runs a callable in a background thread, emits done/error signals."""

    done: QtCore.Signal = QtCore.Signal()
    error: QtCore.Signal = QtCore.Signal(str)

    def __init__(self, fn: Callable[[], object], name: str | None = None) -> None:
        """Store callable and derive name from fn.__name__ if not supplied."""
        super().__init__()
        self._fn: Callable[[], object] = fn
        self._name: str = name or fn.__name__

    def run(self) -> None:
        """Run callable, emit done or error with exception text on failure."""
        log.info("starting worker %s", self._name)
        try:
            self._fn()
        except Exception as e:
            log.exception("%s failed", self._name)
            self.error.emit(str(e))
        else:
            log.info("worker %s completed", self._name)
            self.done.emit()

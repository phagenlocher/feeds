"""Background-thread worker with done/error signals."""

from collections.abc import Callable

from PySide6 import QtCore


class WorkerThread(QtCore.QThread):
    """Runs a callable in a background thread, emits done/error signals."""

    done: QtCore.Signal = QtCore.Signal()
    error: QtCore.Signal = QtCore.Signal(str)

    def __init__(self, fn: Callable[[], object]) -> None:
        super().__init__()
        self._fn: Callable[[], object] = fn

    def run(self) -> None:
        try:
            self._fn()
        except Exception as e:
            self.error.emit(str(e))
        else:
            self.done.emit()

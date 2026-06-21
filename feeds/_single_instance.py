"""Guard against multiple application instances using QSharedMemory + QLocalServer.

Usage::

    from feeds._single_instance import SingleInstanceGuard

    guard = SingleInstanceGuard(on_focus=_bring_window_to_front)
    guard.check()   # sys.exit(0) if another instance is already running
"""

import logging
import sys
from collections.abc import Callable

from PySide6.QtCore import QSharedMemory
from PySide6.QtNetwork import QLocalServer, QLocalSocket

log: logging.Logger = logging.getLogger(__name__)

SHARED_MEMORY_KEY = "feeds-app"


class SingleInstanceGuard:
    """Ensures only one application process runs at a time.

    The **first** process creates a :class:`QSharedMemory` segment and
    a :class:`QLocalServer`.  Subsequent processes detect the existing
    shared memory, notify the server via a local socket, and exit.

    Args:
        on_focus: Callback invoked when a secondary instance requests
            focus.  Typically raises / activates the main window.
    """

    def __init__(self, on_focus: Callable[[], None]) -> None:
        self._on_focus = on_focus
        self._server: QLocalServer | None = None
        self._memory = QSharedMemory(SHARED_MEMORY_KEY)

    def assume_single_instance(self) -> None:
        """Check that the current instance is the only instance of this program.

        If another instance is already running, this method sends a
        ``focus`` request to that instance and then calls
        :func:`sys.exit(0)`.
        """
        if self._memory.attach(QSharedMemory.AccessMode.ReadOnly):
            self._signal_focus()
            sys.exit(0)

        if not self._memory.create(1):
            if self._memory.attach(QSharedMemory.AccessMode.ReadOnly):
                self._signal_focus()
            sys.exit(0)

        QLocalServer.removeServer(SHARED_MEMORY_KEY)
        self._server = QLocalServer()
        self._server.newConnection.connect(self._on_new_connection)
        if not self._server.listen(SHARED_MEMORY_KEY):
            log.error("single-instance server failed: %s", self._server.errorString())

    def _signal_focus(self) -> None:
        """Connect to the running instance's server and request focus."""
        sock = QLocalSocket()
        sock.connectToServer(SHARED_MEMORY_KEY)
        if not sock.waitForConnected(1000):
            log.warning("could not connect to running instance: %s", sock.errorString())
            return
        sock.write(b"focus")
        sock.waitForBytesWritten(1000)
        sock.disconnectFromServer()

    def _on_new_connection(self) -> None:
        """Handle an incoming connection from a secondary instance."""
        if self._server is None:
            return
        conn = self._server.nextPendingConnection()
        if conn is None:
            return
        if conn.waitForReadyRead(1000):
            data = conn.readAll().data()
            if data == b"focus":
                log.info("focus requested by secondary instance")
                self._on_focus()
        conn.disconnectFromServer()

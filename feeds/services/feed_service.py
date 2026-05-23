"""Async orchestration: runs feed operations in background threads."""

import logging
from collections.abc import Callable
from dataclasses import dataclass

from feeds.models.feed import Feed, FeedReader
from feeds.services.worker import WorkerThread

log: logging.Logger = logging.getLogger(__name__)


@dataclass
class _PendingOp:
    fn: Callable[[], object]
    name: str
    on_done: Callable[[], object] | None
    on_error: Callable[[str], object] | None


class FeedService:
    """Manages background worker lifecycle for feed operations.

    Operations are queued when one is already in progress and executed
    sequentially in FIFO order.
    """

    def __init__(self, reader: FeedReader) -> None:
        self._reader: FeedReader = reader
        self._worker: WorkerThread | None = None
        self._queue: list[_PendingOp] = []

    @property
    def is_busy(self) -> bool:
        return self._worker is not None

    def run(
        self,
        fn: Callable[[], object],
        name: str,
        on_done: Callable[[], object] | None = None,
        on_error: Callable[[str], object] | None = None,
    ) -> bool:
        """Execute *fn* in a background thread.

        If an operation is already in progress, *fn* is queued and will
        run when the current operation finishes.
        Always returns True.
        """
        if self._worker is not None:
            self._queue.append(_PendingOp(fn, name, on_done, on_error))
            return True

        self._start(fn, name, on_done, on_error)
        return True

    def _start(
        self,
        fn: Callable[[], object],
        name: str,
        on_done: Callable[[], object] | None,
        on_error: Callable[[str], object] | None,
    ) -> None:
        thread = WorkerThread(fn, name=name)

        def _done() -> None:
            if on_done:
                on_done()

        def _error(msg: str) -> None:
            log.error("service operation failed: %s", msg)
            if on_error:
                on_error(msg)

        def _cleanup() -> None:
            self._worker = None
            self._process_queue()

        thread.done.connect(_done)
        thread.error.connect(_error)
        thread.finished.connect(_cleanup)
        self._worker = thread
        thread.start()

    def _process_queue(self) -> None:
        if self._queue and self._worker is None:
            op: _PendingOp = self._queue.pop(0)
            self._start(op.fn, op.name, op.on_done, op.on_error)

    def add_feed(
        self,
        url: str,
        on_done: Callable[[], object] | None = None,
        on_error: Callable[[str], object] | None = None,
    ) -> None:
        log.info("adding feed %s", url)
        self.run(lambda: self._reader.add_feed(url), "add_feed", on_done, on_error)

    def discover_feeds(
        self,
        url: str,
        on_done: Callable[[list[tuple[str, str]]], object] | None = None,
        on_error: Callable[[str], object] | None = None,
    ) -> None:
        log.info("discovering feeds from %s", url)
        result: list[list[tuple[str, str]]] = []

        def _discover() -> None:
            result.append(self._reader.discover_feeds(url))

        def _on_done() -> None:
            if on_done and result:
                on_done(result[0])

        self.run(_discover, "discover_feeds", _on_done, on_error)

    def update_feed(
        self,
        url: str,
        on_done: Callable[[], object] | None = None,
        on_error: Callable[[str], object] | None = None,
    ) -> None:
        log.info("updating feed %s", url)
        self.run(
            lambda: self._reader.update_feed(url), "update_feed", on_done, on_error
        )

    def update_feeds(
        self,
        on_done: Callable[[], object] | None = None,
        on_error: Callable[[str], object] | None = None,
    ) -> None:
        log.info("updating all feeds")
        self.run(lambda: self._reader.update_feeds(), "update_feeds", on_done, on_error)

    def delete_feed(
        self,
        feed: Feed,
        on_done: Callable[[], object] | None = None,
        on_error: Callable[[str], object] | None = None,
    ) -> None:
        log.info("deleting feed %s", feed.id)
        self.run(
            lambda: self._reader.delete_feed(feed), "delete_feed", on_done, on_error
        )

    def mark_all_as_read(
        self,
        feed: Feed,
        on_done: Callable[[], object] | None = None,
        on_error: Callable[[str], object] | None = None,
    ) -> None:
        log.info("marking all as read in feed %s", feed.id)
        self.run(
            lambda: self._reader.mark_all_as_read(feed),
            "mark_all_as_read",
            on_done,
            on_error,
        )

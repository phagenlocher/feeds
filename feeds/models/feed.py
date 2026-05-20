"""Data-layer: Feed/Entry dataclasses and FeedReader wrapping the reader library."""

import logging
import os
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import reader

log = logging.getLogger(__name__)

_DB_PATH: Path = Path(
    os.environ.get("FEEDS_DB_PATH") or Path("~/.feeds/feeds.db").expanduser()
)


@dataclass(frozen=True, slots=True)
class Feed:
    id: str
    title: str
    last_updated: datetime | None


@dataclass(frozen=True, slots=True)
class Entry:
    url: str
    title: str
    last_updated: datetime | None
    entry_id: str
    feed_id: str
    read: bool


class FeedReader:
    def __init__(self) -> None:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.reader: reader.Reader = reader.make_reader(str(_DB_PATH))

    def add_feed(self, url: str) -> None:
        self.reader.add_feed(url, exist_ok=True)

    def update_feeds(self) -> None:
        self.reader.update_feeds()

    def update_feed(self, feed_url: str) -> None:
        self.reader.update_feed(feed_url)

    def get_feeds(self) -> Iterator[Feed]:
        for f in self.reader.get_feeds():
            yield Feed(id=f.url, title=f.title or "No Title", last_updated=f.updated)

    def get_posts(self, feed: Feed) -> Iterator[Entry]:
        for e in self.reader.get_entries(feed=feed.id):
            if not e.link:
                log.warning("entry %s has no link, skipping", e.id)
                continue
            yield Entry(
                url=e.link,
                title=e.title or "No Title",
                last_updated=e.updated or e.published,
                entry_id=e.id,
                feed_id=feed.id,
                read=e.read,
            )

    def mark_entry_as_read(self, entry: Entry) -> None:
        self.reader.mark_entry_as_read((entry.feed_id, entry.entry_id))

    def mark_entry_as_unread(self, entry: Entry) -> None:
        self.reader.mark_entry_as_unread((entry.feed_id, entry.entry_id))

    def delete_feed(self, feed: Feed) -> None:
        self.reader.delete_feed(feed.id)

    def mark_all_as_read(self, feed: Feed) -> None:
        for e in self.reader.get_entries(feed=feed.id):
            self.reader.mark_entry_as_read((feed.id, e.id))

    def get_unread_count(self, feed: Feed) -> int:
        return (self.reader.get_entry_counts(feed=feed.id, read=False).total) or 0

"""Data-layer: Feed/Entry dataclasses and FeedReader wrapping the reader library."""

import logging
import os
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import feedparser
import reader
import requests
from requests.utils import parse_header_links

from feeds.discovery.youtube import try_youtube

log = logging.getLogger(__name__)

_DB_PATH: Path = Path(
    os.environ.get("FEEDS_DB_PATH") or Path("~/.feeds/feeds.db").expanduser()
)


class _FeedLinkFinder(HTMLParser):
    """HTML parser that extracts feed <link> tags."""

    def __init__(self) -> None:
        super().__init__()
        self.feeds: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "link":
            return
        attrs_dict = {k.lower(): v for k, v in attrs if v is not None}
        rel = attrs_dict.get("rel", "")
        link_type = attrs_dict.get("type", "")
        href = attrs_dict.get("href", "")
        if rel == "alternate" and href and link_type in FEED_MIME_TYPES:
            title = attrs_dict.get("title", href)
            self.feeds.append((href, title))


FEED_MIME_TYPES = frozenset({
    "application/rss+xml",
    "application/atom+xml",
    "application/feed+json",
})

_FEED_PATHS: tuple[str, ...] = (
    "/feed/",
    "/feed",
    "/feed.xml",
    "/index.xml",
    "/atom.xml",
    "/rss",
    "/rss.xml",
    "/feeds/posts/default",
)


def _parse_link_header(header_value: str, base_url: str) -> list[tuple[str, str]]:
    """Parse HTTP ``Link`` response headers for feed references.

    Handles both single and comma-separated ``Link`` headers
    (RFC 5988).  Example::

        Link: </feed.xml>; rel="alternate"; type="application/rss+xml"

    Only entries with ``rel="alternate"`` and a recognised feed
    MIME type are returned.
    """
    feeds: list[tuple[str, str]] = []
    try:
        links = parse_header_links(header_value)
    except Exception:
        return feeds

    for link in links:
        rel = link.get("rel", "").strip().lower()
        link_type = link.get("type", "").strip().lower()
        href = link.get("url", "")
        if rel == "alternate" and href and link_type in FEED_MIME_TYPES:
            title = link.get("title", href)
            feeds.append((urljoin(base_url, href), title))

    return feeds


def _try_common_paths(url: str) -> list[tuple[str, str]]:
    """Probe well-known feed paths on the domain.

    Tried when no feed was found via ``<link>`` tags or ``Link``
    headers.  Probes paths such as ``/feed/`` (WordPress),
    ``/feed.xml`` / ``/index.xml`` (static-site generators),
    ``/atom.xml``, ``/rss`` (Tumblr), and ``/feeds/posts/default``
    (Blogger) relative to the domain root, plus relative to the
    current path if it differs from root.

    Each candidate is fetched (3 s timeout) and run through
    ``feedparser``.  Only candidates that parse as valid feeds are
    returned.
    """
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    prefixes: list[str] = [base]
    stripped = parsed.path.rstrip("/")
    parent = stripped.rsplit("/", 1)[0] if "/" in stripped else ""
    if parent:
        prefixes.append(f"{base}{parent}")

    feeds: list[tuple[str, str]] = []
    seen: set[str] = set()

    for prefix in prefixes:
        for path in _FEED_PATHS:
            feed_url = f"{prefix}{path}"
            if feed_url in seen:
                continue
            seen.add(feed_url)

            try:
                resp = requests.get(
                    feed_url,
                    timeout=3,
                    headers={"User-Agent": "feeds/0.1"},
                    allow_redirects=True,
                )
                resp.raise_for_status()
                parsed_feed = feedparser.parse(resp.content)
                if parsed_feed.version:
                    feed_data = parsed_feed.feed
                    title = (
                        feed_data.get("title", "")
                        if isinstance(feed_data, dict)
                        else ""
                    )
                    feeds.append((resp.url, title or feed_url))
            except requests.RequestException:
                continue
            except Exception:
                log.warning("Failed to parse potential feed at %s", feed_url)
                continue

    return feeds


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
        self._last_discovered_feeds: list[tuple[str, str]] = []

    def add_feed(self, url: str) -> None:
        self.reader.add_feed(url, exist_ok=True)

    @staticmethod
    def _discover_feed_urls(url: str) -> list[tuple[str, str]]:
        """Discover feed URLs from *url* using multiple methods.

        Uses the following methods, in order:

        1. **Direct feed check**
           Tries to parse the response as a feed (RSS, Atom, JSON Feed)
           using ``feedparser``.  If the URL is itself a feed, it is
           returned immediately.

        2. **HTML ``<link>`` tags**
           Scans the HTML for ``<link rel="alternate">`` with a feed
           MIME type (``application/rss+xml``, ``application/atom+xml``,
           ``application/feed+json``).

        3. **HTTP ``Link`` headers**
           Parses ``Link`` response headers (RFC 5988) referencing
           alternate feeds.

        4. **Common path probing**
           Probes well-known feed paths (``/feed/``, ``/feed.xml``,
           ``/index.xml``, etc.) as a last resort.

        Returns:
            ``[(feed_url, title), ...]``, or ``[]`` if nothing was found.

        .. note::

            YouTube URLs are handled by a specialised pre-check
            (:func:`feeds.discovery.youtube.try_youtube`) that runs
            **before** any HTTP request, because YouTube serves a
            GDPR consent wall instead of the actual page to
            automated clients.
        """
        # YouTube pre-handler (bypasses GDPR consent wall —
        # never fetch YouTube HTML pages directly).
        feeds = try_youtube(url)
        if feeds:
            return feeds

        feeds: list[tuple[str, str]] = []
        seen: set[str] = set()

        def _add(href: str, title: str) -> None:
            if href not in seen:
                seen.add(href)
                feeds.append((href, title))

        try:
            resp = requests.get(
                url,
                timeout=10,
                headers={"User-Agent": "feeds/0.1"},
                allow_redirects=True,
            )
            resp.raise_for_status()
        except requests.RequestException:
            log.warning("Failed to fetch %s for feed discovery", url)
            return []

        # --- Method 1: Try to parse as a feed directly ---
        parsed = feedparser.parse(resp.content)
        if parsed.version:
            feed = parsed.feed
            title = feed.get("title", "") if isinstance(feed, dict) else ""
            _add(url, title or url)
            return feeds  # It IS a feed; skip remaining methods.

        content_type = resp.headers.get("Content-Type", "")
        is_html = "text/html" in content_type or "application/xhtml" in content_type

        # --- Method 2: HTML <link> tags ---
        if is_html:
            finder = _FeedLinkFinder()
            try:
                finder.feed(resp.text)
            except Exception:
                log.warning("Failed to parse HTML from %s", url)
            else:
                for href, title in finder.feeds:
                    _add(urljoin(resp.url, href), title)

        # --- Method 3: HTTP Link headers ---
        link_header = resp.headers.get("Link", "")
        if link_header:
            for href, title in _parse_link_header(link_header, resp.url):
                _add(href, title)

        # --- Method 4: Common path probing (last resort, only for HTML) ---
        if not feeds and is_html:
            for href, title in _try_common_paths(resp.url):
                _add(href, title)

        return feeds

    def discover_feeds(self, url: str) -> list[tuple[str, str]]:
        """Discover feed URLs from *url*.

        Returns ``[(feed_url, title), ...]``.
        Results are also available via :attr:`last_discovered_feeds`.
        """
        self._last_discovered_feeds = self._discover_feed_urls(url)
        return self._last_discovered_feeds

    @property
    def last_discovered_feeds(self) -> list[tuple[str, str]]:
        return self._last_discovered_feeds

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

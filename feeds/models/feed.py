"""Data-layer: Feed/Entry dataclasses and FeedReader wrapping the reader library.

The :class:`FeedReader` class is the primary API surface for feed
management.  It wraps the ``reader`` library and adds feed-discovery
logic that can handle raw HTML pages, platform-specific URL patterns
(YouTube, Reddit, Medium, Substack), and common feed path heuristics.

Feed discovery pipeline (in order):

1. Platform-specific pre-handlers (before HTTP fetch)
2. Direct feed parsing via ``feedparser.parse()``
3. HTML ``<link rel="alternate">`` tag scanning
4. HTTP ``Link`` response headers (RFC 5988)
5. Common-path probing (``/feed/``, ``/rss``, etc.)
"""

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

from feeds.discovery.medium import try_medium
from feeds.discovery.reddit import try_reddit
from feeds.discovery.substack import try_substack
from feeds.discovery.utils import USER_AGENT
from feeds.discovery.youtube import try_youtube

log: logging.Logger = logging.getLogger(__name__)

_DB_PATH: Path = Path(
    os.environ.get("FEEDS_DB_PATH") or Path("~/.feeds/feeds.db").expanduser()
)


class _FeedLinkFinder(HTMLParser):
    """HTML parser that extracts feed ``<link>`` tags from a page.

    Collects ``<link rel="alternate">`` elements whose ``type``
    attribute matches a known feed MIME type
    (:data:`FEED_MIME_TYPES`).  Also tracks ``<base href>`` for
    correct relative URL resolution.
    """

    def __init__(self) -> None:
        """Initialise the parser with empty results and no base URL."""
        super().__init__()
        self.feeds: list[tuple[str, str]] = []
        self.base_href: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Process an HTML start tag.

        Handles two tag types:

        * ``<base>`` — records the ``href`` attribute as the base URL
          for resolving relative feed URLs.
        * ``<link>`` — checks for ``rel="alternate"`` (space-separated
          multi-value support) and a recognised feed MIME type, then
          appends ``(href, title)`` to :attr:`feeds`.

        Args:
            tag: The HTML tag name (lowercased by ``HTMLParser``).
            attrs: List of ``(name, value)`` tuples from the parser.
        """
        attrs_dict = {k.lower(): v for k, v in attrs if v is not None}

        if tag == "base":
            href = attrs_dict.get("href", "")
            if href:
                self.base_href = href
            return

        if tag != "link":
            return

        rel = attrs_dict.get("rel", "").strip()
        link_type = attrs_dict.get("type", "")
        href = attrs_dict.get("href", "")
        if href and "alternate" in rel.split() and link_type in FEED_MIME_TYPES:
            title = attrs_dict.get("title", href)
            self.feeds.append((href, title))


FEED_MIME_TYPES = frozenset(
    {
        "application/rss+xml",
        "application/atom+xml",
        "application/feed+json",
    }
)
"""Recognised feed MIME types for autodiscovery.

Used when scanning ``<link>`` tags and ``Link`` HTTP headers to
identify feed references.  Includes RSS, Atom, and JSON Feed.
"""

_FEED_PATHS: tuple[str, ...] = (
    "/feed/",
    "/feed",
    "/feed.xml",
    "/feed.json",
    "/index.xml",
    "/atom.xml",
    "/atom",
    "/rss",
    "/rss/",
    "/rss.xml",
    "/blog?format=rss",
    "/feeds/posts/default",
)
"""Well-known feed URL paths probed as a fallback discovery method.

Each path is appended to the domain root (and the current path's
parent directory) and tested with ``feedparser``.

Platforms targeted:

* ``/feed/``, ``/feed`` — WordPress
* ``/feed.xml``, ``/index.xml`` — static-site generators (Hugo, Jekyll)
* ``/feed.json`` — JSON Feed
* ``/atom.xml``, ``/atom`` — Atom feeds
* ``/rss``, ``/rss/``, ``/rss.xml`` — Tumblr, Ghost, generic RSS
* ``/blog?format=rss`` — Squarespace
* ``/feeds/posts/default`` — Blogger
"""


def _parse_link_header(header_value: str, base_url: str) -> list[tuple[str, str]]:
    """Parse HTTP ``Link`` response headers for feed references.

    Handles both single and comma-separated ``Link`` headers
    (RFC 5988).  Example::

        Link: </feed.xml>; rel="alternate"; type="application/rss+xml"

    Only entries with ``rel="alternate"`` and a recognised feed
    MIME type are returned.

    Args:
        header_value: The raw ``Link`` header value.
        base_url: The base URL for resolving relative ``href`` values.

    Returns:
        List of ``(feed_url, title)`` tuples found in the header.
    """
    feeds: list[tuple[str, str]] = []
    try:
        links: list[dict[str, str]] = parse_header_links(header_value)
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
    headers.  Probes paths from :data:`_FEED_PATHS` relative to the
    domain root, plus relative to the current path's parent directory
    if it differs from root.

    Each candidate is fetched with a 3-second timeout and validated
    through ``feedparser``.  Only candidates that parse as valid
    feeds are returned.

    Args:
        url: The original page URL (used to extract scheme, host, and
            parent path).

    Returns:
        List of ``(feed_url, title)`` tuples for discovered feeds.
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
                resp: requests.Response = requests.get(
                    feed_url,
                    timeout=3,
                    headers={"User-Agent": USER_AGENT},
                    allow_redirects=True,
                )
                resp.raise_for_status()
                parsed_feed: feedparser.FeedParserDict = feedparser.parse(resp.content)
                if parsed_feed.version:
                    feed_data = parsed_feed.feed
                    title = feed_data.get("title", "")
                    feeds.append((resp.url, title or feed_url))
            except requests.RequestException:
                continue
            except Exception:
                log.warning("Failed to parse potential feed at %s", feed_url)
                continue

    return feeds


@dataclass(frozen=True, slots=True)
class Feed:
    """A single RSS/Atom feed tracked in the local database.

    Attributes:
        id: The feed's URL (used as the unique identifier).
        title: Human-readable display title (user title if set, else original).
        last_updated: Timestamp of the most recent update, or ``None``
            if never updated.
        user_title: Custom title set by the user, or ``None``.
    """

    id: str
    title: str
    last_updated: datetime | None
    user_title: str | None = None


@dataclass(frozen=True, slots=True)
class Entry:
    """A single entry (article/post) within a feed.

    Attributes:
        url: Permalink to the entry.
        title: Entry headline.
        last_updated: Publication or last-updated timestamp.
        entry_id: Unique identifier within the feed (``reader`` internals).
        feed_id: The :attr:`Feed.id` this entry belongs to.
        read: Whether the entry has been marked as read.
        author: Author name(s) as a string, or empty if unknown.
    """

    url: str
    title: str
    last_updated: datetime | None
    entry_id: str
    feed_id: str
    read: bool
    author: str = ""


class FeedReader:
    """High-level interface for feed management and discovery.

    Wraps the ``reader`` library and provides feed discovery,
    subscription management, and entry navigation.  All database
    state is persisted to the SQLite database at :data:`_DB_PATH`.

    Typical usage::

        reader = FeedReader()
        reader.add_feed("https://example.com/feed.xml")
        reader.update_feeds()
        for feed in reader.get_feeds():
            for entry in reader.get_posts(feed):
                print(entry.title)
    """

    def __init__(self) -> None:
        """Initialise the reader, creating the database directory if needed."""
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.reader: reader.Reader = reader.make_reader(str(_DB_PATH))
        self._last_discovered_feeds: list[tuple[str, str]] = []

    def add_feed(self, url: str) -> None:
        """Subscribe to a feed URL.

        If the feed is already subscribed, this is a no-op.

        Args:
            url: The feed URL to add.
        """
        log.info("subscribing to feed %s", url)
        self.reader.add_feed(url, exist_ok=True)

    @staticmethod
    def _discover_feed_urls(url: str) -> list[tuple[str, str]]:
        """Discover feed URLs from *url* using multiple methods.

        Uses the following methods, in order:

        1. **Platform pre-handlers** — specialised handlers for
           Substack, Medium, Reddit, and YouTube that run **before**
           any HTTP request.  They construct the feed URL directly
           from known platform URL patterns, bypassing slow page
           fetches and consent walls.

        2. **Direct feed check** — tries to parse the response as a
           feed (RSS, Atom, JSON Feed) using ``feedparser``.  If the
           URL is itself a feed, it is returned immediately.

        3. **HTML ``<link>`` tags** — scans the HTML for
           ``<link rel="alternate">`` with a feed MIME type
           (``application/rss+xml``, ``application/atom+xml``,
           ``application/feed+json``).  Supports multi-value ``rel``
           attributes and ``<base href>`` for relative URL resolution.

        4. **HTTP ``Link`` headers** — parses ``Link`` response
           headers (RFC 5988) referencing alternate feeds.

        5. **Common path probing** — probes well-known feed paths
           (``/feed/``, ``/feed.xml``, ``/index.xml``, etc.) as a
           last resort when all other methods fail.

        Args:
            url: The URL to discover feeds from.

        Returns:
            ``[(feed_url, title), ...]``, or ``[]`` if nothing was found.
        """
        feeds = try_substack(url)
        if feeds:
            log.debug("Substack handler returned %d feed(s)", len(feeds))
            return feeds
        feeds = try_medium(url)
        if feeds:
            log.debug("Medium handler returned %d feed(s)", len(feeds))
            return feeds
        feeds = try_reddit(url)
        if feeds:
            log.debug("Reddit handler returned %d feed(s)", len(feeds))
            return feeds
        feeds = try_youtube(url)
        if feeds:
            log.debug("YouTube handler returned %d feed(s)", len(feeds))
            return feeds

        feeds: list[tuple[str, str]] = []
        seen: set[str] = set()

        def _add(href: str, title: str) -> None:
            if href not in seen:
                seen.add(href)
                feeds.append((href, title))

        try:
            resp: requests.Response = requests.get(
                url,
                timeout=10,
                headers={"User-Agent": USER_AGENT},
                allow_redirects=True,
            )
            resp.raise_for_status()
        except requests.RequestException:
            log.warning("Failed to fetch %s for feed discovery", url)
            return []

        # Method 1: try to parse as a feed directly
        parsed: feedparser.FeedParserDict = feedparser.parse(resp.content)
        if parsed.version:
            log.debug("%s is a feed directly (version=%s)", url, parsed.version)
            feed = parsed.feed
            title = feed.get("title", "")
            _add(url, title or url)
            return feeds  # It IS a feed; skip remaining methods.
        log.debug("%s is not a feed (version=%s)", url, parsed.version)

        content_type: str = resp.headers.get("Content-Type", "")
        is_html = "text/html" in content_type or "application/xhtml+xml" in content_type

        # Method 2: HTML <link> tags
        if is_html:
            log.debug("scanning HTML <link> tags for feed references")
            finder: _FeedLinkFinder = _FeedLinkFinder()
            try:
                finder.feed(resp.text)
            except Exception:
                log.warning("Failed to parse HTML from %s", url)
            else:
                base_url = (
                    urljoin(resp.url, finder.base_href)
                    if finder.base_href
                    else resp.url
                )
                log.debug("found %d feed(s) via <link> tags", len(finder.feeds))
                for href, title in finder.feeds:
                    log.debug("  <link> feed: %s (%s)", href, title)
                    _add(urljoin(base_url, href), title)
        else:
            log.debug("content type is %s, skipping HTML scan", content_type)

        # Method 3: HTTP Link headers
        link_header: str = resp.headers.get("Link", "")
        if link_header:
            log.debug("parsing HTTP Link headers")
            for href, title in _parse_link_header(link_header, resp.url):
                log.debug("  Link header feed: %s (%s)", href, title)
                _add(href, title)
        else:
            log.debug("no Link headers found")

        # Method 4: common path probing (only for HTML)
        if not feeds and is_html:
            log.debug("no feeds found yet, probing common paths on %s", resp.url)
            path_feeds = _try_common_paths(resp.url)
            log.debug("common path probing returned %d feed(s)", len(path_feeds))
            for href, title in path_feeds:
                _add(href, title)
        elif feeds:
            log.debug(
                "skipping common path probing (already found %d feed(s))", len(feeds)
            )
        else:
            log.debug("skipping common path probing (content type %s)", content_type)

        return feeds

    def discover_feeds(self, url: str) -> list[tuple[str, str]]:
        """Discover feed URLs from *url*.

        Wraps :meth:`_discover_feed_urls` and caches the result in
        :attr:`last_discovered_feeds`.

        Args:
            url: The URL to discover feeds from.

        Returns:
            ``[(feed_url, title), ...]``.
        """
        log.info("discovering feeds from %s", url)
        self._last_discovered_feeds = self._discover_feed_urls(url)
        log.info("discovered %d feed(s)", len(self._last_discovered_feeds))
        return self._last_discovered_feeds

    @property
    def last_discovered_feeds(self) -> list[tuple[str, str]]:
        """The most recently discovered feed URLs and titles.

        Populated by :meth:`discover_feeds`.  Returns an empty list
        if no discovery has been performed yet.
        """
        return self._last_discovered_feeds

    def update_feeds(self, scheduled: bool = True) -> None:
        """Fetch new entries for all subscribed feeds.

        Args:
            scheduled: Whether to obey the per-feed update schedule.
        """
        log.info("updating all feeds")
        feed_count: int = len(list(self.reader.get_feeds()))
        workers: int = min(feed_count, (os.cpu_count() or 1) * 2)
        self.reader.update_feeds(workers=workers, scheduled=scheduled)

    def update_feed(self, feed_url: str) -> None:
        """Fetch new entries for a single feed.

        Args:
            feed_url: The URL of the feed to update.
        """
        log.info("updating feed %s", feed_url)
        self.reader.update_feed(feed_url)

    def get_feeds(self) -> Iterator[Feed]:
        """Yield all subscribed feeds.

        Yields:
            :class:`Feed` instances in an unspecified order.
        """
        for f in self.reader.get_feeds():
            yield Feed(
                id=f.url,
                title=f.resolved_title or "No Title",
                last_updated=f.updated,
                user_title=f.user_title,
            )

    def get_posts(self, feed: Feed) -> Iterator[Entry]:
        """Yield all entries (posts) belonging to a feed.

        Entries without a ``link`` attribute are skipped with a
        warning log.

        Args:
            feed: The feed whose entries to retrieve.

        Yields:
            :class:`Entry` instances in insertion order.
        """
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
                author=e.authors_str or "",
            )

    def mark_entry_as_read(self, entry: Entry) -> None:
        """Mark a single entry as read.

        Args:
            entry: The entry to mark.
        """
        log.info("marking entry read: %s", entry.entry_id)
        self.reader.mark_entry_as_read((entry.feed_id, entry.entry_id))

    def mark_entry_as_unread(self, entry: Entry) -> None:
        """Mark a single entry as unread.

        Args:
            entry: The entry to mark.
        """
        log.info("marking entry unread: %s", entry.entry_id)
        self.reader.mark_entry_as_unread((entry.feed_id, entry.entry_id))

    def set_feed_user_title(self, feed: Feed, title: str) -> None:
        """Set a custom display title for a feed.

        Args:
            feed: The feed to rename.
            title: The new display title.
        """
        log.info("setting user title for feed %s to '%s'", feed.id, title)
        self.reader.set_feed_user_title(feed.id, title)

    def delete_feed(self, feed: Feed) -> None:
        """Unsubscribe a feed and remove all its entries.

        Args:
            feed: The feed to delete.
        """
        log.info("unsubscribing feed %s", feed.id)
        self.reader.delete_feed(feed.id)

    def mark_all_as_read(self, feed: Feed) -> None:
        """Mark every entry in a feed as read.

        Args:
            feed: The feed whose entries should be marked read.
        """
        log.info("marking all entries read in feed %s", feed.id)
        for e in self.reader.get_entries(feed=feed.id):
            self.reader.mark_entry_as_read((feed.id, e.id))

    def prune_feed(self, feed: Feed, n: int) -> int:
        """Keep only the *n* most recent entries, delete the rest.

        Entries are sorted by ``updated``/``published`` (newest first).
        Returns the number of entries deleted.

        Args:
            feed: The feed to prune.
            n: The number of most recent entries to keep.

        Returns:
            The number of entries deleted (0 if nothing was pruned).
        """
        entries = list(self.reader.get_entries(feed=feed.id))
        if len(entries) <= n:
            log.info("feed %s has %d entries, nothing to prune", feed.id, len(entries))
            return 0

        def _sort_key(e: reader.types.Entry) -> datetime:
            return e.updated or e.published or datetime.min

        sorted_entries: list[reader.types.Entry] = sorted(
            entries, key=_sort_key, reverse=True
        )
        to_delete = sorted_entries[n:]
        log.info(
            "pruning %d entries from feed %s (keeping %d)",
            len(to_delete),
            feed.id,
            n,
        )
        entry_ids: list[tuple[str, str]] = [(feed.id, e.id) for e in to_delete]
        self.reader._storage.delete_entries(entry_ids, added_by=None)
        return len(to_delete)

    def get_unread_count(self, feed: Feed) -> int:
        """Return the number of unread entries in a feed.

        Args:
            feed: The feed to count unread entries for.

        Returns:
            The unread entry count (0 if all are read).
        """
        return (self.reader.get_entry_counts(feed=feed.id, read=False).total) or 0

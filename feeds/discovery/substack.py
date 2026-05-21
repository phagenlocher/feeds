"""Substack feed discovery.

Supported URL patterns:

* ``https://NEWSLETTER.substack.com`` — newsletter home
* ``https://NEWSLETTER.substack.com/p/ARTICLE`` — article page

All Substack newsletters expose their full RSS feed at ``/feed`` on the
subdomain.  This handler extracts the subdomain and constructs the feed
URL directly, avoiding a full page fetch.
"""

import logging
from urllib.parse import urlparse

import feedparser
import requests

log: logging.Logger = logging.getLogger(__name__)

_USER_AGENT = "feeds/0.1"
_FEED_TIMEOUT = 10


def try_substack(url: str) -> list[tuple[str, str]]:
    """Discover a Substack feed from *url*.

    Extracts the subdomain from a ``*.substack.com`` hostname and
    constructs the feed URL as ``https://{subdomain}.substack.com/feed``.

    For example:

    * ``https://example.substack.com`` → ``https://example.substack.com/feed``
    * ``https://example.substack.com/p/some-article`` → ``https://example.substack.com/feed``

    The candidate is validated with ``feedparser`` before being returned.

    Args:
        url: A Substack URL (e.g. ``https://example.substack.com``).

    Returns:
        ``[(feed_url, title)]`` if a valid feed was found, ``[]`` otherwise.
    """
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    if not hostname.endswith(".substack.com"):
        return []

    # Extract the newsletter name by stripping the ".substack.com" suffix.
    subdomain = hostname.removesuffix(".substack.com")
    if not subdomain:
        return []

    feed_url = f"https://{hostname}/feed"
    return _validate_feed(feed_url)


def _validate_feed(feed_url: str) -> list[tuple[str, str]]:
    """Fetch *feed_url* and confirm it is a valid RSS/Atom feed.

    Args:
        feed_url: The candidate feed URL to validate.

    Returns:
        ``[(feed_url, title)]`` if the URL returns parseable feed
        content, ``[]`` otherwise.
    """
    try:
        resp: requests.Response = requests.get(
            feed_url,
            timeout=_FEED_TIMEOUT,
            headers={"User-Agent": _USER_AGENT},
        )
        resp.raise_for_status()
        parsed: feedparser.FeedParserDict = feedparser.parse(resp.content)
        if parsed.version:
            feed = parsed.feed
            title = feed.get("title", "") if isinstance(feed, dict) else ""
            return [(feed_url, title or feed_url)]
    except Exception:
        log.debug("Substack feed %s is not valid", feed_url)
    return []

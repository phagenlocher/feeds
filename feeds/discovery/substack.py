"""Substack feed discovery.

Supported URL patterns:

* ``https://NEWSLETTER.substack.com`` — newsletter home
* ``https://NEWSLETTER.substack.com/p/ARTICLE`` — article page
"""

import logging
from urllib.parse import urlparse

import feedparser
import requests

log: logging.Logger = logging.getLogger(__name__)

_USER_AGENT = "feeds/0.1"
_FEED_TIMEOUT = 10


def try_substack(url: str) -> list[tuple[str, str]]:
    """Attempt to discover a Substack feed from *url*.

    Returns ``[(feed_url, title)]`` or ``[]``.
    """
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    if not hostname.endswith(".substack.com"):
        return []

    # Extract subdomain — strip ".substack.com"
    subdomain = hostname.removesuffix(".substack.com")
    if not subdomain:
        return []

    feed_url = f"https://{hostname}/feed"
    return _validate_feed(feed_url)


def _validate_feed(feed_url: str) -> list[tuple[str, str]]:
    """Fetch and validate *feed_url* with ``feedparser``."""
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

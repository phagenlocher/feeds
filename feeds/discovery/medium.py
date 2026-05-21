"""Medium feed discovery.

Supported URL patterns:

* ``medium.com/@USERNAME`` — user profile
* ``medium.com/@USERNAME/article-title`` — user article
* ``medium.com/PUBLICATION`` — publication
* ``medium.com/PUBLICATION/article-title`` — publication article

Custom domains mapped to Medium are not handled here — they fall through
to generic path probing.
"""

import logging
import re
from urllib.parse import urlparse

import feedparser
import requests

log: logging.Logger = logging.getLogger(__name__)

_USER_AGENT = "feeds/0.1"
_FEED_TIMEOUT = 10

# Paths that are definitely not profiles or publications.
_SKIP_PATHS: re.Pattern[str] = re.compile(
    r"^/(tag|topic|search|settings|me|new-story|sign-in|sign-up|m/sitemap|_/)/"
)


def try_medium(url: str) -> list[tuple[str, str]]:
    """Attempt to discover a Medium feed from *url*.

    Returns ``[(feed_url, title)]`` or ``[]``.
    """
    parsed = urlparse(url)
    if "medium.com" not in parsed.netloc:
        return []

    path = parsed.path.rstrip("/")
    if not path:
        return []

    # Skip known non-feed paths
    if _SKIP_PATHS.match(path):
        return []

    medium_path = path.strip("/").split("/")[0]

    feed_url = f"https://medium.com/feed/{medium_path}"
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
        log.debug("Medium feed %s is not valid", feed_url)
    return []

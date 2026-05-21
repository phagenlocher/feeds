"""Medium feed discovery.

Supported URL patterns:

* ``medium.com/@USERNAME`` — user profile
* ``medium.com/@USERNAME/article-title`` — user article
* ``medium.com/PUBLICATION`` — publication
* ``medium.com/PUBLICATION/article-title`` — publication article

Custom domains mapped to Medium are not handled here — they fall through
to generic path probing (HTML ``<link>`` tags and common paths).
"""

import logging
import re
from urllib.parse import urlparse

import feedparser
import requests

log: logging.Logger = logging.getLogger(__name__)

_USER_AGENT = "feeds/0.1"
_FEED_TIMEOUT = 10

# Regex matching Medium paths that are definitely not user profiles
# or publication pages.  These are internal or utility routes that
# would produce false positives if we blindly prepended ``/feed/``.
_SKIP_PATHS: re.Pattern[str] = re.compile(
    r"^/(tag|topic|search|settings|me|new-story|sign-in|sign-up|m/sitemap|_/)/"
)


def try_medium(url: str) -> list[tuple[str, str]]:
    """Discover a Medium feed from *url*.

    Extracts the first path segment (either ``@USERNAME`` or a
    publication slug) and prepends ``/feed/`` to form the feed URL:

    * ``medium.com/@USERNAME`` → ``medium.com/feed/@USERNAME``
    * ``medium.com/PUBLICATION`` → ``medium.com/feed/PUBLICATION``

    Known non-feed paths (tags, search, settings, etc.) are skipped
    early.  The candidate is validated with ``feedparser`` before
    being returned.

    Args:
        url: A Medium URL (e.g. ``https://medium.com/@jack``).

    Returns:
        ``[(feed_url, title)]`` if a valid feed was found, ``[]`` otherwise.
    """
    parsed = urlparse(url)
    if "medium.com" not in parsed.netloc:
        return []

    path = parsed.path.rstrip("/")
    if not path:
        return []

    if _SKIP_PATHS.match(path):
        return []

    # Take only the first path segment (ignore article titles, etc.).
    medium_path = path.strip("/").split("/")[0]

    feed_url = f"https://medium.com/feed/{medium_path}"
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
        log.debug("Medium feed %s is not valid", feed_url)
    return []

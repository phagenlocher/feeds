"""Reddit feed discovery.

Supported URL patterns:

* ``/r/SUBREDDIT/...`` — subreddit
* ``/user/USERNAME/...`` — user feed

Handles ``www.reddit.com``, ``old.reddit.com``, and bare ``reddit.com``.

Reddit does not include ``<link rel="alternate">`` tags with feed MIME
types in its HTML, so the generic discovery pipeline (HTML parsing,
``Link`` headers) will **not** find Reddit feeds.  This handler is
essential for Reddit support.
"""

import logging
import re
from urllib.parse import urlparse

import feedparser
import requests

log: logging.Logger = logging.getLogger(__name__)

_USER_AGENT = "feeds/0.1"
_FEED_TIMEOUT = 10


def try_reddit(url: str) -> list[tuple[str, str]]:
    """Discover a Reddit feed from *url*.

    Matches subreddit URLs (``/r/SUBREDDIT``) and user profile URLs
    (``/user/USERNAME``) on any ``reddit.com`` variant.

    The constructed feed URL follows Reddit's RSS convention:

    * ``https://www.reddit.com/r/{subreddit}/.rss``
    * ``https://www.reddit.com/user/{username}/.rss``

    Each candidate is validated with ``feedparser`` before being
    returned.

    Args:
        url: A Reddit URL (e.g. ``https://www.reddit.com/r/python``).

    Returns:
        ``[(feed_url, title)]`` if a valid feed was found, ``[]`` otherwise.
    """
    parsed = urlparse(url)
    if "reddit.com" not in parsed.netloc:
        return []

    path = parsed.path.rstrip("/")

    # /r/SUBREDDIT — extract subreddit name from the path.
    m: re.Match[str] | None = re.match(r"/r/([\w]+)", path)
    if m:
        return _validate_feed(f"https://www.reddit.com/r/{m.group(1)}/.rss")

    # /user/USERNAME — extract username from the path.
    m = re.match(r"/user/([\w-]+)", path)
    if m:
        return _validate_feed(f"https://www.reddit.com/user/{m.group(1)}/.rss")

    return []


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
        log.debug("Reddit feed %s is not valid", feed_url)
    return []

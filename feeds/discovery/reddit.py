"""Reddit feed discovery.

Supported URL patterns:

* ``/r/SUBREDDIT/...`` — subreddit
* ``/user/USERNAME/...`` — user feed

Handles ``www.reddit.com``, ``old.reddit.com``, and bare ``reddit.com``.
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
    """Attempt to discover a Reddit feed from *url*.

    Returns ``[(feed_url, title)]`` or ``[]``.
    """
    parsed = urlparse(url)
    if "reddit.com" not in parsed.netloc:
        return []

    path = parsed.path.rstrip("/")

    # /r/SUBREDDIT
    m: re.Match[str] | None = re.match(r"/r/([\w]+)", path)
    if m:
        return _validate_feed(f"https://www.reddit.com/r/{m.group(1)}/.rss")

    # /user/USERNAME
    m = re.match(r"/user/([\w-]+)", path)
    if m:
        return _validate_feed(f"https://www.reddit.com/user/{m.group(1)}/.rss")

    return []


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
        log.debug("Reddit feed %s is not valid", feed_url)
    return []

"""Utility helpers for feed discovery."""

import logging

import feedparser
import requests

log: logging.Logger = logging.getLogger(__name__)

USER_AGENT = "feeds/0.1"
_FEED_TIMEOUT = 10


def validate_feed(feed_url: str) -> list[tuple[str, str]]:
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
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
        )
        resp.raise_for_status()
        parsed: feedparser.FeedParserDict = feedparser.parse(resp.content)
        if parsed.version:
            title = parsed.feed.get("title", "")
            return [(resp.url, title or feed_url)]
    except requests.RequestException:
        log.debug("Feed %s is not valid (HTTP error)", feed_url)
    return []

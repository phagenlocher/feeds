"""Utility helpers for feed discovery."""

import logging

from reader._parser import default_parser

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
        parser = default_parser(session_timeout=_FEED_TIMEOUT)
        parser.session_factory.user_agent = USER_AGENT
        result = parser(feed_url)
        if result is not None:
            feed = result.feed
            title = feed.title or ""
            return [(feed_url, title or feed_url)]
    except Exception:
        log.debug("Feed %s is not valid", feed_url)
    return []

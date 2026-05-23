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

import re
from urllib.parse import urlparse

from feeds.discovery.utils import validate_feed


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
        return validate_feed(f"https://www.reddit.com/r/{m.group(1)}/.rss")

    # /user/USERNAME — extract username from the path.
    m = re.match(r"/user/([\w-]+)", path)
    if m:
        return validate_feed(f"https://www.reddit.com/user/{m.group(1)}/.rss")

    return []

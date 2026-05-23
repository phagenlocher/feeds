"""Substack feed discovery.

Supported URL patterns:

* ``https://NEWSLETTER.substack.com`` — newsletter home
* ``https://NEWSLETTER.substack.com/p/ARTICLE`` — article page

All Substack newsletters expose their full RSS feed at ``/feed`` on the
subdomain.  This handler extracts the subdomain and constructs the feed
URL directly, avoiding a full page fetch.
"""

from urllib.parse import urlparse

from feeds.discovery.utils import validate_feed


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
    return validate_feed(feed_url)

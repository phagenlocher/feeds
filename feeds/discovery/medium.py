"""Medium feed discovery.

Supported URL patterns:

* ``medium.com/@USERNAME`` — user profile
* ``medium.com/@USERNAME/article-title`` — user article
* ``medium.com/PUBLICATION`` — publication
* ``medium.com/PUBLICATION/article-title`` — publication article

Custom domains mapped to Medium are not handled here — they fall through
to generic path probing (HTML ``<link>`` tags and common paths).
"""

import re
from urllib.parse import urlparse

from feeds.discovery.utils import validate_feed

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
    return validate_feed(feed_url)

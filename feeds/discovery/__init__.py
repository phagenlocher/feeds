"""Platform-specific feed discovery handlers.

Each module in this package exports a ``try_*`` function that checks whether
*a given URL belongs to a known platform and, if so, constructs the
corresponding feed URL directly — avoiding a full page fetch.

Handlers run **before** any HTTP request is made to the URL itself and
are called from :meth:`feeds.models.feed.FeedReader._discover_feed_urls`.

Available handlers:

* :func:`feeds.discovery.youtube.try_youtube` — YouTube (bypasses GDPR wall)
* :func:`feeds.discovery.reddit.try_reddit` — Reddit subreddit/user feeds
* :func:`feeds.discovery.medium.try_medium` — Medium profile/publication feeds
* :func:`feeds.discovery.substack.try_substack` — Substack newsletter feeds
"""

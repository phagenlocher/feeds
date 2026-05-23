"""YouTube feed discovery.

YouTube blocks automated page access with a GDPR consent wall, so we **never
fetch YouTube HTML pages**.  Instead we derive the feed URL directly from the
URL pattern or via the oEmbed API, both of which work without consent.

Supported URL patterns:

* ``/channel/UC_ID`` — channel ID (most reliable)
* ``/user/NAME`` — legacy username
* ``/c/NAME`` — custom URL
* ``/@HANDLE`` — channel handle
* ``/watch?v=VIDEO_ID`` — video page (resolved via oEmbed)
* ``/shorts/VIDEO_ID`` — YouTube Shorts (resolved via oEmbed)
* ``/embed/VIDEO_ID`` — embedded player (resolved via oEmbed)
* ``youtu.be/VIDEO_ID`` — shortened link (resolved via oEmbed)
"""

import logging
import re
from urllib.parse import parse_qs, urlparse

import requests

from feeds.discovery.utils import validate_feed

log: logging.Logger = logging.getLogger(__name__)

_USER_AGENT = "feeds/0.1"
_OEMBED_TIMEOUT = 5


def try_youtube(url: str) -> list[tuple[str, str]]:
    """Attempt to discover a YouTube channel feed from *url*.

    This is meant to be called **before** any HTTP request is made
    to the URL itself, since YouTube requires a GDPR consent cookie
    to serve the actual page content.

    Returns ``[(feed_url, title)]`` or ``[]``.
    """
    parsed = urlparse(url)
    if "youtube.com" not in parsed.netloc and "youtu.be" not in parsed.netloc:
        return []

    path = parsed.path.rstrip("/")

    # /channel/UC_ID
    m: re.Match[str] | None = re.match(r"/channel/(UC[\w-]{22,})", path)
    if m:
        return validate_feed(
            f"https://www.youtube.com/feeds/videos.xml?channel_id={m.group(1)}"
        )

    # /user/NAME (legacy)
    m = re.match(r"/user/([\w.-]+)", path)
    if m:
        return validate_feed(
            f"https://www.youtube.com/feeds/videos.xml?user={m.group(1)}"
        )

    # /c/NAME or /@HANDLE
    m = re.match(r"/(?:c/|@)([\w.-]+)", path)
    if m:
        return validate_feed(
            f"https://www.youtube.com/feeds/videos.xml?user={m.group(1)}"
        )

    # /watch?v=VIDEO_ID
    if path == "/watch":
        video_id: str | None = parse_qs(parsed.query).get("v", [None])[0]
        if video_id:
            return _feed_from_video_id(video_id)

    # /shorts/VIDEO_ID
    m = re.match(r"/shorts/([\w-]+)", path)
    if m:
        return _feed_from_video_id(m.group(1))

    # /embed/VIDEO_ID
    m = re.match(r"/embed/([\w-]+)", path)
    if m:
        return _feed_from_video_id(m.group(1))

    # youtu.be/VIDEO_ID
    if "youtu.be" in parsed.netloc:
        video_id = path.lstrip("/")
        if video_id and "/" not in video_id:
            return _feed_from_video_id(video_id)

    return []


def _feed_from_video_id(video_id: str) -> list[tuple[str, str]]:
    """Resolve a YouTube video ID to a channel feed via oEmbed.

    The oEmbed endpoint (``youtube.com/oembed``) works without
    consent and returns ``author_url``, from which we derive the
    channel handle and construct the feed URL.
    """
    try:
        url = (
            "https://www.youtube.com/oembed"
            f"?url=https://www.youtube.com/watch?v={video_id}"
            "&format=json"
        )
        resp: requests.Response = requests.get(
            url,
            timeout=_OEMBED_TIMEOUT,
            headers={"User-Agent": _USER_AGENT},
        )
        resp.raise_for_status()
        data = resp.json()
        author_url: str = data.get("author_url", "")
        m: re.Match[str] | None = re.search(r"/(@?[\w.-]+)$", author_url)
        if m:
            handle = m.group(1).lstrip("@")
            return validate_feed(
                f"https://www.youtube.com/feeds/videos.xml?user={handle}"
            )
    except Exception:
        log.debug("Failed to resolve YouTube video %s via oEmbed", video_id)
    return []

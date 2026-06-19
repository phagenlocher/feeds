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

from feeds import USER_AGENT
from feeds.discovery.utils import validate_feed

log: logging.Logger = logging.getLogger(__name__)

_OEMBED_TIMEOUT = 5
_YOUTUBE_CLIENT_VERSION = "2.20250101.00.00"


def try_youtube(url: str) -> list[tuple[str, str]]:
    """Attempt to discover a YouTube channel feed from *url*.

    This is meant to be called **before** any HTTP request is made
    to the URL itself, since YouTube requires a GDPR consent cookie
    to serve the actual page content.

    Returns ``[(feed_url, title)]`` or ``[]``.
    """
    parsed = urlparse(url)
    if "youtube.com" not in parsed.netloc and "youtu.be" not in parsed.netloc:
        log.debug("not a YouTube URL: %s", url)
        return []

    path = parsed.path.rstrip("/")
    log.debug("checking YouTube path: %s", path)

    # /channel/UC_ID
    m: re.Match[str] | None = re.match(r"/channel/(UC[\w-]{22,})", path)
    if m:
        log.debug("detected YouTube channel ID: %s", m.group(1))
        return validate_feed(
            f"https://www.youtube.com/feeds/videos.xml?channel_id={m.group(1)}"
        )

    # /user/NAME (legacy)
    m = re.match(r"/user/([\w.-]+)", path)
    if m:
        log.debug("detected YouTube username: %s", m.group(1))
        return validate_feed(
            f"https://www.youtube.com/feeds/videos.xml?user={m.group(1)}"
        )

    # /c/NAME or /@HANDLE
    m = re.match(r"/(?:c/|@)([\w.-]+)", path)
    if m:
        log.debug("detected YouTube handle/custom URL: %s", m.group(1))
        channel_id = _resolve_channel_id(url)
        if channel_id:
            return validate_feed(
                f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
            )

    # /watch?v=VIDEO_ID
    if path == "/watch":
        video_id: str | None = parse_qs(parsed.query).get("v", [None])[0]
        if video_id:
            log.debug("resolving YouTube video ID via oEmbed: %s", video_id)
            return _feed_from_video_id(video_id)

    # /shorts/VIDEO_ID
    m = re.match(r"/shorts/([\w-]+)", path)
    if m:
        log.debug("resolving YouTube Shorts video ID via oEmbed: %s", m.group(1))
        return _feed_from_video_id(m.group(1))

    # /embed/VIDEO_ID
    m = re.match(r"/embed/([\w-]+)", path)
    if m:
        log.debug("resolving YouTube embed video ID via oEmbed: %s", m.group(1))
        return _feed_from_video_id(m.group(1))

    # youtu.be/VIDEO_ID
    if "youtu.be" in parsed.netloc:
        video_id = path.lstrip("/")
        if video_id and "/" not in video_id:
            log.debug("resolving youtu.be video ID via oEmbed: %s", video_id)
            return _feed_from_video_id(video_id)

    log.debug("YouTube path %s did not match any known pattern", path)
    return []


def _resolve_channel_id(channel_url: str) -> str | None:
    """Resolve a YouTube channel URL to a channel ID.

    Uses the internal ``youtubei/v1/navigation/resolve_url`` API
    which works without authentication or consent.
    """
    try:
        data = {
            "context": {
                "client": {
                    "clientName": "WEB",
                    "clientVersion": _YOUTUBE_CLIENT_VERSION,
                }
            },
            "url": channel_url,
        }
        resp: requests.Response = requests.post(
            "https://www.youtube.com/youtubei/v1/navigation/resolve_url",
            json=data,
            timeout=_OEMBED_TIMEOUT,
            headers={
                "User-Agent": USER_AGENT,
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()
        result = resp.json()
        endpoint = result.get("endpoint", {})
        browse_endpoint = endpoint.get("browseEndpoint", {})
        browse_id: str | None = browse_endpoint.get("browseId")
        if browse_id and browse_id.startswith("UC"):
            log.debug("resolved channel ID: %s", browse_id)
            return browse_id
    except (requests.RequestException, ValueError):
        log.debug("Failed to resolve channel URL: %s", channel_url)
    return None


def _feed_from_video_id(video_id: str) -> list[tuple[str, str]]:
    """Resolve a YouTube video ID to a channel feed via oEmbed.

    The oEmbed endpoint (``youtube.com/oembed``) works without
    consent and returns ``author_url``, from which we resolve the
    channel ID and construct the feed URL.
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
            headers={"User-Agent": USER_AGENT},
        )
        resp.raise_for_status()
        data = resp.json()
        author_url: str = data.get("author_url", "")

        if "/user/" in author_url:
            m: re.Match[str] | None = re.search(r"/user/([\w.-]+)", author_url)
            if m:
                log.debug("detected legacy user: %s", m.group(1))
                result = validate_feed(
                    f"https://www.youtube.com/feeds/videos.xml?user={m.group(1)}"
                )
                if result:
                    return result

        channel_id = _resolve_channel_id(author_url)
        if channel_id:
            return validate_feed(
                f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
            )
    except requests.RequestException:
        log.debug("Failed to resolve YouTube video %s via oEmbed", video_id)
    return []

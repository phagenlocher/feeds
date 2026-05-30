# Feed Discovery

Feed discovery is the process of finding RSS/Atom feed URLs from a web
page or platform URL.  feeds implements a multi-stage pipeline in
`feeds/models/feed.py` (`FeedReader._discover_feed_urls`) that covers
HTML autodiscovery, HTTP headers, platform-specific patterns, and
well-known path probing.

---

## 1. Discovery Pipeline

Methods are tried **in order**, short-circuting on first success:

### Stage 1: Platform pre-handlers (before any HTTP request)

Specialised handlers that construct feed URLs directly from known URL
patterns without fetching the page.  This avoids consent walls and
unnecessary network requests.

| Handler | Module | URL patterns detected |
|---------|--------|-----------------------|
| Substack | `feeds/discovery/substack.py` | `*.substack.com` → `/feed` |
| Medium | `feeds/discovery/medium.py` | `/@USERNAME`, `/PUBLICATION` → `/feed/...` |
| Reddit | `feeds/discovery/reddit.py` | `/r/SUBREDDIT`, `/user/USERNAME` → `/.rss` |
| YouTube | `feeds/discovery/youtube.py` | `/channel/UC_*`, `/user/*`, `/@HANDLE`, `/watch`, `/shorts/`, `/embed/`, `youtu.be/*` |

Each handler calls `validate_feed()` from `feeds/discovery/utils.py` to
verify the candidate is a real, parseable feed before returning it.

### Stage 2: Direct feed parsing

If no platform handler matched, the URL is fetched via HTTP and parsed
via `feedparser`.  If the response itself is a feed (RSS/Atom/JSON
Feed), it is returned immediately; no further discovery is needed.

### Stage 3: HTML `<link rel="alternate">` tags

The `_FeedLinkFinder` HTML parser scans for `<link>` elements with
`rel="alternate"` and a recognised feed MIME type.  Supports multi-value
`rel` attributes (e.g. `rel="stylesheet alternate"`) and `<base href>`
for relative URL resolution.

### Stage 4: HTTP `Link` headers (RFC 5988)

`_parse_link_header()` in `feeds/models/feed.py:136` parses the `Link`
response header for feed references in the format:

```
Link: </feed.xml>; rel="alternate"; type="application/rss+xml"
```

Only entries with `rel="alternate"` and a recognised feed MIME type are
returned.  Relative `href` values are resolved against the response URL.

### Stage 5: Common path probing

As a last resort, `_try_common_paths()` in `feeds/models/feed.py:171`
probes well-known feed paths.  Each candidate is fetched and validated
via `feedparser`.  Paths are probed relative to the domain root **and**
relative to the current page's parent directory.

---

## 2. HTML Autodiscovery: The Standard

The most reliable method is a `<link>` element in the `<head>`:

```html
<!-- RSS 2.0 -->
<link rel="alternate" type="application/rss+xml"
      title="My Feed" href="https://example.com/feed" />

<!-- Atom -->
<link rel="alternate" type="application/atom+xml"
      title="My Feed" href="https://example.com/atom.xml" />
```

### Recognised MIME types

Defined in `FEED_MIME_TYPES` (`feeds/models/feed.py:92`):

- `application/rss+xml`
- `application/atom+xml`
- `application/feed+json` (JSON Feed)

### Spec rules

| Attribute | Required value | Notes |
|-----------|---------------|-------|
| `rel` | must contain `"alternate"` | Space-separated multi-value support via `rel.split()` |
| `type` | one of `FEED_MIME_TYPES` | Case-sensitive match |
| `href` | Feed URL | Can be relative; resolved against `<base href>` or page URL |
| `title` | Human-readable name | Optional; used for display |

A page can advertise **multiple feeds** (e.g. RSS + Atom, or per-section
feeds).  feeds collects them all and presents them to the user in the
discovery dialog (`feeds/app.py:179`).

---

## 3. Well-Known Path Probing

Defined in `_FEED_PATHS` (`feeds/models/feed.py:105`):

| Path | Primary target |
|------|---------------|
| `/feed/`, `/feed` | WordPress |
| `/feed.xml` | Static-site generators (Hugo, Jekyll) |
| `/feed.json` | JSON Feed |
| `/index.xml` | Hugo, Jekyll |
| `/atom.xml`, `/atom` | Atom feeds |
| `/rss`, `/rss/`, `/rss.xml` | Tumblr, Ghost, generic RSS |
| `/blog?format=rss` | Squarespace |
| `/feeds/posts/default` | Blogger |

---

## 4. Feed Validation

`validate_feed()` in `feeds/discovery/utils.py:12` verifies that a
candidate URL returns valid feed content.  It uses `reader._parser.default_parser()`
to fetch and parse the URL; if the parser returns a result with a
nonzero `version`, the candidate is considered valid.  The feed title
is extracted from the parsed result.

---

## 5. UI Integration

The discovery flow in `feeds/app.py`:

1. User enters a URL in the "Add Feed" dialog
2. `FeedReader.discover_feeds(url)` is called on a background thread via `_service.discover_feeds()`
3. Results are cached in `FeedReader.last_discovered_feeds`
4. If exactly one feed is found, it is added immediately (`_add_discovered_feed`)
5. If multiple feeds are found, a selection dialog is shown (handled in `feeds/app.py:238`)
6. The selected feed is subscribed via `FeedReader.add_feed()`

---

## 6. Platform Feed URL Patterns Reference

### Blogging & CMS

| Platform | Feed URL pattern | Status |
|----------|-----------------|--------|
| WordPress | `https://example.com/feed` | ✅ (path probing) |
| WordPress | `https://example.com/category/NAME/feed` | ✅ (path probing) |
| WordPress | `https://example.com/tag/NAME/feed` | ✅ (path probing) |
| WordPress | `https://example.com/author/NAME/feed` | ✅ (path probing) |
| Ghost | `https://example.com/rss/` | ✅ (path probing) |
| Ghost | `https://example.com/tag/TAG/rss/` | ✅ (path probing) |
| Ghost | `https://example.com/author/AUTHOR/rss/` | ✅ (path probing) |
| Blogger | `https://example.blogspot.com/feeds/posts/default` | ✅ (path probing) |
| Blogger | `...?alt=rss` | ❌ |
| Squarespace | `https://example.com/blog?format=rss` | ✅ (path probing) |
| Squarespace | `https://example.com/PAGE?format=rss` | ✅ (path probing) |

### Newsletter platforms

| Platform | Feed URL pattern | Status |
|----------|-----------------|--------|
| Substack | `https://NEWSLETTER.substack.com/feed` | ✅ (pre-handler) |
| Substack (custom domain) | `https://customdomain.com/feed` | ✅ (path probing / autodiscovery) |
| Medium | `https://medium.com/feed/@USERNAME` | ✅ (pre-handler) |
| Medium | `https://medium.com/feed/PUBLICATION` | ✅ (pre-handler) |
| Beehiiv | `https://NEWSLETTER.beehiiv.com/feed` | Token; path probing may find `/feed` |

### Video & social

| Platform | Feed URL pattern | Status |
|----------|-----------------|--------|
| YouTube (channel ID) | `https://www.youtube.com/feeds/videos.xml?channel_id=UC_...` | ✅ (pre-handler) |
| YouTube (legacy user) | `https://www.youtube.com/feeds/videos.xml?user=NAME` | ✅ (pre-handler) |
| YouTube (handle) | `https://www.youtube.com/feeds/videos.xml?user=NAME` | ✅ (via oEmbed) |
| YouTube (playlist) | `https://www.youtube.com/feeds/videos.xml?playlist_id=ID` | Token; not implemented |
| Tumblr | `https://example.tumblr.com/rss` | Token; path probing may find `/rss` or `/rss.xml` |
| Bluesky | `https://bsky.app/profile/USERNAME/rss` | ❌ |
| Mastodon | `https://mastodon.social/@USERNAME.rss` | ❌ |

### Reddit

| What | Feed URL pattern | Status |
|------|-----------------|--------|
| Subreddit | `https://reddit.com/r/SUBREDDIT/.rss` | ✅ (pre-handler) |
| Subreddit (sorted) | `/r/SUBREDDIT/new.rss` | ❌ |
| Front page | `https://reddit.com/.rss` | ❌ |
| User posts | `https://reddit.com/user/USERNAME/.rss` | ✅ (pre-handler) |
| User comments | `https://reddit.com/user/USERNAME/comments.rss` | ❌ |
| Multi-subreddit | `https://reddit.com/r/sub1+sub2+sub3.rss` | ❌ |
| Domain links | `https://reddit.com/domain/DOMAIN/.rss` | ❌ |
| Comment thread | `/r/SUB/comments/POST_ID/....rss` | ❌ |
| Search results | `https://reddit.com/search.xml?q=QUERY` | ❌ |

### Podcasts

Podcasts are natively RSS-based.  Every podcast has a feed URL (RSS with
`<enclosure>` tags pointing to audio files).  feeds can subscribe to
podcast feeds directly if the URL is known, but there is no podcast
directory search or dedicated podcast discovery.

---

## 7. Decision Tree (annotated with implementation status)

```
Given a URL:
│
├─ 1. Platform pre-handler match?                           ✅ implemented
│       Substack / Medium / Reddit / YouTube
│       └─ Found → validate_feed() → return ✓
│
├─ 2. Fetch the page →
│       ├─ Check HTTP Link header for rel="alternate"       ✅ implemented
│       │
│       ├─ Parse as feed directly via feedparser             ✅ implemented
│       │   └─ Is a feed? → return ✓
│       │
│       ├─ Parse HTML <link rel="alternate"> tags            ✅ implemented
│       │   └─ Found? → return ✓
│       │
│       └─ Probe well-known paths                            ✅ implemented
│           /feed → /rss → /feed.xml → ... (12 paths)
│           └─ Returns valid feed? → return ✓
│
├─ 3. Bluesky / Mastodon / Tumblr / Beehiiv?                ❌ not implemented
│       └─ Would require platform-specific pre-handlers
│
├─ 4. Reddit variants (comments, multi-sub, etc.)?          ❌ not implemented
│
├─ 5. YouTube playlist feeds?                               ❌ not implemented
│
└─ 6. No feed found → return []                              ✅ handled
```

---

## 8. External Libraries & Tools

### Python

- **[feedsearch](https://pypi.org/project/feedsearch/)**: Synchronous
  feed discovery library: searches `<link>` tags, does CMS detection,
  probes common paths.
- **[feedsearch-crawler](https://pypi.org/project/feedsearch-crawler/)**: Async version; embeddable in scrapers and aggregators.
- **[Feedsearch API](https://feedsearch.dev/)**: REST API for feed discovery.

### Browser extensions

- **Awesome RSS**: Detects `<link rel="alternate">` tags, shows toolbar icon.
- **RSS Feed URL Finder**: Lightweight feed detector.
- Feedly / Inoreader: Built-in feed detection in the reader app.

### Online tools

- **Tiny RSS Finder**: Scans meta tags, common paths, platform patterns.
- **W3C Feed Validator**: Validates whether a URL is a well-formed feed.
- **RSS.app**: Can generate a feed for sites that don't have one.

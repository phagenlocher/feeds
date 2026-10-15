# Feed discovery

## Context

Feed discovery finds RSS/Atom/JSON Feed URLs from a web page or platform URL.
feeds implements a multi-stage pipeline in `feeds_core::discovery` that covers
platform handlers, HTML autodiscovery, HTTP headers and well-known path
probing. `discovery::discover_feeds` orchestrates the pipeline; the platform
handlers live in `feeds_core/src/discovery/{substack,medium,reddit,youtube}.rs`.

## Behaviour

### Pipeline

**Scenario: the pipeline runs in order**
**Given** an arbitrary URL
**When** `discovery::discover_feeds` runs
**Then** the stages are tried in this order, with the first non-empty handler
result winning:

1. Platform pre-handlers (before fetching the page)
2. Direct feed parsing
3. HTML `<link rel="alternate">` tags
4. HTTP `Link` headers (RFC 8288)
5. Common path probing

### Platform pre-handlers

**Scenario: a known platform URL is recognised**
**Given** a URL matching a platform pattern
**When** discovery starts
**Then** the handler constructs a feed URL directly, without fetching the page
first
**And** the candidate feed URL is fetched and validated with
`discovery::utils::validate_feed`

**Scenario: a Substack URL is added**
**Given** a URL matching `*.substack.com`
**Then** `/feed` is tried

**Scenario: a Medium URL is added**
**Given** a URL matching `/@USERNAME` or `/PUBLICATION`
**Then** `/feed/...` is tried

**Scenario: a Reddit URL is added**
**Given** a URL matching `/r/SUBREDDIT` or `/user/USERNAME`
**Then** `/.rss` is tried

**Scenario: a YouTube URL is added**
**Given** a URL matching `/channel/UC*`, `/user/*`, `/c/*`, `/@HANDLE`,
`/watch`, `/shorts/`, `/embed/` or `youtu.be/*`
**Then** the handler resolves the corresponding channel, user or video feed
using the patterns in the Reference section

Handlers avoid consent walls and unnecessary requests.

### Direct feed parsing

**Scenario: the URL is already a feed**
**Given** a URL that returns a feed
**When** the response body is parsed with `feed_rs`
**Then** it is returned immediately

**Scenario: the page cannot be fetched**
**Given** fetching the URL fails at the network or HTTP level
**When** discovery runs
**Then** the failure is returned as an error instead of an empty result
**And** callers can distinguish "the URL is broken or unreachable" from "the
page simply has no feed"

### HTML autodiscovery

**Scenario: a page advertises feeds in its HTML**
**Given** an HTML page containing `<link rel="alternate">` elements with a
recognised feed MIME type
**When** `discovery::html::extract_feed_links` parses it with `scraper`
(html5ever)
**Then** every matching feed URL is collected
**And** `<base href>` is honoured and relative URLs are resolved with the `url`
crate

**Scenario: a link element uses multiple rel tokens**
**Given** a `<link>` whose `rel` contains several space-separated tokens, such
as `rel="stylesheet alternate"`
**Then** it is matched because `rel` is compared by token

**Scenario: a page advertises several feeds**
**Given** more than one matching `<link>` element
**Then** all feeds are collected and presented for selection

### HTTP Link headers

**Scenario: the page advertises a feed in a Link header**
**Given** a response with a `Link` header containing `rel="alternate"` and a
feed MIME type
**When** `discovery::link_header::parse_link_header` parses it
**Then** the entries are returned
**And** relative `href` values are resolved against the response URL

### Path probing

**Scenario: no earlier stage found a feed**
**Given** the response is HTML and did not yield a feed through the previous
stages
**When** `discovery::common_paths::probe_common_paths` runs
**Then** well-known feed paths are probed relative to the domain root and the
current page's parent directory
**And** each candidate is validated via `parse::feed_title`

### Feed validation

**Scenario: a candidate is validated**
**Given** a candidate feed URL
**When** `discovery::utils::validate_feed` fetches it
**Then** it returns `[(final_url, title)]` if `parse::feed_title` recognises it
**And** otherwise it returns `[]`

### Add Feed UI integration

**Scenario: the user adds a feed**
**Given** the user enters a URL in the "Add Feed" dialog
**When** the `discover_feeds` Tauri command calls
`discovery::discover_feeds` asynchronously
**Then** discovery runs

**Scenario: exactly one feed is found**
**Given** discovery returns one feed
**When** Add Feed completes
**Then** the feed is added and updated immediately

**Scenario: several feeds are found**
**Given** discovery returns more than one feed
**When** Add Feed completes
**Then** a selection dialog is shown
**And** the selected feeds are subscribed and updated

**Scenario: no feed is found**
**Given** discovery returns an empty result
**Then** the status bar shows "No feed found at this URL"

**Scenario: the page cannot be fetched**
**Given** discovery fails to fetch the page
**Then** the status bar shows `Failed to add feed <url>: <reason>`

## Reference

### Recognised MIME types

Defined in `discovery::FEED_MIME_TYPES`:

- `application/rss+xml`
- `application/atom+xml`
- `application/feed+json` (JSON Feed)

`rel` is matched by token, so multi-value forms like
`rel="stylesheet alternate"` work. A page may advertise multiple feeds; they are
all collected and presented for selection.

### Well-known paths

Defined as `discovery::common_paths::FEED_PATHS`:

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

### Platform URL patterns

#### Blogging & CMS

| Platform | Feed URL pattern | Status |
|----------|-----------------|--------|
| WordPress | `https://example.com/feed` | ✅ (path probing) |
| WordPress | `/category/NAME/feed`, `/tag/NAME/feed`, `/author/NAME/feed` | ✅ (HTML autodiscovery; not path-probed) |
| Ghost | `https://example.com/rss/` | ✅ (path probing) |
| Blogger | `https://example.blogspot.com/feeds/posts/default` | ✅ (path probing) |
| Squarespace | `https://example.com/blog?format=rss` | ✅ (path probing) |

WordPress category, tag and author feeds are normally advertised in the page's
HTML. They are not in `FEED_PATHS`, so they are not guessed from the category
URL itself.

#### Newsletter platforms

| Platform | Feed URL pattern | Status |
|----------|-----------------|--------|
| Substack | `https://NEWSLETTER.substack.com/feed` | ✅ (pre-handler) |
| Medium | `https://medium.com/feed/@USERNAME` | ✅ (pre-handler) |
| Beehiiv | `https://NEWSLETTER.beehiiv.com/feed` | token; path probing |

The Medium handler skips internal path prefixes (`tag`, `topic`, `search`,
`settings`, `me`, `new-story`, `sign-in`, `sign-up`, `m`, `_`).

#### Video & social

| Platform | Feed URL pattern | Status |
|----------|-----------------|--------|
| YouTube (channel ID) | `https://www.youtube.com/feeds/videos.xml?channel_id=UC...` (starts with `UC`, at least 24 characters) | ✅ (pre-handler) |
| YouTube (user URL) | `...?user=NAME` | ✅ (pre-handler) |
| YouTube (handle) | `...?channel_id=UC...` via resolve_url API | ✅ (pre-handler) |
| YouTube (video/Shorts/embed/youtu.be) | resolved via oEmbed | ✅ |
| Tumblr | `https://example.tumblr.com/rss` | token; path probing |
| Bluesky / Mastodon | — | ❌ not implemented |

#### Reddit

| What | Feed URL pattern | Status |
|------|-----------------|--------|
| Subreddit | `https://reddit.com/r/SUBREDDIT/.rss` | ✅ (pre-handler) |
| User posts | `https://reddit.com/user/USERNAME/.rss` | ✅ (pre-handler) |
| Sorted/comments/multi-sub | — | ❌ not implemented |

### Decision tree

```
Given a URL:
│
├─ 1. Platform pre-handler match?                           ✅ implemented
│       Substack / Medium / Reddit / YouTube
│       └─ Found → validate_feed() → return ✓
│
├─ 2. Fetch the page →
│       ├─ Parse as feed directly via feed-rs                ✅ implemented
│       ├─ Parse HTML <link rel="alternate"> tags            ✅ implemented
│       ├─ Check HTTP Link header for rel="alternate"       ✅ implemented
│       └─ Probe well-known paths                            ✅ implemented
│
├─ 3. Bluesky / Mastodon / Tumblr / Beehiiv?                ❌ no dedicated handlers
│       Tumblr (/rss) and Beehiiv (/feed) may work via path probing
├─ 4. Reddit variants (comments, multi-sub, etc.)?          ❌ not implemented
├─ 5. YouTube playlist feeds?                               ❌ not implemented
└─ 6. No feed found → return []                              ✅ handled
```

### Module layout

- `feeds_core/src/discovery/mod.rs` — pipeline orchestration
- `feeds_core/src/discovery/{substack,medium,reddit,youtube}.rs` — platform handlers
- `feeds_core/src/discovery/html.rs` — HTML autodiscovery
- `feeds_core/src/discovery/link_header.rs` — RFC 8288 `Link` header parsing
- `feeds_core/src/discovery/common_paths.rs` — well-known path probing
- `feeds_core/src/discovery/utils.rs` — `validate_feed`

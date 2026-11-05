# RSS / Atom and storage

## Context

feeds uses a layered approach to feed parsing and management: `feed-rs` for
parsing, and purpose-built modules in `feeds-core` for storage and
synchronisation.

| Layer | Crate / module | Role |
|-------|----------------|------|
| Parsing | `feed-rs` (via `feeds_core::parse`) | RSS 0.9x/1.0/2.0, Atom 0.3/1.0, JSON Feed |
| Database / sync | `feeds_core::store` | SQLite storage, read state, tags |
| Update | `feeds_core::update` | Conditional GET, de-duplication, scheduling |
| HTTP | `reqwest` | Fetching feeds and pages during discovery |
| Retry | `backon` | Exponential backoff |

## Behaviour

### Parsing

**Scenario: a valid feed is parsed**
**Given** bytes containing RSS, Atom or JSON Feed
**When** `parse::parse_bytes(&[u8])` is called
**Then** a unified `ParsedFeed` model is returned with `title`, `link`,
`updated`, `author`, `version` and `entries`

**Scenario: the input is not a feed**
**Given** bytes containing an HTML page or other non-feed content
**When** `parse::parse_bytes` is called
**Then** it returns `Error::FeedParse`
**And** callers can use that error to decide whether the input “is a feed”

**Scenario: Media RSS contains empty text**
**Given** a feed with an empty `<media:title>` or `<media:description>`
**When** `feed-rs` rejects it with `missing text at position N`
**Then** the parse is retried once with those empty elements stripped
(`repair_empty_media_text`)
**And** the feed parses successfully

This workaround exists because `feed-rs` 3.x rejects empty Media RSS elements
(YouTube emits an empty `<media:description>` for videos without one), while the
`feeds` model ignores Media RSS fields.

**Scenario: a feed uses date-only timestamps**
**Given** a feed whose `<pubDate>`, `<lastBuildDate>`, `<published>`, `<updated>`
or `<dc:date>` lacks a time or a time zone, e.g. `Mon, 25 May 2026`
**When** it is parsed
**Then** the timestamp is completed to `Mon, 25 May 2026 00:00:00 +0000`
before parsing
**And** the entry keeps its date

Feeds built by Hugo emit such date-only timestamps. `chrono` — and with it
`feed-rs` — rejects them silently, so without this step every entry of such a
feed would end up without a date.

**Scenario: a feed version is reported**
**Given** a successfully parsed feed
**When** its version is requested
**Then** `version_string` maps `FeedType` onto historical names such as
`rss20` and `atom10`

`parse::feed_title` is the convenience wrapper used by discovery;
`parse::is_feed` is a public helper for checking whether bytes parse as a feed.

### Persistence

**Scenario: new entries are stored in chronological order**
**Given** a new entry with `published` or `updated`
**When** it is inserted by `apply_update`
**Then** `recent_sort` is set to its publication date, or to its update date
when the feed publishes none
**And** when the entry has no date, `recent_sort` falls back to *now*
**And** entries always sort chronologically

**Scenario: an existing entry is updated**
**Given** an entry id that is already stored
**When** an update supplies new data for it
**Then** the entry is updated by id
**And** its read state, `added` timestamp and `recent_sort` are not disturbed

**Scenario: entries are ordered by their date**
**Given** a feed whose entries carry publication dates
**When** the entries are listed
**Then** they are ordered newest-first by that date
**And** an entry's sort key is set when it is first stored and is not changed
by later fetches
**And** an entry without any date is ordered by the moment it was first
imported

**Scenario: a feed is deleted**
**Given** a subscribed feed with entries and tags
**When** `delete_feed` is called
**Then** the feed and its entries and feed tags are removed by cascade

**Scenario: timestamps are stored**
**Given** a timestamp from a feed
**When** it is persisted
**Then** it is stored as RFC 3339 (`chrono::DateTime<Utc>`)
**And** parsing also accepts a space-separated ISO 8601 form via
`datetime::parse`

**Scenario: an entry's date is its publication date**
**Given** a stored entry with a `published` and an `updated` timestamp
**When** the entry is read back
**Then** its date is the `published` timestamp
**And** when the feed publishes no date, the `updated` timestamp is used
**And** when the feed has neither, the entry has no date

**Scenario: the newest entry date is derived**
**Given** a feed whose entries are ordered newest-first
**When** `models::newest_entry_date` is called with them
**Then** the date of the newest entry that carries one is returned
**And** `None` is returned when no entry carries a date

**Scenario: feeds are filtered by tag**
**Given** a `TagFilter`
**When** `get_feeds` is called
**Then** `All` returns every feed, `Untagged` returns feeds without tags, and
`Tags(Vec<String>)` returns feeds matching any of the tags (OR semantics)

**Scenario: feeds that were never fetched are hidden**
**Given** a subscribed feed without any of a title, a user title, or entries
**When** `get_visible_feeds` is called
**Then** that feed is not returned
**And** `get_feeds` still returns it

### Updating a single feed

**Scenario: a feed is fetched conditionally**
**Given** cached `caching_info` (`{ "etag", "last-modified" }`)
**When** `update_feed` runs
**Then** it sends a conditional `GET`

**Scenario: the server answers 304 Not Modified**
**Given** a conditional `GET` returns `304 Not Modified`
**When** the response is handled
**Then** `apply_not_modified` pushes `update_after` forward

**Scenario: the server returns a feed**
**Given** a conditional `GET` returns a feed body
**When** it is parsed and applied with `apply_update`
**Then** new entries are inserted and existing entries are updated by id without
disturbing read state
**And** the new `caching_info` is persisted
**And** `last_exception` is cleared
**And** `update_after` is set to now + 60 minutes

**Scenario: an update fails**
**Given** fetching a feed (including reading the response body), checking its
HTTP status, or parsing fails
**When** the update is aborted
**Then** the error is recorded in `last_exception` via `record_update_error`
**And** it is logged with the feed URL
(`tracing::warn!("feed update failed for {url}: …")`)

### Updating all feeds

**Scenario: all eligible feeds are updated**
**Given** a set of feeds selected by `feeds_to_update`
**When** `update_feeds(scheduled)` runs
**Then** feeds are fetched concurrently with `buffer_unordered`, using
`min(feed_count, 2 × CPUs)` workers (at least one)

**Scenario: a scheduled update skips feeds that are not due**
**Given** `scheduled = true`
**And** a feed's `update_after` is in the future
**When** `update_feeds` runs
**Then** that feed is skipped

**Scenario: an update run reports its outcome**
**Given** an `update_feeds` run
**When** it finishes
**Then** it returns an `UpdateReport` with success and new-entry counts
**And** it carries an `UpdateFailure` (`url`, display `title`, `error`) for every
feed that failed
**And** the GUI shows failures in the status bar (see
[`gui.md`](gui.md))

**Scenario: the app starts**
**Given** feeds are subscribed
**When** the main window mounts
**Then** the frontend triggers `update_feeds(scheduled: true)` once
**And** the startup behaviour is specified in
[`startup-update.md`](startup-update.md)

**Scenario: an HTTP request fails transiently**
**Given** a feed request fails
**When** it is retried
**Then** `backon` makes 3 attempts in total (the initial request plus at most
two retries) with exponential backoff between 1 and 10 seconds

### Read state

**Scenario: an entry is marked read or unread**
**Given** a stored entry
**When** `set_entry_read(feed, entry_id, read)` is called
**Then** the entry's read state is persisted

**Scenario: all entries are marked read**
**Given** a feed with unread entries
**When** `mark_all_as_read(feed)` is called
**Then** every entry in that feed is marked read

**Scenario: the unread count is requested**
**Given** a feed
**When** `unread_count(feed)` is called
**Then** the number of unread entries is returned

### Tagging

**Scenario: a new tag receives a color**
**Given** a tag without a stored color
**When** a color is needed
**Then** a deterministic color is derived from an MD5 hash of the tag name
mapped onto HLS (`feeds_core::tags::default_color_for_tag`)

**Scenario: missing tag colors are filled in**
**Given** known tags with missing colors
**When** `Feeds::ensure_tag_colors` runs
**Then** a color is assigned to each missing tag
**And** the `tag_colors` table is written when something changed
**And** the Tauri layer calls it when settings are read and after a feed's tags
are updated

**Scenario: a tag is renamed**
**Given** an existing tag with a color
**When** `Feeds::rename_tag` renames it
**Then** the old name's color is carried over to the new name
**And** the new tag keeps its existing color if it already has one; otherwise a
default color is assigned

**Scenario: a tag is deleted**
**Given** an existing tag with a color
**When** `Feeds::delete_tag` deletes it
**Then** the tag is removed from every feed
**And** its color is dropped

**Scenario: tags are shown and managed in the GUI**
**Given** the main window
**When** the user works with tags
**Then** the UI exposes a tag filter (All / Untagged / tag), colored tag pills,
a "Tag feed…" dialog and a "Manage Tags…" dialog (rename / delete / recolor)

Tag **colors** are stored in the `tag_colors` table of the database.

### Settings

**Scenario: the settings are read**
**Given** a database
**When** `Feeds::get_settings` is called
**Then** the font size and the tag colors are read from the database
**And** a font size that was never stored falls back to 14 px
**And** a stored font size below 6 px falls back to 14 px

**Scenario: the font size is stored**
**Given** a font size
**When** `Feeds::set_font_size` is called
**Then** the size is written to the `app_settings` table
**And** a size below 6 px is stored as 14 px
**And** the stored value is returned

**Scenario: a tag color is stored**
**Given** a tag and a color
**When** `Feeds::set_tag_color` is called
**Then** the color is written to the `tag_colors` table

All persistent state lives in the SQLite database. `settings.json` is a legacy
format that is not read by the application.

### OPML

**Scenario: feeds are exported**
**Given** subscribed feeds
**When** `feeds_core::opml` exports them
**Then** an OPML 2.0 document containing all feeds is produced
**And** feeds that have never been fetched successfully are still included (see
[`gui.md`](gui.md))

**Scenario: feeds are imported**
**Given** an OPML file, including nested outlines
**When** it is imported
**Then** an `ImportedFeed` with its URL and optional title is read for every outline
**And** the feeds are subscribed

## Reference

### Data models

#### `Feed` (`feeds_core::models::Feed`)

```rust
pub struct Feed {
    pub id: String,                    // feed URL (unique identifier)
    pub title: String,                 // display title (user title if set)
    pub last_updated: Option<DateTime<Utc>>,  // last successful fetch
    pub user_title: Option<String>,
}
```

#### `Entry` (`feeds_core::models::Entry`)

```rust
pub struct Entry {
    pub url: String,
    pub title: String,
    pub date: Option<DateTime<Utc>>,   // published, else updated
    pub entry_id: String,
    pub feed_id: String,
    pub read: bool,
    pub author: String,
}
```

Both derive `Serialize`/`Deserialize` (they cross the Tauri IPC boundary).

`feeds_core::models::newest_entry_date(&[Entry]) -> Option<DateTime<Utc>>`
returns the date of the newest entry of a newest-first list, skipping entries
without a date.

#### `ImportedFeed` (`feeds_core::opml::ImportedFeed`)

```rust
pub struct ImportedFeed {
    pub url: String,                  // subscription URL from xmlUrl
    pub title: Option<String>,        // outline title/text, None when blank
}
```

Returned by `feeds_core::opml::import_feeds`.

### Storage

SQLite via `rusqlite` (bundled). Default path `~/.feeds/feeds.db`.

#### Schema

```sql
CREATE TABLE feeds (
    url TEXT PRIMARY KEY NOT NULL, title TEXT, link TEXT, updated TEXT,
    user_title TEXT, caching_info TEXT, update_after TEXT, last_retrieved TEXT,
    last_updated TEXT, added TEXT NOT NULL, last_exception TEXT,
    stale INTEGER NOT NULL DEFAULT 0, updates_enabled INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE entries (
    id TEXT NOT NULL, feed TEXT NOT NULL REFERENCES feeds(url) ON DELETE CASCADE,
    title TEXT, link TEXT, updated TEXT, published TEXT, author TEXT,
    read INTEGER NOT NULL DEFAULT 0, read_modified TEXT, added TEXT NOT NULL,
    recent_sort TEXT NOT NULL, PRIMARY KEY (id, feed)
);
CREATE INDEX entries_by_recent ON entries (recent_sort DESC, feed, id);
CREATE INDEX entries_by_feed   ON entries (feed);
CREATE TABLE feed_tags (feed TEXT NOT NULL REFERENCES feeds(url) ON DELETE CASCADE,
    key TEXT NOT NULL, PRIMARY KEY (feed, key));
CREATE TABLE app_settings (key TEXT PRIMARY KEY NOT NULL, value TEXT NOT NULL);
CREATE TABLE tag_colors (tag TEXT PRIMARY KEY NOT NULL, color TEXT NOT NULL);
```

Timestamps are stored as RFC 3339.

The schema is created with `CREATE TABLE IF NOT EXISTS`, so opening an older
database adds the missing tables. `Store::SCHEMA_VERSION` is written to the
`user_version` pragma, but it gates no migration.

Tags are plain names: `feed_tags` holds one row per tag name per feed, and the
tag's color lives in `tag_colors`.

#### Public API (`Store`)

`add_feed`, `delete_feed`, `feed_exists`, `get_feeds(TagFilter)`,
`get_visible_feeds(TagFilter)`, `get_feed_nodes(TagFilter)`, `get_feed`,
`feed_count`,
`has_feeds`, `set_feed_user_title`, `get_entries`, `entry_count`, `unread_count`,
`set_entry_read`, `mark_all_as_read`, `prune_feed`, `get_tags`, `set_tag`,
`delete_tag`, `tag_keys`, `rename_tag`, `delete_tag_globally`,
`feeds_to_update`, `feed_update_state`, `apply_update`, `apply_not_modified`,
`record_update_error`, `set_caching_info`, `get_setting`, `set_setting`,
`delete_setting`, `get_tag_color`, `set_tag_color`, `delete_tag_color`,
`all_tag_colors`.

`TagFilter` is `All | Untagged | Tags(Vec<String>)` (OR semantics for tags).

> **Note:** the connection is wrapped in a `std::sync::Mutex`, which is *not*
> reentrant. `apply_update` counts inserted entries inside the same transaction
> rather than re-locking.

### Updating

`update_feeds(scheduled)` selects URLs with `feeds_to_update` and returns the
`UpdateReport`. The frontend triggers `update_feeds(scheduled: true)` once on
startup, so every eligible feed gets its first update after the program
launches.

HTTP retries use `backon` (3 attempts in total: the initial request plus at
most two retries, exponential 1–10 s).

### Tag colors

Tag colors live in the `tag_colors` table. New tags receive a deterministic
color derived from an MD5 hash of the name mapped onto HLS
(`feeds_core::tags::default_color_for_tag`). Colors are assigned lazily:
`Feeds::ensure_tag_colors` fills in any missing color for the known tags and
writes the table when something changed; `Feeds::rename_tag` carries the old
name's color over to the new one, keeping the new name's existing color if the
old tag had none, and `Feeds::delete_tag` drops the color with the tag. The
Tauri layer calls `ensure_tag_colors` when settings are read and after a feed's
tags are updated.

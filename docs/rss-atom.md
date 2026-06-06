# RSS / Atom Handling

feeds uses a layered approach for feed parsing and management:

| Layer | Library | Role |
|-------|---------|------|
| Database / Sync | `reader` (v3.24+) | SQLite-based feed storage, update orchestration, entry tracking |
| Parsing | `feedparser` (v6.0+) | Low-level RSS/Atom/JSON Feed parsing |
| HTTP | `requests` (v2.31+) | Fetching feeds and pages during discovery |

---

## 1. Library Overview

### `reader` library

The core feed-management library. Provides:

- `reader.make_reader(path)`: create (or open) a SQLite-backed reader.
- `reader.add_feed(url)` / `reader.delete_feed(url)`: subscription
  management.
- `reader.update_feeds(workers=N)` / `reader.update_feed(url)`: parallel or single feed update using `feedparser` internally.
- `reader.get_feeds()` / `reader.get_entries(feed=...)`: query feeds
  and entries.
- `reader.mark_entry_as_read((feed_id, entry_id))` / `mark_entry_as_unread`: read-state tracking.
- `reader.get_entry_counts(feed=..., read=...)`: aggregate counters.

### `feedparser` library

Used directly in two places:

1. **Direct feed validation** during discovery: `feedparser.parse()`
   checks whether a URL returns parseable feed content.
2. **Common-path probing**: validates probed feed candidates.

### `requests` library

Used for all HTTP fetches during feed discovery (not for feed updates;
`reader` handles its own HTTP internally).

---

## 2. `FeedReader` Class

**File:** `feeds/models/feed.py:294`

High-level wrapper around `reader.Reader` that adds feed discovery and
converts reader types into local `Feed`/`Entry` dataclasses.

### Initialisation (line 311)

```python
def __init__(self) -> None:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    self.reader = reader.make_reader(str(_DB_PATH))
```

The SQLite database path defaults to `~/.feeds/feeds.db` and can be
overridden with the `FEEDS_DB_PATH` environment variable.

### Public API

| Method | Line | Description |
|--------|------|-------------|
| `add_feed(url)` | 317 | Subscribe to a feed (no-op if already subscribed) |
| `discover_feeds(url)` | 454 | Discover feed URLs from a page, caches results |
| `update_feeds(scheduled=True)` | 480 | Update all feeds with adaptive parallelism |
| `update_feed(feed_url)` | 491 | Update a single feed |
| `get_feeds(tags=None)` | 500 | Yield all subscribed `Feed` instances; `tags=False` for untagged, `tags=[...]` for OR filter |
| `get_posts(feed)` | 514 | Yield all `Entry` instances for a feed |
| `mark_entry_as_read(entry)` | 530 | Mark entry as read |
| `mark_entry_as_unread(entry)` | 539 | Mark entry as unread |
| `set_feed_user_title(feed, title)` | 548 | Set a custom display title for a feed |
| `delete_feed(feed)` | 558 | Unsubscribe and delete a feed |
| `mark_all_as_read(feed)` | 567 | Mark all entries in a feed as read |
| `prune_feed(feed, n)` | 577 | Keep only the `n` most recent entries |
| `get_unread_count(feed)` | 612 | Return unread count for a feed |
| `get_feed_tags(feed_url)` | 623 | Return tag names for a feed |
| `get_all_tag_keys()` | 634 | Return all tag names across all feeds |
| `set_feed_tag(feed_url, tag)` | 642 | Add a tag to a feed |
| `remove_feed_tag(feed_url, tag)` | 652 | Remove a tag from a feed |
| `rename_tag(old, new)` | 662 | Rename a tag across all feeds (updates all feeds) |
| `delete_tag(tag)` | 674 | Delete a tag from all feeds |

### Properties

| Property | Line | Description |
|----------|------|-------------|
| `last_discovered_feeds` | 471 | Cached result from last `discover_feeds()` call |

---

## 3. Data Models

### `Feed`: `feeds/models/feed.py:254`

```python
@dataclass(frozen=True, slots=True)
class Feed:
    id: str                    # Feed URL (unique identifier)
    title: str                 # Display title
    user_title: str | None     # Custom user-set display title (None = use feed title)
    last_updated: datetime | None  # Most recent update timestamp
```

### `Entry`: `feeds/models/feed.py:272`

```python
@dataclass(frozen=True, slots=True)
class Entry:
    url: str                   # Permalink to the article
    title: str                 # Entry headline
    last_updated: datetime | None  # Publication/update timestamp
    entry_id: str              # Unique ID within feed (reader internals)
    feed_id: str               # Feed.id this entry belongs to
    read: bool                 # Read/unread state
    author: str = ""           # Author name(s)
```

Both dataclasses are **frozen** (immutable, hashable) and use
**slots** for memory efficiency. `Entry` uses `dataclasses.replace()`
to create modified copies when toggling read state.

---

## 4. Storage

- **Engine**: SQLite
- **Default path**: `~/.feeds/feeds.db`
- **Override**: `FEEDS_DB_PATH` environment variable
- **Managed by**: the `reader` library. No raw SQL is written in
  feeds; all database operations go through `reader`'s API.

---

## 5. Feed Updating

### All feeds (line 480)

```python
def update_feeds(self, scheduled: bool = True) -> None:
    feed_count = len(list(self.reader.get_feeds()))
    workers = min(feed_count, (os.cpu_count() or 1) * 2)
    self.reader.update_feeds(workers=workers, scheduled=scheduled)
```

Adaptive parallelism: uses up to `2 × CPU cores` concurrent workers.
The `reader` library handles HTTP fetching and feedparser parsing
internally for each feed.

When `scheduled=True` (default), the `reader` library's built-in
update scheduling (60-minute interval) causes feeds updated recently
to be silently skipped. Pass `scheduled=False` to force a full refresh
of every subscribed feed.

### Single feed (line 491)

```python
def update_feed(self, feed_url: str) -> None:
    self.reader.update_feed(feed_url)
```

---

## 6. Read / Unread State

Read state is tracked per-entry by the `reader` library.

| Operation | Method | Implementation |
|-----------|--------|---------------|
| Mark read | `mark_entry_as_read(entry)` | Calls `reader.mark_entry_as_read((feed_id, entry_id))` |
| Mark unread | `mark_entry_as_unread(entry)` | Calls `reader.mark_entry_as_unread((feed_id, entry_id))` |
| Mark all read | `mark_all_as_read(feed)` | Iterates all entries, marks each read |
| Count unread | `get_unread_count(feed)` | Calls `reader.get_entry_counts(feed=..., read=False).total` |

---

## 7. Feed Deletion

```python
def delete_feed(self, feed: Feed) -> None:
    self.reader.delete_feed(feed.id)
```

Removes the feed subscription, all associated entries, and all tag
references from the database (the ``reader`` library handles tag
cleanup automatically on feed deletion).

---

## 8. Tagging

Tags are **per-feed** metadata stored in the ``reader`` library's
SQLite database via ``reader.set_tag(feed_url, key, True)`` /
``reader.delete_tag(feed_url, key)``.  Tags persist across sessions
and are automatically cleaned up when a feed is deleted.

### Tag colors

Colors are stored separately in ``~/.feeds/settings.json`` (the
``tag_colors`` dictionary) because the ``reader`` library does not
support tag metadata.  A 12-color palette is used; new tags are
auto-assigned an unused color when first created (`_pick_tag_color` in
``feeds/ui/dialogs.py:28``).

### UI

- **Tag filter**: a ``QComboBox`` above the feed tree (hidden by
  default, toggled via ``Ctrl+T`` or Display → Show Tag Filter)
  filters top-level feeds using ``reader.get_feeds(tags=[tag])`` (OR
  logic).  "Untagged" shows feeds with no tags (``tags=False``).
- **Tag pills**: color-coded inline badges rendered after the feed
  title via the ``TwoLineRenderer`` delegate.
- **Tag feed dialog**: right-click a feed → "Tag feed…" to assign
  tags via checkboxes; new tags can be created inline.
- **Manage tags dialog**: Display → Manage Tags… to rename, delete,
  or recolor tags globally.

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

**File:** `feeds/models/feed.py:275`

High-level wrapper around `reader.Reader` that adds feed discovery and
converts reader types into local `Feed`/`Entry` dataclasses.

### Initialisation (line 292)

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
| `add_feed(url)` | 298 | Subscribe to a feed (no-op if already subscribed) |
| `discover_feeds(url)` | 448 | Discover feed URLs from a page, caches results |
| `update_feeds(scheduled=True)` | 474 | Update all feeds with adaptive parallelism |
| `update_feed(feed_url)` | 481 | Update a single feed |
| `get_feeds()` | 490 | Yield all subscribed `Feed` instances |
| `get_posts(feed)` | 499 | Yield all `Entry` instances for a feed |
| `mark_entry_as_read(entry)` | 525 | Mark entry as read |
| `mark_entry_as_unread(entry)` | 534 | Mark entry as unread |
| `delete_feed(feed)` | 543 | Unsubscribe and delete a feed |
| `mark_all_as_read(feed)` | 552 | Mark all entries in a feed as read |
| `get_unread_count(feed)` | 562 | Return unread count for a feed |

### Properties

| Property | Line | Description |
|----------|------|-------------|
| `last_discovered_feeds` | 465 | Cached result from last `discover_feeds()` call |

---

## 3. Data Models

### `Feed`: `feeds/models/feed.py:236`

```python
@dataclass(frozen=True, slots=True)
class Feed:
    id: str                    # Feed URL (unique identifier)
    title: str                 # Display title
    last_updated: datetime | None  # Most recent update timestamp
```

### `Entry`: `feeds/models/feed.py:252`

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

### All feeds (line 474)

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

### Single feed (line 481)

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

Entries without a `link` attribute are skipped with a warning log
during iteration (`get_posts`, line 511-514).

---

## 7. Feed Deletion

```python
def delete_feed(self, feed: Feed) -> None:
    self.reader.delete_feed(feed.id)
```

Removes the feed subscription and all associated entries from the
database.

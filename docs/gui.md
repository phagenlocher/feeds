# GUI Architecture

feeds uses **PySide6** (Qt for Python) for its desktop GUI. The UI is
built entirely programmatically — no `.ui` files or QSS stylesheets.

```
FeedsApp (QMainWindow)                [feeds/app.py:18]
├── Menu Bar: "Feed" menu with "Add Feed" | "Update Feeds"
├── FeedTreePane                      [feeds/ui/panes.py:30]
│   └── FeedTreeWidget (QTreeWidget)
│       ├── Feed 1 (top-level, collapsible)
│       │   ├── Entry 1 (child)
│       │   ├── Entry 2 (child)
│       │   └── …
│       ├── Feed 2 (top-level, collapsible)
│       │   ├── Entry 1 (child)
│       │   └── …
│       └── …
└── StatusBar
```

---

## 1. Entry Point

**`feeds/__main__.py`** — `python -m feeds`

Parses `-v`/`--verbose` for debug logging, creates a `QApplication`,
instantiates `FeedsApp`, and enters the Qt event loop.

---

## 2. Main Window — `FeedsApp`

**File:** `feeds/app.py:18`

`FeedsApp(QMainWindow)` is the application window. Responsibilities:

- **Menu bar** (line 56): "Feed" menu with "Add Feed" action (triggers
  discovery flow) and "Update Feeds" action (triggers background update
  of all feeds).
- **FeedTreePane** (line 69): Single central widget containing a
- **Busy state** (line 113): Disables the "Update" menu action during
  background operations and shows "Updating…" text.
- **Status bar**: Shows transient messages (errors, progress updates)
  that auto-clear after a configurable timeout.

### Signal wiring

| Signal | Handler | Description |
|--------|---------|-------------|
| `FeedTreePane.entry_activated(Entry)` | `_on_entry_activated` (line 151) | Marks entry read + opens URL in system browser |
| `FeedTreePane.entry_read_requested(Entry)` | `_on_entry_read` (line 155) | Marks a single entry as read |
| `FeedTreePane.entry_unread_requested(Entry)` | `_on_entry_unread` (line 158) | Marks a single entry as unread |
| `FeedTreePane.read_all_requested(int)` | `_read_all_async` (line 316) | Marks all entries in a feed as read |
| `FeedTreePane.remove_feed_requested(int)` | `_remove_feed_async` (line 294) | Unsubscribes and deletes a feed |
| `FeedTreePane.update_feed_requested(int)` | `_update_single_feed` (line 274) | Manually updates a single feed |

### Async flow

All blocking operations (feed discovery, adding, updating, deletion,
mark-all-read) are dispatched to `FeedService`, which runs them on a
background `QThread`. Callbacks rebuild the tree via `refresh(reader)`.

---

## 3. Tree Pane — `FeedTreePane`

**File:** `feeds/ui/panes.py:30`

`FeedTreePane(QWidget)` replaces the old two-pane splitter. It
contains a single `FeedTreeWidget(QTreeWidget)` where:

- **Top-level items** = subscribed feeds
- **Child items** = entries (posts) of that feed
- Feeds are **collapsed by default**; click the arrow to expand.

### Signals

| Signal | Type | Emitted when |
|--------|------|-------------|
| `entry_activated` | `Entry` | User double-clicks an entry |
| `entry_read_requested` | `Entry` | "Mark Read" context menu |
| `entry_unread_requested` | `Entry` | "Mark Unread" context menu |
| `read_all_requested` | `int` (feed row) | "Mark all as read" context menu |
| `remove_feed_requested` | `int` (feed row) | "Remove feed" context menu |
| `update_feed_requested` | `int` (feed row) | "Update feed" context menu |

### Display — feed items

Each feed item shows:
- **Title** — feed title with unread count: `"Feed Name (3)"`
- **Subtitle** — last-updated date (`"2025-12-01"`)
- **Bold** — indicates unread entries exist

### Display — entry items

Each entry item shows:
- **Title** — entry headline
- **Subtitle** — `"Author · 2025-12-01"` (author and date, joined by ·)
- **Bold** — indicates the entry is unread

### Context menu — feed (right-click)

| Action | Behavior |
|--------|----------|
| Mark all as read | Emits `read_all_requested(feed_index)` |
| Remove feed | Shows confirmation `QMessageBox`, then emits `remove_feed_requested(feed_index)` |
| Copy URL | Copies feed URL to system clipboard |
| Update feed | Emits `update_feed_requested(feed_index)` |

### Context menu — entry (right-click)

| Action | Behavior |
|--------|----------|
| Mark Read / Mark Unread | Toggles label based on current state; updates visual immediately, emits `entry_read_requested(Entry)` / `entry_unread_requested(Entry)` |

### Visual updates

The pane handles entry-level visual updates directly (no signal round-trip):

- `mark_entry_read(item)` — removes bold from entry, decrements parent feed unread count
- `mark_entry_unread(item)` — adds bold to entry, increments parent feed unread count

Bulk operations (update all, mark all as read, remove) trigger a full
`refresh(reader)` which rebuilds the entire tree from the database.

---

## 4. Tree Widget — `FeedTreeWidget`

**File:** `feeds/ui/widgets.py:11`

A `QTreeWidget` subclass used by `FeedTreePane`. Features:

- **Hand cursor** — changes to `PointingHandCursor` when hovering over
  items (via `eventFilter` on the viewport).
- **Font scaling** — `set_font_size()` recalculates item heights and
  reapplies fonts recursively through the tree hierarchy.
- **Item builder** — `build_item(title, subtitle, bold)` creates a
  `QTreeWidgetItem` with the subtitle stored in `UserRole` data.
- **Animations** — `setAnimated(True)` for smooth expand/collapse.
- **Hidden header** — no column headers displayed.
- **Selection styling** — blue background / white text via inline
  stylesheet.

### Custom data roles (widgets.py)

| Role | Value | Used on |
|------|-------|---------|
| `ItemTypeRole` (User+1) | `"feed"` / `"entry"` | All items |
| `FeedIndexRole` (User+2) | `int` (index in `pane.feeds`) | All items |
| `DataRole` (User+3) | `Feed` / `Entry` | All items |

---

## 5. Item Delegate — `TwoLineRenderer`

**File:** `feeds/ui/delegates.py:6`

A `QStyledItemDelegate` that paints each tree item in two lines:

```
Title (bold if unread, or normal weight)   ← top half
Subtitle (gray #888888, smaller font)      ← bottom half
```

- **Selected state**: Uses palette highlight colors for both title and
  subtitle.
- **Height**: `max(46, font.pointSize() * 4)` — scales with font size.

---

## 6. Dialogs

### `AddFeedDialog` — `feeds/ui/dialogs.py:11`

Simple dialog with a URL input field:

- **Validation**: Enables the "Add" button only when `urlparse`
  returns both a `scheme` and `netloc`.
- **Enter key** submits, Escape cancels.

### `AddFeedChoiceDialog` — `feeds/ui/dialogs.py:46`

Shown when multiple feeds are discovered from a single URL:

- **Multi-selection** `QListWidget` showing each feed's title and URL.
- "Add Selected" submits; "Cancel" aborts.
- `selected_feeds` property returns `[(url, title), ...]`.

---

## 7. Background Threading

### `FeedService` — `feeds/services/feed_service.py:21`

Orchestrates async feed operations. Maintains a single `WorkerThread`
and a FIFO queue of pending operations.

- `run(fn, name, on_done, on_error)` — enqueues or starts immediately
  if no worker is active.
- Sequential execution: each operation must finish before the next
  starts (`_process_queue`).
- High-level wrappers: `add_feed`, `discover_feeds`, `update_feed`,
  `update_feeds`, `delete_feed`, `mark_all_as_read`.

### `WorkerThread` — `feeds/services/worker.py:11`

Minimal `QThread` subclass:

- Runs a single callable in `run()`.
- Emits `done` signal on success, `error(str)` on failure.
- `finished` (built-in `QThread` signal) triggers queue processing.

---

## 8. Feed Addition Flow

1. User clicks "Add Feed" → `AddFeedDialog` opens.
2. URL entered → `FeedService.discover_feeds()` runs in background.
3. On completion:
   - **0 feeds**: Error message in status bar.
   - **1 feed**: Added and updated immediately.
   - **Multiple**: `AddFeedChoiceDialog` for selection.
4. Chain: `discover` → `add_feed` → `update_feed` → refresh tree
   → expand the newly added feed.
5. For multiple feeds, they are added sequentially with progress
   updates in the status bar (`_add_feeds_sequentially`).

---

## 9. Entry activation

When a tree entry is activated (double-clicked):

1. `FeedTreePane` updates the visual immediately (removes bold,
   decrements parent feed unread count).
2. Emits `entry_activated(Entry)` signal.
3. `FeedsApp` marks the entry as read in the database.
4. The entry's URL is opened in the system default browser via
   `webbrowser.open()`.

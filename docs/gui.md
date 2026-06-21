# GUI Architecture

feeds uses **PySide6** (Qt for Python) for its desktop GUI. The UI is
built entirely programmatically; no `.ui` files or QSS stylesheets.

```
FeedsApp (QMainWindow)                [feeds/app.py:27]
├── Menu Bar: "Feed" menu with "Add Feed" | "Update Feeds" | "Export Feeds" (OPML) | "Import Feeds" (OPML)
├── Menu Bar: "Display" menu with "Show Searchbar" | "Show Tag Filter" | "Manage Tags" | "Zoom In" | "Zoom Out" | "Reset Zoom"
├── FeedTreePane                      [feeds/ui/panes.py:58]
│   ├── SearchBar (QLineEdit)
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

**`feeds/__main__.py`**: `python -m feeds`

Parses `-v`/`--verbose` for debug logging, creates a `QApplication`,
instantiates `FeedsApp`, and enters the Qt event loop.

---

## 2. Main Window: `FeedsApp`

**File:** `feeds/app.py:27`

`FeedsApp(QMainWindow)` is the application window. Responsibilities:

- **Menu bar** (line 82): "Feed" menu with "Add Feed" action (triggers
  discovery flow) and "Update Feeds" action (triggers background update
  of all feeds).
- **Display menu** (line 105): "Show Searchbar" checkable action
   (`Ctrl+F`) toggles the fuzzy search bar (see §10).
   "Show Tag Filter" checkable action (`Ctrl+T`) toggles the tag
   filter combo (see §10). "Zoom In" (`Ctrl++`), "Zoom Out"
   (`Ctrl+-`), and "Reset Zoom" (`Ctrl+0`) control the application
   font size.
- **Font zoom** (line 196): Applies globally via
  `QApplication.setFont()` and propagates to the tree widget's
  item heights. Default is 12pt, clamped to minimum 6pt.
- **FeedTreePane** (line 141): Single central widget containing a
- **Busy state** (line 200): Disables the "Update" menu action during
  background operations and shows "Updating…" text.
- **Status bar**: Shows transient messages (errors, progress updates)
  that auto-clear after a configurable timeout.

### Signal wiring

| Signal | Handler | Description |
|--------|---------|-------------|
| `FeedTreePane.entry_activated(Entry)` | `_on_entry_activated` (line 223) | Marks entry read + opens URL in system browser |
| `FeedTreePane.entry_read_requested(Entry)` | `_on_entry_read` (line 227) | Marks a single entry as read |
| `FeedTreePane.entry_unread_requested(Entry)` | `_on_entry_unread` (line 230) | Marks a single entry as unread |
| `FeedTreePane.read_all_requested(int)` | `_read_all_async` (line 513) | Marks all entries in a feed as read |
| `FeedTreePane.remove_feed_requested(int)` | `_remove_feed_async` (line 457) | Unsubscribes and deletes a feed |
| `FeedTreePane.rename_feed_requested(int)` | `_rename_feed` (line 480) | Opens rename dialog for a feed |
| `FeedTreePane.update_feed_requested(int)` | `_update_single_feed` (line 434) | Manually updates a single feed |
| `FeedTreePane.prune_feed_requested(int, int)` | `_prune_feed_async` (line 536) | Prunes old entries from a feed |
| `FeedTreePane.search_visibility_changed(bool)` | `_on_search_visibility_changed` (line 192) | Keeps searchbar action checked state in sync |
| `FeedTreePane.tag_filter_visibility_changed(bool)` | `_on_tag_filter_visibility_changed` | Keeps tag filter action checked state in sync |

### Async flow

All blocking operations (feed discovery, adding, updating, deletion,
mark-all-read) are dispatched to `FeedService`, which runs them on a
background `QThread`. Callbacks rebuild the tree via `refresh(reader)`.

---

## 3. Tree Pane: `FeedTreePane`

**File:** `feeds/ui/panes.py:58`

`FeedTreePane(QWidget)` contains a single `FeedTreeWidget(QTreeWidget)`
where:

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
| `rename_feed_requested` | `int` (feed row) | "Rename" context menu |
| `update_feed_requested` | `int` (feed row) | "Update feed" context menu |
| `prune_feed_requested` | `int, int` (feed row, n) | "Prune entries" context menu |
| `search_visibility_changed` | `bool` | Search bar shown/hidden |
| `tag_filter_visibility_changed` | `bool` | Tag filter combo shown/hidden |

### Display: feed items

Each feed item shows:
- **Title**: feed title with unread count: `"Feed Name (3)"`
- **Subtitle**: last-updated date (`"2025-12-01"`)
- **Bold**: indicates unread entries exist

### Display: entry items

Each entry item shows:
- **Title**: entry headline
- **Subtitle**: `"Author · 2025-12-01"` (author and date, joined by ·)
- **Bold**: indicates the entry is unread

### Context menu: feed (right-click)

| Action | Behavior |
|--------|----------|
| Mark all as read | Emits `read_all_requested(feed_index)` |
| Remove feed | Shows confirmation `QMessageBox`, then emits `remove_feed_requested(feed_index)` |
| Prune entries | Submenu: presets (10/25/50) and custom N; shows confirmation, then emits `prune_feed_requested(feed_index, n)` |
| Rename | Emits `rename_feed_requested(feed_index)` |
| Copy URL | Copies feed URL to system clipboard |
| Update feed | Emits `update_feed_requested(feed_index)` |

### Context menu: entry (right-click)

| Action | Behavior |
|--------|----------|
| Mark Read / Mark Unread | Toggles label based on current state; updates visual immediately, emits `entry_read_requested(Entry)` / `entry_unread_requested(Entry)` |

### Visual updates

The pane handles entry-level visual updates directly (no signal round-trip):

- `mark_entry_read(item)`: removes bold from entry, decrements parent feed unread count
- `mark_entry_unread(item)`: adds bold to entry, increments parent feed unread count

Bulk operations (update all, mark all as read, remove) trigger a full
`refresh(reader)` which rebuilds the entire tree from the database.

---

## 4. Tree Widget: `FeedTreeWidget`

**File:** `feeds/ui/widgets.py:23`

A `QTreeWidget` subclass used by `FeedTreePane`. Features:

- **Hand cursor**: changes to `PointingHandCursor` when hovering over
  items (via `eventFilter` on the viewport).
- **Font scaling**: `set_font_size()` recalculates item heights and
  reapplies fonts recursively through the tree hierarchy.
- **Item builder**: `build_item(title, subtitle, bold)` creates a
  `QTreeWidgetItem` with the subtitle stored in `UserRole` data.
- **Animations**: `setAnimated(True)` for smooth expand/collapse.
- **Hidden header**: no column headers displayed.
- **Selection styling**: handled by the `TwoLineRenderer` delegate,
  which uses palette highlight colors.

### Custom data roles (widgets.py)

| Role | Value | Used on |
|------|-------|---------|
| `ItemTypeRole` (User+1) | `ItemType.FEED` (1) / `ItemType.ENTRY` (2) | All items |
| `FeedIndexRole` (User+2) | `int` (index in `pane.feeds`) | All items |
| `DataRole` (User+3) | `Feed` / `Entry` | All items |

---

## 5. Item Delegate: `TwoLineRenderer`

**File:** `feeds/ui/delegates.py:13`

A `QStyledItemDelegate` that paints each tree item in two lines:

```
Title (bold if unread, or normal weight)   ← top half
Subtitle (muted palette color, smaller font)  ← bottom half
```

- **Selected state**: Uses palette highlight colors for both title and
  subtitle.
- **Height**: `max(46, font.pointSize() * 4)`; scales with font size.

---

## 6. Dialogs

### `AddFeedDialog`: `feeds/ui/dialogs.py:11`

Simple dialog with a URL input field:

- **Validation**: Enables the "Add" button only when `urlparse`
  returns both a `scheme` and `netloc`.
- **Enter key** submits, Escape cancels.

### `AddFeedChoiceDialog`: `feeds/ui/dialogs.py:88`

Shown when multiple feeds are discovered from a single URL:

- **Multi-selection** `QListWidget` showing each feed's title and URL.
- "Add Selected" submits; "Cancel" aborts.
- `selected_feeds` property returns `[(url, title), ...]`.

---

## 7. Background Threading

### `FeedService`: `feeds/services/feed_service.py:22`

Orchestrates async feed operations. Maintains a single `WorkerThread`
and a FIFO queue of pending operations.

- `run(fn, name, on_done, on_error)`: enqueues or starts immediately
  if no worker is active.
- Sequential execution: each operation must finish before the next
  starts (`_process_queue`).
- High-level wrappers: `add_feed`, `discover_feeds`, `update_feed`,
  `update_feeds`, `delete_feed`, `mark_all_as_read`, `prune_feed`,
  `set_feed_user_title`.

### `WorkerThread`: `feeds/services/worker.py:11`

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

---

## 10. Search / Filter

### Entry search

A `QLineEdit` search bar sits above the tree widget in `FeedTreePane`,
hidden by default.  It provides fuzzy filtering of entries by title,
powered by **rapidfuzz** (`fuzz.partial_ratio`).

### Tag filter

A `QComboBox` tag filter sits below the search bar, hidden by default.
It provides filtering of top-level feeds by tag via the ``reader``
library's native OR filter (`reader.get_feeds(tags=[tag])`).  The
combo lists "All tags" (default), "Untagged", and each defined tag.

---

## 11. Single-Instance Guard

**File:** `feeds/_single_instance.py`

The app prevents multiple concurrent processes via `SingleInstanceGuard`, which
uses two Qt primitives working together:

1. **`QSharedMemory`** (`feeds-app` key) — atomic first-instance detection at
   the OS level.  The winning process creates a 1-byte segment; subsequent
   processes fail to attach (the OS owns the key and releases it on crash).
2. **`QLocalServer`** / **`QLocalSocket`** — the first instance listens on a
   named socket (`/tmp/feeds-app` on Linux / macOS, a named pipe on Windows).
   Secondary instances connect, send `b"focus"`, and exit.

### Flow

```
Secondary instance                  First instance
       │                                  │
       ├─ QSharedMemory.attach() ─────────┤
       │  (fails — already owned)         │
       ├─ QLocalSocket.connect() ────────►│
       │  sends b"focus"                  ├─ QLocalServer.newConnection
       │  sys.exit(0)                     │  → showNormal/raise_/activateWindow
       │                                  │  → QApplication.alert(3000ms)
```

### Race-condition recovery

If two instances start simultaneously, `QSharedMemory.create()` succeeds for
exactly one process (atomic OS mutex); the loser retries `attach()`, connects,
and exits.

### Platform notes

| Platform | Activation |
|----------|-----------|
| X11/Linux | `raise_()` + `activateWindow()` — may be blocked by some WMs |
| Wayland | `activateWindow()` often denied; `alert()` provides taskbar flash |
| macOS | `raise_()` + `activateWindow()` work; `alert()` flashes dock icon |
| Windows | `raise_()` + `activateWindow()` work; `alert()` flashes taskbar |

### Keyboard shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+F` | Toggle the search bar (show/hide). When shown, it is focused and existing text is selected. |
| `Ctrl+T` | Toggle the tag filter (show/hide). When hidden, the filter is reset to "All tags". |
| `Ctrl++` / `Ctrl+=` | Zoom in: increase the application font size by 1pt. |
| `Ctrl+-` | Zoom out: decrease the application font size by 1pt (min 6pt). |
| `Ctrl+0` | Reset zoom to the default font size (12pt). |
| `Escape` (in search bar) | Clear the search bar, hide it, and return focus to the tree. |
| `Escape` (in tag filter) | Reset the tag filter to "All tags", hide it, and return focus to the tree. |

### Fuzzy matching

- Each entry's title is compared against the search query using
  `rapidfuzz.fuzz.partial_ratio` with a threshold of 80.
- Entries that match are shown; non-matching entries are hidden via
  `QTreeWidgetItem.setHidden(True)`.
- Feed items (top-level) are hidden when they have zero visible
  children.
- An **empty** search bar clears all filters: every entry and feed is
  shown.

### Interaction with tree rebuilds

`refresh()` reapplies the current filter text after rebuilding the
tree from the database.  This means the filter persists across feed
updates, additions, removals, and read-state bulk changes.

State restoration (`_save_state` / `_restore_state`) runs after
filtering.  If the previously selected item is now hidden due to
filtering, `scrollToItem` is skipped to avoid jumping to an
off-screen item.

# GUI Architecture

feeds uses **PySide6** (Qt for Python) for its desktop GUI. The UI is
built entirely programmatically — no `.ui` files or QSS stylesheets.

```
FeedsApp (QMainWindow)                [feeds/app.py:18]
├── QToolBar: "Add Feed" | "Update Feeds"
├── QSplitter (horizontal)
│   ├── FeedsPane (left, 240px)       [feeds/ui/panes.py:32]
│   └── EntriesPane (right, 560px)    [feeds/ui/panes.py:129]
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

- **Toolbar** (line 56): "Add Feed" button (triggers discovery flow)
  and "Update Feeds" button (triggers background update of all feeds).
- **Splitter layout** (line 69): Horizontal `QSplitter` with
  `FeedsPane` (240 px initial) on the left and `EntriesPane`
  (560 px initial) on the right.
- **Font zoom** (line 87): `Ctrl++`/`Ctrl+=` to zoom in, `Ctrl+-` to
  zoom out, `Ctrl+0` to reset (base 12 pt). Adjusts both the
  application-wide font and the item sizes in both panes.
- **Busy state** (line 117): Disables the "Update" button during
  background operations and shows "Updating…" text.
- **Status bar**: Shows transient messages (errors, progress updates)
  that auto-clear after a configurable timeout.

### Signal wiring

| Signal | Handler | Description |
|--------|---------|-------------|
| `FeedsPane.feed_selected(int)` | `_on_feed_selected` (line 130) | Populates `EntriesPane` with entries for the chosen feed |
| `FeedsPane.read_all_requested(int)` | `_read_all_async` (line 333) | Marks all entries in a feed as read |
| `FeedsPane.remove_feed_requested(int)` | `_remove_feed_async` (line 310) | Unsubscribes and deletes a feed |
| `EntriesPane.entry_activated(int)` | `_on_entry_activated` (line 159) | Marks entry read + opens URL in system browser |
| `EntriesPane.entry_read_requested(int)` | `_on_entry_read` (line 163) | Marks a single entry as read |
| `EntriesPane.entry_unread_requested(int)` | `_on_entry_unread` (line 167) | Marks a single entry as unread |

### Async flow

All blocking operations (feed discovery, adding, updating, deletion,
mark-all-read) are dispatched to `FeedService` (see below), which runs
them on a background `QThread`. Callbacks update the UI on completion.

---

## 3. Left Pane — `FeedsPane`

**File:** `feeds/ui/panes.py:32`

Shows the list of subscribed feeds with unread counts. Uses a
`FeedListWidget` with a `TwoLineRenderer` delegate.

### Signals

| Signal | Type | Emitted when |
|--------|------|-------------|
| `feed_selected` | `int` (row index) | User clicks a feed |
| `read_all_requested` | `int` (row index) | "Mark all as read" context menu |
| `remove_feed_requested` | `int` (row index) | "Remove feed" context menu |

### Display

Each item shows:
- **Title** — feed title with unread count: `"Feed Name (3)"`
- **Subtitle** — last-updated date (`"2025-12-01"`)
- **Bold** — indicates unread entries exist

### Context menu (line 87)

Right-click on a feed:

| Action | Behavior |
|--------|----------|
| Mark all as read | Emits `read_all_requested` |
| Remove feed | Shows confirmation `QMessageBox`, then emits `remove_feed_requested` |
| Copy URL | Copies feed URL to system clipboard |

Uses `match`/`case` with `typing.assert_never` for exhaustive dispatch
on the `FeedMenuAction` enum.

---

## 4. Right Pane — `EntriesPane`

**File:** `feeds/ui/panes.py:129`

Shows the entries (articles) for the currently selected feed.

### Signals

| Signal | Type | Emitted when |
|--------|------|-------------|
| `entry_activated` | `int` (row index) | User double-clicks an entry |
| `entry_read_requested` | `int` (row index) | "Mark Read" context menu |
| `entry_unread_requested` | `int` (row index) | "Mark Unread" context menu |

### Display

Each item shows:
- **Title** — entry headline
- **Subtitle** — `"Author · 2025-12-01"` (author and date, joined by ·)
- **Bold** — indicates the entry is unread

### Interaction

- **Double-click**: Marks the entry as read and opens its URL in the
  system browser via `webbrowser.open()`.
- **Context menu** (line 197): Toggle "Mark Read" / "Mark Unread"
  depending on current state.

---

## 5. Shared Widget — `FeedListWidget`

**File:** `feeds/ui/widgets.py:6`

A `QListWidget` subclass used by both panes. Adds:

- **Hand cursor** — changes to `PointingHandCursor` when hovering over
  items (via `eventFilter` on the viewport, line 50).
- **Font scaling** — `set_font_size()` recalculates item heights and
  reapplies fonts (line 19).
- **Item builder** — `build_item(title, subtitle, bold)` creates a
  `QListWidgetItem` with the subtitle stored in `UserRole` data
  (line 40).
- **Selection styling** — blue background / white text via inline
  stylesheet (line 13).

---

## 6. Item Delegate — `TwoLineRenderer`

**File:** `feeds/ui/delegates.py:6`

A `QStyledItemDelegate` that paints each list item in two lines:

```
Title (bold if unread, or normal weight)   ← top half
Subtitle (gray #888888, smaller font)      ← bottom half
```

- **Selected state**: Uses palette highlight colors for both title and
  subtitle (line 30-39).
- **Height**: `max(46, font.pointSize() * 4)` — scales with font size
  (line 64).

---

## 7. Dialogs

### `AddFeedDialog` — `feeds/ui/dialogs.py:11`

Simple dialog with a URL input field:

- **Validation** (line 37): Enables the "Add" button only when
  `urlparse` returns both a `scheme` and `netloc`.
- **Enter key** submits, Escape cancels.

### `AddFeedChoiceDialog` — `feeds/ui/dialogs.py:46`

Shown when multiple feeds are discovered from a single URL:

- **Multi-selection** `QListWidget` showing each feed's title and URL.
- "Add Selected" submits; "Cancel" aborts.
- `selected_feeds` property returns `[(url, title), ...]`.

---

## 8. Background Threading

### `FeedService` — `feeds/services/feed_service.py:21`

Orchestrates async feed operations. Maintains a single `WorkerThread`
and a FIFO queue of pending operations.

- `run(fn, name, on_done, on_error)` — enqueues or starts immediately
  if no worker is active (line 37).
- Sequential execution: each operation must finish before the next
  starts (`_process_queue`, line 85).
- High-level wrappers: `add_feed`, `discover_feeds`, `update_feed`,
  `update_feeds`, `delete_feed`, `mark_all_as_read`.

### `WorkerThread` — `feeds/services/worker.py:11`

Minimal `QThread` subclass:

- Runs a single callable in `run()`.
- Emits `done` signal on success, `error(str)` on failure.
- `finished` (built-in `QThread` signal) triggers queue processing.

---

## 9. Feed Addition Flow

1. User clicks "Add Feed" → `AddFeedDialog` opens.
2. URL entered → `FeedService.discover_feeds()` runs in background.
3. On completion:
   - **0 feeds**: Error message in status bar.
   - **1 feed**: Added and updated immediately.
   - **Multiple**: `AddFeedChoiceDialog` for selection.
4. Chain: `discover` → `add_feed` → `update_feed` → select in pane.
5. For multiple feeds, they are added sequentially with progress
   updates in the status bar (`_add_feeds_sequentially`, line 234).

---

## 10. Entry activation

When a feed entry is activated (double-clicked):

1. The entry is marked as read in the database.
2. The entry's URL is opened in the system default browser via
   `webbrowser.open()`.
3. The feed's unread count is recalculated and the feed list item
   font is updated (bold removed if no unread remaining).

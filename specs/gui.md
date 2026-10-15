# GUI (Tauri + Svelte)

## Context

feeds uses **[Tauri v2](https://tauri.app)** for the desktop shell and a
**Svelte + TypeScript** frontend rendered in the system webview.

The GUI holds no database or feed-fetching logic: most operations invoke a Tauri
command that calls into `feeds-core`, while file pickers, the browser opener and
the clipboard use Tauri plugins, and OPML files are read or written through the
`read_file` / `write_file` commands.

```
Webview (Svelte)                         Rust (feeds-app)
┌───────────────────────────┐            ┌──────────────────────────────┐
│ App.svelte                │  invoke →  │ #[tauri::command] commands.rs │
│  - tree (feeds + entries) │  ← events  │   ↓                           │
│  - context menus, dialogs │            │ AppState { Feeds, busy }      │
│  - search / tag filter    │            │   ↓                           │
│  - status bar             │            │ feeds-core (store/update/…)   │
└───────────────────────────┘            └──────────────────────────────┘
```

## Behaviour

### Window and startup

**Scenario: the main window opens**
**Given** the app is launched
**When** `feeds_app::run()` has completed setup
**Then** a single window titled "Feeds" is shown at 800×600 (minimum 480×360)
**And** it loads the built Svelte app from `ui/dist`
**And** the native menu contains the Feed, Display and Help menus
**And** the `Feeds` facade is open, the settings are read from the database, and
the font size is applied to the native UI

**Scenario: a menu item is selected**
**Given** the main window is open
**When** the user selects a native menu item
**Then** the frontend receives a `"menu"` event carrying the item id
**And** `App.svelte` performs the corresponding action from the menu table in
the Reference section

**Scenario: the app is started a second time**
**Given** an instance of feeds is already running
**When** the app is launched again
**Then** the second process forwards to the first
**And** the existing window is unminimised, shown and focused
**And** no second window is created

### Feed tree

**Scenario: a feed with unread entries is rendered**
**Given** `get_tree` returns a feed with an unread count greater than zero
**When** the tree is rendered
**Then** the feed row reads `"Title (N)"` in bold, where `N` is the unread count
**And** it shows its colored tag pills and the publication date of its newest
entry

**Scenario: a feed row shows the date of the newest entry**
**Given** `get_tree` returns a feed whose entries carry dates
**When** the tree is rendered
**Then** the feed row shows the publication date of the feed's newest entry as
`YYYY-MM-DD`
**And** it never shows the feed's last-updated (last fetch) timestamp
**And** the date is not affected by an active search filter
**And** a feed whose entries carry no date shows no date

**Scenario: a feed has never been fetched successfully**
**Given** a subscribed feed has no title, no user title, and no entries
**When** the tree is rendered
**Then** the feed is hidden from the tree
**And** it remains subscribed and included in OPML exports
**And** it reappears after a later update once it has a title or at least one entry

**Scenario: entries are rendered**
**Given** a feed with entries is expanded
**When** its child rows are rendered
**Then** each entry uses a single-line layout: the title on the left and the
date `YYYY-MM-DD` on the right
**And** the author is not shown
**And** the title is elided when it does not fit, so the date stays visible
**And** the date is the entry's publication date
**And** unread entries are bold

**Scenario: dates are rendered in the local time zone**
**Given** an entry with a timestamp
**When** its date is rendered
**Then** the calendar day shown is the local day of that timestamp

**Scenario: an entry is opened**
**Given** an entry is selected
**When** the user double-clicks it
**Then** the entry is marked read
**And** its URL is opened in the system browser when the entry has a link

### Startup update

The startup update is specified in [`startup-update.md`](startup-update.md).

### Context menus

**Scenario: a feed is right-clicked**
**Given** a feed row
**When** the user opens its context menu
**Then** the menu offers Mark all as read, Remove, Prune, Tag, Rename,
Copy URL and Update

**Scenario: an entry is right-clicked**
**Given** an entry row
**When** the user opens its context menu
**Then** the menu offers Mark Read/Unread and Copy URL

### Dialogs

**Scenario: a dialog is opened**
**Given** the main window
**When** the user triggers Add Feed, Choose feeds, Rename, Prune, Tag feed,
Tag color, Manage tags or About
**Then** the dialog is shown as a modal overlay

**Scenario: a tag is recolored**
**Given** the Manage Tags or Tag color dialog
**When** the user picks a color
**Then** an in-app dialog offers a color input and a hex field accepting
`#rgb` or `#rrggbb` (normalized to `#rrggbb`)

**Scenario: OPML import or export is chosen**
**Given** the Feed menu
**When** the user selects Import Feeds… or Export Feeds…
**Then** `@tauri-apps/plugin-dialog` is used to pick the path
**And** the file is read or written with the `read_file` / `write_file` commands

**Scenario: several feeds are discovered**
**Given** discovery returns more than one feed
**When** Add Feed completes
**Then** a selection dialog is shown before subscribing

### Search and tag filter

**Scenario: the user searches for text**
**Given** the search bar is visible
**When** the user types a query
**Then** after a 300 ms debounce all entry titles are sent to `fuzzy_filter`
in one call
**And** non-matching rows are hidden
**And** feeds with no visible entries are hidden

**Scenario: the search results stay in sync with the query**
**Given** the search query changes
**When** the tree re-renders
**Then** filtering is applied through the reactive `visibleNodes` derivation in
`App.svelte`
**And** it is not applied through helper functions called from the template,
because Svelte cannot see a function's dependencies and would not re-evaluate a
template expression that called a helper such as `feedVisible(node)` when the
query changed

**Scenario: the tag filter changes**
**Given** the tag filter is set to `""`, `"__untagged__"` or a tag name
**When** the filter changes
**Then** the tree is reloaded with `get_tree(filter)`

### Zoom

**Scenario: the app starts with default settings**
**Given** no font-size setting has been stored
**When** the UI loads
**Then** the font size is 14 px

**Scenario: the user zooms in, out or resets**
**Given** the UI is visible
**When** the user presses `Ctrl++` (or `Ctrl+=`), `Ctrl+-` or `Ctrl+0`
**Then** the font size changes, is clamped to a minimum of 6 px, and is
persisted to the database
**And** the `--font-size` CSS variable is updated
**And** on Linux the native GTK menu bar and its popups are updated by
`feeds-app::native::apply_font_size` to the same pixel size
**And** macOS/Windows menus are left to the OS and cannot be resized

**Scenario: shortcuts are handled in the webview**
**Given** the zoom shortcuts
**When** they are dispatched
**Then** they are handled by `onKey` in the webview rather than as native menu
accelerators, because `+` has no accelerator code (it is Shift+`=`)

### Status bar

**Scenario: an operation reports progress**
**Given** an operation is running
**When** the status bar shows a progress label such as “Updating feeds…”
**Then** the label is cleared automatically when the operation finishes without
reporting its own result
**And** transient messages clear after 4 seconds

**Scenario: a feed fails to update**
**Given** `update_feeds` returns an `UpdateReport` with `failed` entries
**When** the update finishes
**Then** the status bar reads `Failed to update <feed title>: <reason>`
**And** a summary is shown when several feeds failed
**And** the message clears after 4 seconds

### Theme

**Scenario: the system theme is used**
**Given** the app is running
**When** the system light/dark palette changes
**Then** all colors update through CSS variables mapped to the system palette
(`Canvas`, `CanvasText`, `Highlight`, `HighlightText`) and `color-mix`
**And** theme colors are not hardcoded (the modal backdrop and menu shadow use
translucent black)

### Keyboard shortcuts

**Scenario: a shortcut is pressed**
**Given** the main window has focus
**When** the user presses a key from the shortcut table in the Reference section
**Then** the corresponding action is performed
**And** `Escape` first clears the search bar, then closes menus and dialogs

## Reference

### Entry point

`crates/feeds-app/src/main.rs` calls `feeds_app::run()`, which:

1. Parses CLI arguments with `clap` (`-d/--data-dir`, `-v/--verbose`;
   `--version` is provided by `clap`).
2. Initialises `tracing-subscriber`.
3. Registers plugins: `single-instance`, `opener`, `dialog`,
   `clipboard-manager`.
4. In `setup`: opens the `Feeds` facade, reads the settings from the
   database, applies the font size to the native UI, and installs the native
   menu.
5. Registers the command handler and runs the Tauri app.

### Main window

`tauri.conf.json` defines a single window titled "Feeds" (800×600, min 480×360).
The webview loads the built Svelte app (`ui/dist`).

### Native menu

`crates/feeds-app/src/menu.rs` builds the menu; menu events are emitted to the
frontend as a `"menu"` event carrying the item id, which `App.svelte` handles:

| Menu | Items |
|------|-------|
| Feed | Add Feed (`Ctrl+N`), Update Feeds (`Ctrl+R`), Export Feeds…, Import Feeds… |
| Display | Show Searchbar (`Ctrl+F`), Show Tag Filter (`Ctrl+T`), Manage Tags…, Zoom In, Zoom Out, Reset Zoom (webview shortcuts, see Zoom) |
| Help | Report Issue, About |

### Commands

Defined in `crates/feeds-app/src/commands.rs` and invoked from the frontend with
`@tauri-apps/api/core`'s `invoke`.

| Command | Description |
|---------|-------------|
| `get_tree(filter)` | Feeds with entries, unread counts, tags and the date of the newest entry |
| `has_feeds` | Whether any feed is subscribed |
| `app_version` | The app version, shown in the About dialog |
| `add_feed(url)` | Subscribe (idempotent) |
| `delete_feed(url)` | Unsubscribe and delete entries |
| `rename_feed(url, title)` | Set a custom display title |
| `set_entry_read(feed, entryId, read)` | Toggle read state |
| `mark_all_as_read(feed)` | Mark every entry read |
| `prune_feed(feed, n)` | Keep the `n` most recent entries |
| `discover_feeds(url)` | Run the discovery pipeline |
| `update_feed(url)` | Fetch one feed |
| `update_feeds(scheduled)` | Fetch feeds concurrently; with `scheduled = true`, only feeds whose `update_after` has passed |
| `get_tag_keys` / `get_feed_tags` / `set_feed_tags` | Tag queries and updates |
| `default_tag_colors(tags)` | Deterministic colors for tags without a stored one |
| `rename_tag(old, new)` / `delete_tag(tag)` | Global tag operations |
| `get_settings` | The font size and the tag colors |
| `set_font_size(size)` | Persist the font size and apply it to the native UI |
| `set_tag_color(tag, color)` | Persist the color of a single tag |
| `export_opml` / `import_opml(xml)` | OPML import/export |
| `read_file(path)` / `write_file(path, contents)` | File helpers for OPML dialogs |
| `fuzzy_filter(query, texts)` | Rust-side fuzzy matching |

Async commands (`discover_feeds`, `update_feed`, `update_feeds`) run on Tauri's
async runtime.

### Frontend state

`crates/feeds-app/ui/src/App.svelte` is a single Svelte component holding the UI
state:

| State | Purpose |
|-------|---------|
| `nodes` | Feeds + entries from `get_tree` |
| `expanded` | Set of expanded feed URLs |
| `selected` | Currently selected feed/entry |
| `filterText` / `hidden` | Search query and its fuzzy result set |
| `tagFilter` | `""`, `"__untagged__"`, or a tag name |
| `tagKeys` | All tag names, used by the tag filter and dialogs |
| `showSearch` / `showTagFilter` | Visibility of the search bar and the tag filter |
| `settings` | Font size and tag colors |
| `previewColors` | Deterministic colors for tags without a stored color |
| `busy` / `status` | Operation state and status-bar text |
| `contextMenu` | Open context menu and its target |
| dialog state (`addDialog`, `addChoices`, `renameDialog`, `pruneDialog`, `tagDialog`, `manageDialog`, `colorDialog`, `aboutDialog`) | Open modal and its inputs |
| `version` | App version, shown in the About dialog |

The feed visibility rule is implemented by `Store::get_visible_feeds`, as
opposed to `Store::get_feeds` which includes unfetched feeds. A feed is visible
when its `title` or `user_title` is non-empty, or when it has at least one
entry.

`FeedNode` carries `feed`, `unread`, `tags`, `entries` and `newest_date` — the
publication date of the feed's newest entry, or `null` when no entry carries a
date. The feed row renders `newest_date`; the feed's own `last_updated` (the
last successful fetch) is not shown.

### Keyboard shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+N` | Add Feed |
| `Ctrl+R` | Update Feeds |
| `Ctrl+F` | Toggle the search bar |
| `Ctrl+T` | Toggle the tag filter |
| `Ctrl++` (or `Ctrl+=`) / `Ctrl+-` / `Ctrl+0` | Zoom in / out / reset |
| `Enter` | Open the selected entry |
| `Escape` | Clear the search bar / close menus and dialogs |

### Single instance

`tauri-plugin-single-instance` ensures one process. A second launch forwards to
the first, which unminimises, shows and focuses its window.

### Source layout

- `crates/feeds-app/src/lib.rs` — Tauri setup, plugins, command registration
- `crates/feeds-app/src/commands.rs` — Tauri commands
- `crates/feeds-app/src/menu.rs` — native menu
- `crates/feeds-app/src/native.rs` — GTK font-size application
- `crates/feeds-app/src/state.rs` — shared `AppState`
- `crates/feeds-app/ui/src/App.svelte` — frontend

# feeds: RSS/Atom/JSON Feed indexer (Rust + Tauri)

## Rules for agents
- Linting and formatting must be checked and fixed after every code change.
- When planning, always check if documentation (README.md, AGENTS.md, specs/) needs updates and plan accordingly.
- Keep `feeds-core` free of any Tauri/GUI dependency; all behaviour belongs there.

## Commands for agents
- `just format`: `cargo fmt --all`
- `just lint`: build the frontend, then `cargo clippy --workspace --all-targets -- -D warnings`
- `just test`: build the frontend, then `cargo test --workspace`

Agents may not use any other just commands.
The frontend recipes (`just ui-install` / `just ui-build`) always use
`corepack pnpm`; `npm` is not supported.

## Conventions
- Rust 2021 edition, stable toolchain.
- `feeds-core` is GUI-agnostic; `feeds-app` is the Tauri shell.
- Logging uses `tracing`: `tracing::info!` for user actions, DB writes and
  state changes, and `tracing::warn!` for recoverable errors. Most core modules
  log; several modules, notably the Tauri command layer, currently have no
  tracing calls of their own and rely on `feeds-core`.
- Data models (`Feed`, `Entry`, `ParsedFeed`, …) are plain structs with
  `serde` derives where they cross the IPC boundary.
- Errors: a single `feeds_core::Error` enum built with `thiserror`; fallible
  commands return `Result<T, String>`, while infallible ones return plain values.
- Use `rusqlite` with `params![]` placeholders for values — never interpolate
  values into SQL. Dynamic `WHERE` and placeholder fragments are assembled only
  from fixed strings, as in `Store::query_feeds`.
- All persistent state lives in the SQLite database, settings included
  (`app_settings` for scalars, `tag_colors` for tag colors). `settings.json` is
  a legacy format the application does not read.
- The schema is created with `CREATE TABLE IF NOT EXISTS`, so new tables are
  added to an existing database on open. `Store::SCHEMA_VERSION` is written to
  the `user_version` pragma, but it gates no migration.
- The SQLite connection is wrapped in a `std::sync::Mutex`, which is **not
  reentrant**: never call a locking method on `Store` while already holding a
  guard/transaction.
- Timestamps: store RFC 3339 (`chrono::DateTime<Utc>`); parsing also accepts a
  space-separated ISO 8601 form via `datetime::parse`.
- Dates shown in the tree are **publication** dates (an entry's update date is
  only the fallback when a feed publishes none); they are rendered as
  `YYYY-MM-DD` in the user's local time zone. A feed row shows the date of its
  newest entry, never the feed's last-updated timestamp.
- Fuzzy title matching uses partial-ratio matching (threshold 80).
- Frontend: Svelte 4 + TypeScript; theme colors derive from the system palette
  via CSS variables (`Canvas`, `CanvasText`, `Highlight`, `HighlightText`) and
  `color-mix`. The modal backdrop and menu shadow use translucent black.

## Layout
- `crates/feeds-core/src/parse` — `feed-rs` adapter
- `crates/feeds-core/src/store` — SQLite storage
- `crates/feeds-core/src/update` — conditional GET, de-duplication, scheduling
- `crates/feeds-core/src/discovery` — platform handlers + HTML/Link/probing
- `crates/feeds-app/src/commands.rs` — Tauri commands
- `crates/feeds-app/ui/src/App.svelte` — frontend

## Development method
- All behaviour is specified in `specs/` as acceptance criteria
  (Given/When/Then scenarios); each spec also keeps non-normative
  implementation detail in a **Reference** section.
- RSS/Atom parsing, storage, updating and discovery are developed
  **test-first** (`cargo test`, `httpmock`); the specs define what those tests
  verify.
- UI behaviour is **spec-driven** directly from the scenarios in `specs/`.

## Releases
- Releases are cut on GitHub; `.github/workflows/release.yml` builds the Linux
  bundles (deb/rpm/AppImage, amd64 + aarch64) for every published release.
- The release tag must match the app version in all three places:
  `Cargo.toml` (`workspace.package.version`),
  `crates/feeds-app/tauri.conf.json` and `crates/feeds-app/ui/package.json`.
  The workflow verifies that all three agree with each other and with the tag
  (minus `v`) and fails on any mismatch.
- `.github/workflows/ci.yml` runs the `just format` / `just lint` / `just test`
  equivalents on every pull request and every push to `main`.

## Specs
- `README.md`: overview, build and run instructions
- `specs/README.md`: spec format and index
- `specs/gui.md`: Tauri/Svelte shell, commands, tree, dialogs, zoom, status bar, theme
- `specs/rss-atom.md`: parsing, storage, updating, read state, tags, OPML
- `specs/discovery.md`: feed discovery pipeline and platform handlers
- `specs/startup-update.md`: startup update behaviour and its schedule

# feeds

**feeds** is a lightweight desktop RSS/Atom/JSON Feed **indexer**, written in
Rust with a [Tauri v2](https://tauri.app) shell and a Svelte frontend.

It fetches feed metadata, catalogs entries, and tracks read/unread state,
but never renders the content; delegating it to the browser.

## Feed Discovery

When adding a feed it's often enough to just paste the domain of a blog or
publication without finding the specific RSS/Atom URL.
You want to add `https://lobste.rs/` feeds but don't know where the correct URL
is? No problem.
Or do you only want to add the feed of a tag like `https://lobste.rs/t/compilers`?
Just paste it.
**feeds** tries to discover RSS/Atom/JSON Feed URLs from arbitrary URLs and
gives you a choice on which discovered feeds to add.

There is also special logic for adding feeds from:

* YouTube
* Medium
* Reddit
* Substack

## Why an indexer?

An _indexer_ is different from a _reader_ in that it only shows you the entries
of a feed but doesn't display them. The displaying is left to the system's
browser. Since many blogs feature their own design and often some
JavaScript-powered features, it only makes sense to delegate the display of
posts to browsers and not handle that internally. This program is only about
keeping track of what feed entries you have seen or not.

## Quick start

### Requirements

* Rust (stable)
* [`just`](https://just.systems) — most build and development commands below
  are `just` recipes
* Node.js 18.12+ with corepack; the frontend is built with **pnpm 10** (pinned in
  `crates/feeds-app/ui/package.json`), so `npm` is not supported
* Linux only: `webkit2gtk-4.1`, `libsoup-3.0`, `gtk+-3.0` and OpenSSL
  (`libssl-dev`) development packages
* Linux only, for building the installers: `librsvg2-dev` and `patchelf`

### Build & run

```sh
just ui-install     # install frontend dependencies (first time only)
just run            # build and launch the app
```

Release build:

```sh
just build          # cargo build --release --workspace --features feeds-app/custom-protocol
```

Install the release binary into `~/.local/bin`:

```sh
just install
```

Tauri bundles (installers):

```sh
just bundle         # every bundle format (requires the `tauri` CLI)
just appimage       # portable Linux AppImage (installs the `tauri` CLI if missing)
```

## Data

* Database: `~/.feeds/feeds.db` (SQLite) — holds everything that is
  persistent, including the settings (font size, tag colors)
* Override the directory with `--data-dir` / `-d`.
* Other flags: `--verbose` / `-v` (debug logging) and `--version`.

## Development

```sh
just format   # cargo fmt --all
just lint     # build the frontend, then cargo clippy --workspace --all-targets -- -D warnings
just test     # build the frontend, then cargo test --workspace
```

Frontend:

```sh
just ui-install   # install dependencies
just ui-build     # production build into crates/feeds-app/ui/dist
cd crates/feeds-app/ui && corepack pnpm dev   # dev server on :1420
```

Third-party notices (regenerate `THIRD-PARTY-NOTICES`, which is attached to
every release):

```sh
just notices
```

Behaviour is specified in [`specs/`](specs/); parsing, storage, updating and
discovery are developed test-first.


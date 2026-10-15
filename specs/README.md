# Specifications

This directory is the single source of truth for how `feeds` behaves.

## Spec format

Every spec uses the same three sections:

1. **Context** — a short description of the capability and where it lives.
2. **Behaviour** — normative acceptance criteria written as
   `Scenario: …` blocks with **Given / When / Then** steps. This is the part
   used to judge whether an implementation is correct.
3. **Reference** — non-normative implementation detail: data models, schemas,
   command tables, module paths and support matrices. Reference material may
   be superseded by the code and is kept here for orientation, not as an
   independent contract.

Rust parsing, storage, updating and discovery are developed **test-first**.
Their specs are acceptance criteria; `cargo test` is the verification. UI
behaviour is driven directly from the scenarios in these specs.

## Index

| Spec | Covers |
|------|--------|
| [`rss-atom.md`](rss-atom.md) | Feed parsing, data models, SQLite storage, updating, read state, tags, OPML |
| [`discovery.md`](discovery.md) | Feed discovery pipeline and platform handlers |
| [`gui.md`](gui.md) | Tauri/Svelte shell, commands, tree, dialogs, zoom, status bar, theme |
| [`startup-update.md`](startup-update.md) | Startup update behaviour and its schedule |

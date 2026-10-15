//! `feeds-core`: storage, parsing, discovery and update logic for feeds.
//!
//! This crate is GUI-agnostic; the Tauri shell in `feeds-app` depends on it.

pub mod api;
pub mod datetime;
pub mod discovery;
pub mod error;
pub mod fuzzy;
pub mod http;
pub mod models;
pub mod opml;
pub mod parse;
pub mod settings;
pub mod store;
pub mod tags;
pub mod update;

pub use api::{default_data_dir, Feeds};
pub use error::{Error, Result};
pub use models::{newest_entry_date, DiscoveredFeed, Entry, Feed, ParsedEntry, ParsedFeed};
pub use settings::Settings;
pub use store::{Store, TagFilter, UpdateOutcome};
pub use tags::TagColors;

/// Application version, taken from `Cargo.toml`.
pub const APP_VERSION: &str = env!("CARGO_PKG_VERSION");

/// HTTP user agent, e.g. `feeds/v0.2.0`.
pub const USER_AGENT: &str = concat!("feeds/v", env!("CARGO_PKG_VERSION"));

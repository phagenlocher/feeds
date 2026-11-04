//! High-level facade tying storage, discovery and updates together.
//!
//! This is the main entry point used by the Tauri commands.

use std::path::{Path, PathBuf};

use reqwest::Client;

use crate::discovery;
use crate::error::Result;
use crate::http;
use crate::models::{DiscoveredFeed, Entry, Feed, FeedNode};
use crate::settings::{self, Settings};
use crate::store::{Store, TagFilter, UpdateOutcome};
use crate::{opml, tags, update, USER_AGENT};

/// The default data directory (`~/.feeds`).
pub fn default_data_dir() -> PathBuf {
    directories::BaseDirs::new()
        .map(|dirs| dirs.home_dir().join(".feeds"))
        .unwrap_or_else(|| PathBuf::from(".feeds"))
}

/// Name of the Rust database file.
pub const DB_FILENAME: &str = "feeds.db";

/// Application facade over the feeds database and network client.
pub struct Feeds {
    store: Store,
    client: Client,
    data_dir: PathBuf,
}

impl Feeds {
    /// Open the feeds database in `data_dir` (defaulting to `~/.feeds`).
    pub fn open(data_dir: Option<PathBuf>) -> Result<Self> {
        let data_dir = data_dir.unwrap_or_else(default_data_dir);
        let db_path = data_dir.join(DB_FILENAME);
        let store = Store::open(&db_path)?;
        let client = http::build_client(USER_AGENT);
        Ok(Self {
            store,
            client,
            data_dir,
        })
    }

    /// The resolved data directory.
    pub fn data_dir(&self) -> &Path {
        &self.data_dir
    }

    /// Path to the SQLite database.
    pub fn db_path(&self) -> PathBuf {
        self.data_dir.join(DB_FILENAME)
    }

    /// Access the underlying store.
    pub fn store(&self) -> &Store {
        &self.store
    }

    /// Access the shared HTTP client.
    pub fn client(&self) -> &Client {
        &self.client
    }

    // ── Subscriptions ──────────────────────────────────────────────────

    /// Whether any feed is subscribed.
    pub fn has_feeds(&self) -> Result<bool> {
        self.store.has_feeds()
    }

    /// Number of subscribed feeds.
    pub fn feed_count(&self) -> Result<i64> {
        self.store.feed_count()
    }

    /// Subscribe to a feed URL (idempotent).
    pub fn add_feed(&self, url: &str) -> Result<()> {
        self.store.add_feed(url, true)
    }

    /// Remove a feed and its entries.
    pub fn delete_feed(&self, url: &str) -> Result<()> {
        self.store.delete_feed(url)
    }

    /// List feeds, optionally filtered by tag.
    pub fn get_feeds(&self, filter: TagFilter) -> Result<Vec<Feed>> {
        self.store.get_feeds(filter)
    }

    /// List feeds to show in the tree (excludes feeds that never fetched
    /// successfully).
    pub fn get_visible_feeds(&self, filter: TagFilter) -> Result<Vec<Feed>> {
        self.store.get_visible_feeds(filter)
    }

    /// List visible feeds with their entries, unread counts, tags and newest
    /// entry dates, ready for the tree.
    pub fn get_feed_nodes(&self, filter: TagFilter) -> Result<Vec<FeedNode>> {
        self.store.get_feed_nodes(filter)
    }

    /// Get a single feed.
    pub fn get_feed(&self, url: &str) -> Result<Option<Feed>> {
        self.store.get_feed(url)
    }

    /// Set a custom display title for a feed.
    pub fn set_feed_user_title(&self, url: &str, title: &str) -> Result<()> {
        self.store.set_feed_user_title(url, title)
    }

    // ── Entries ────────────────────────────────────────────────────────

    /// List entries of a feed, newest first.
    pub fn get_entries(&self, feed: &str) -> Result<Vec<Entry>> {
        self.store.get_entries(feed)
    }

    /// Unread entry count for a feed.
    pub fn unread_count(&self, feed: &str) -> Result<i64> {
        self.store.unread_count(feed)
    }

    /// Mark an entry read or unread.
    pub fn set_entry_read(&self, feed: &str, entry_id: &str, read: bool) -> Result<()> {
        self.store.set_entry_read(feed, entry_id, read)
    }

    /// Mark all entries in a feed as read.
    pub fn mark_all_as_read(&self, feed: &str) -> Result<usize> {
        self.store.mark_all_as_read(feed)
    }

    /// Keep only the `n` most recent entries of a feed.
    pub fn prune_feed(&self, feed: &str, n: i64) -> Result<usize> {
        self.store.prune_feed(feed, n)
    }

    // ── Tags ───────────────────────────────────────────────────────────

    /// Tag names of a feed.
    pub fn get_tags(&self, feed: &str) -> Result<Vec<String>> {
        self.store.get_tags(feed)
    }

    /// Tag names of a feed.
    pub fn get_feed_tags(&self, feed: &str) -> Result<Vec<String>> {
        self.get_tags(feed)
    }

    /// All tag names across all feeds.
    pub fn get_all_tag_keys(&self) -> Result<Vec<String>> {
        self.store.tag_keys()
    }

    /// Add a tag to a feed.
    pub fn set_feed_tag(&self, feed: &str, tag: &str) -> Result<()> {
        self.store.set_tag(feed, tag)
    }

    /// Remove a tag from a feed.
    pub fn remove_feed_tag(&self, feed: &str, tag: &str) -> Result<()> {
        self.store.delete_tag(feed, tag)
    }

    /// Rename a tag across all feeds, carrying its color across.
    ///
    /// The color assigned to `old` (if any) is moved to `new`. When `old`
    /// had no color, `new` keeps its own color or gets a deterministic
    /// default.
    pub fn rename_tag(&self, old: &str, new: &str) -> Result<()> {
        self.store.rename_tag(old, new)?;
        match self.store.get_tag_color(old)? {
            Some(color) => {
                self.store.set_tag_color(new, &color)?;
                self.store.delete_tag_color(old)?;
                tracing::info!("carried tag color from '{old}' to '{new}'");
            }
            None => {
                if self.store.get_tag_color(new)?.is_none() {
                    self.store
                        .set_tag_color(new, &tags::default_color_for_tag(new))?;
                    tracing::info!("assigned a default color to '{new}'");
                }
            }
        }
        Ok(())
    }

    /// Delete a tag from all feeds, dropping its color.
    pub fn delete_tag(&self, tag: &str) -> Result<()> {
        self.store.delete_tag_globally(tag)?;
        self.store.delete_tag_color(tag)
    }

    /// Ensure every known tag has a color assigned.
    ///
    /// Returns `true` when at least one color was added.
    pub fn ensure_tag_colors(&self) -> Result<bool> {
        let keys = self.get_all_tag_keys()?;
        let mut changed = false;
        for key in &keys {
            if self.store.get_tag_color(key)?.is_none() {
                self.store
                    .set_tag_color(key, &tags::default_color_for_tag(key))?;
                changed = true;
            }
        }
        if changed {
            tracing::info!("assigned default colors to {} tag(s)", keys.len());
        }
        Ok(changed)
    }

    // ── Settings ───────────────────────────────────────────────────────

    /// The application settings, read from the database.
    ///
    /// Any known tag without a color is assigned a deterministic one first,
    /// so the result always carries a color for every tag in use.
    pub fn get_settings(&self) -> Result<Settings> {
        self.ensure_tag_colors()?;
        let font_size = match self.store.get_setting(settings::SETTING_FONT_SIZE)? {
            Some(raw) => raw.parse::<i32>().unwrap_or(settings::DEFAULT_FONT_SIZE),
            None => settings::DEFAULT_FONT_SIZE,
        };
        let settings = Settings::new(font_size, self.store.all_tag_colors()?);
        Ok(settings.normalized())
    }

    /// Persist the application font size.
    ///
    /// Returns the stored value, which is clamped to a usable size.
    pub fn set_font_size(&self, size: i32) -> Result<i32> {
        let size = if size < settings::MIN_FONT_SIZE {
            settings::DEFAULT_FONT_SIZE
        } else {
            size
        };
        self.store
            .set_setting(settings::SETTING_FONT_SIZE, &size.to_string())?;
        Ok(size)
    }

    /// Persist the color of a single tag.
    pub fn set_tag_color(&self, tag: &str, color: &str) -> Result<()> {
        self.store.set_tag_color(tag, color)
    }

    // ── Discovery & updates ────────────────────────────────────────────

    /// Discover feed URLs from a page or platform URL.
    pub async fn discover_feeds(&self, url: &str) -> Result<Vec<DiscoveredFeed>> {
        discovery::discover_feeds(&self.client, url).await
    }

    /// Fetch and store a single feed.
    pub async fn update_feed(&self, url: &str) -> Result<UpdateOutcome> {
        update::update_feed(&self.store, &self.client, url).await
    }

    /// Update all feeds, optionally honouring the 60-minute schedule.
    pub async fn update_feeds(&self, scheduled: bool) -> Result<update::UpdateReport> {
        update::update_feeds(&self.store, &self.client, scheduled).await
    }

    // ── OPML ───────────────────────────────────────────────────────────

    /// Export all feeds as an OPML document.
    pub fn export_opml(&self) -> Result<String> {
        let feeds = self.get_feeds(TagFilter::All)?;
        opml::export_feeds(&feeds)
    }

    /// Import feeds from an OPML document; returns the number added.
    pub fn import_opml(&self, xml: &str) -> Result<usize> {
        let feeds = opml::import_feeds(xml)?;
        let mut count = 0;
        for (url, _title) in feeds {
            self.add_feed(&url)?;
            count += 1;
        }
        Ok(count)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const FEED: &str = "https://example.com/feed";

    fn feeds() -> (tempfile::TempDir, Feeds) {
        let dir = tempfile::tempdir().unwrap();
        let feeds = Feeds::open(Some(dir.path().to_path_buf())).unwrap();
        (dir, feeds)
    }

    #[test]
    fn ensure_tag_colors_assigns_and_persists() {
        let (_dir, feeds) = feeds();
        feeds.add_feed(FEED).unwrap();
        feeds.set_feed_tag(FEED, "rust").unwrap();
        feeds.set_feed_tag(FEED, "news").unwrap();

        assert!(feeds.ensure_tag_colors().unwrap());
        let settings = feeds.get_settings().unwrap();
        let rust = settings.tag_colors.get("rust").cloned().unwrap();
        let news = settings.tag_colors.get("news").cloned().unwrap();
        assert_ne!(rust, news);

        // Persisted in the database.
        assert_eq!(feeds.store().get_tag_color("rust").unwrap(), Some(rust));
        assert_eq!(feeds.store().get_tag_color("news").unwrap(), Some(news));

        // Idempotent: nothing changes on a second pass.
        assert!(!feeds.ensure_tag_colors().unwrap());
    }

    #[test]
    fn ensure_tag_colors_only_adds_new_tags() {
        let (_dir, feeds) = feeds();
        feeds.add_feed(FEED).unwrap();
        feeds.set_feed_tag(FEED, "rust").unwrap();

        feeds.ensure_tag_colors().unwrap();
        let rust = feeds.store().get_tag_color("rust").unwrap().unwrap();

        feeds.set_feed_tag(FEED, "news").unwrap();
        assert!(feeds.ensure_tag_colors().unwrap());
        assert_eq!(feeds.store().get_tag_color("rust").unwrap(), Some(rust));
        assert!(feeds.store().get_tag_color("news").unwrap().is_some());
    }

    #[test]
    fn rename_tag_carries_color_over() {
        let (_dir, feeds) = feeds();
        feeds.add_feed(FEED).unwrap();
        feeds.set_feed_tag(FEED, "news").unwrap();

        feeds.ensure_tag_colors().unwrap();
        let news = feeds.store().get_tag_color("news").unwrap().unwrap();

        feeds.rename_tag("news", "tech").unwrap();
        assert_eq!(feeds.get_all_tag_keys().unwrap(), vec!["tech".to_string()]);
        assert!(feeds.store().get_tag_color("news").unwrap().is_none());
        assert_eq!(feeds.store().get_tag_color("tech").unwrap(), Some(news));
    }

    #[test]
    fn rename_tag_assigns_default_when_old_has_no_color() {
        let (_dir, feeds) = feeds();
        feeds.add_feed(FEED).unwrap();
        feeds.set_feed_tag(FEED, "news").unwrap();

        feeds.rename_tag("news", "tech").unwrap();
        assert_eq!(
            feeds.store().get_tag_color("tech").unwrap(),
            Some(tags::default_color_for_tag("tech"))
        );
        assert_eq!(feeds.get_all_tag_keys().unwrap(), vec!["tech".to_string()]);
    }

    #[test]
    fn delete_tag_drops_the_color() {
        let (_dir, feeds) = feeds();
        feeds.add_feed(FEED).unwrap();
        feeds.set_feed_tag(FEED, "news").unwrap();
        feeds.ensure_tag_colors().unwrap();
        assert!(feeds.store().get_tag_color("news").unwrap().is_some());

        feeds.delete_tag("news").unwrap();
        assert!(feeds.get_all_tag_keys().unwrap().is_empty());
        assert!(feeds.store().get_tag_color("news").unwrap().is_none());
    }

    #[test]
    fn settings_default_to_the_default_font_size() {
        let (_dir, feeds) = feeds();
        let settings = feeds.get_settings().unwrap();
        assert_eq!(settings.font_size, settings::DEFAULT_FONT_SIZE);
        assert!(settings.tag_colors.is_empty());
    }

    #[test]
    fn the_font_size_is_stored_in_the_database() {
        let (_dir, feeds) = feeds();
        assert_eq!(feeds.set_font_size(21).unwrap(), 21);
        assert_eq!(feeds.get_settings().unwrap().font_size, 21);
        assert_eq!(
            feeds
                .store()
                .get_setting(settings::SETTING_FONT_SIZE)
                .unwrap(),
            Some("21".to_string())
        );
    }

    #[test]
    fn a_too_small_font_size_falls_back_to_the_default() {
        let (_dir, feeds) = feeds();
        assert_eq!(
            feeds.set_font_size(settings::MIN_FONT_SIZE - 1).unwrap(),
            settings::DEFAULT_FONT_SIZE
        );
        assert_eq!(
            feeds.get_settings().unwrap().font_size,
            settings::DEFAULT_FONT_SIZE
        );
    }

    #[test]
    fn a_tag_color_is_stored_in_the_database() {
        let (_dir, feeds) = feeds();
        feeds.set_tag_color("rust", "#ff0000").unwrap();
        let settings = feeds.get_settings().unwrap();
        assert_eq!(
            settings.tag_colors.get("rust").map(String::as_str),
            Some("#ff0000")
        );
    }
}

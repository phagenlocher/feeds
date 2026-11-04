//! Tauri commands exposed to the frontend.

use chrono::{DateTime, Utc};
use feeds_core::{newest_entry_date, DiscoveredFeed, Entry, Feed, Settings, TagFilter};
use serde::Serialize;
use tauri::State;

use crate::state::AppState;

fn err<E: std::fmt::Display>(e: E) -> String {
    e.to_string()
}

/// A feed together with its entries and UI metadata.
#[derive(Debug, Clone, Serialize)]
pub struct FeedNode {
    /// The feed itself.
    pub feed: Feed,
    /// Unread entry count.
    pub unread: i64,
    /// Tag names attached to the feed.
    pub tags: Vec<String>,
    /// Entries, newest first.
    pub entries: Vec<Entry>,
    /// Publication date of the newest entry, shown in the tree.
    pub newest_date: Option<DateTime<Utc>>,
}

/// Return the whole tree (feeds + entries), optionally tag-filtered.
#[tauri::command]
pub fn get_tree(
    state: State<'_, AppState>,
    filter: Option<String>,
) -> Result<Vec<FeedNode>, String> {
    let filter = match filter.as_deref() {
        None | Some("") => TagFilter::All,
        Some("__untagged__") => TagFilter::Untagged,
        Some(tag) => TagFilter::Tags(vec![tag.to_string()]),
    };
    let feeds = state.feeds.get_visible_feeds(filter).map_err(err)?;
    let mut nodes = Vec::with_capacity(feeds.len());
    for feed in feeds {
        let unread = state.feeds.unread_count(&feed.id).map_err(err)?;
        let tags = state.feeds.get_feed_tags(&feed.id).map_err(err)?;
        let entries = state.feeds.get_entries(&feed.id).map_err(err)?;
        nodes.push(FeedNode {
            newest_date: newest_entry_date(&entries),
            feed,
            unread,
            tags,
            entries,
        });
    }
    Ok(nodes)
}

/// Whether the store contains any feeds.
#[tauri::command]
pub fn has_feeds(state: State<'_, AppState>) -> Result<bool, String> {
    state.feeds.has_feeds().map_err(err)
}

/// Application version string.
#[tauri::command]
pub fn app_version() -> String {
    feeds_core::APP_VERSION.to_string()
}

/// Subscribe to a feed URL.
#[tauri::command]
pub fn add_feed(state: State<'_, AppState>, url: String) -> Result<(), String> {
    state.feeds.add_feed(&url).map_err(err)
}

/// Remove a feed.
#[tauri::command]
pub fn delete_feed(state: State<'_, AppState>, url: String) -> Result<(), String> {
    state.feeds.delete_feed(&url).map_err(err)
}

/// Rename a feed's display title.
#[tauri::command]
pub fn rename_feed(state: State<'_, AppState>, url: String, title: String) -> Result<(), String> {
    state.feeds.set_feed_user_title(&url, &title).map_err(err)
}

/// Mark a single entry read or unread.
#[tauri::command]
pub fn set_entry_read(
    state: State<'_, AppState>,
    feed: String,
    entry_id: String,
    read: bool,
) -> Result<(), String> {
    state
        .feeds
        .set_entry_read(&feed, &entry_id, read)
        .map_err(err)
}

/// Mark every entry in a feed as read.
#[tauri::command]
pub fn mark_all_as_read(state: State<'_, AppState>, feed: String) -> Result<usize, String> {
    state.feeds.mark_all_as_read(&feed).map_err(err)
}

/// Keep only the `n` most recent entries of a feed.
#[tauri::command]
pub fn prune_feed(state: State<'_, AppState>, feed: String, n: i64) -> Result<usize, String> {
    state.feeds.prune_feed(&feed, n).map_err(err)
}

/// Discover feed URLs from a page or platform URL.
#[tauri::command]
pub async fn discover_feeds(
    state: State<'_, AppState>,
    url: String,
) -> Result<Vec<DiscoveredFeed>, String> {
    state.feeds.discover_feeds(&url).await.map_err(err)
}

/// Fetch and store a single feed.
#[tauri::command]
pub async fn update_feed(state: State<'_, AppState>, url: String) -> Result<(), String> {
    state.feeds.update_feed(&url).await.map_err(err)?;
    Ok(())
}

/// Update all feeds (optionally honouring the schedule).
#[tauri::command]
pub async fn update_feeds(
    state: State<'_, AppState>,
    scheduled: Option<bool>,
) -> Result<feeds_core::update::UpdateReport, String> {
    let previous = state.set_busy(true);
    let result = state.feeds.update_feeds(scheduled.unwrap_or(false)).await;
    state.set_busy(previous);
    result.map_err(err)
}

/// All tag names across all feeds.
#[tauri::command]
pub fn get_tag_keys(state: State<'_, AppState>) -> Result<Vec<String>, String> {
    state.feeds.get_all_tag_keys().map_err(err)
}

/// Deterministic default colors for tags, so the UI can preview tags that do
/// not have a stored color yet.
#[tauri::command]
pub fn default_tag_colors(tags: Vec<String>) -> std::collections::HashMap<String, String> {
    tags.into_iter()
        .map(|tag| {
            let color = feeds_core::tags::default_color_for_tag(&tag);
            (tag, color)
        })
        .collect()
}

/// Tags of a single feed.
#[tauri::command]
pub fn get_feed_tags(state: State<'_, AppState>, feed: String) -> Result<Vec<String>, String> {
    state.feeds.get_feed_tags(&feed).map_err(err)
}

/// Replace the tag set of a feed.
#[tauri::command]
pub fn set_feed_tags(
    state: State<'_, AppState>,
    feed: String,
    tags: Vec<String>,
) -> Result<(), String> {
    let current = state.feeds.get_feed_tags(&feed).map_err(err)?;
    for tag in tags.iter().filter(|t| !current.contains(t)) {
        state.feeds.set_feed_tag(&feed, tag).map_err(err)?;
    }
    for tag in current.iter().filter(|t| !tags.contains(t)) {
        state.feeds.remove_feed_tag(&feed, tag).map_err(err)?;
    }
    state.feeds.ensure_tag_colors().map_err(err)?;
    Ok(())
}

/// Rename a tag across all feeds, carrying its color across.
#[tauri::command]
pub fn rename_tag(state: State<'_, AppState>, old: String, new: String) -> Result<(), String> {
    state.feeds.rename_tag(&old, &new).map_err(err)
}

/// Delete a tag from all feeds.
#[tauri::command]
pub fn delete_tag(state: State<'_, AppState>, tag: String) -> Result<(), String> {
    state.feeds.delete_tag(&tag).map_err(err)
}

/// Current settings, auto-assigning colors to any tag missing one.
#[tauri::command]
pub fn get_settings(state: State<'_, AppState>) -> Result<Settings, String> {
    state.feeds.get_settings().map_err(err)
}

/// Persist the application font size.
#[tauri::command]
pub fn set_font_size(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
    size: i32,
) -> Result<i32, String> {
    let size = state.feeds.set_font_size(size).map_err(err)?;
    let _ = app.run_on_main_thread(move || crate::native::apply_font_size(size));
    Ok(size)
}

/// Persist the color of a single tag.
#[tauri::command]
pub fn set_tag_color(state: State<'_, AppState>, tag: String, color: String) -> Result<(), String> {
    state.feeds.set_tag_color(&tag, &color).map_err(err)
}

/// Export all feeds as an OPML document.
#[tauri::command]
pub fn export_opml(state: State<'_, AppState>) -> Result<String, String> {
    state.feeds.export_opml().map_err(err)
}

/// Import feeds from an OPML document; returns the number added.
#[tauri::command]
pub fn import_opml(state: State<'_, AppState>, xml: String) -> Result<usize, String> {
    state.feeds.import_opml(&xml).map_err(err)
}

/// Read a UTF-8 text file.
#[tauri::command]
pub fn read_file(path: String) -> Result<String, String> {
    std::fs::read_to_string(&path).map_err(err)
}

/// Write a UTF-8 text file.
#[tauri::command]
pub fn write_file(path: String, contents: String) -> Result<(), String> {
    std::fs::write(&path, contents).map_err(err)
}

/// Fuzzy-match a query against a list of texts.
#[tauri::command]
pub fn fuzzy_filter(query: String, texts: Vec<String>) -> Vec<bool> {
    if query.is_empty() {
        return vec![true; texts.len()];
    }
    texts
        .into_iter()
        .map(|text| feeds_core::fuzzy::matches(&query, &text))
        .collect()
}

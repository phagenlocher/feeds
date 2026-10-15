//! Data models shared across parsing, storage and the IPC boundary.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

/// A single RSS/Atom feed tracked in the local database.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Feed {
    /// The feed's URL (used as the unique identifier).
    pub id: String,
    /// Human-readable display title (user title if set, else original).
    pub title: String,
    /// Timestamp of the last successful fetch, or `None` if never fetched.
    ///
    /// This is not shown in the tree; the tree shows the publication date of
    /// the feed's newest entry instead.
    pub last_updated: Option<DateTime<Utc>>,
    /// Custom title set by the user, or `None`.
    pub user_title: Option<String>,
}

impl Feed {
    /// The title to display, falling back to a placeholder.
    pub fn display_title(&self) -> &str {
        if self.title.is_empty() {
            "No Title"
        } else {
            &self.title
        }
    }
}

/// A single entry (article/post) within a feed.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Entry {
    /// Permalink to the entry.
    pub url: String,
    /// Entry headline.
    pub title: String,
    /// Publication date of the entry.
    ///
    /// Falls back to the entry's update date when the feed does not publish
    /// one, and is `None` when the feed provides neither. This is the date
    /// shown in the GUI.
    pub date: Option<DateTime<Utc>>,
    /// Unique identifier within the feed.
    pub entry_id: String,
    /// The [`Feed::id`] this entry belongs to.
    pub feed_id: String,
    /// Whether the entry has been marked as read.
    pub read: bool,
    /// Author name(s) as a string, or empty if unknown.
    pub author: String,
}

/// The publication date of the newest entry in a list of entries.
///
/// The list must be ordered newest-first, as returned by
/// [`crate::store::Store::get_entries`]. Entries without a date are skipped,
/// so the result is the date of the newest entry that carries one, or `None`
/// when no entry has a date.
pub fn newest_entry_date(entries: &[Entry]) -> Option<DateTime<Utc>> {
    entries.iter().find_map(|e| e.date)
}

/// A discovered feed candidate: `(url, title)`.
pub type DiscoveredFeed = (String, String);

/// A parsed feed ready to be stored.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ParsedFeed {
    /// Feed title, if present.
    pub title: Option<String>,
    /// Feed link (site URL), if present.
    pub link: Option<String>,
    /// Feed-level updated timestamp, if present.
    pub updated: Option<DateTime<Utc>>,
    /// Feed-level author, if present.
    pub author: Option<String>,
    /// Detected format/version string (e.g. `rss20`, `atom10`).
    pub version: String,
    /// Entries contained in the feed.
    pub entries: Vec<ParsedEntry>,
}

/// A parsed entry ready to be stored.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ParsedEntry {
    /// Unique identifier within the feed.
    pub id: String,
    /// Entry title, if present.
    pub title: Option<String>,
    /// Entry permalink, if present.
    pub link: Option<String>,
    /// Entry updated timestamp, if present.
    pub updated: Option<DateTime<Utc>>,
    /// Entry published timestamp, if present.
    pub published: Option<DateTime<Utc>>,
    /// Joined author names, if present.
    pub author: Option<String>,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::datetime;

    fn entry(id: &str, date: Option<&str>) -> Entry {
        Entry {
            url: format!("https://example.com/{id}"),
            title: id.into(),
            date: date.map(|d| datetime::parse(d).unwrap()),
            entry_id: id.into(),
            feed_id: "https://example.com/feed".into(),
            read: false,
            author: String::new(),
        }
    }

    #[test]
    fn newest_entry_date_of_an_empty_list_is_none() {
        assert_eq!(newest_entry_date(&[]), None);
    }

    #[test]
    fn newest_entry_date_is_the_first_entrys_date() {
        let entries = vec![
            entry("new", Some("2024-05-05T10:00:00Z")),
            entry("old", Some("2024-01-01T10:00:00Z")),
        ];
        assert_eq!(
            newest_entry_date(&entries),
            Some(datetime::parse("2024-05-05T10:00:00Z").unwrap())
        );
    }

    #[test]
    fn newest_entry_date_skips_entries_without_a_date() {
        let entries = vec![
            entry("undated", None),
            entry("dated", Some("2024-05-05T10:00:00Z")),
        ];
        assert_eq!(
            newest_entry_date(&entries),
            Some(datetime::parse("2024-05-05T10:00:00Z").unwrap())
        );
    }

    #[test]
    fn newest_entry_date_is_none_when_no_entry_is_dated() {
        let entries = vec![entry("a", None), entry("b", None)];
        assert_eq!(newest_entry_date(&entries), None);
    }
}

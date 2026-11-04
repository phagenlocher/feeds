//! SQLite storage for feeds, entries, read state and tags.

use std::collections::BTreeMap;
use std::path::Path;
use std::sync::{Mutex, MutexGuard};

use chrono::{DateTime, Utc};
use rusqlite::{params, Connection, OptionalExtension, Row};

use crate::datetime;
use crate::error::{Error, Result};
use crate::models::{newest_entry_date, Entry, Feed, FeedNode, ParsedFeed};

/// Current on-disk schema version.
pub const SCHEMA_VERSION: i64 = 1;

/// Default scheduled-update interval, in minutes.
pub const DEFAULT_UPDATE_INTERVAL_MINUTES: i64 = 60;

const DDL: &str = r#"
CREATE TABLE IF NOT EXISTS feeds (
    url             TEXT PRIMARY KEY NOT NULL,
    title           TEXT,
    link            TEXT,
    updated         TEXT,
    user_title      TEXT,
    caching_info    TEXT,
    update_after    TEXT,
    last_retrieved  TEXT,
    last_updated    TEXT,
    added           TEXT NOT NULL,
    last_exception  TEXT,
    stale           INTEGER NOT NULL DEFAULT 0,
    updates_enabled INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS entries (
    id            TEXT NOT NULL,
    feed          TEXT NOT NULL REFERENCES feeds(url) ON DELETE CASCADE,
    title         TEXT,
    link          TEXT,
    updated       TEXT,
    published     TEXT,
    author        TEXT,
    read          INTEGER NOT NULL DEFAULT 0,
    read_modified TEXT,
    added         TEXT NOT NULL,
    recent_sort   TEXT NOT NULL,
    PRIMARY KEY (id, feed)
);

CREATE INDEX IF NOT EXISTS entries_by_recent ON entries (recent_sort DESC, feed, id);
CREATE INDEX IF NOT EXISTS entries_by_feed   ON entries (feed);

CREATE TABLE IF NOT EXISTS feed_tags (
    feed  TEXT NOT NULL REFERENCES feeds(url) ON DELETE CASCADE,
    key   TEXT NOT NULL,
    PRIMARY KEY (feed, key)
);

CREATE TABLE IF NOT EXISTS app_settings (
    key   TEXT PRIMARY KEY NOT NULL,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tag_colors (
    tag   TEXT PRIMARY KEY NOT NULL,
    color TEXT NOT NULL
);
"#;

/// Filter for [`Store::get_feeds`].
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum TagFilter {
    /// All feeds (no tag filtering).
    All,
    /// Feeds that have no tags at all.
    Untagged,
    /// Feeds that have any of the given tags (OR semantics).
    Tags(Vec<String>),
}

/// State needed by the update engine for a single feed.
#[derive(Debug, Clone)]
pub struct FeedUpdateState {
    /// Feed URL.
    pub url: String,
    /// Stored caching info (ETag / Last-Modified) as raw JSON.
    pub caching_info: Option<String>,
    /// Whether updates are enabled.
    pub updates_enabled: bool,
    /// Whether the feed is marked stale.
    pub stale: bool,
    /// When the feed becomes eligible for a scheduled update.
    pub update_after: Option<DateTime<Utc>>,
}

/// A handle to the feeds database.
pub struct Store {
    conn: Mutex<Connection>,
}

impl Store {
    /// Open (creating if needed) a store at `path`.
    pub fn open(path: impl AsRef<Path>) -> Result<Self> {
        let path = path.as_ref();
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)
                .map_err(|e| Error::DataDir(format!("{}: {e}", parent.display())))?;
        }
        let conn = Connection::open(path)?;
        Self::from_connection(conn)
    }

    /// Open an in-memory store (used by tests).
    pub fn open_in_memory() -> Result<Self> {
        Self::from_connection(Connection::open_in_memory()?)
    }

    fn from_connection(conn: Connection) -> Result<Self> {
        conn.pragma_update(None, "foreign_keys", "ON")?;
        conn.execute_batch(DDL)?;
        conn.pragma_update(None, "user_version", SCHEMA_VERSION)?;
        tracing::info!("opened feeds database (schema v{SCHEMA_VERSION})");
        Ok(Self {
            conn: Mutex::new(conn),
        })
    }

    fn lock(&self) -> MutexGuard<'_, Connection> {
        self.conn.lock().unwrap_or_else(|e| e.into_inner())
    }

    // ── Feeds ──────────────────────────────────────────────────────────

    /// Subscribe to a feed URL. If `exist_ok` is true, an existing feed is
    /// left untouched; otherwise a duplicate is reported as an error.
    pub fn add_feed(&self, url: &str, exist_ok: bool) -> Result<()> {
        tracing::info!("subscribing to feed {url}");
        let now = datetime::format(&datetime::now());
        let conn = self.lock();
        let changed = conn.execute(
            "INSERT INTO feeds (url, added) VALUES (?1, ?2)
             ON CONFLICT(url) DO NOTHING",
            params![url, now],
        )?;
        if changed == 0 && !exist_ok {
            return Err(Error::Database(rusqlite::Error::QueryReturnedNoRows));
        }
        Ok(())
    }

    /// Remove a feed and all its entries/tags (cascade).
    pub fn delete_feed(&self, url: &str) -> Result<()> {
        tracing::info!("unsubscribing feed {url}");
        self.lock()
            .execute("DELETE FROM feeds WHERE url = ?1", params![url])?;
        Ok(())
    }

    /// Whether a feed exists.
    pub fn feed_exists(&self, url: &str) -> Result<bool> {
        let count: i64 = self.lock().query_row(
            "SELECT COUNT(*) FROM feeds WHERE url = ?1",
            params![url],
            |r| r.get(0),
        )?;
        Ok(count > 0)
    }

    /// Total number of feeds.
    pub fn feed_count(&self) -> Result<i64> {
        let count: i64 = self
            .lock()
            .query_row("SELECT COUNT(*) FROM feeds", [], |r| r.get(0))?;
        Ok(count)
    }

    /// Whether the store contains at least one feed.
    pub fn has_feeds(&self) -> Result<bool> {
        Ok(self.feed_count()? > 0)
    }

    /// List feeds, optionally filtered by tags.
    ///
    /// Includes feeds that are hidden from the tree (see
    /// [`Store::get_visible_feeds`]); used for export.
    pub fn get_feeds(&self, filter: TagFilter) -> Result<Vec<Feed>> {
        self.query_feeds(filter, false)
    }

    /// List feeds to display in the tree.
    ///
    /// A feed is hidden until it has a title, a user title, or at least one
    /// entry, so a feed whose first update failed (e.g. imported while its
    /// server was down) does not show up as an empty row. The subscription is
    /// kept and the feed reappears once a later update gives it a title or an
    /// entry.
    pub fn get_visible_feeds(&self, filter: TagFilter) -> Result<Vec<Feed>> {
        self.query_feeds(filter, true)
    }

    /// List the visible feeds with the data the tree renders.
    ///
    /// Each node bundles the feed, its unread count, its tags, its entries
    /// (newest first) and the publication date of its newest entry. Hidden
    /// feeds (see [`Store::get_visible_feeds`]) are excluded.
    pub fn get_feed_nodes(&self, filter: TagFilter) -> Result<Vec<FeedNode>> {
        let feeds = self.get_visible_feeds(filter)?;
        let mut nodes = Vec::with_capacity(feeds.len());
        for feed in feeds {
            let unread = self.unread_count(&feed.id)?;
            let tags = self.get_tags(&feed.id)?;
            let entries = self.get_entries(&feed.id)?;
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

    fn query_feeds(&self, filter: TagFilter, visible_only: bool) -> Result<Vec<Feed>> {
        let conn = self.lock();

        let mut conditions: Vec<String> = Vec::new();
        let mut bound: Vec<String> = Vec::new();
        let mut distinct = "";
        let mut join = "";
        match &filter {
            TagFilter::All => {}
            TagFilter::Untagged => {
                conditions.push(
                    "NOT EXISTS (SELECT 1 FROM feed_tags t WHERE t.feed = f.url)".to_string(),
                );
            }
            TagFilter::Tags(tags) => {
                distinct = "DISTINCT ";
                join = " JOIN feed_tags t ON t.feed = f.url";
                let placeholders = vec!["?"; tags.len()].join(",");
                conditions.push(format!("t.key IN ({placeholders})"));
                bound = tags.clone();
            }
        }
        if visible_only {
            conditions.push(
                "((f.title IS NOT NULL AND TRIM(f.title) <> '') \
                 OR (f.user_title IS NOT NULL AND TRIM(f.user_title) <> '') \
                 OR EXISTS (SELECT 1 FROM entries e WHERE e.feed = f.url))"
                    .to_string(),
            );
        }

        let where_clause = if conditions.is_empty() {
            String::new()
        } else {
            format!(" WHERE {}", conditions.join(" AND "))
        };
        let sql = format!(
            "SELECT {distinct}f.url, f.title, f.user_title, f.last_updated \
             FROM feeds f{join}{where_clause} \
             ORDER BY COALESCE(f.user_title, f.title, f.url) COLLATE NOCASE"
        );

        let mut stmt = conn.prepare(&sql)?;
        let params_ref: Vec<&dyn rusqlite::ToSql> =
            bound.iter().map(|s| s as &dyn rusqlite::ToSql).collect();
        let rows = stmt.query_map(params_ref.as_slice(), row_to_feed)?;
        let feeds = rows.collect::<rusqlite::Result<Vec<_>>>()?;
        Ok(feeds)
    }

    /// Fetch a single feed by URL.
    pub fn get_feed(&self, url: &str) -> Result<Option<Feed>> {
        let conn = self.lock();
        let mut stmt =
            conn.prepare("SELECT url, title, user_title, last_updated FROM feeds WHERE url = ?1")?;
        let mut rows = stmt.query(params![url])?;
        match rows.next()? {
            Some(row) => Ok(Some(row_to_feed(row)?)),
            None => Ok(None),
        }
    }

    /// Set a custom user title for a feed.
    pub fn set_feed_user_title(&self, url: &str, title: &str) -> Result<()> {
        tracing::info!("setting user title for feed {url} to '{title}'");
        self.lock().execute(
            "UPDATE feeds SET user_title = ?2 WHERE url = ?1",
            params![url, title],
        )?;
        Ok(())
    }

    // ── Entries ────────────────────────────────────────────────────────

    /// List entries of a feed ordered by recency.
    pub fn get_entries(&self, feed: &str) -> Result<Vec<Entry>> {
        let conn = self.lock();
        let mut stmt = conn.prepare(
            "SELECT id, feed, title, link, updated, published, author, read
             FROM entries WHERE feed = ?1
             ORDER BY recent_sort DESC, id DESC",
        )?;
        let rows = stmt.query_map(params![feed], row_to_entry)?;
        let entries = rows.collect::<rusqlite::Result<Vec<_>>>()?;
        Ok(entries)
    }

    /// Number of entries in a feed.
    pub fn entry_count(&self, feed: &str) -> Result<i64> {
        let count: i64 = self.lock().query_row(
            "SELECT COUNT(*) FROM entries WHERE feed = ?1",
            params![feed],
            |r| r.get(0),
        )?;
        Ok(count)
    }

    /// Number of unread entries in a feed.
    pub fn unread_count(&self, feed: &str) -> Result<i64> {
        let count: i64 = self.lock().query_row(
            "SELECT COUNT(*) FROM entries WHERE feed = ?1 AND read = 0",
            params![feed],
            |r| r.get(0),
        )?;
        Ok(count)
    }

    /// Mark a single entry read or unread.
    pub fn set_entry_read(&self, feed: &str, entry_id: &str, read: bool) -> Result<()> {
        let now = datetime::format(&datetime::now());
        self.lock().execute(
            "UPDATE entries SET read = ?3, read_modified = ?4 WHERE feed = ?1 AND id = ?2",
            params![feed, entry_id, read as i64, now],
        )?;
        Ok(())
    }

    /// Mark every entry in a feed as read.
    pub fn mark_all_as_read(&self, feed: &str) -> Result<usize> {
        let now = datetime::format(&datetime::now());
        let changed = self.lock().execute(
            "UPDATE entries SET read = 1, read_modified = ?2 WHERE feed = ?1 AND read = 0",
            params![feed, now],
        )?;
        tracing::info!("marked {changed} entries read in feed {feed}");
        Ok(changed)
    }

    /// Keep only the `n` most recent entries; return how many were deleted.
    pub fn prune_feed(&self, feed: &str, n: i64) -> Result<usize> {
        let conn = self.lock();
        let total: i64 = conn.query_row(
            "SELECT COUNT(*) FROM entries WHERE feed = ?1",
            params![feed],
            |r| r.get(0),
        )?;
        if total <= n {
            return Ok(0);
        }
        let deleted = conn.execute(
            "DELETE FROM entries WHERE feed = ?1 AND id NOT IN (
                 SELECT id FROM entries WHERE feed = ?1
                 ORDER BY recent_sort DESC, id DESC LIMIT ?2
             )",
            params![feed, n],
        )?;
        tracing::info!("pruned {deleted} entries from feed {feed} (keeping {n})");
        Ok(deleted)
    }

    // ── Tags ───────────────────────────────────────────────────────────

    /// Return the tag names of a feed.
    pub fn get_tags(&self, feed: &str) -> Result<Vec<String>> {
        let conn = self.lock();
        let mut stmt = conn.prepare("SELECT key FROM feed_tags WHERE feed = ?1 ORDER BY key")?;
        let rows = stmt.query_map(params![feed], |r| r.get::<_, String>(0))?;
        Ok(rows.collect::<rusqlite::Result<Vec<_>>>()?)
    }

    /// Add a tag on a feed.
    pub fn set_tag(&self, feed: &str, key: &str) -> Result<()> {
        tracing::info!("setting tag '{key}' on feed {feed}");
        self.lock().execute(
            "INSERT INTO feed_tags (feed, key) VALUES (?1, ?2)
             ON CONFLICT(feed, key) DO NOTHING",
            params![feed, key],
        )?;
        Ok(())
    }

    /// Remove a tag from a feed.
    pub fn delete_tag(&self, feed: &str, key: &str) -> Result<()> {
        tracing::info!("removing tag '{key}' from feed {feed}");
        self.lock().execute(
            "DELETE FROM feed_tags WHERE feed = ?1 AND key = ?2",
            params![feed, key],
        )?;
        Ok(())
    }

    /// All distinct tag keys across all feeds, sorted.
    pub fn tag_keys(&self) -> Result<Vec<String>> {
        let conn = self.lock();
        let mut stmt = conn.prepare("SELECT DISTINCT key FROM feed_tags ORDER BY key")?;
        let rows = stmt.query_map([], |r| r.get::<_, String>(0))?;
        Ok(rows.collect::<rusqlite::Result<Vec<_>>>()?)
    }

    /// Rename a tag across all feeds.
    pub fn rename_tag(&self, old: &str, new: &str) -> Result<()> {
        tracing::info!("renaming tag '{old}' to '{new}'");
        let conn = self.lock();
        conn.execute(
            "DELETE FROM feed_tags WHERE key = ?1 AND feed IN (
                SELECT feed FROM feed_tags WHERE key = ?2)",
            params![new, old],
        )?;
        conn.execute(
            "UPDATE feed_tags SET key = ?1 WHERE key = ?2",
            params![new, old],
        )?;
        Ok(())
    }

    /// Delete a tag from all feeds.
    pub fn delete_tag_globally(&self, key: &str) -> Result<()> {
        tracing::info!("deleting tag '{key}' from all feeds");
        self.lock()
            .execute("DELETE FROM feed_tags WHERE key = ?1", params![key])?;
        Ok(())
    }

    // ── Update support ─────────────────────────────────────────────────

    /// Return feeds eligible for update.
    pub fn feeds_to_update(&self, scheduled: bool, now: DateTime<Utc>) -> Result<Vec<String>> {
        let conn = self.lock();
        let mut stmt = conn.prepare(
            "SELECT url, update_after FROM feeds WHERE updates_enabled = 1 ORDER BY url",
        )?;
        let rows = stmt.query_map([], |r| {
            Ok((r.get::<_, String>(0)?, r.get::<_, Option<String>>(1)?))
        })?;
        let mut urls = Vec::new();
        for row in rows {
            let (url, update_after) = row?;
            if !scheduled {
                urls.push(url);
                continue;
            }
            let eligible = match datetime::parse_opt(update_after) {
                None => true,
                Some(after) => now >= after,
            };
            if eligible {
                urls.push(url);
            }
        }
        Ok(urls)
    }

    /// Load update state for a single feed.
    pub fn feed_update_state(&self, url: &str) -> Result<Option<FeedUpdateState>> {
        let conn = self.lock();
        let row = conn
            .query_row(
                "SELECT url, caching_info, updates_enabled, stale, update_after
                 FROM feeds WHERE url = ?1",
                params![url],
                |r| {
                    Ok((
                        r.get::<_, String>(0)?,
                        r.get::<_, Option<String>>(1)?,
                        r.get::<_, i64>(2)?,
                        r.get::<_, i64>(3)?,
                        r.get::<_, Option<String>>(4)?,
                    ))
                },
            )
            .optional()?;
        Ok(row.map(
            |(url, caching_info, enabled, stale, after)| FeedUpdateState {
                url,
                caching_info,
                updates_enabled: enabled != 0,
                stale: stale != 0,
                update_after: datetime::parse_opt(after),
            },
        ))
    }

    /// Apply the results of a successful fetch+parse for a feed.
    ///
    /// Entries are ordered by their published (or, failing that, updated)
    /// date; entries without any date fall back to the moment they were first
    /// imported. The sort key is set when an entry is first stored and is not
    /// changed by later fetches.
    pub fn apply_update(
        &self,
        url: &str,
        parsed: &ParsedFeed,
        caching_info: Option<String>,
        now: DateTime<Utc>,
    ) -> Result<UpdateOutcome> {
        let now_s = datetime::format(&now);
        let mut conn = self.lock();
        let tx = conn.transaction()?;

        let before: i64 = tx.query_row(
            "SELECT COUNT(*) FROM entries WHERE feed = ?1",
            params![url],
            |r| r.get(0),
        )?;

        for entry in &parsed.entries {
            let recent_sort = entry.published.or(entry.updated).unwrap_or(now);
            tx.execute(
                "INSERT INTO entries
                     (id, feed, title, link, updated, published, author, read, read_modified, added, recent_sort)
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, 0, NULL, ?8, ?9)
                 ON CONFLICT(id, feed) DO UPDATE SET
                     title = excluded.title,
                     link = excluded.link,
                     updated = excluded.updated,
                     published = excluded.published,
                     author = excluded.author",
                params![
                    entry.id,
                    url,
                    entry.title,
                    entry.link,
                    entry.updated.map(|d| datetime::format(&d)),
                    entry.published.map(|d| datetime::format(&d)),
                    entry.author,
                    now_s,
                    datetime::format(&recent_sort),
                ],
            )?;
        }

        tx.execute(
            "UPDATE feeds SET
                 title = COALESCE(?2, title),
                 link = COALESCE(?3, link),
                 updated = COALESCE(?4, updated),
                 caching_info = ?5,
                 last_retrieved = ?6,
                 last_updated = ?6,
                 last_exception = NULL,
                 stale = 0,
                 update_after = ?7
             WHERE url = ?1",
            params![
                url,
                parsed.title,
                parsed.link,
                parsed.updated.map(|d| datetime::format(&d)),
                caching_info,
                now_s,
                datetime::format(
                    &(now + chrono::Duration::minutes(DEFAULT_UPDATE_INTERVAL_MINUTES))
                ),
            ],
        )?;

        // Count within the same transaction — the connection mutex is not
        // reentrant, so we must not call `self.lock()` again while `tx` lives.
        let after: i64 = tx.query_row(
            "SELECT COUNT(*) FROM entries WHERE feed = ?1",
            params![url],
            |r| r.get(0),
        )?;
        tx.commit()?;

        Ok(UpdateOutcome {
            url: url.to_string(),
            title: parsed.title.clone(),
            new_entries: (after - before).max(0) as usize,
            total_entries: parsed.entries.len(),
        })
    }

    /// Record a failed update attempt.
    pub fn record_update_error(&self, url: &str, message: &str) -> Result<()> {
        let now = datetime::format(&datetime::now());
        self.lock().execute(
            "UPDATE feeds SET last_exception = ?2, last_retrieved = ?3 WHERE url = ?1",
            params![url, message, now],
        )?;
        Ok(())
    }

    /// Handle a `304 Not Modified` response: push the next scheduled
    /// update forward and clear any previous error.
    pub fn apply_not_modified(&self, url: &str, now: DateTime<Utc>) -> Result<()> {
        let next =
            datetime::format(&(now + chrono::Duration::minutes(DEFAULT_UPDATE_INTERVAL_MINUTES)));
        self.lock().execute(
            "UPDATE feeds SET last_retrieved = ?2, update_after = ?3, last_exception = NULL
             WHERE url = ?1",
            params![url, datetime::format(&now), next],
        )?;
        Ok(())
    }

    /// Store the caching info (ETag/Last-Modified) for a feed.
    pub fn set_caching_info(&self, url: &str, caching_info: Option<&str>) -> Result<()> {
        self.lock().execute(
            "UPDATE feeds SET caching_info = ?2 WHERE url = ?1",
            params![url, caching_info],
        )?;
        Ok(())
    }

    // ── Settings ───────────────────────────────────────────────────────

    /// Get a persisted application setting.
    pub fn get_setting(&self, key: &str) -> Result<Option<String>> {
        Ok(self
            .lock()
            .query_row(
                "SELECT value FROM app_settings WHERE key = ?1",
                params![key],
                |r| r.get(0),
            )
            .optional()?)
    }

    /// Persist an application setting, replacing any previous value.
    pub fn set_setting(&self, key: &str, value: &str) -> Result<()> {
        tracing::info!("setting '{key}'");
        self.lock().execute(
            "INSERT INTO app_settings (key, value) VALUES (?1, ?2)
             ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            params![key, value],
        )?;
        Ok(())
    }

    /// Remove a persisted application setting.
    pub fn delete_setting(&self, key: &str) -> Result<()> {
        tracing::info!("removing setting '{key}'");
        self.lock()
            .execute("DELETE FROM app_settings WHERE key = ?1", params![key])?;
        Ok(())
    }

    // ── Tag colors ─────────────────────────────────────────────────────

    /// The color assigned to a tag, if any.
    pub fn get_tag_color(&self, tag: &str) -> Result<Option<String>> {
        Ok(self
            .lock()
            .query_row(
                "SELECT color FROM tag_colors WHERE tag = ?1",
                params![tag],
                |r| r.get(0),
            )
            .optional()?)
    }

    /// Assign a color to a tag, replacing any previous one.
    pub fn set_tag_color(&self, tag: &str, color: &str) -> Result<()> {
        tracing::info!("setting color of tag '{tag}'");
        self.lock().execute(
            "INSERT INTO tag_colors (tag, color) VALUES (?1, ?2)
             ON CONFLICT(tag) DO UPDATE SET color = excluded.color",
            params![tag, color],
        )?;
        Ok(())
    }

    /// Remove the color assigned to a tag.
    pub fn delete_tag_color(&self, tag: &str) -> Result<()> {
        tracing::info!("removing color of tag '{tag}'");
        self.lock()
            .execute("DELETE FROM tag_colors WHERE tag = ?1", params![tag])?;
        Ok(())
    }

    /// All assigned tag colors, keyed by tag name.
    pub fn all_tag_colors(&self) -> Result<BTreeMap<String, String>> {
        let conn = self.lock();
        let mut stmt = conn.prepare("SELECT tag, color FROM tag_colors ORDER BY tag")?;
        let rows = stmt.query_map([], |r| Ok((r.get(0)?, r.get(1)?)))?;
        Ok(rows.collect::<rusqlite::Result<BTreeMap<_, _>>>()?)
    }
}

/// Summary of an applied update.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UpdateOutcome {
    /// Feed URL.
    pub url: String,
    /// Feed title after the update, if present.
    pub title: Option<String>,
    /// Number of entries newly inserted.
    pub new_entries: usize,
    /// Number of entries seen in the feed.
    pub total_entries: usize,
}

fn row_to_feed(row: &Row<'_>) -> rusqlite::Result<Feed> {
    let url: String = row.get(0)?;
    let raw_title: Option<String> = row.get(1)?;
    let user_title: Option<String> = row.get(2)?;
    let last_updated: Option<String> = row.get(3)?;
    let title = user_title
        .clone()
        .or(raw_title)
        .filter(|t| !t.trim().is_empty())
        .unwrap_or_default();
    Ok(Feed {
        id: url,
        title,
        last_updated: datetime::parse_opt(last_updated),
        user_title,
    })
}

fn row_to_entry(row: &Row<'_>) -> rusqlite::Result<Entry> {
    let id: String = row.get(0)?;
    let feed: String = row.get(1)?;
    let title: Option<String> = row.get(2)?;
    let link: Option<String> = row.get(3)?;
    let updated: Option<String> = row.get(4)?;
    let published: Option<String> = row.get(5)?;
    let author: Option<String> = row.get(6)?;
    let read: i64 = row.get(7)?;
    // The publication date is the entry's date; feeds that publish none fall
    // back to the update date.
    let date = datetime::parse_opt(published).or_else(|| datetime::parse_opt(updated));
    Ok(Entry {
        url: link.unwrap_or_default(),
        title: title
            .filter(|t| !t.trim().is_empty())
            .unwrap_or_else(|| "No Title".to_string()),
        date,
        entry_id: id,
        feed_id: feed,
        read: read != 0,
        author: author.unwrap_or_default(),
    })
}

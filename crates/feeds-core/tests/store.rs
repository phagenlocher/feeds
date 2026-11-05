//! Integration tests for the storage layer.

// Setup helpers panic on failure; the tests themselves rely on that.
#![allow(clippy::unwrap_used)]

use feeds_core::store::TagFilter;
use feeds_core::{FeedNode, Feeds, Store};

fn store() -> Store {
    Store::open_in_memory().unwrap()
}

#[test]
fn add_and_list_feeds() {
    let store = store();
    store.add_feed("https://b.example/feed", false).unwrap();
    store.add_feed("https://a.example/feed", false).unwrap();
    // Idempotent with exist_ok = true.
    store.add_feed("https://a.example/feed", true).unwrap();

    let feeds = store.get_feeds(TagFilter::All).unwrap();
    assert_eq!(feeds.len(), 2);
    // Sorted case-insensitively by title fallback (URL here).
    assert_eq!(feeds[0].id, "https://a.example/feed");
}

#[test]
fn feeds_without_a_successful_fetch_are_hidden_from_the_tree() {
    let store = store();
    store.add_feed("https://down.example/feed", true).unwrap();
    store.add_feed("https://ok.example/feed", true).unwrap();

    // The healthy feed has fetched once and has an entry, but no title.
    let parsed = feeds_core::ParsedFeed {
        title: None,
        link: None,
        updated: None,
        author: None,
        version: "rss20".into(),
        entries: vec![feeds_core::ParsedEntry {
            id: "1".into(),
            title: Some("Post".into()),
            link: None,
            updated: None,
            published: None,
            author: None,
        }],
    };
    store
        .apply_update("https://ok.example/feed", &parsed, None, chrono::Utc::now())
        .unwrap();

    // Both subscriptions exist…
    assert_eq!(store.get_feeds(TagFilter::All).unwrap().len(), 2);
    // …but the never-fetched one is hidden from the tree.
    let visible = store.get_visible_feeds(TagFilter::All).unwrap();
    assert_eq!(visible.len(), 1);
    assert_eq!(visible[0].id, "https://ok.example/feed");
}

#[test]
fn feed_nodes_bundle_entries_tags_and_unread_state() {
    let store = store();
    let url = "https://example.com/feed";
    store.add_feed(url, true).unwrap();

    let ts = |s: &str| {
        chrono::DateTime::parse_from_rfc3339(s)
            .unwrap()
            .with_timezone(&chrono::Utc)
    };
    let entry = |id: &str, published: &str| feeds_core::ParsedEntry {
        id: id.into(),
        title: Some(id.into()),
        link: None,
        updated: None,
        published: Some(ts(published)),
        author: None,
    };
    let parsed = feeds_core::ParsedFeed {
        title: Some("Example".into()),
        link: None,
        updated: None,
        author: None,
        version: "rss20".into(),
        entries: vec![
            entry("old", "2024-01-01T00:00:00Z"),
            entry("new", "2024-05-05T00:00:00Z"),
        ],
    };
    store
        .apply_update(url, &parsed, None, chrono::Utc::now())
        .unwrap();
    store.set_tag(url, "news").unwrap();
    store.set_entry_read(url, "new", true).unwrap();

    let nodes = store.get_feed_nodes(TagFilter::All).unwrap();
    assert_eq!(nodes.len(), 1);
    let node = &nodes[0];
    assert_eq!(node.feed.id, url);
    assert_eq!(node.unread, 1);
    assert_eq!(node.tags, vec!["news".to_string()]);
    assert_eq!(node.entries.len(), 2);
    // Entries are newest first.
    assert_eq!(node.entries[0].entry_id, "new");
    assert_eq!(node.newest_date, Some(ts("2024-05-05T00:00:00Z")));
}

#[test]
fn feed_nodes_exclude_hidden_feeds() {
    let store = store();
    store.add_feed("https://down.example/feed", true).unwrap();
    assert_eq!(
        store.get_feed_nodes(TagFilter::All).unwrap(),
        Vec::<FeedNode>::new()
    );
}

#[test]
fn add_duplicate_without_exist_ok_errors() {
    let store = store();
    store.add_feed("https://example.com/feed", false).unwrap();
    assert!(store.add_feed("https://example.com/feed", false).is_err());
}

#[test]
fn entries_round_trip_and_read_state() {
    let store = store();
    store.add_feed("https://example.com/feed", true).unwrap();
    let parsed = feeds_core::ParsedFeed {
        title: Some("Example".into()),
        link: None,
        updated: None,
        author: None,
        version: "rss20".into(),
        entries: vec![
            feeds_core::ParsedEntry {
                id: "1".into(),
                title: Some("First".into()),
                link: Some("https://example.com/1".into()),
                updated: None,
                published: None,
                author: Some("Alice".into()),
            },
            feeds_core::ParsedEntry {
                id: "2".into(),
                title: Some("Second".into()),
                link: Some("https://example.com/2".into()),
                updated: None,
                published: None,
                author: None,
            },
        ],
    };
    let outcome = store
        .apply_update(
            "https://example.com/feed",
            &parsed,
            None,
            chrono::Utc::now(),
        )
        .unwrap();
    assert_eq!(outcome.new_entries, 2);
    assert_eq!(store.entry_count("https://example.com/feed").unwrap(), 2);
    assert_eq!(store.unread_count("https://example.com/feed").unwrap(), 2);

    let entries = store.get_entries("https://example.com/feed").unwrap();
    assert_eq!(entries.len(), 2);
    assert!(entries.iter().any(|e| e.author == "Alice"));

    store
        .set_entry_read("https://example.com/feed", "1", true)
        .unwrap();
    assert_eq!(store.unread_count("https://example.com/feed").unwrap(), 1);

    // Marking an entry unread again increments the count.
    store
        .set_entry_read("https://example.com/feed", "1", false)
        .unwrap();
    assert_eq!(store.unread_count("https://example.com/feed").unwrap(), 2);

    store.mark_all_as_read("https://example.com/feed").unwrap();
    assert_eq!(store.unread_count("https://example.com/feed").unwrap(), 0);
}

#[test]
fn redundant_entries_are_deduplicated_by_id() {
    let store = store();
    store.add_feed("https://example.com/feed", true).unwrap();
    let entry = feeds_core::ParsedEntry {
        id: "same".into(),
        title: Some("v1".into()),
        link: None,
        updated: None,
        published: None,
        author: None,
    };
    let parsed = |title: &str| feeds_core::ParsedFeed {
        title: None,
        link: None,
        updated: None,
        author: None,
        version: "rss20".into(),
        entries: vec![feeds_core::ParsedEntry {
            title: Some(title.into()),
            ..entry.clone()
        }],
    };
    store
        .apply_update(
            "https://example.com/feed",
            &parsed("v1"),
            None,
            chrono::Utc::now(),
        )
        .unwrap();
    let outcome = store
        .apply_update(
            "https://example.com/feed",
            &parsed("v2"),
            None,
            chrono::Utc::now(),
        )
        .unwrap();
    assert_eq!(outcome.new_entries, 0);
    assert_eq!(store.entry_count("https://example.com/feed").unwrap(), 1);
    assert_eq!(
        store.get_entries("https://example.com/feed").unwrap()[0].title,
        "v2"
    );
}

#[test]
fn prune_keeps_most_recent() {
    let store = store();
    store.add_feed("https://example.com/feed", true).unwrap();
    let mut entries = Vec::new();
    for i in 0..5 {
        entries.push(feeds_core::ParsedEntry {
            id: format!("{i}"),
            title: Some(format!("Entry {i}")),
            link: None,
            updated: None,
            published: None,
            author: None,
        });
    }
    let parsed = feeds_core::ParsedFeed {
        title: None,
        link: None,
        updated: None,
        author: None,
        version: "rss20".into(),
        entries,
    };
    store
        .apply_update(
            "https://example.com/feed",
            &parsed,
            None,
            chrono::Utc::now(),
        )
        .unwrap();
    let deleted = store.prune_feed("https://example.com/feed", 3).unwrap();
    assert_eq!(deleted, 2);
    assert_eq!(store.entry_count("https://example.com/feed").unwrap(), 3);
}

#[test]
fn entries_are_ordered_by_date_across_updates() {
    let store = store();
    let url = "https://example.com/feed";
    store.add_feed(url, true).unwrap();

    let entry = |id: &str, published: &str| feeds_core::ParsedEntry {
        id: id.into(),
        title: Some(id.into()),
        link: None,
        updated: None,
        published: Some(
            chrono::DateTime::parse_from_rfc3339(published)
                .unwrap()
                .with_timezone(&chrono::Utc),
        ),
        author: None,
    };
    let feed = |entries: Vec<feeds_core::ParsedEntry>| feeds_core::ParsedFeed {
        title: None,
        link: None,
        updated: None,
        author: None,
        version: "rss20".into(),
        entries,
    };

    store
        .apply_update(
            url,
            &feed(vec![entry("a", "2020-01-02T00:00:00Z")]),
            None,
            chrono::Utc::now(),
        )
        .unwrap();
    // A later fetch introduces entries older and newer than "a"; they must be
    // ordered by date, not by the time they were imported.
    store
        .apply_update(
            url,
            &feed(vec![
                entry("b", "2020-01-01T00:00:00Z"),
                entry("c", "2020-01-03T00:00:00Z"),
            ]),
            None,
            chrono::Utc::now(),
        )
        .unwrap();

    let ids: Vec<String> = store
        .get_entries(url)
        .unwrap()
        .into_iter()
        .map(|e| e.entry_id)
        .collect();
    assert_eq!(ids, ["c", "a", "b"]);
}

#[test]
fn entry_dates_prefer_the_publication_date() {
    let store = store();
    let url = "https://example.com/feed";
    store.add_feed(url, true).unwrap();

    let ts = |s: &str| {
        chrono::DateTime::parse_from_rfc3339(s)
            .unwrap()
            .with_timezone(&chrono::Utc)
    };
    let entry =
        |id: &str, published: Option<&str>, updated: Option<&str>| feeds_core::ParsedEntry {
            id: id.into(),
            title: Some(id.into()),
            link: None,
            updated: updated.map(ts),
            published: published.map(ts),
            author: None,
        };
    let feed = |entries: Vec<feeds_core::ParsedEntry>| feeds_core::ParsedFeed {
        title: None,
        link: None,
        updated: None,
        author: None,
        version: "rss20".into(),
        entries,
    };

    store
        .apply_update(
            url,
            &feed(vec![
                // Published long ago, updated recently: the publication date
                // wins.
                entry(
                    "both",
                    Some("2024-01-01T00:00:00Z"),
                    Some("2024-06-01T00:00:00Z"),
                ),
                // No publication date: the update date is the fallback.
                entry("updated-only", None, Some("2024-03-01T00:00:00Z")),
                // No date at all.
                entry("undated", None, None),
            ]),
            None,
            chrono::Utc::now(),
        )
        .unwrap();

    let entries = store.get_entries(url).unwrap();
    let date_of = |id: &str| entries.iter().find(|e| e.entry_id == id).unwrap().date;
    assert_eq!(date_of("both"), Some(ts("2024-01-01T00:00:00Z")));
    assert_eq!(date_of("updated-only"), Some(ts("2024-03-01T00:00:00Z")));
    assert_eq!(date_of("undated"), None);

    // The newest entry date is the newest published date — the newest update
    // date does not win.
    assert_eq!(
        feeds_core::newest_entry_date(&entries),
        Some(ts("2024-03-01T00:00:00Z"))
    );
}

#[test]
fn undated_entries_keep_their_import_time_as_sort_key() {
    let store = store();
    let url = "https://example.com/feed";
    store.add_feed(url, true).unwrap();

    let ts = |s: &str| {
        chrono::DateTime::parse_from_rfc3339(s)
            .unwrap()
            .with_timezone(&chrono::Utc)
    };
    let entry = |id: &str, published: Option<&str>| feeds_core::ParsedEntry {
        id: id.into(),
        title: Some(id.into()),
        link: None,
        updated: None,
        published: published.map(ts),
        author: None,
    };
    let feed = |entries: Vec<feeds_core::ParsedEntry>| feeds_core::ParsedFeed {
        title: None,
        link: None,
        updated: None,
        author: None,
        version: "rss20".into(),
        entries,
    };
    let ids = |store: &Store| -> Vec<String> {
        store
            .get_entries(url)
            .unwrap()
            .into_iter()
            .map(|e| e.entry_id)
            .collect()
    };

    // "z" is imported without a date, so its sort key is the moment it was
    // first seen. Later fetches do not change that key, so "z" stays above
    // "m", which was published in between.
    store
        .apply_update(
            url,
            &feed(vec![entry("z", None)]),
            None,
            ts("2026-01-01T00:00:00Z"),
        )
        .unwrap();
    store
        .apply_update(
            url,
            &feed(vec![
                entry("z", None),
                entry("m", Some("2026-03-01T00:00:00Z")),
            ]),
            None,
            ts("2026-06-01T00:00:00Z"),
        )
        .unwrap();

    assert_eq!(ids(&store), ["m", "z"]);
}

#[test]
fn tags_filter_and_rename() {
    let store = store();
    store.add_feed("https://a.example/feed", true).unwrap();
    store.add_feed("https://b.example/feed", true).unwrap();
    store.set_tag("https://a.example/feed", "news").unwrap();

    let tagged = store
        .get_feeds(TagFilter::Tags(vec!["news".into()]))
        .unwrap();
    assert_eq!(tagged.len(), 1);
    assert_eq!(tagged[0].id, "https://a.example/feed");

    let untagged = store.get_feeds(TagFilter::Untagged).unwrap();
    assert_eq!(untagged.len(), 1);
    assert_eq!(untagged[0].id, "https://b.example/feed");

    assert_eq!(store.tag_keys().unwrap(), vec!["news".to_string()]);

    store.rename_tag("news", "tech").unwrap();
    assert_eq!(store.tag_keys().unwrap(), vec!["tech".to_string()]);
    assert_eq!(
        store.get_tags("https://a.example/feed").unwrap(),
        vec!["tech".to_string()]
    );

    store.delete_tag_globally("tech").unwrap();
    assert_eq!(store.tag_keys().unwrap(), Vec::<String>::new());
}

#[test]
fn deleting_a_feed_cascades_to_entries() {
    let store = store();
    store.add_feed("https://example.com/feed", true).unwrap();
    let parsed = feeds_core::ParsedFeed {
        title: None,
        link: None,
        updated: None,
        author: None,
        version: "rss20".into(),
        entries: vec![feeds_core::ParsedEntry {
            id: "1".into(),
            title: None,
            link: None,
            updated: None,
            published: None,
            author: None,
        }],
    };
    store
        .apply_update(
            "https://example.com/feed",
            &parsed,
            None,
            chrono::Utc::now(),
        )
        .unwrap();
    store.delete_feed("https://example.com/feed").unwrap();
    assert!(!store.feed_exists("https://example.com/feed").unwrap());
    assert_eq!(store.entry_count("https://example.com/feed").unwrap(), 0);
}

#[test]
fn facade_opml_round_trip() {
    let dir = tempfile::tempdir().unwrap();
    let feeds = Feeds::open(Some(dir.path().to_path_buf())).unwrap();
    feeds.add_feed("https://example.com/feed").unwrap();
    feeds.add_feed("https://rust-lang.org/feed.xml").unwrap();

    let xml = feeds.export_opml().unwrap();
    assert!(xml.contains("https://example.com/feed"));

    let dir2 = tempfile::tempdir().unwrap();
    let feeds2 = Feeds::open(Some(dir2.path().to_path_buf())).unwrap();
    assert_eq!(feeds2.import_opml(&xml).unwrap(), 2);
    assert_eq!(feeds2.feed_count().unwrap(), 2);
}

#[test]
fn application_settings_round_trip() {
    let store = store();
    assert_eq!(store.get_setting("font_size").unwrap(), None);

    store.set_setting("font_size", "22").unwrap();
    assert_eq!(
        store.get_setting("font_size").unwrap(),
        Some("22".to_string())
    );

    // Setting the same key again replaces the value.
    store.set_setting("font_size", "18").unwrap();
    assert_eq!(
        store.get_setting("font_size").unwrap(),
        Some("18".to_string())
    );

    store.delete_setting("font_size").unwrap();
    assert_eq!(store.get_setting("font_size").unwrap(), None);
}

#[test]
fn tag_colors_round_trip() {
    let store = store();
    assert_eq!(store.get_tag_color("rust").unwrap(), None);
    assert!(store.all_tag_colors().unwrap().is_empty());

    store.set_tag_color("rust", "#ff0000").unwrap();
    store.set_tag_color("news", "#00ff00").unwrap();
    assert_eq!(
        store.get_tag_color("rust").unwrap(),
        Some("#ff0000".to_string())
    );

    // Setting the same tag again replaces the color.
    store.set_tag_color("rust", "#0000ff").unwrap();
    assert_eq!(
        store.get_tag_color("rust").unwrap(),
        Some("#0000ff".to_string())
    );

    let all = store.all_tag_colors().unwrap();
    assert_eq!(all.len(), 2);
    assert_eq!(all.get("news").map(String::as_str), Some("#00ff00"));
    assert_eq!(all.get("rust").map(String::as_str), Some("#0000ff"));

    store.delete_tag_color("rust").unwrap();
    assert_eq!(store.get_tag_color("rust").unwrap(), None);
    assert_eq!(store.all_tag_colors().unwrap().len(), 1);
}

#[test]
fn opening_an_existing_database_adds_the_settings_tables() {
    let dir = tempfile::tempdir().unwrap();
    let db_path = dir.path().join("feeds.db");

    // An older database: the feeds/entries/tags tables, but no settings.
    {
        let conn = rusqlite::Connection::open(&db_path).unwrap();
        conn.execute_batch(
            "CREATE TABLE feeds (url TEXT PRIMARY KEY NOT NULL, added TEXT NOT NULL);
             CREATE TABLE entries (id TEXT NOT NULL, feed TEXT NOT NULL, title TEXT,
                link TEXT, updated TEXT, published TEXT, author TEXT, read INTEGER NOT NULL
                DEFAULT 0, read_modified TEXT, added TEXT NOT NULL, recent_sort TEXT NOT NULL,
                PRIMARY KEY (id, feed));
             CREATE TABLE feed_tags (feed TEXT NOT NULL, key TEXT NOT NULL,
                PRIMARY KEY (feed, key));",
        )
        .unwrap();
        conn.execute(
            "INSERT INTO feeds (url, added) VALUES ('https://example.com/feed', '2026-01-01')",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO feed_tags (feed, key)
             VALUES ('https://example.com/feed', 'rust')",
            [],
        )
        .unwrap();
    }

    // Opening it adds the new tables and keeps the existing data.
    let store = Store::open(&db_path).unwrap();
    assert_eq!(store.feed_count().unwrap(), 1);
    assert_eq!(store.tag_keys().unwrap(), vec!["rust".to_string()]);

    store.set_setting("font_size", "22").unwrap();
    store.set_tag_color("rust", "#ff0000").unwrap();
    assert_eq!(
        store.get_setting("font_size").unwrap(),
        Some("22".to_string())
    );
    assert_eq!(
        store.get_tag_color("rust").unwrap(),
        Some("#ff0000".to_string())
    );
}

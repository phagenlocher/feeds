//! Integration tests for the persisted application settings.

// Setup helpers panic on failure; the tests themselves rely on that.
#![allow(clippy::unwrap_used)]

use feeds_core::settings::{DEFAULT_FONT_SIZE, MIN_FONT_SIZE, SETTING_FONT_SIZE};
use feeds_core::Feeds;

const FEED: &str = "https://example.com/feed";

fn open(dir: &std::path::Path) -> Feeds {
    Feeds::open(Some(dir.to_path_buf())).unwrap()
}

#[test]
fn a_fresh_database_yields_the_default_settings() {
    let dir = tempfile::tempdir().unwrap();
    let feeds = open(dir.path());

    let settings = feeds.get_settings().unwrap();
    assert_eq!(settings.font_size, DEFAULT_FONT_SIZE);
    assert!(settings.tag_colors.is_empty());
}

#[test]
fn the_font_size_survives_a_restart() {
    let dir = tempfile::tempdir().unwrap();

    {
        let feeds = open(dir.path());
        assert_eq!(feeds.set_font_size(21).unwrap(), 21);
    }

    let feeds = open(dir.path());
    assert_eq!(feeds.get_settings().unwrap().font_size, 21);
    assert_eq!(
        feeds.store().get_setting(SETTING_FONT_SIZE).unwrap(),
        Some("21".to_string())
    );
}

#[test]
fn a_font_size_below_the_minimum_is_rejected() {
    let dir = tempfile::tempdir().unwrap();
    let feeds = open(dir.path());

    assert_eq!(
        feeds.set_font_size(MIN_FONT_SIZE - 1).unwrap(),
        DEFAULT_FONT_SIZE
    );
    assert_eq!(feeds.get_settings().unwrap().font_size, DEFAULT_FONT_SIZE);
}

#[test]
fn tag_colors_survive_a_restart() {
    let dir = tempfile::tempdir().unwrap();

    {
        let feeds = open(dir.path());
        feeds.add_feed(FEED).unwrap();
        feeds.set_feed_tag(FEED, "rust").unwrap();
        feeds.set_tag_color("rust", "#ff0000").unwrap();
    }

    let feeds = open(dir.path());
    let settings = feeds.get_settings().unwrap();
    assert_eq!(
        settings.tag_colors.get("rust").map(String::as_str),
        Some("#ff0000")
    );
}

#[test]
fn a_new_tag_is_given_a_deterministic_color() {
    let dir = tempfile::tempdir().unwrap();
    let feeds = open(dir.path());
    feeds.add_feed(FEED).unwrap();
    feeds.set_feed_tag(FEED, "rust").unwrap();

    let settings = feeds.get_settings().unwrap();
    let color = settings.tag_colors.get("rust").cloned().unwrap();
    assert_eq!(
        color,
        feeds_core::tags::default_color_for_tag("rust"),
        "the assigned color is the deterministic default"
    );
}

#[test]
fn an_existing_color_is_not_overwritten() {
    let dir = tempfile::tempdir().unwrap();
    let feeds = open(dir.path());
    feeds.add_feed(FEED).unwrap();
    feeds.set_feed_tag(FEED, "rust").unwrap();
    feeds.set_tag_color("rust", "#ff0000").unwrap();

    // Reading the settings assigns colors to missing tags only.
    let settings = feeds.get_settings().unwrap();
    assert_eq!(
        settings.tag_colors.get("rust").map(String::as_str),
        Some("#ff0000")
    );
}

#[test]
fn renaming_a_tag_carries_its_color_over() {
    let dir = tempfile::tempdir().unwrap();
    let feeds = open(dir.path());
    feeds.add_feed(FEED).unwrap();
    feeds.set_feed_tag(FEED, "news").unwrap();
    feeds.set_tag_color("news", "#e66100").unwrap();

    feeds.rename_tag("news", "tech").unwrap();

    let settings = feeds.get_settings().unwrap();
    assert!(!settings.tag_colors.contains_key("news"));
    assert_eq!(
        settings.tag_colors.get("tech").map(String::as_str),
        Some("#e66100")
    );
}

#[test]
fn renaming_a_tag_keeps_the_color_of_the_new_name() {
    let dir = tempfile::tempdir().unwrap();
    let feeds = open(dir.path());
    feeds.add_feed(FEED).unwrap();
    feeds.set_feed_tag(FEED, "news").unwrap();
    feeds.set_feed_tag(FEED, "tech").unwrap();
    // "news" has no color of its own, "tech" has one.
    feeds.set_tag_color("tech", "#3584e4").unwrap();

    feeds.rename_tag("news", "tech").unwrap();

    let settings = feeds.get_settings().unwrap();
    assert_eq!(
        settings.tag_colors.get("tech").map(String::as_str),
        Some("#3584e4")
    );
}

#[test]
fn deleting_a_tag_drops_its_color() {
    let dir = tempfile::tempdir().unwrap();
    let feeds = open(dir.path());
    feeds.add_feed(FEED).unwrap();
    feeds.set_feed_tag(FEED, "news").unwrap();
    feeds.set_tag_color("news", "#e66100").unwrap();

    feeds.delete_tag("news").unwrap();

    let settings = feeds.get_settings().unwrap();
    assert!(!settings.tag_colors.contains_key("news"));
    assert_eq!(feeds.get_all_tag_keys().unwrap(), Vec::<String>::new());
}

//! Feed parsing adapter.
//!
//! Wraps [`feed_rs`] behind a small, stable surface used to decide whether a
//! response body is a feed, read a feed title, and parse a body into the
//! unified [`ParsedFeed`] model, so the backend can be swapped if needed.

use std::sync::OnceLock;

use feed_rs::model::{FeedType, Person};
use feed_rs::parser;
use regex::Regex;

use crate::error::{Error, Result};
use crate::models::{ParsedEntry, ParsedFeed};

/// Parse feed bytes into the crate's unified model.
///
/// Returns [`Error::FeedParse`] if the bytes are not a recognisable
/// RSS/Atom/JSON feed (e.g. an HTML page).
pub fn parse_bytes(bytes: &[u8]) -> Result<ParsedFeed> {
    let parsed = parse_feed(bytes).map_err(|e| Error::FeedParse(e.to_string()))?;
    Ok(convert(parsed))
}

/// Return `true` if `bytes` parse as a feed.
pub fn is_feed(bytes: &[u8]) -> bool {
    parse_feed(bytes).is_ok()
}

/// Extract the feed title from `bytes`, if the bytes are a feed.
pub fn feed_title(bytes: &[u8]) -> Option<String> {
    parse_feed(bytes)
        .ok()
        .and_then(|f| f.title.map(|t| t.content).filter(|t| !t.trim().is_empty()))
}

/// Parse with [`feed_rs`], repairing a known incompatibility on failure.
fn parse_feed(bytes: &[u8]) -> parser::ParseFeedResult<feed_rs::model::Feed> {
    let normalized = normalize_rfc2822_timestamps(bytes);
    let bytes: &[u8] = match &normalized {
        Some(text) => text.as_bytes(),
        None => bytes,
    };
    match parser::parse(bytes) {
        Ok(feed) => Ok(feed),
        Err(err) => match repair_empty_media_text(bytes) {
            Some(text) => match parser::parse(text.as_bytes()) {
                Ok(feed) => {
                    tracing::debug!("parsed feed after stripping empty Media RSS text elements");
                    Ok(feed)
                }
                Err(_) => Err(err),
            },
            None => Err(err),
        },
    }
}

/// Complete RFC 2822 timestamps that lack a time, a time zone, or both.
///
/// Feeds built by Hugo emit `<pubDate>Mon, 25 May 2026</pubDate>` — a date
/// without a time or time zone. `chrono`, and with it feed-rs, rejects those
/// silently, so every entry of such a feed ends up without any date at all.
/// Rewrite them to a complete timestamp (`Mon, 25 May 2026 00:00:00 +0000`)
/// before parsing.
///
/// Timestamps that are already complete are left untouched.
fn normalize_rfc2822_timestamps(bytes: &[u8]) -> Option<String> {
    static RE: OnceLock<Regex> = OnceLock::new();
    #[expect(
        clippy::expect_used,
        reason = "the pattern is a literal that is known to compile"
    )]
    let re = RE.get_or_init(|| {
        Regex::new(
            r"(?is)<(pubDate|lastBuildDate|published|updated|dc:date)\s*>\s*([A-Za-z]{3,9},?\s+)?(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})(\s+\d{1,2}:\d{2}(?::\d{2})?)?\s*</(pubDate|lastBuildDate|published|updated|dc:date)>",
        )
        .expect("static pattern is valid")
    });
    let text = std::str::from_utf8(bytes).ok()?;
    let normalized = re.replace_all(text, |caps: &regex::Captures<'_>| {
        let tag = &caps[1];
        // Leave a mismatched pair of tags alone rather than corrupting it.
        if tag != &caps[5] {
            return caps[0].to_string();
        }
        let weekday = caps.get(2).map_or("", |m| m.as_str());
        let date = &caps[3];
        // The captured time keeps its leading whitespace; the default adds it.
        let time = caps.get(4).map_or(" 00:00:00", |m| m.as_str());
        format!("<{tag}>{weekday}{date}{time} +0000</{tag}>")
    });
    (normalized != text).then(|| normalized.into_owned())
}

/// feed-rs 3.x treats an *empty* Media RSS text element as fatal: it routes
/// `<media:title>`/`<media:description>` through its Atom text-construct
/// parser, which errors with `missing text at position N` when the element has
/// no content.
/// YouTube emits exactly that (`<media:description></media:description>`) for
/// videos without a description. Since Media RSS fields are ignored by this
/// crate's model, drop those empty elements and let the caller retry.
fn repair_empty_media_text(bytes: &[u8]) -> Option<String> {
    static RE: OnceLock<Regex> = OnceLock::new();
    #[expect(
        clippy::expect_used,
        reason = "the pattern is a literal that is known to compile"
    )]
    let re = RE.get_or_init(|| {
        Regex::new(
            r"(?is)<media:(?:title|description)(?:\s[^>]*?)?\s*(?:/>|>\s*</media:(?:title|description)\s*>)",
        )
        .expect("static pattern is valid")
    });
    let text = std::str::from_utf8(bytes).ok()?;
    let repaired = re.replace_all(text, "");
    (repaired != text).then(|| repaired.into_owned())
}

/// Map a [`FeedType`] to the historical version string.
pub fn version_string(feed_type: FeedType) -> String {
    match feed_type {
        FeedType::Atom => "atom10",
        FeedType::RSS0 => "rss0.9x",
        FeedType::RSS1 => "rss10",
        FeedType::RSS2 => "rss20",
        FeedType::JSON => "json11",
    }
    .to_string()
}

fn join_authors(authors: &[Person]) -> Option<String> {
    let names: Vec<&str> = authors
        .iter()
        .filter_map(|p| p.name.as_deref())
        .filter(|n| !n.trim().is_empty())
        .collect();
    if names.is_empty() {
        None
    } else {
        Some(names.join(", "))
    }
}

fn convert(feed: feed_rs::model::Feed) -> ParsedFeed {
    let title = feed
        .title
        .as_ref()
        .map(|t| t.content.clone())
        .filter(|t| !t.trim().is_empty());
    let link = feed
        .links
        .iter()
        .find(|l| l.rel.as_deref().unwrap_or("alternate") == "alternate")
        .or_else(|| feed.links.first())
        .map(|l| l.href.clone());
    let author = join_authors(&feed.authors);

    let entries = feed
        .entries
        .into_iter()
        .map(|e| {
            let link = e
                .links
                .iter()
                .find(|l| l.rel.as_deref().unwrap_or("alternate") == "alternate")
                .or_else(|| e.links.first())
                .map(|l| l.href.clone());
            let id = if e.id.trim().is_empty() {
                link.clone().unwrap_or_default()
            } else {
                e.id.clone()
            };
            ParsedEntry {
                id,
                title: e
                    .title
                    .as_ref()
                    .map(|t| t.content.clone())
                    .filter(|t| !t.trim().is_empty()),
                link,
                updated: e.updated,
                published: e.published,
                author: join_authors(&e.authors),
            }
        })
        .collect();

    ParsedFeed {
        title,
        link,
        updated: feed.updated,
        author,
        version: version_string(feed.feed_type),
        entries,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const RSS: &str = r#"<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Example Feed</title>
    <link>https://example.com</link>
    <item>
      <title>First Post</title>
      <link>https://example.com/post/1</link>
      <guid>post-1</guid>
      <pubDate>Mon, 06 Sep 2010 00:01:00 +0000</pubDate>
      <author>alice@example.com (Alice)</author>
    </item>
  </channel>
</rss>"#;

    #[test]
    fn parses_rss_title_and_entries() {
        let feed = parse_bytes(RSS.as_bytes()).unwrap();
        assert_eq!(feed.version, "rss20");
        assert_eq!(feed.title.as_deref(), Some("Example Feed"));
        assert_eq!(feed.entries.len(), 1);
        assert_eq!(feed.entries[0].title.as_deref(), Some("First Post"));
        assert_eq!(feed.entries[0].id, "post-1");
    }

    #[test]
    fn html_is_not_a_feed() {
        let html = b"<!DOCTYPE html><html><head><title>x</title></head></html>";
        assert!(!is_feed(html));
        assert!(parse_bytes(html).is_err());
    }

    #[test]
    fn feed_title_helper() {
        assert_eq!(feed_title(RSS.as_bytes()).as_deref(), Some("Example Feed"));
        assert_eq!(feed_title(b"<html></html>"), None);
    }

    /// YouTube emits an empty `<media:description>` for videos without one;
    /// feed-rs rejects that with `missing text at position N`.
    const ATOM_EMPTY_MEDIA_DESC: &str = r#"<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/">
  <title>Test Channel</title>
  <id>yt:channel:test</id>
  <entry>
    <id>yt:video:abc</id>
    <title>Some Video</title>
    <media:group>
      <media:title>Some Video</media:title>
      <media:content url="https://example.com/v" type="video/mp4"/>
      <media:description></media:description>
      <media:community>
        <media:statistics views="1"/>
      </media:community>
    </media:group>
  </entry>
</feed>"#;

    #[test]
    fn parses_empty_media_description() {
        let feed = parse_bytes(ATOM_EMPTY_MEDIA_DESC.as_bytes()).unwrap();
        assert_eq!(feed.title.as_deref(), Some("Test Channel"));
        assert_eq!(feed.entries.len(), 1);
        assert_eq!(feed.entries[0].id, "yt:video:abc");
        assert_eq!(feed.entries[0].title.as_deref(), Some("Some Video"));
        assert!(is_feed(ATOM_EMPTY_MEDIA_DESC.as_bytes()));
    }

    #[test]
    fn parses_self_closing_empty_media_description() {
        let xml = ATOM_EMPTY_MEDIA_DESC.replace(
            "<media:description></media:description>",
            "<media:description/>",
        );
        assert!(parse_bytes(xml.as_bytes()).is_ok());
    }

    /// Hugo emits RFC 2822 timestamps without a time or time zone, which
    /// `chrono` — and with it feed-rs — rejects, leaving the entries undated.
    const RSS_DATE_ONLY: &str = r#"<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Date Only</title>
    <link>https://example.com</link>
    <item>
      <title>First Post</title>
      <link>https://example.com/post/1</link>
      <guid>post-1</guid>
      <pubDate>Mon, 25 May 2026</pubDate>
    </item>
    <item>
      <title>Second Post</title>
      <link>https://example.com/post/2</link>
      <guid>post-2</guid>
      <pubDate>25 May 2026</pubDate>
    </item>
    <item>
      <title>Third Post</title>
      <link>https://example.com/post/3</link>
      <guid>post-3</guid>
      <pubDate>Tue, 26 May 2026 10:30</pubDate>
    </item>
  </channel>
</rss>"#;

    #[test]
    fn parses_date_only_timestamps() {
        let feed = parse_bytes(RSS_DATE_ONLY.as_bytes()).unwrap();
        assert_eq!(feed.entries.len(), 3);

        let published = |id: &str| {
            feed.entries
                .iter()
                .find(|e| e.id == id)
                .unwrap()
                .published
                .map(|d| d.to_rfc3339())
        };
        assert_eq!(
            published("post-1").as_deref(),
            Some("2026-05-25T00:00:00+00:00")
        );
        assert_eq!(
            published("post-2").as_deref(),
            Some("2026-05-25T00:00:00+00:00")
        );
        assert_eq!(
            published("post-3").as_deref(),
            Some("2026-05-26T10:30:00+00:00")
        );
    }

    #[test]
    fn keeps_complete_timestamps_untouched() {
        let feed = parse_bytes(RSS.as_bytes()).unwrap();
        assert_eq!(
            feed.entries[0].published.map(|d| d.to_rfc3339()),
            Some("2010-09-06T00:01:00+00:00".to_string())
        );
    }

    #[test]
    fn normalizes_date_only_timestamps_in_atom_feeds() {
        let xml = r#"<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Atom Date Only</title>
  <id>urn:uuid:1</id>
  <updated>Mon, 25 May 2026</updated>
  <entry>
    <id>urn:uuid:2</id>
    <title>Some Entry</title>
    <published>Mon, 25 May 2026</published>
    <updated>Mon, 25 May 2026</updated>
  </entry>
</feed>"#;
        let feed = parse_bytes(xml.as_bytes()).unwrap();
        assert_eq!(
            feed.entries[0].published.map(|d| d.to_rfc3339()),
            Some("2026-05-25T00:00:00+00:00".to_string())
        );
        assert_eq!(
            feed.updated.map(|d| d.to_rfc3339()),
            Some("2026-05-25T00:00:00+00:00".to_string())
        );
    }
}

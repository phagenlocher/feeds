//! Integration tests for the update engine (conditional GET + parsing).

use feeds_core::Feeds;
use httpmock::prelude::*;

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
    </item>
    <item>
      <title>Second Post</title>
      <link>https://example.com/post/2</link>
      <guid>post-2</guid>
      <pubDate>Tue, 07 Sep 2010 00:01:00 +0000</pubDate>
    </item>
  </channel>
</rss>"#;

#[tokio::test]
async fn updates_feed_and_stores_entries() {
    let server = MockServer::start();
    let feed = server.mock(|when, then| {
        when.method(GET).path("/feed");
        then.status(200)
            .header("content-type", "application/rss+xml")
            .body(RSS);
    });

    let dir = tempfile::tempdir().unwrap();
    let feeds = Feeds::open(Some(dir.path().to_path_buf())).unwrap();
    let url = server.url("/feed");
    feeds.add_feed(&url).unwrap();

    let outcome = feeds.update_feed(&url).await.unwrap();
    assert_eq!(outcome.new_entries, 2);
    assert_eq!(feeds.store().entry_count(&url).unwrap(), 2);

    let stored = feeds.get_feed(&url).unwrap().unwrap();
    assert_eq!(stored.title, "Example Feed");
    feed.assert();
}

#[tokio::test]
async fn sends_conditional_headers_and_handles_304() {
    let server = MockServer::start();
    let fresh = server.mock(|when, then| {
        when.method(GET)
            .path("/feed")
            .header_missing("if-none-match");
        then.status(200)
            .header("content-type", "application/rss+xml")
            .header("etag", "\"v1\"")
            .body(RSS);
    });
    let not_modified = server.mock(|when, then| {
        when.method(GET)
            .path("/feed")
            .header("if-none-match", "\"v1\"");
        then.status(304);
    });

    let dir = tempfile::tempdir().unwrap();
    let feeds = Feeds::open(Some(dir.path().to_path_buf())).unwrap();
    let url = server.url("/feed");
    feeds.add_feed(&url).unwrap();

    feeds.update_feed(&url).await.unwrap();
    fresh.assert();

    let second = feeds.update_feed(&url).await.unwrap();
    assert_eq!(second.new_entries, 0);
    not_modified.assert();
    assert_eq!(feeds.store().entry_count(&url).unwrap(), 2);
}

#[tokio::test]
async fn records_error_on_http_failure() {
    let server = MockServer::start();
    server.mock(|when, then| {
        when.method(GET).path("/broken");
        then.status(500);
    });

    let dir = tempfile::tempdir().unwrap();
    let feeds = Feeds::open(Some(dir.path().to_path_buf())).unwrap();
    let url = server.url("/broken");
    feeds.add_feed(&url).unwrap();

    assert!(feeds.update_feed(&url).await.is_err());
}

#[tokio::test]
async fn failed_feeds_are_counted_and_others_still_update() {
    let server = MockServer::start();
    server.mock(|when, then| {
        when.method(GET).path("/feed");
        then.status(200)
            .header("content-type", "application/rss+xml")
            .body(RSS);
    });
    server.mock(|when, then| {
        when.method(GET).path("/broken");
        then.status(500);
    });

    let dir = tempfile::tempdir().unwrap();
    let feeds = Feeds::open(Some(dir.path().to_path_buf())).unwrap();
    let broken = server.url("/broken");
    feeds.add_feed(&server.url("/feed")).unwrap();
    feeds.add_feed(&broken).unwrap();
    feeds.set_feed_user_title(&broken, "Broken Feed").unwrap();

    let report = feeds.update_feeds(false).await.unwrap();
    assert_eq!(report.updated, 1);
    assert_eq!(report.failed, 1);
    assert_eq!(report.new_entries, 2);
    assert_eq!(report.failures.len(), 1);
    let failure = &report.failures[0];
    assert_eq!(failure.url, broken);
    assert_eq!(failure.title, "Broken Feed");
    assert!(failure.error.contains("http error"), "{}", failure.error);
}

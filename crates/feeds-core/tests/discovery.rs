//! Integration tests for the discovery pipeline.

use feeds_core::discovery;
use feeds_core::http;
use httpmock::prelude::*;

fn client() -> reqwest::Client {
    http::build_client(feeds_core::USER_AGENT)
}

#[tokio::test]
async fn detects_a_direct_feed() {
    let server = MockServer::start();
    server.mock(|when, then| {
        when.method(GET).path("/feed.xml");
        then.status(200)
            .header("content-type", "application/rss+xml")
            .body("<rss version=\"2.0\"><channel><title>Direct</title></channel></rss>");
    });

    let url = server.url("/feed.xml");
    let feeds = discovery::discover_feeds(&client(), &url).await.unwrap();
    assert_eq!(feeds.len(), 1);
    assert_eq!(feeds[0].0, url);
    assert_eq!(feeds[0].1, "Direct");
}

#[tokio::test]
async fn detects_html_link_tags() {
    let server = MockServer::start();
    server.mock(|when, then| {
        when.method(GET).path("/blog");
        then.status(200).header("content-type", "text/html").body(
            r#"<html><head>
                    <link rel="alternate" type="application/rss+xml" title="RSS" href="/feed.xml">
                </head><body></body></html>"#,
        );
    });

    let url = server.url("/blog");
    let feeds = discovery::discover_feeds(&client(), &url).await.unwrap();
    assert_eq!(feeds.len(), 1);
    assert_eq!(feeds[0].0, server.url("/feed.xml"));
    assert_eq!(feeds[0].1, "RSS");
}

#[tokio::test]
async fn detects_link_header() {
    let server = MockServer::start();
    server.mock(|when, then| {
        when.method(GET).path("/page");
        then.status(200)
            .header("content-type", "text/html")
            .header(
                "link",
                "</feed.xml>; rel=\"alternate\"; type=\"application/rss+xml\"",
            )
            .body("<html><head></head><body></body></html>");
    });

    let url = server.url("/page");
    let feeds = discovery::discover_feeds(&client(), &url).await.unwrap();
    assert_eq!(feeds.len(), 1);
    assert_eq!(feeds[0].0, server.url("/feed.xml"));
}

#[tokio::test]
async fn probes_common_paths_as_fallback() {
    let server = MockServer::start();
    server.mock(|when, then| {
        when.method(GET).path("/");
        then.status(200)
            .header("content-type", "text/html")
            .body("<html><head></head><body></body></html>");
    });
    server.mock(|when, then| {
        when.method(GET).path("/feed");
        then.status(200)
            .header("content-type", "application/rss+xml")
            .body("<rss version=\"2.0\"><channel><title>Probed</title></channel></rss>");
    });

    let url = server.url("/");
    let feeds = discovery::discover_feeds(&client(), &url).await.unwrap();
    assert!(feeds
        .iter()
        .any(|(href, title)| title == "Probed" && href.ends_with("/feed")));
}

#[tokio::test]
async fn reports_network_error_instead_of_no_feeds() {
    let server = MockServer::start();
    server.mock(|when, then| {
        when.method(GET).path("/broken");
        then.status(502);
    });

    let err = discovery::discover_feeds(&client(), &server.url("/broken"))
        .await
        .expect_err("an HTTP failure must not look like 'no feeds found'");
    assert!(err.to_string().contains("http error"), "{err}");
}

#[tokio::test]
async fn subreddit_url_maps_to_rss() {
    let server = MockServer::start();
    server.mock(|when, then| {
        when.method(GET).path("/r/rust/.rss");
        then.status(200)
            .header("content-type", "application/rss+xml")
            .body("<rss version=\"2.0\"><channel><title>r/rust</title></channel></rss>");
    });

    // Point the handler at the mock by using a reddit.com-like host that we
    // cannot rewrite; instead verify the *pattern* through the generic path.
    // The dedicated handler is unit-tested via the URL builder below.
    let _ = server;

    let built = feeds_core::discovery::reddit::reddit_feed_url("https://www.reddit.com/r/rust");
    assert_eq!(built.as_deref(), Some("https://www.reddit.com/r/rust/.rss"));
    let built_user =
        feeds_core::discovery::reddit::reddit_feed_url("https://reddit.com/user/alice/posts");
    assert_eq!(
        built_user.as_deref(),
        Some("https://www.reddit.com/user/alice/.rss")
    );
}

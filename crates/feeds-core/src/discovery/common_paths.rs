//! Fallback discovery: probe well-known feed paths.

use std::time::Duration;

use reqwest::Client;
use url::Url;

use crate::models::DiscoveredFeed;
use crate::parse;

/// Well-known feed paths probed as a last resort.
pub const FEED_PATHS: &[&str] = &[
    "/feed/",
    "/feed",
    "/feed.xml",
    "/feed.json",
    "/index.xml",
    "/atom.xml",
    "/atom",
    "/rss",
    "/rss/",
    "/rss.xml",
    "/blog?format=rss",
    "/feeds/posts/default",
];

const PROBE_TIMEOUT: Duration = Duration::from_secs(3);

/// Probe `url`'s domain root and parent directory for common feed paths.
pub async fn probe_common_paths(client: &Client, url: &str) -> Vec<DiscoveredFeed> {
    let Ok(parsed) = Url::parse(url) else {
        return Vec::new();
    };
    // Use the full origin so non-default ports are preserved.
    let base = parsed.origin().ascii_serialization();

    let mut prefixes = vec![base.clone()];
    let stripped = parsed.path().trim_end_matches('/');
    if let Some(idx) = stripped.rfind('/') {
        let parent = &stripped[..idx];
        if !parent.is_empty() && parent != "/" {
            prefixes.push(format!("{base}{parent}"));
        }
    }

    let mut feeds = Vec::new();
    let mut seen = std::collections::HashSet::new();

    for prefix in prefixes {
        for path in FEED_PATHS {
            let feed_url = format!("{prefix}{path}");
            if !seen.insert(feed_url.clone()) {
                continue;
            }
            let Ok(resp) = client
                .get(&feed_url)
                .timeout(PROBE_TIMEOUT)
                .send()
                .await
                .and_then(reqwest::Response::error_for_status)
            else {
                continue;
            };
            let final_url = resp.url().to_string();
            let Ok(bytes) = resp.bytes().await else {
                continue;
            };
            if let Some(title) = parse::feed_title(&bytes) {
                let title = if title.trim().is_empty() {
                    feed_url.clone()
                } else {
                    title
                };
                feeds.push((final_url, title));
            }
        }
    }

    feeds
}

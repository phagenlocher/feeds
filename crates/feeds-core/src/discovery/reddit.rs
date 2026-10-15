//! Reddit feed discovery.

use reqwest::Client;
use url::Url;

use super::utils::validate_feed;
use crate::models::DiscoveredFeed;

/// Map a Reddit URL to its `.rss` feed URL, if it matches a known pattern.
pub fn reddit_feed_url(url: &str) -> Option<String> {
    let parsed = Url::parse(url).ok()?;
    let host = parsed.host_str()?.to_ascii_lowercase();
    if !host.contains("reddit.com") {
        return None;
    }
    let path = parsed.path().trim_end_matches('/');

    if let Some(rest) = path.strip_prefix("/r/") {
        let name = first_segment(rest)?;
        return Some(format!("https://www.reddit.com/r/{name}/.rss"));
    }
    if let Some(rest) = path.strip_prefix("/user/") {
        let name = first_segment(rest)?;
        return Some(format!("https://www.reddit.com/user/{name}/.rss"));
    }
    None
}

/// Discover a Reddit feed from `url`.
pub async fn try_reddit(client: &Client, url: &str) -> Vec<DiscoveredFeed> {
    let Some(feed_url) = reddit_feed_url(url) else {
        return Vec::new();
    };
    tracing::info!("detected Reddit feed: {feed_url}");
    validate_feed(client, &feed_url).await
}

fn first_segment(path: &str) -> Option<&str> {
    let segment = path.split('/').next().unwrap_or("");
    if segment.is_empty() {
        None
    } else {
        Some(segment)
    }
}

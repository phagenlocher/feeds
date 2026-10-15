//! Medium feed discovery.

use reqwest::Client;
use url::Url;

use super::utils::validate_feed;
use crate::models::DiscoveredFeed;

/// Internal/utility paths that never yield a Medium feed.
const SKIP_SEGMENTS: &[&str] = &[
    "tag",
    "topic",
    "search",
    "settings",
    "me",
    "new-story",
    "sign-in",
    "sign-up",
    "m",
    "_",
];

/// Discover a Medium feed from `url`.
pub async fn try_medium(client: &Client, url: &str) -> Vec<DiscoveredFeed> {
    let Ok(parsed) = Url::parse(url) else {
        return Vec::new();
    };
    let Some(host) = parsed.host_str() else {
        return Vec::new();
    };
    if !host.to_ascii_lowercase().contains("medium.com") {
        return Vec::new();
    }

    let path = parsed.path().trim_end_matches('/');
    if path.is_empty() {
        return Vec::new();
    }
    let first = path.trim_start_matches('/').split('/').next().unwrap_or("");
    if first.is_empty() || SKIP_SEGMENTS.contains(&first) {
        tracing::debug!("Medium non-feed path skipped: {path}");
        return Vec::new();
    }

    tracing::info!("detected Medium publication/user: {first}");
    validate_feed(client, &format!("https://medium.com/feed/{first}")).await
}

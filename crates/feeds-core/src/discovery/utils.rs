//! Shared helpers for feed discovery.

use std::time::Duration;

use reqwest::Client;

use crate::models::DiscoveredFeed;
use crate::parse;

/// Timeout used when validating candidate feed URLs.
pub const FEED_TIMEOUT: Duration = Duration::from_secs(10);

/// Fetch `feed_url` and confirm it returns parseable feed content.
///
/// Returns `[(final_url, title)]` on success, or an empty vector.
pub async fn validate_feed(client: &Client, feed_url: &str) -> Vec<DiscoveredFeed> {
    let resp = match client.get(feed_url).timeout(FEED_TIMEOUT).send().await {
        Ok(resp) => resp,
        Err(e) => {
            tracing::debug!("feed {feed_url} is not valid (http: {e})");
            return Vec::new();
        }
    };
    let resp = match resp.error_for_status() {
        Ok(resp) => resp,
        Err(e) => {
            tracing::debug!("feed {feed_url} is not valid (status: {e})");
            return Vec::new();
        }
    };
    let final_url = resp.url().to_string();
    let bytes = match resp.bytes().await {
        Ok(bytes) => bytes,
        Err(_) => return Vec::new(),
    };
    match parse::feed_title(&bytes) {
        Some(title) => vec![(final_url, title)],
        None => Vec::new(),
    }
}

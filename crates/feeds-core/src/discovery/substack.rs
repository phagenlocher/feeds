//! Substack feed discovery.

use reqwest::Client;
use url::Url;

use super::utils::validate_feed;
use crate::models::DiscoveredFeed;

/// Discover a Substack feed from `url`.
pub async fn try_substack(client: &Client, url: &str) -> Vec<DiscoveredFeed> {
    let Ok(parsed) = Url::parse(url) else {
        return Vec::new();
    };
    let Some(hostname) = parsed.host_str() else {
        return Vec::new();
    };
    let hostname = hostname.to_ascii_lowercase();
    if !hostname.ends_with(".substack.com") {
        return Vec::new();
    }
    let subdomain = hostname.trim_end_matches(".substack.com");
    if subdomain.is_empty() {
        return Vec::new();
    }
    tracing::info!("detected Substack newsletter: {subdomain}");
    validate_feed(client, &format!("https://{hostname}/feed")).await
}

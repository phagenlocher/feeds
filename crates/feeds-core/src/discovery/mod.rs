//! Feed discovery pipeline.
//!
//! Stages, tried in order, with the first non-empty handler result winning:
//!
//! 1. Platform pre-handlers (Substack, Medium, Reddit, YouTube)
//! 2. Direct feed parsing of the fetched response
//! 3. HTML `<link rel="alternate">` tags
//! 4. HTTP `Link` headers (RFC 8288)
//! 5. Common-path probing

pub mod common_paths;
pub mod html;
pub mod link_header;
pub mod medium;
pub mod reddit;
pub mod substack;
pub mod utils;
pub mod youtube;

use std::time::Duration;

use reqwest::{header, Client, Response};

use crate::error::Result;
use crate::http::{self, ConditionalHeaders};
use crate::models::DiscoveredFeed;
use crate::parse;

/// Recognised feed MIME types for autodiscovery.
pub const FEED_MIME_TYPES: [&str; 3] = [
    "application/rss+xml",
    "application/atom+xml",
    "application/feed+json",
];

/// Whether `mime` is a recognised feed MIME type.
pub fn is_feed_mime(mime: &str) -> bool {
    FEED_MIME_TYPES.contains(&mime)
}

const DISCOVERY_TIMEOUT: Duration = Duration::from_secs(10);

/// Discover feed URLs from `url`.
pub async fn discover_feeds(client: &Client, url: &str) -> Result<Vec<DiscoveredFeed>> {
    tracing::info!("discovering feeds from {url}");

    // Stage 1: platform pre-handlers.
    for feeds in [
        substack::try_substack(client, url).await,
        medium::try_medium(client, url).await,
        reddit::try_reddit(client, url).await,
        youtube::try_youtube(client, url).await,
    ] {
        if !feeds.is_empty() {
            return Ok(feeds);
        }
    }

    // Stage 2..5: fetch and inspect the response.
    let resp = match http::get_with_retry(
        client,
        url,
        &ConditionalHeaders::default(),
        DISCOVERY_TIMEOUT,
    )
    .await
    .and_then(|r| r.error_for_status().map_err(crate::error::Error::Http))
    {
        Ok(resp) => resp,
        Err(e) => {
            tracing::warn!("failed to fetch {url} for feed discovery: {e}");
            // Surface the failure instead of reporting "no feeds found": the
            // user needs to distinguish a broken URL from a network/server
            // error.
            return Err(e);
        }
    };

    Ok(extract_feeds_from_response(client, resp, url).await)
}

async fn extract_feeds_from_response(
    client: &Client,
    resp: Response,
    original_url: &str,
) -> Vec<DiscoveredFeed> {
    let final_url = resp.url().to_string();
    let content_type = resp
        .headers()
        .get(header::CONTENT_TYPE)
        .and_then(|v| v.to_str().ok())
        .unwrap_or("")
        .to_string();
    let link_header = resp
        .headers()
        .get(header::LINK)
        .and_then(|v| v.to_str().ok())
        .map(str::to_string);

    let Ok(bytes) = resp.bytes().await else {
        return Vec::new();
    };

    let mut feeds: Vec<DiscoveredFeed> = Vec::new();
    let mut seen = std::collections::HashSet::new();

    // Method 1: the response itself is a feed.
    if let Ok(parsed) = parse::parse_bytes(&bytes) {
        tracing::debug!(
            "{original_url} is a feed directly (version={})",
            parsed.version
        );
        let title = parsed.title.filter(|t| !t.trim().is_empty());
        return vec![(
            original_url.to_string(),
            title.unwrap_or_else(|| original_url.to_string()),
        )];
    }

    let is_html =
        content_type.contains("text/html") || content_type.contains("application/xhtml+xml");

    // Method 2: HTML <link> tags.
    if is_html {
        let text = String::from_utf8_lossy(&bytes);
        for (href, title) in html::extract_feed_links(&text, &final_url) {
            if seen.insert(href.clone()) {
                feeds.push((href, title));
            }
        }
    }

    // Method 3: HTTP Link headers.
    if let Some(header_value) = link_header {
        for (href, title) in link_header::parse_link_header(&header_value, &final_url) {
            if seen.insert(href.clone()) {
                feeds.push((href, title));
            }
        }
    }

    // Method 4: common-path probing (HTML only, and only if still empty).
    if feeds.is_empty() && is_html {
        for (href, title) in common_paths::probe_common_paths(client, &final_url).await {
            if seen.insert(href.clone()) {
                feeds.push((href, title));
            }
        }
    }

    feeds
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn recognizes_feed_mime_types() {
        assert!(is_feed_mime("application/rss+xml"));
        assert!(is_feed_mime("application/atom+xml"));
        assert!(is_feed_mime("application/feed+json"));
        assert!(!is_feed_mime("text/html"));
    }
}

//! YouTube feed discovery.
//!
//! YouTube blocks automated page access with a consent wall, so we never
//! fetch YouTube HTML. Instead we derive the feed URL from the URL pattern
//! or via the `oEmbed` / `resolve_url` APIs, both of which work without
//! consent.

use std::time::Duration;

use reqwest::Client;
use serde_json::json;
use url::Url;

use super::utils::validate_feed;
use crate::models::DiscoveredFeed;

const OEMBED_TIMEOUT: Duration = Duration::from_secs(5);
const YOUTUBE_CLIENT_VERSION: &str = "2.20250101.00.00";

/// Discover a YouTube channel feed from `url`.
pub async fn try_youtube(client: &Client, url: &str) -> Vec<DiscoveredFeed> {
    let Ok(parsed) = Url::parse(url) else {
        return Vec::new();
    };
    let host = parsed.host_str().unwrap_or("").to_ascii_lowercase();
    if !host.contains("youtube.com") && !host.contains("youtu.be") {
        return Vec::new();
    }
    let path = parsed.path().trim_end_matches('/');

    // /channel/UC_ID
    if let Some(rest) = path.strip_prefix("/channel/") {
        let id = first_segment(rest);
        if id.starts_with("UC") && id.len() >= 24 {
            return channel_feed(client, id).await;
        }
    }

    // /user/NAME (username-based channel URL)
    if let Some(rest) = path.strip_prefix("/user/") {
        let name = first_segment(rest);
        if !name.is_empty() {
            return user_feed(client, name).await;
        }
    }

    // /c/NAME or /@HANDLE
    if let Some(rest) = path.strip_prefix("/c/").or_else(|| path.strip_prefix("/@")) {
        let name = first_segment(rest);
        if !name.is_empty() {
            if let Some(channel_id) = resolve_channel_id(client, url).await {
                return channel_feed(client, &channel_id).await;
            }
        }
    }

    // /watch?v=VIDEO_ID
    if path == "/watch" {
        if let Some((_, id)) = parsed.query_pairs().find(|(k, _)| k == "v") {
            return feed_from_video_id(client, &id).await;
        }
    }

    // /shorts/ID and /embed/ID
    for prefix in ["/shorts/", "/embed/"] {
        if let Some(rest) = path.strip_prefix(prefix) {
            let id = first_segment(rest);
            if !id.is_empty() {
                return feed_from_video_id(client, id).await;
            }
        }
    }

    // youtu.be/VIDEO_ID
    if host.contains("youtu.be") {
        let id = path.trim_start_matches('/');
        if !id.is_empty() && !id.contains('/') {
            return feed_from_video_id(client, id).await;
        }
    }

    Vec::new()
}

fn first_segment(path: &str) -> &str {
    path.split('/').next().unwrap_or("")
}

async fn channel_feed(client: &Client, channel_id: &str) -> Vec<DiscoveredFeed> {
    validate_feed(
        client,
        &format!("https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"),
    )
    .await
}

async fn user_feed(client: &Client, user: &str) -> Vec<DiscoveredFeed> {
    validate_feed(
        client,
        &format!("https://www.youtube.com/feeds/videos.xml?user={user}"),
    )
    .await
}

/// Resolve a channel URL to a `UC...` channel ID via the `resolve_url` API.
async fn resolve_channel_id(client: &Client, channel_url: &str) -> Option<String> {
    let body = json!({
        "context": { "client": { "clientName": "WEB", "clientVersion": YOUTUBE_CLIENT_VERSION } },
        "url": channel_url,
    });
    let resp = client
        .post("https://www.youtube.com/youtubei/v1/navigation/resolve_url")
        .json(&body)
        .timeout(OEMBED_TIMEOUT)
        .send()
        .await
        .ok()?
        .error_for_status()
        .ok()?;
    let value: serde_json::Value = resp.json().await.ok()?;
    let browse_id = value
        .get("endpoint")?
        .get("browseEndpoint")?
        .get("browseId")?
        .as_str()?;
    if browse_id.starts_with("UC") {
        Some(browse_id.to_string())
    } else {
        None
    }
}

/// Resolve a video ID to a channel feed via the oEmbed API.
async fn feed_from_video_id(client: &Client, video_id: &str) -> Vec<DiscoveredFeed> {
    let url = format!(
        "https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
    );
    let Some(value) = client
        .get(url)
        .timeout(OEMBED_TIMEOUT)
        .send()
        .await
        .ok()
        .and_then(|r| r.error_for_status().ok())
    else {
        return Vec::new();
    };
    let Some(value) = value.json::<serde_json::Value>().await.ok() else {
        return Vec::new();
    };
    let Some(author_url) = value.get("author_url").and_then(|v| v.as_str()) else {
        return Vec::new();
    };

    if let Some(rest) = author_url.split("/user/").nth(1) {
        let name = first_segment(rest);
        if !name.is_empty() {
            let feeds = user_feed(client, name).await;
            if !feeds.is_empty() {
                return feeds;
            }
        }
    }

    match resolve_channel_id(client, author_url).await {
        Some(id) => channel_feed(client, &id).await,
        None => Vec::new(),
    }
}

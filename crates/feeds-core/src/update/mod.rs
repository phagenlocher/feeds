//! Feed update engine: conditional GET, parsing, de-duplication, scheduling.

use std::time::Duration;

use chrono::{Duration as ChronoDuration, Utc};
use futures::stream::{self, StreamExt};
use reqwest::Client;
use serde::{Deserialize, Serialize};

use crate::error::{Error, Result};
use crate::http::{self, ConditionalHeaders};
use crate::parse;
use crate::store::{Store, UpdateOutcome, DEFAULT_UPDATE_INTERVAL_MINUTES};

/// Caching info persisted for conditional GETs.
#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq, Eq)]
pub struct CachingInfo {
    /// `ETag` header value.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub etag: Option<String>,
    /// `Last-Modified` header value.
    #[serde(rename = "last-modified", skip_serializing_if = "Option::is_none")]
    pub last_modified: Option<String>,
}

impl CachingInfo {
    fn from_json(raw: Option<&str>) -> Self {
        raw.and_then(|s| serde_json::from_str(s).ok())
            .unwrap_or_default()
    }

    fn to_json(&self) -> Option<String> {
        if self.etag.is_none() && self.last_modified.is_none() {
            None
        } else {
            serde_json::to_string(self).ok()
        }
    }

    fn conditional(&self) -> ConditionalHeaders {
        ConditionalHeaders {
            if_none_match: self.etag.clone(),
            if_modified_since: self.last_modified.clone(),
        }
    }
}

const FETCH_TIMEOUT: Duration = Duration::from_secs(30);

/// A feed that could not be updated, with a reason suitable for display.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct UpdateFailure {
    /// Feed URL.
    pub url: String,
    /// Display title of the feed, falling back to its URL.
    pub title: String,
    /// Human-readable failure reason.
    pub error: String,
}

/// Report summarising a multi-feed update.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct UpdateReport {
    /// Number of feeds updated successfully.
    pub updated: usize,
    /// Number of newly inserted entries across all feeds.
    pub new_entries: usize,
    /// Number of feeds that failed to update.
    pub failed: usize,
    /// Details of every failed feed, including title and reason.
    pub failures: Vec<UpdateFailure>,
}

/// Fetch and store a single feed.
pub async fn update_feed(store: &Store, client: &Client, url: &str) -> Result<UpdateOutcome> {
    tracing::info!("updating feed {url}");
    match update_feed_inner(store, client, url).await {
        Ok(outcome) => Ok(outcome),
        Err(e) => {
            tracing::warn!("feed update failed for {url}: {e}");
            Err(e)
        }
    }
}

/// Fetch and store a single feed, without the surrounding failure log.
async fn update_feed_inner(store: &Store, client: &Client, url: &str) -> Result<UpdateOutcome> {
    let state = store
        .feed_update_state(url)?
        .ok_or_else(|| Error::FeedNotFound(url.to_string()))?;
    if !state.updates_enabled {
        return Ok(noop_outcome(url, None, store));
    }

    let caching = CachingInfo::from_json(state.caching_info.as_deref());
    let resp = match http::get_with_retry(client, url, &caching.conditional(), FETCH_TIMEOUT).await
    {
        Ok(resp) => resp,
        Err(e) => {
            store.record_update_error(url, &e.to_string())?;
            return Err(e);
        }
    };

    if resp.status() == reqwest::StatusCode::NOT_MODIFIED {
        tracing::debug!("feed {url} not modified (304)");
        store.apply_not_modified(url, Utc::now())?;
        return Ok(noop_outcome(url, None, store));
    }

    let resp = match resp.error_for_status() {
        Ok(resp) => resp,
        Err(e) => {
            store.record_update_error(url, &e.to_string())?;
            return Err(Error::Http(e));
        }
    };

    let (etag, last_modified) = http::caching_from_response(&resp);
    let bytes = match resp.bytes().await {
        Ok(bytes) => bytes,
        Err(e) => {
            let error = Error::Http(e);
            store.record_update_error(url, &error.to_string())?;
            return Err(error);
        }
    };

    let parsed = match parse::parse_bytes(&bytes) {
        Ok(parsed) => parsed,
        Err(e) => {
            store.record_update_error(url, &e.to_string())?;
            return Err(e);
        }
    };

    let caching_json = CachingInfo {
        etag,
        last_modified,
    }
    .to_json();
    store.apply_update(url, &parsed, caching_json, Utc::now())
}

fn noop_outcome(url: &str, title: Option<String>, store: &Store) -> UpdateOutcome {
    UpdateOutcome {
        url: url.to_string(),
        title,
        new_entries: 0,
        total_entries: usize::try_from(store.entry_count(url).unwrap_or(0).max(0))
            .unwrap_or_default(),
    }
}

/// Update the given set of feeds concurrently.
pub async fn update_urls(store: &Store, client: &Client, urls: Vec<String>) -> UpdateReport {
    if urls.is_empty() {
        return UpdateReport::default();
    }
    let workers = default_workers(urls.len());
    tracing::info!("updating {} feed(s) with {} workers", urls.len(), workers);

    let results: Vec<(String, Result<UpdateOutcome>)> = stream::iter(urls)
        .map(|url| async move {
            let result = update_feed(store, client, &url).await;
            (url, result)
        })
        .buffer_unordered(workers)
        .collect()
        .await;

    let mut report = UpdateReport::default();
    for (url, result) in results {
        match result {
            Ok(outcome) => {
                report.updated += 1;
                report.new_entries += outcome.new_entries;
            }
            // `update_feed` already logged the failing URL and reason.
            Err(e) => {
                report.failed += 1;
                report.failures.push(UpdateFailure {
                    title: failure_title(store, &url),
                    url,
                    error: e.to_string(),
                });
            }
        }
    }
    report
}

/// Best display name for a feed that failed to update.
fn failure_title(store: &Store, url: &str) -> String {
    store
        .get_feed(url)
        .ok()
        .flatten()
        .map(|feed| feed.title)
        .filter(|title| !title.trim().is_empty())
        .unwrap_or_else(|| url.to_string())
}

/// Update all feeds, optionally honouring the schedule.
pub async fn update_feeds(store: &Store, client: &Client, scheduled: bool) -> Result<UpdateReport> {
    let now = Utc::now();
    let urls = store.feeds_to_update(scheduled, now)?;
    if urls.is_empty() {
        tracing::info!("no feeds to update");
        return Ok(UpdateReport::default());
    }
    Ok(update_urls(store, client, urls).await)
}

fn default_workers(feed_count: usize) -> usize {
    let cpus = std::thread::available_parallelism().map_or(1, std::num::NonZeroUsize::get);
    feed_count.min(cpus * 2).max(1)
}

/// Next scheduled update time given an interval.
pub fn next_update_after(now: chrono::DateTime<Utc>) -> chrono::DateTime<Utc> {
    now + ChronoDuration::minutes(DEFAULT_UPDATE_INTERVAL_MINUTES)
}

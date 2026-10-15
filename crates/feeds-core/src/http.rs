//! Shared HTTP client and retry helpers.

use std::time::Duration;

use backon::{ExponentialBuilder, Retryable};
use reqwest::{header, Client, Response};

use crate::error::{Error, Result};

/// Build the shared HTTP client with the given user agent.
pub fn build_client(user_agent: &str) -> Client {
    Client::builder()
        .user_agent(user_agent)
        .timeout(Duration::from_secs(30))
        .build()
        .unwrap_or_else(|_| Client::new())
}

/// Conditional-request headers derived from stored caching info.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct ConditionalHeaders {
    /// `If-None-Match` value.
    pub if_none_match: Option<String>,
    /// `If-Modified-Since` value.
    pub if_modified_since: Option<String>,
}

impl ConditionalHeaders {
    fn apply(&self, mut req: reqwest::RequestBuilder) -> reqwest::RequestBuilder {
        if let Some(etag) = &self.if_none_match {
            req = req.header(header::IF_NONE_MATCH, etag);
        }
        if let Some(lm) = &self.if_modified_since {
            req = req.header(header::IF_MODIFIED_SINCE, lm);
        }
        req
    }
}

fn backoff() -> ExponentialBuilder {
    ExponentialBuilder::default()
        // Two retries after the initial request: three attempts in total.
        .with_max_times(2)
        .with_min_delay(Duration::from_secs(1))
        .with_max_delay(Duration::from_secs(10))
}

/// GET `url` with exponential-backoff retry (3 attempts in total).
pub async fn get_with_retry(
    client: &Client,
    url: &str,
    conditional: &ConditionalHeaders,
    timeout: Duration,
) -> Result<Response> {
    (|| async {
        conditional
            .apply(client.get(url).timeout(timeout))
            .send()
            .await
    })
    .retry(backoff())
    .await
    .map_err(Error::Http)
}

/// Extract `(etag, last_modified)` from a response, if present.
pub fn caching_from_response(resp: &Response) -> (Option<String>, Option<String>) {
    let etag = resp
        .headers()
        .get(header::ETAG)
        .and_then(|v| v.to_str().ok())
        .map(str::to_string);
    let last_modified = resp
        .headers()
        .get(header::LAST_MODIFIED)
        .and_then(|v| v.to_str().ok())
        .map(str::to_string);
    (etag, last_modified)
}

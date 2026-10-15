//! Error types for `feeds-core`.

use thiserror::Error;

/// Result alias used throughout the crate.
pub type Result<T> = std::result::Result<T, Error>;

/// Errors produced by `feeds-core`.
#[derive(Debug, Error)]
pub enum Error {
    /// A database operation failed.
    #[error("database error: {0}")]
    Database(#[from] rusqlite::Error),

    /// An HTTP request failed.
    #[error("http error: {0}")]
    Http(#[from] reqwest::Error),

    /// A URL could not be parsed.
    #[error("invalid url: {0}")]
    Url(#[from] url::ParseError),

    /// JSON (de)serialization failed.
    #[error("json error: {0}")]
    Json(#[from] serde_json::Error),

    /// A timestamps could not be parsed.
    #[error("invalid timestamp: {0}")]
    Timestamp(String),

    /// A feed could not be parsed.
    #[error("feed parse error: {0}")]
    FeedParse(String),

    /// An I/O operation failed.
    #[error("io error: {0}")]
    Io(#[from] std::io::Error),

    /// A requested feed does not exist.
    #[error("feed not found: {0}")]
    FeedNotFound(String),

    /// The directory containing the database could not be created.
    #[error("could not create data directory: {0}")]
    DataDir(String),

    /// A retryable operation exhausted its attempts.
    #[error("operation failed after retries: {0}")]
    Retry(String),

    /// An OPML document could not be parsed or generated.
    #[error("opml error: {0}")]
    Opml(String),
}

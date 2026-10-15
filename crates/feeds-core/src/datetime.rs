//! Timestamp helpers.
//!
//! Timestamps are stored as RFC 3339. Parsing also accepts a space-separated
//! ISO 8601 form (`2024-01-01 12:00:00+00:00`, or without an offset as naive
//! UTC), which feed timestamps occasionally use.

use chrono::{DateTime, NaiveDateTime, Utc};

use crate::error::{Error, Result};

/// Format a timestamp as RFC 3339 for storage.
pub fn format(dt: &DateTime<Utc>) -> String {
    dt.to_rfc3339()
}

/// Parse a timestamp, accepting RFC 3339 and a space-separated ISO 8601 form
/// (with or without an offset).
pub fn parse(raw: &str) -> Result<DateTime<Utc>> {
    if let Ok(dt) = DateTime::parse_from_rfc3339(raw) {
        return Ok(dt.with_timezone(&Utc));
    }
    for fmt in ["%Y-%m-%d %H:%M:%S%.f%:z", "%Y-%m-%d %H:%M:%S%.f"] {
        if let Ok(dt) = DateTime::parse_from_str(raw, fmt) {
            return Ok(dt.with_timezone(&Utc));
        }
        if let Ok(naive) = NaiveDateTime::parse_from_str(raw, fmt) {
            return Ok(naive.and_utc());
        }
    }
    Err(Error::Timestamp(raw.to_string()))
}

/// Parse an optional timestamp column.
pub fn parse_opt(raw: Option<String>) -> Option<DateTime<Utc>> {
    raw.as_deref().and_then(|s| parse(s).ok())
}

/// Current time as UTC.
pub fn now() -> DateTime<Utc> {
    Utc::now()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_rfc3339() {
        let dt = parse("2024-01-01T12:00:00+00:00").unwrap();
        assert_eq!(dt.to_rfc3339(), "2024-01-01T12:00:00+00:00");
    }

    #[test]
    fn parses_reader_space_form_with_offset() {
        let dt = parse("2024-01-01 12:00:00+00:00").unwrap();
        assert_eq!(dt.to_rfc3339(), "2024-01-01T12:00:00+00:00");
    }

    #[test]
    fn parses_reader_space_form_naive_as_utc() {
        let dt = parse("2024-01-01 12:00:00").unwrap();
        assert_eq!(dt.to_rfc3339(), "2024-01-01T12:00:00+00:00");
    }

    #[test]
    fn round_trips() {
        let dt = now();
        assert_eq!(parse(&format(&dt)).unwrap(), dt);
    }
}

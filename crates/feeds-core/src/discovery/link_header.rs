//! RFC 8288 / RFC 5988 `Link` header parsing.
//!
//! Extracts feed URLs advertised by HTTP `Link` headers during discovery.

use url::Url;

/// Parse a `Link` header value, returning `(url, title)` for every link
/// whose `rel` is `alternate` and whose `type` is a known feed MIME type.
pub fn parse_link_header(value: &str, base_url: &str) -> Vec<(String, String)> {
    let base = Url::parse(base_url).ok();
    let mut out = Vec::new();

    for entry in split_entries(value) {
        let parts = split_params(&entry);
        let mut it = parts.into_iter();
        let Some(target) = it.next() else { continue };
        let target = target.trim();
        if !target.starts_with('<') || !target.ends_with('>') {
            continue;
        }
        let href = &target[1..target.len() - 1];

        let mut rel = String::new();
        let mut link_type = String::new();
        let mut title = String::new();
        for param in it {
            let Some((k, v)) = param.split_once('=') else {
                continue;
            };
            let k = k.trim().to_ascii_lowercase();
            let v = unquote(v.trim());
            match k.as_str() {
                "rel" => rel = v.to_ascii_lowercase(),
                "type" => link_type = v.to_ascii_lowercase(),
                "title" => title = v,
                _ => {}
            }
        }

        if rel == "alternate" && crate::discovery::is_feed_mime(&link_type) && !href.is_empty() {
            let resolved = base
                .as_ref()
                .and_then(|b| b.join(href).ok())
                .map(|u| u.to_string())
                .unwrap_or_else(|| href.to_string());
            let title = if title.is_empty() {
                resolved.clone()
            } else {
                title
            };
            out.push((resolved, title));
        }
    }

    out
}

/// Split a header value into individual link entries on top-level commas.
fn split_entries(value: &str) -> Vec<String> {
    let mut entries = Vec::new();
    let mut current = String::new();
    let mut in_quotes = false;
    let mut in_angle = false;
    for c in value.chars() {
        match c {
            '"' => {
                in_quotes = !in_quotes;
                current.push(c);
            }
            '<' if !in_quotes => {
                in_angle = true;
                current.push(c);
            }
            '>' if !in_quotes => {
                in_angle = false;
                current.push(c);
            }
            ',' if !in_quotes && !in_angle => {
                entries.push(std::mem::take(&mut current));
            }
            _ => current.push(c),
        }
    }
    if !current.trim().is_empty() {
        entries.push(current);
    }
    entries
}

/// Split a single entry into `;`-separated parts, respecting quotes.
fn split_params(entry: &str) -> Vec<String> {
    let mut parts = Vec::new();
    let mut current = String::new();
    let mut in_quotes = false;
    for c in entry.chars() {
        match c {
            '"' => {
                in_quotes = !in_quotes;
                current.push(c);
            }
            ';' if !in_quotes => {
                parts.push(std::mem::take(&mut current));
            }
            _ => current.push(c),
        }
    }
    parts.push(current);
    parts
}

fn unquote(value: &str) -> String {
    let trimmed = value.trim();
    trimmed
        .strip_prefix('"')
        .and_then(|v| v.strip_suffix('"'))
        .unwrap_or(trimmed)
        .to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_feed_link_header() {
        let header = r#"</feed.xml>; rel="alternate"; type="application/rss+xml"; title="RSS""#;
        let links = parse_link_header(header, "https://example.com/blog");
        assert_eq!(
            links,
            vec![(
                "https://example.com/feed.xml".to_string(),
                "RSS".to_string()
            )]
        );
    }

    #[test]
    fn ignores_non_feed_types() {
        let header = r#"</style.css>; rel="stylesheet"; type="text/css""#;
        assert!(parse_link_header(header, "https://example.com/").is_empty());
    }

    #[test]
    fn handles_multiple_entries() {
        let header = concat!(
            r#"</a.xml>; rel="alternate"; type="application/atom+xml","#,
            r#"</rss.xml>; rel="alternate"; type="application/rss+xml""#
        );
        let links = parse_link_header(header, "https://example.com/");
        assert_eq!(links.len(), 2);
        assert_eq!(links[0].0, "https://example.com/a.xml");
        assert_eq!(links[1].0, "https://example.com/rss.xml");
    }
}

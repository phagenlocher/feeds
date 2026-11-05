//! HTML `<link rel="alternate">` autodiscovery.

use scraper::{Html, Selector};
use url::Url;

use super::is_feed_mime;
use crate::models::DiscoveredFeed;

/// Extract feed links from an HTML document.
///
/// Honours `<base href>` for relative URL resolution. Returns one
/// [`DiscoveredFeed`] per match, in document order.
///
/// # Panics
///
/// Panics only if the built-in `base`/`link` selector patterns stop being
/// valid, which the literals rule out.
#[expect(
    clippy::expect_used,
    reason = "the selector patterns are literals known to be valid"
)]
pub fn extract_feed_links(html: &str, page_url: &str) -> Vec<DiscoveredFeed> {
    let document = Html::parse_document(html);

    // Resolve the base URL (<base href> if present, else the page URL).
    let base_selector = Selector::parse("base").expect("valid selector");
    let base_href = document
        .select(&base_selector)
        .find_map(|el| el.value().attr("href"))
        .map(str::to_string);
    let base_url: Option<Url> = base_href
        .as_deref()
        .and_then(|href| Url::parse(page_url).ok()?.join(href).ok())
        .or_else(|| Url::parse(page_url).ok());

    let link_selector = Selector::parse("link").expect("valid selector");
    let mut feeds = Vec::new();

    for element in document.select(&link_selector) {
        let value = element.value();
        let rel = value.attr("rel").unwrap_or("").trim();
        let link_type = value.attr("type").unwrap_or("").to_ascii_lowercase();
        let href = value.attr("href").unwrap_or("");

        if href.is_empty() {
            continue;
        }
        if !rel.split_whitespace().any(|r| r == "alternate") {
            continue;
        }
        if !is_feed_mime(&link_type) {
            continue;
        }

        let resolved = base_url
            .as_ref()
            .and_then(|b| b.join(href).ok())
            .map_or_else(|| href.to_string(), |u| u.to_string());
        let title = value
            .attr("title")
            .map_or_else(|| resolved.clone(), str::to_string);
        feeds.push(DiscoveredFeed {
            url: resolved,
            title,
        });
    }

    feeds
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn finds_rss_and_atom_links() {
        let html = r#"<html><head>
            <link rel="alternate" type="application/rss+xml" title="RSS" href="/feed">
            <link rel="alternate" type="application/atom+xml" title="Atom" href="/atom.xml">
            <link rel="stylesheet" type="text/css" href="/style.css">
        </head></html>"#;
        let feeds = extract_feed_links(html, "https://example.com/blog/");
        assert_eq!(feeds.len(), 2);
        assert_eq!(
            feeds[0],
            DiscoveredFeed {
                url: "https://example.com/feed".to_string(),
                title: "RSS".to_string(),
            }
        );
        assert_eq!(feeds[1].url, "https://example.com/atom.xml");
    }

    #[test]
    fn honours_base_href() {
        let html = r#"<html><head>
            <base href="https://cdn.example.com/">
            <link rel="alternate" type="application/rss+xml" href="feed.xml">
        </head></html>"#;
        let feeds = extract_feed_links(html, "https://example.com/");
        assert_eq!(feeds[0].url, "https://cdn.example.com/feed.xml");
    }

    #[test]
    fn supports_multi_value_rel() {
        let html = r#"<link rel="stylesheet alternate" type="application/rss+xml" href="/f">"#;
        let feeds = extract_feed_links(html, "https://example.com/");
        assert_eq!(feeds.len(), 1);
    }

    #[test]
    fn ignores_missing_alternate() {
        let html = r#"<link rel="stylesheet" type="application/rss+xml" href="/f">"#;
        assert_eq!(extract_feed_links(html, "https://example.com/"), []);
    }
}

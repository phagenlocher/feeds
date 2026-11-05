//! OPML import and export.

use opml::OPML;

use crate::error::{Error, Result};
use crate::models::Feed;

/// Serialize feeds as an OPML 2.0 subscription list.
pub fn export_feeds(feeds: &[Feed]) -> Result<String> {
    let mut opml = OPML::default();
    opml.head = Some(opml::Head {
        title: Some("feeds".to_string()),
        ..Default::default()
    });
    for feed in feeds {
        opml.add_feed(feed.display_title(), &feed.id);
    }
    opml.to_string().map_err(|e| Error::Opml(e.to_string()))
}

/// A feed parsed from an OPML outline.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ImportedFeed {
    /// Subscription URL from the outline's `xmlUrl`.
    pub url: String,
    /// Outline title/text, or `None` when blank.
    pub title: Option<String>,
}

/// Parse an OPML document into imported feeds.
pub fn import_feeds(xml: &str) -> Result<Vec<ImportedFeed>> {
    let opml = OPML::from_str(xml).map_err(|e| Error::Opml(e.to_string()))?;
    Ok(collect_outlines(&opml.body.outlines))
}

fn collect_outlines(outlines: &[opml::Outline]) -> Vec<ImportedFeed> {
    let mut out = Vec::new();
    for outline in outlines {
        if let Some(url) = &outline.xml_url {
            let title = outline
                .title
                .clone()
                .or_else(|| Some(outline.text.clone()))
                .filter(|t| !t.trim().is_empty());
            out.push(ImportedFeed {
                url: url.clone(),
                title,
            });
        }
        out.extend(collect_outlines(&outline.outlines));
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn round_trips_feeds() {
        let feeds = vec![
            Feed {
                id: "https://example.com/feed".into(),
                title: "Example".into(),
                last_updated: None,
                user_title: None,
            },
            Feed {
                id: "https://rust-lang.org/feed.xml".into(),
                title: "Rust Blog".into(),
                last_updated: None,
                user_title: None,
            },
        ];
        let xml = export_feeds(&feeds).unwrap();
        let imported = import_feeds(&xml).unwrap();
        assert_eq!(imported.len(), 2);
        assert_eq!(imported[0].url, "https://example.com/feed");
        assert_eq!(imported[0].title.as_deref(), Some("Example"));
    }

    #[test]
    fn handles_nested_outlines() {
        let xml = r#"<opml version="2.0"><head/><body>
            <outline text="Tech">
              <outline text="Rust" xmlUrl="https://rust-lang.org/feed.xml"/>
            </outline>
        </body></opml>"#;
        let imported = import_feeds(xml).unwrap();
        assert_eq!(
            imported,
            vec![ImportedFeed {
                url: "https://rust-lang.org/feed.xml".to_string(),
                title: Some("Rust".to_string()),
            }]
        );
    }
}

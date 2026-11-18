//! Fuzzy title matching for the UI's "filter entries" feature.
//!
//! This mirrors the former Python implementation, which used `RapidFuzz`'s
//! `fuzz.partial_ratio`: normalized Indel similarity (derived from the longest
//! common subsequence) over the best alignment of the shorter string in the
//! longer one.

// String lengths are far below 2^53, so converting them to `f64` is exact in
// practice and the similarity ratios the API promises are unaffected.
#![expect(
    clippy::cast_precision_loss,
    reason = "lengths are far below 2^53, so the cast is lossless here"
)]

use serde::Serialize;

/// A matched range in a title, in Unicode scalar-value offsets.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub struct MatchSpan {
    /// First matched character.
    pub start: usize,
    /// One past the last matched character.
    pub end: usize,
}

/// Default match threshold.
pub const PARTIAL_RATIO_THRESHOLD: f64 = 85.0;

/// Normalized Indel similarity (0–100).
pub fn ratio(a: &str, b: &str) -> f64 {
    let a: Vec<char> = a.chars().collect();
    let b: Vec<char> = b.chars().collect();
    ratio_chars(&a, &b)
}

/// Best [`ratio`] between the shorter string and any alignment of it in the
/// longer string, including prefix and suffix alignments.
pub fn partial_ratio(a: &str, b: &str) -> f64 {
    let a_chars = lower_chars(a);
    let b_chars = lower_chars(b);
    partial_ratio_chars(&a_chars, &b_chars)
}

/// The best-matching range in `title` for every whitespace-separated token in
/// `query`, or an empty vector when any token does not match above the default
/// threshold.
pub fn find_matches(query: &str, title: &str) -> Vec<MatchSpan> {
    if query.is_empty() || title.is_empty() {
        return Vec::new();
    }

    let (haystack, origin) = lower_chars_with_origin(title);
    if haystack.is_empty() {
        return Vec::new();
    }

    let mut spans = Vec::new();
    for token in query.split_whitespace() {
        let needle = lower_chars(token);
        if needle.is_empty() {
            continue;
        }
        let Some(span) = match_span(&needle, &haystack, &origin) else {
            return Vec::new();
        };
        spans.push(span);
    }
    merge_spans(spans)
}

fn match_span(needle: &[char], haystack: &[char], origin: &[usize]) -> Option<MatchSpan> {
    let (score, span) = if haystack.len() >= needle.len() {
        let (mut score, span) = best_alignment(needle, haystack);
        // RapidFuzz also tries the opposite direction for equal-length strings,
        // which lets a prefix or suffix of either string win.
        if score < 100.0 && needle.len() == haystack.len() {
            score = score.max(best_alignment(haystack, needle).0);
        }
        (score, span)
    } else {
        // The title is the needle, so no range inside it was recorded.
        (best_alignment(haystack, needle).0, None)
    };

    if score < PARTIAL_RATIO_THRESHOLD {
        return None;
    }

    let (start, end) = match span {
        Some((start, end)) if end > start => (start, end),
        _ => (0, haystack.len()),
    };
    Some(MatchSpan {
        start: origin[start],
        end: origin[end - 1] + 1,
    })
}

/// Sort spans and merge the ones that overlap.
fn merge_spans(mut spans: Vec<MatchSpan>) -> Vec<MatchSpan> {
    spans.sort_by_key(|span| span.start);
    let mut merged: Vec<MatchSpan> = Vec::with_capacity(spans.len());
    for span in spans {
        match merged.last_mut() {
            Some(last) if span.start <= last.end => last.end = last.end.max(span.end),
            _ => merged.push(span),
        }
    }
    merged
}

/// Whether `title` matches `query` above the default threshold.
pub fn matches(query: &str, title: &str) -> bool {
    if query.is_empty() {
        return true;
    }
    !find_matches(query, title).is_empty()
}

/// Lowercase `text`, recording the index of the original character that
/// produced each lowercased character. Lowercasing can expand a character
/// (e.g. `İ` becomes `i` plus a combining dot), so the two lengths differ.
fn lower_chars_with_origin(text: &str) -> (Vec<char>, Vec<usize>) {
    let mut chars = Vec::new();
    let mut origin = Vec::new();
    for (index, ch) in text.chars().enumerate() {
        for lower in ch.to_lowercase() {
            chars.push(lower);
            origin.push(index);
        }
    }
    (chars, origin)
}

fn lower_chars(text: &str) -> Vec<char> {
    text.chars().flat_map(char::to_lowercase).collect()
}

fn partial_ratio_chars(a: &[char], b: &[char]) -> f64 {
    if a.is_empty() || b.is_empty() {
        return if a.is_empty() && b.is_empty() {
            100.0
        } else {
            0.0
        };
    }

    let (short, long) = if a.len() <= b.len() { (a, b) } else { (b, a) };

    let (mut best, _) = best_alignment(short, long);
    if best < 100.0 && short.len() == long.len() {
        best = best.max(best_alignment(long, short).0);
    }
    best
}

/// Best score between `needle` and an alignment in `long`, together with the
/// character range in `long` that produced it.
fn best_alignment(needle: &[char], long: &[char]) -> (f64, Option<(usize, usize)>) {
    let mut best: f64 = 0.0;
    let mut span = None;

    if long.len() > needle.len() {
        for (start, window) in long.windows(needle.len()).enumerate() {
            let score = ratio_chars(needle, window);
            if score > best {
                best = score;
                span = Some((start, start + needle.len()));
            }
            if best >= 100.0 {
                return (100.0, span);
            }
        }
    }

    for end in 1..needle.len() {
        let score = ratio_chars(needle, &long[..end]);
        if score > best {
            best = score;
            span = Some((0, end));
        }
    }
    for start in (long.len() - needle.len())..long.len() {
        let score = ratio_chars(needle, &long[start..]);
        if score > best {
            best = score;
            span = Some((start, long.len()));
        }
    }
    (best, span)
}

fn ratio_chars(a: &[char], b: &[char]) -> f64 {
    let total = a.len() + b.len();
    if total == 0 {
        return 100.0;
    }
    let distance = total - 2 * lcs_len(a, b);
    (1.0 - distance as f64 / total as f64) * 100.0
}

/// Length of the longest common subsequence of `a` and `b`.
fn lcs_len(a: &[char], b: &[char]) -> usize {
    if a.is_empty() || b.is_empty() {
        return 0;
    }
    let mut previous = vec![0usize; b.len() + 1];
    let mut current = vec![0usize; b.len() + 1];
    for ca in a {
        for (j, cb) in b.iter().enumerate() {
            current[j + 1] = if ca == cb {
                previous[j] + 1
            } else {
                previous[j + 1].max(current[j])
            };
        }
        std::mem::swap(&mut previous, &mut current);
    }
    previous[b.len()]
}

#[cfg(test)]
mod tests {
    use super::*;

    fn assert_score(actual: f64, expected: f64) {
        assert!(
            (actual - expected).abs() < 1e-9,
            "expected {expected}, got {actual}"
        );
    }

    #[test]
    fn identical_strings_score_100() {
        assert_score(ratio("hello", "hello"), 100.0);
        assert_score(partial_ratio("hello", "hello"), 100.0);
    }

    #[test]
    fn ratio_uses_indel_similarity() {
        assert_score(
            ratio("this is a test", "this is a test!"),
            96.551_724_137_931_03,
        );
        assert_score(ratio("latex", "paintings"), 28.571_428_571_428_57);
    }

    #[test]
    fn partial_ratio_finds_substring() {
        assert_score(partial_ratio("rust", "I love rust programming"), 100.0);
        assert_score(partial_ratio("cat", "concatenate"), 100.0);
    }

    #[test]
    fn partial_ratio_handles_prefixes_and_suffixes() {
        assert_score(partial_ratio("abcdefgh", "xxabcdef"), 85.714_285_714_285_72);
        assert_score(partial_ratio("latex", "latest"), 88.888_888_888_888_89);
    }

    #[test]
    fn partial_ratio_handles_short_titles() {
        // Equal-length strings also try prefixes and suffixes of the title.
        assert_score(partial_ratio("latex", "gadts"), 50.0);
    }

    #[test]
    fn partial_ratio_ignores_case() {
        assert_score(partial_ratio("latex", "Is LaTeX worth it?"), 100.0);
    }

    #[test]
    fn typo_tolerance_stops_short_of_unrelated_titles() {
        // These matched under the previous Levenshtein implementation.
        assert!(!matches("latex", "Paintings"));
        assert!(!matches(
            "latex",
            "Black box Amazon: algorithm discriminates customers"
        ));
        assert!(matches("latex", "Is LaTeX worth it?"));
    }

    #[test]
    fn matching_respects_threshold() {
        assert!(matches("rust", "Rust programming"));
        assert!(!matches("zzzzzz", "Rust programming"));
        // 88.89 is above the threshold; 80 is below it.
        assert!(matches("latex", "Software Projects Will Be Late"));
        assert!(!matches("latex", "Dhall is now a template engine"));
    }

    #[test]
    fn empty_query_matches_everything() {
        assert!(matches("", "anything"));
    }

    fn matched_texts(query: &str, title: &str) -> Option<Vec<String>> {
        let spans = find_matches(query, title);
        if spans.is_empty() {
            return None;
        }
        Some(
            spans
                .iter()
                .map(|span| {
                    title
                        .chars()
                        .skip(span.start)
                        .take(span.end - span.start)
                        .collect()
                })
                .collect(),
        )
    }

    #[test]
    fn find_matches_returns_the_best_aligned_spans() {
        assert_eq!(
            matched_texts("latex", "Is LaTeX worth it?"),
            Some(vec!["LaTeX".to_string()])
        );
        assert_eq!(
            matched_texts("latex", "Software Projects Will Be Late"),
            Some(vec!["Late".to_string()])
        );
        assert_eq!(
            matched_texts("rust", "In Blob We Trust"),
            Some(vec!["rust".to_string()])
        );
    }

    #[test]
    fn find_matches_requires_every_query_token() {
        assert_eq!(
            matched_texts("defeat return", "Defeating Return Type Polymorphism"),
            Some(vec!["Defeat".to_string(), "Return".to_string()])
        );
        assert_eq!(
            find_matches("defeat missing", "Defeating Return Type Polymorphism"),
            Vec::new()
        );
    }

    #[test]
    fn find_matches_is_order_independent() {
        assert_eq!(
            matched_texts("return defeat", "Defeating Return Type Polymorphism"),
            Some(vec!["Defeat".to_string(), "Return".to_string()])
        );
    }

    #[test]
    fn find_matches_merges_duplicate_tokens() {
        assert_eq!(find_matches("rust rust", "Rust and Boll").len(), 1);
    }

    #[test]
    fn find_matches_returns_none_for_non_matches() {
        assert_eq!(find_matches("latex", "Paintings"), Vec::new());
        assert_eq!(find_matches("", "anything"), Vec::new());
    }

    #[test]
    fn find_matches_highlights_a_short_title_whole() {
        let spans = find_matches("xxgadtsyy", "gadts");
        assert_eq!(spans.len(), 1);
        assert_eq!((spans[0].start, spans[0].end), (0, 5));
    }

    #[test]
    fn find_matches_maps_expanded_lowercase_chars() {
        // 'İ' lowercases to `i` plus a combining dot; the span must still
        // cover the single original character.
        let spans = find_matches("i", "İ");
        assert_eq!(spans.len(), 1);
        assert_eq!((spans[0].start, spans[0].end), (0, 1));
    }
}

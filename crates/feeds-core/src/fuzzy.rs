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
    let a_lower = a.to_lowercase();
    let b_lower = b.to_lowercase();
    let a_chars: Vec<char> = a_lower.chars().collect();
    let b_chars: Vec<char> = b_lower.chars().collect();
    partial_ratio_chars(&a_chars, &b_chars)
}

/// Whether `title` matches `query` above the default threshold.
pub fn matches(query: &str, title: &str) -> bool {
    if query.is_empty() {
        return true;
    }
    partial_ratio(query, title) >= PARTIAL_RATIO_THRESHOLD
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

    let mut best = best_alignment(short, long);
    // RapidFuzz also tries the opposite direction for equal-length strings,
    // which lets a prefix or suffix of either string win.
    if best < 100.0 && short.len() == long.len() {
        best = best.max(best_alignment(long, short));
    }
    best
}

fn best_alignment(needle: &[char], long: &[char]) -> f64 {
    let mut best: f64 = 0.0;

    if long.len() > needle.len() {
        for window in long.windows(needle.len()) {
            best = best.max(ratio_chars(needle, window));
            if best >= 100.0 {
                return 100.0;
            }
        }
    }

    for end in 1..needle.len() {
        best = best.max(ratio_chars(needle, &long[..end]));
    }
    for start in (long.len() - needle.len())..long.len() {
        best = best.max(ratio_chars(needle, &long[start..]));
    }
    best
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
}

//! Fuzzy title matching for the UI's "filter entries" feature.

/// Default match threshold.
pub const PARTIAL_RATIO_THRESHOLD: f64 = 80.0;

/// Normalized Levenshtein similarity (0–100).
pub fn ratio(a: &str, b: &str) -> f64 {
    let a: Vec<char> = a.chars().collect();
    let b: Vec<char> = b.chars().collect();
    let total = a.len() + b.len();
    if total == 0 {
        return 100.0;
    }
    let distance = levenshtein(&a, &b);
    100.0 * (1.0 - distance as f64 / total as f64)
}

/// Best [`ratio`] between the shorter string and any same-length window of
/// the longer string.
pub fn partial_ratio(a: &str, b: &str) -> f64 {
    let a_lower = a.to_lowercase();
    let b_lower = b.to_lowercase();
    let a_chars: Vec<char> = a_lower.chars().collect();
    let b_chars: Vec<char> = b_lower.chars().collect();

    if a_chars.is_empty() || b_chars.is_empty() {
        return if a_chars.is_empty() && b_chars.is_empty() {
            100.0
        } else {
            0.0
        };
    }

    let (short, long) = if a_chars.len() <= b_chars.len() {
        (&a_chars, &b_chars)
    } else {
        (&b_chars, &a_chars)
    };

    if short.len() == long.len() {
        return ratio(&a_lower, &b_lower);
    }

    let mut best: f64 = 0.0;
    for window in long.windows(short.len()) {
        let score = ratio_chars(short, window);
        if score > best {
            best = score;
        }
        if best >= 100.0 {
            break;
        }
    }
    best
}

/// Whether `title` matches `query` above the default threshold.
pub fn matches(query: &str, title: &str) -> bool {
    if query.is_empty() {
        return true;
    }
    partial_ratio(query, title) >= PARTIAL_RATIO_THRESHOLD
}

fn ratio_chars(a: &[char], b: &[char]) -> f64 {
    let total = a.len() + b.len();
    if total == 0 {
        return 100.0;
    }
    let distance = levenshtein(a, b);
    100.0 * (1.0 - distance as f64 / total as f64)
}

fn levenshtein(a: &[char], b: &[char]) -> usize {
    if a.is_empty() {
        return b.len();
    }
    if b.is_empty() {
        return a.len();
    }
    let mut prev: Vec<usize> = (0..=b.len()).collect();
    let mut curr = vec![0usize; b.len() + 1];
    for (i, ca) in a.iter().enumerate() {
        curr[0] = i + 1;
        for (j, cb) in b.iter().enumerate() {
            let cost = usize::from(ca != cb);
            curr[j + 1] = (prev[j + 1] + 1).min(curr[j] + 1).min(prev[j] + cost);
        }
        std::mem::swap(&mut prev, &mut curr);
    }
    prev[b.len()]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn identical_strings_score_100() {
        assert_eq!(ratio("hello", "hello"), 100.0);
        assert_eq!(partial_ratio("hello", "hello"), 100.0);
    }

    #[test]
    fn partial_ratio_finds_substring() {
        let score = partial_ratio("rust", "I love rust programming");
        assert!(score >= 95.0, "score was {score}");
    }

    #[test]
    fn matching_respects_threshold() {
        assert!(matches("rust", "Rust programming"));
        assert!(!matches("zzzzzz", "Rust programming"));
    }

    #[test]
    fn empty_query_matches_everything() {
        assert!(matches("", "anything"));
    }
}

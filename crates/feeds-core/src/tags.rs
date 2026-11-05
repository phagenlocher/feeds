//! Deterministic tag-color assignment.
//!
//! Hashes the tag name with MD5 and maps three derived bytes onto HLS.

use std::collections::BTreeMap;

/// Map of tag name to `#rrggbb` color.
pub type TagColors = BTreeMap<String, String>;

/// Return a stable default color (`#rrggbb`) for `tag`.
pub fn default_color_for_tag(tag: &str) -> String {
    let digest = md5::compute(tag.as_bytes()).0;
    let hue = f64::from(digest[0] ^ digest[3] ^ digest[6] ^ digest[9] ^ digest[12]) / 255.0;
    let saturation_seed =
        f64::from(digest[1] ^ digest[4] ^ digest[7] ^ digest[10] ^ digest[13]) / 255.0;
    let lightness_seed =
        f64::from(digest[2] ^ digest[5] ^ digest[8] ^ digest[11] ^ digest[14]) / 255.0;
    let saturation = 0.2 * saturation_seed + 0.6;
    let lightness = 0.2 * lightness_seed + 0.55;
    let (red, green, blue) = hls_to_rgb(hue, lightness, saturation);
    format!(
        "#{:02x}{:02x}{:02x}",
        channel_byte(red),
        channel_byte(green),
        channel_byte(blue)
    )
}

/// Convert a color channel in `0.0..=1.0` to its byte value.
#[expect(
    clippy::cast_possible_truncation,
    clippy::cast_sign_loss,
    reason = "the value is clamped to 0.0..=255.0 before the cast"
)]
fn channel_byte(value: f64) -> u8 {
    (value * 255.0).round().clamp(0.0, 255.0) as u8
}

fn hls_to_rgb(h: f64, l: f64, s: f64) -> (f64, f64, f64) {
    if s == 0.0 {
        return (l, l, l);
    }
    let m2 = if l <= 0.5 {
        l * (1.0 + s)
    } else {
        l + s - l * s
    };
    let m1 = 2.0 * l - m2;
    (
        hue_to_rgb(m1, m2, h + 1.0 / 3.0),
        hue_to_rgb(m1, m2, h),
        hue_to_rgb(m1, m2, h - 1.0 / 3.0),
    )
}

fn hue_to_rgb(m1: f64, m2: f64, hue: f64) -> f64 {
    let hue = hue.rem_euclid(1.0);
    if hue < 1.0 / 6.0 {
        m1 + (m2 - m1) * hue * 6.0
    } else if hue < 0.5 {
        m2
    } else if hue < 2.0 / 3.0 {
        m1 + (m2 - m1) * (2.0 / 3.0 - hue) * 6.0
    } else {
        m1
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_color_is_stable_and_valid() {
        let a = default_color_for_tag("compilers");
        let b = default_color_for_tag("compilers");
        assert_eq!(a, b);
        assert_eq!(a.len(), 7);
        assert!(a.starts_with('#'));
        assert!(a[1..].chars().all(|c| c.is_ascii_hexdigit()));
    }

    #[test]
    fn different_tags_can_differ() {
        assert_ne!(default_color_for_tag("a"), default_color_for_tag("b"));
    }
}

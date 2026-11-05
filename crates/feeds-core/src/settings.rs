//! Persistent application settings, stored in the database.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

use crate::tags::TagColors;

/// Default application font size, in CSS pixels.
pub const DEFAULT_FONT_SIZE: i32 = 14;
/// Minimum application font size, in CSS pixels.
pub const MIN_FONT_SIZE: i32 = 6;

/// Key of the font size in the `app_settings` table.
pub const SETTING_FONT_SIZE: &str = "font_size";

/// Application settings, as stored in the database.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Settings {
    /// Application font size in CSS pixels.
    #[serde(default = "default_font_size")]
    pub font_size: i32,
    /// Tag name to `#rrggbb` color mapping.
    #[serde(default)]
    pub tag_colors: TagColors,
}

fn default_font_size() -> i32 {
    DEFAULT_FONT_SIZE
}

impl Default for Settings {
    fn default() -> Self {
        Self {
            font_size: DEFAULT_FONT_SIZE,
            tag_colors: BTreeMap::new(),
        }
    }
}

impl Settings {
    /// Build settings from their stored parts.
    pub fn new(font_size: i32, tag_colors: TagColors) -> Self {
        Self {
            font_size,
            tag_colors,
        }
    }

    /// Return the settings with the font size clamped to a usable value.
    ///
    /// A font size below [`MIN_FONT_SIZE`] is not usable and falls back to
    /// [`DEFAULT_FONT_SIZE`].
    #[must_use]
    pub fn normalized(&self) -> Self {
        let mut settings = self.clone();
        if settings.font_size < MIN_FONT_SIZE {
            settings.font_size = DEFAULT_FONT_SIZE;
        }
        settings
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn defaults_are_sane() {
        let settings = Settings::default();
        assert_eq!(settings.font_size, DEFAULT_FONT_SIZE);
        assert!(settings.tag_colors.is_empty());
    }

    #[test]
    fn new_keeps_the_given_values() {
        let mut colors = TagColors::new();
        colors.insert("rust".into(), "#ff0000".into());
        let settings = Settings::new(15, colors);
        assert_eq!(settings.font_size, 15);
        assert_eq!(
            settings.tag_colors.get("rust").map(String::as_str),
            Some("#ff0000")
        );
    }

    #[test]
    fn a_too_small_font_size_falls_back_to_the_default() {
        let settings = Settings::new(2, TagColors::new()).normalized();
        assert_eq!(settings.font_size, DEFAULT_FONT_SIZE);
    }

    #[test]
    fn a_usable_font_size_is_kept() {
        let settings = Settings::new(MIN_FONT_SIZE, TagColors::new()).normalized();
        assert_eq!(settings.font_size, MIN_FONT_SIZE);
    }
}

//! Shared application state.

use std::sync::atomic::{AtomicBool, Ordering};

use feeds_core::Feeds;

/// State shared across Tauri commands.
pub struct AppState {
    /// The core facade (storage + http + discovery).
    pub feeds: Feeds,
    /// Whether a background operation is running.
    pub busy: AtomicBool,
}

impl AppState {
    /// Create state from a core facade.
    pub fn new(feeds: Feeds) -> Self {
        Self {
            feeds,
            busy: AtomicBool::new(false),
        }
    }

    /// Set the busy flag and return the previous value.
    pub fn set_busy(&self, busy: bool) -> bool {
        self.busy.swap(busy, Ordering::SeqCst)
    }
}

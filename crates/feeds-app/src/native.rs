//! Platform-native integration the webview cannot reach.
//!
//! Font zoom in the UI scales the web content through a CSS variable. On Linux
//! the menu bar and its popups are drawn by GTK, *outside* the webview, so they
//! are scaled through a GTK stylesheet using the very same pixel size as the
//! web content.

/// Apply the application font size (in CSS pixels) to native UI.
///
/// On platforms where the menu is drawn by the OS (macOS, Windows) this is a
/// no-op — those menus cannot be resized.
pub fn apply_font_size(font_size: i32) {
    #[cfg(target_os = "linux")]
    linux::apply(font_size);
    #[cfg(not(target_os = "linux"))]
    let _ = font_size;
}

#[cfg(target_os = "linux")]
mod linux {
    use std::cell::RefCell;

    use gtk::prelude::*;

    thread_local! {
        /// The stylesheet applied to the GTK menu widgets.
        static PROVIDER: RefCell<Option<gtk::CssProvider>> = const { RefCell::new(None) };
    }

    pub fn apply(font_size: i32) {
        let px = font_size.max(1);
        // Keep the menu exactly as large as the web content, which uses
        // `--font-size: <px>px`.
        let css = format!("menubar, menu, menuitem {{ font-size: {px}px; }}");
        PROVIDER.with(|slot| {
            let mut slot = slot.borrow_mut();
            let provider = slot.get_or_insert_with(|| {
                let provider = gtk::CssProvider::new();
                if let Some(screen) = gtk::gdk::Screen::default() {
                    gtk::StyleContext::add_provider_for_screen(
                        &screen,
                        &provider,
                        gtk::STYLE_PROVIDER_PRIORITY_APPLICATION,
                    );
                }
                provider
            });
            let _ = provider.load_from_data(css.as_bytes());
        });
    }
}

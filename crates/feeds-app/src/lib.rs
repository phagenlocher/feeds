//! Tauri application entry point and plugin wiring.

mod commands;
mod menu;
mod native;
mod state;

use std::path::PathBuf;

use clap::Parser;
use feeds_core::Feeds;
use state::AppState;
use tauri::{Emitter, Manager};

/// Command-line arguments.
#[derive(Debug, Parser)]
#[command(name = "feeds", version = feeds_core::APP_VERSION, about = "RSS/Atom indexer")]
struct Args {
    /// Data directory for feeds.db (default: ~/.feeds)
    #[arg(short = 'd', long = "data-dir")]
    data_dir: Option<PathBuf>,
    /// Enable debug logging
    #[arg(short = 'v', long = "verbose")]
    verbose: bool,
}

/// Build and run the Tauri application.
///
/// # Panics
///
/// Panics if the Tauri event loop terminates with an error, which leaves the
/// process with no running UI.
#[expect(
    clippy::expect_used,
    reason = "the event loop cannot continue once Tauri fails"
)]
pub fn run() {
    let args = Args::parse();
    let level = if args.verbose {
        tracing::Level::DEBUG
    } else {
        tracing::Level::INFO
    };
    drop(
        tracing_subscriber::fmt()
            .with_max_level(level)
            .with_target(false)
            .try_init(),
    );

    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                drop(window.unminimize());
                drop(window.show());
                drop(window.set_focus());
            }
        }))
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_clipboard_manager::init())
        .on_menu_event(|app, event| {
            drop(app.emit("menu", event.id().as_ref().to_string()));
        })
        .setup(move |app| {
            let feeds = Feeds::open(args.data_dir.clone()).map_err(|e| {
                Box::<dyn std::error::Error>::from(std::io::Error::other(e.to_string()))
            })?;

            // The settings live in the database. A failure to read them must
            // not keep the app from starting.
            let font_size = match feeds.get_settings() {
                Ok(settings) => settings.font_size,
                Err(e) => {
                    tracing::warn!("could not read the settings: {e}");
                    feeds_core::settings::DEFAULT_FONT_SIZE
                }
            };
            native::apply_font_size(font_size);
            app.manage(AppState::new(feeds));
            menu::install(app.handle())?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::get_tree,
            commands::has_feeds,
            commands::app_version,
            commands::add_feed,
            commands::delete_feed,
            commands::rename_feed,
            commands::set_entry_read,
            commands::mark_all_as_read,
            commands::prune_feed,
            commands::discover_feeds,
            commands::update_feed,
            commands::update_feeds,
            commands::get_tag_keys,
            commands::default_tag_colors,
            commands::get_feed_tags,
            commands::set_feed_tags,
            commands::rename_tag,
            commands::delete_tag,
            commands::get_settings,
            commands::set_font_size,
            commands::set_tag_color,
            commands::export_opml,
            commands::import_opml,
            commands::read_file,
            commands::write_file,
            commands::fuzzy_filter,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

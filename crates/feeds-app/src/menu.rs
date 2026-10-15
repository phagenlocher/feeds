//! Native application menu.

use tauri::menu::{MenuBuilder, MenuItemBuilder, SubmenuBuilder};
use tauri::{AppHandle, Runtime};

/// Install the application menu and wire up the standard items.
pub fn install<R: Runtime>(app: &AppHandle<R>) -> tauri::Result<()> {
    let add = MenuItemBuilder::with_id("add_feed", "Add Feed")
        .accelerator("CmdOrCtrl+N")
        .build(app)?;
    let update = MenuItemBuilder::with_id("update_feeds", "Update Feeds")
        .accelerator("CmdOrCtrl+R")
        .build(app)?;
    let export = MenuItemBuilder::with_id("export_opml", "Export Feeds…").build(app)?;
    let import = MenuItemBuilder::with_id("import_opml", "Import Feeds…").build(app)?;

    let feed_menu = SubmenuBuilder::new(app, "Feed")
        .item(&add)
        .item(&update)
        .separator()
        .item(&export)
        .item(&import)
        .build()?;

    let search = MenuItemBuilder::with_id("toggle_search", "Show Searchbar")
        .accelerator("CmdOrCtrl+F")
        .build(app)?;
    let tag_filter = MenuItemBuilder::with_id("toggle_tag_filter", "Show Tag Filter")
        .accelerator("CmdOrCtrl+T")
        .build(app)?;
    let manage_tags = MenuItemBuilder::with_id("manage_tags", "Manage Tags…").build(app)?;
    // Zoom shortcuts are handled in the webview (`onKey`), because "+" has no
    // valid native accelerator code (the "+" key is Shift+"=" on most layouts).
    let zoom_in = MenuItemBuilder::with_id("zoom_in", "Zoom In").build(app)?;
    let zoom_out = MenuItemBuilder::with_id("zoom_out", "Zoom Out").build(app)?;
    let zoom_reset = MenuItemBuilder::with_id("zoom_reset", "Reset Zoom").build(app)?;

    let display_menu = SubmenuBuilder::new(app, "Display")
        .item(&search)
        .item(&tag_filter)
        .separator()
        .item(&manage_tags)
        .separator()
        .item(&zoom_in)
        .item(&zoom_out)
        .item(&zoom_reset)
        .build()?;

    let report = MenuItemBuilder::with_id("report_issue", "Report Issue").build(app)?;
    let about = MenuItemBuilder::with_id("about", "About").build(app)?;
    let help_menu = SubmenuBuilder::new(app, "Help")
        .item(&report)
        .separator()
        .item(&about)
        .build()?;

    let menu = MenuBuilder::new(app)
        .item(&feed_menu)
        .item(&display_menu)
        .item(&help_menu)
        .build()?;

    app.set_menu(menu)?;
    Ok(())
}

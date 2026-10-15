# Startup update

## Context

When the program starts, subscribed feeds should be refreshed without the user
having to press "Update Feeds". This first update of a session honours the
60-minute schedule: feeds whose `update_after` is still in the future are
skipped, while feeds that have never been fetched (or are due) are updated.

## Behaviour

**Scenario: feeds are updated on startup**

**Given** the app has at least one subscribed feed
**And** a feed has never been fetched, or its `update_after` has passed
**When** the main window mounts
**Then** the frontend invokes `update_feeds(scheduled: true)` once
**And** the tree is reloaded afterwards so new entries appear
**And** the status bar reads “Feeds updated” when `UpdateReport.updated` is
greater than zero (this includes feeds that answered `304 Not Modified`)
**And** the message clears after 4 seconds

**Scenario: no feed is due on startup**

**Given** every subscribed feed was updated less than 60 minutes ago
**When** the main window mounts
**Then** no feed is fetched
**And** the status bar shows no result message

**Scenario: a feed fails to update**

**Given** a feed fails to update during the startup update
**When** the update finishes
**Then** the status bar reads `Failed to update <feed title>: <reason>`
**And** the message clears after 4 seconds

**Scenario: a feed within its schedule is not refetched**

**Given** a feed was updated less than 60 minutes ago
**When** the main window mounts
**Then** that feed is not fetched again

**Scenario: no feeds**

**Given** no feed is subscribed
**When** the main window mounts
**Then** no update is triggered and no status message is shown

## Reference

The startup update is a single `update_feeds(scheduled: true)` invocation from
`App.svelte`, made after the first tree load. The frontend checks `has_feeds`
first and skips the update entirely when nothing is subscribed. The 60-minute
interval and the per-feed `update_after` value are written by
`feeds_core::store` (`apply_update` and `apply_not_modified`);
`feeds_core::update` selects the feeds that are due. See
[`rss-atom.md`](rss-atom.md).

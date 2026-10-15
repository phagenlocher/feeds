<script lang="ts">
  import { onMount, tick } from "svelte";
  import { invoke } from "@tauri-apps/api/core";
  import { listen } from "@tauri-apps/api/event";
  import { openUrl } from "@tauri-apps/plugin-opener";
  import {
    open as openDialog,
    save as saveDialog,
    message,
    confirm,
  } from "@tauri-apps/plugin-dialog";
  import { writeText } from "@tauri-apps/plugin-clipboard-manager";
  import { UNTAGGED } from "./lib/types";
  import type {
    Entry,
    FeedNode,
    Settings,
    UpdateFailure,
    UpdateReport,
  } from "./lib/types";

  let nodes: FeedNode[] = [];
  let settings: Settings = { font_size: 14, tag_colors: {} };
  let tagKeys: string[] = [];
  let tagFilter = "";
  let showSearch = false;
  let showTagFilter = false;
  let filterText = "";
  let busy = false;
  let status = "";
  let version = "";
  let expanded = new Set<string>();
  let selected: { feed: string; entry: string | null } | null = null;
  let hidden = new Set<string>();
  let previewColors: Record<string, string> = {};

  let contextMenu:
    | { x: number; y: number; kind: "feed" | "entry"; node: FeedNode; entry?: Entry }
    | null = null;
  let ctxEl: HTMLDivElement | null = null;

  // Dialogs
  let addDialog = false;
  let addUrl = "";
  let addChoices: { url: string; title: string }[] | null = null;
  let choiceSelected = new Set<string>();
  let renameDialog: FeedNode | null = null;
  let renameValue = "";
  let pruneDialog: FeedNode | null = null;
  let pruneValue = 25;
  let tagDialog:
    | { node: FeedNode; all: string[]; selected: Set<string>; newTag: string }
    | null = null;
  let manageDialog = false;
  let aboutDialog = false;
  let colorDialog = false;
  let colorTag = "";
  let colorValue = "#888888";
  let colorHex = "#888888";

  let filterTimer: ReturnType<typeof setTimeout> | undefined;

  const entryKey = (feed: string, entry: string) => feed + "\u0000" + entry;

  // Reactive view of the tree. Computed here (rather than in the template via
  // helper functions) so Svelte re-runs it whenever the query or `hidden`
  // changes: the compiler cannot see through a function call in the template.
  // With a query active, only matching entries are kept and feeds left with no
  // matching entry disappear.
  $: visibleNodes = filterText
    ? nodes
        .map((node) => ({
          ...node,
          entries: node.entries.filter(
            (e) => !hidden.has(entryKey(e.feed_id, e.entry_id)),
          ),
        }))
        .filter((node) => node.entries.length > 0)
    : nodes;

  // Renders a timestamp as `YYYY-MM-DD` in the user's local time zone.
  function fmtDate(iso: string | null): string {
    if (!iso) return "";
    const d = new Date(iso);
    if (isNaN(d.getTime())) return "";
    const month = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${d.getFullYear()}-${month}-${day}`;
  }

  function setStatus(text: string) {
    status = text;
    if (text) {
      const shown = text;
      setTimeout(() => {
        if (status === shown) status = "";
      }, 4000);
    }
  }

  // A status message naming the failed feed(s) and the reason, so a failed
  // update is visible without having to read the log.
  function updateFailureMessage(failures: UpdateFailure[]): string {
    const details = failures.map((f) => `${f.title}: ${f.error}`).join("; ");
    return failures.length === 1
      ? `Failed to update ${details}`
      : `Failed to update ${failures.length} feeds: ${details}`;
  }

  async function load() {
    nodes = await invoke<FeedNode[]>("get_tree", { filter: tagFilter || null });
    tagKeys = await invoke<string[]>("get_tag_keys");
    await applyFilter();
    await ensurePreviewColors();
  }

  // Deterministic preview colors for tags without a stored color yet (e.g. a
  // tag just typed into the tag dialog, before it is saved), so their pills
  // are never a plain gray fallback.
  async function ensurePreviewColors(extra: string[] = []) {
    const wanted = new Set([...tagKeys, ...extra]);
    const missing = [...wanted].filter(
      (tag) => !settings.tag_colors[tag] && !previewColors[tag],
    );
    if (missing.length === 0) return;
    const colors = await invoke<Record<string, string>>("default_tag_colors", {
      tags: missing,
    });
    previewColors = { ...previewColors, ...colors };
  }

  async function loadSettings() {
    settings = await invoke<Settings>("get_settings");
    applyZoom();
  }

  function applyZoom() {
    document.documentElement.style.setProperty("--font-size", settings.font_size + "px");
  }

  async function applyFilter() {
    if (!filterText) {
      hidden = new Set();
      return;
    }
    const entries = nodes.flatMap((n) => n.entries);
    try {
      const res = await invoke<boolean[]>("fuzzy_filter", {
        query: filterText,
        texts: entries.map((e) => e.title),
      });
      const h = new Set<string>();
      entries.forEach((e, i) => {
        if (!res[i]) h.add(entryKey(e.feed_id, e.entry_id));
      });
      hidden = h;
    } catch {
      hidden = new Set();
    }
  }

  function onFilterInput() {
    clearTimeout(filterTimer);
    filterTimer = setTimeout(() => applyFilter(), 300);
  }

  function toggleFeed(url: string) {
    const s = new Set(expanded);
    if (s.has(url)) s.delete(url);
    else s.add(url);
    expanded = s;
  }

  async function run(label: string, fn: () => Promise<void>) {
    busy = true;
    status = label;
    try {
      await fn();
    } catch (e) {
      setStatus(String(e));
    } finally {
      busy = false;
      // A callback that finishes without reporting anything must not leave
      // the progress label on screen forever.
      if (status === label) status = "";
    }
  }

  async function openEntry(node: FeedNode, entry: Entry) {
    if (!entry.read) {
      await invoke("set_entry_read", {
        feed: entry.feed_id,
        entryId: entry.entry_id,
        read: true,
      });
      entry.read = true;
      node.unread = Math.max(0, node.unread - 1);
      nodes = nodes;
    }
    if (entry.url) await openUrl(entry.url);
  }

  async function markRead(node: FeedNode, entry: Entry, read: boolean) {
    await invoke("set_entry_read", {
      feed: entry.feed_id,
      entryId: entry.entry_id,
      read,
    });
    entry.read = read;
    node.unread = Math.max(0, node.unread + (read ? -1 : 1));
    nodes = nodes;
  }

  // ── Add feed flow ──────────────────────────────────────────────────
  function openAdd() {
    addUrl = "";
    addDialog = true;
  }

  async function submitAdd() {
    const url = addUrl.trim();
    addDialog = false;
    if (!url) return;
    if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(url)) {
      setStatus("Please enter a full URL (including https://)");
      return;
    }
    await run("Discovering feeds…", async () => {
      let found: { url: string; title: string }[];
      try {
        found = await invoke<{ url: string; title: string }[]>("discover_feeds", {
          url,
        });
      } catch (e) {
        setStatus(`Failed to add feed ${url}: ${e}`);
        return;
      }
      if (found.length === 0) {
        setStatus("No feed found at this URL");
        return;
      }
      if (found.length === 1) {
        if (await addAndUpdate(found[0].url)) setStatus("Feed added");
        return;
      }
      addChoices = found;
      choiceSelected = new Set(found.map((f) => f.url));
    });
  }

  // Returns whether the feed was added *and* fetched successfully.
  async function addAndUpdate(feedUrl: string): Promise<boolean> {
    await invoke("add_feed", { url: feedUrl });
    try {
      await invoke("update_feed", { url: feedUrl });
    } catch (e) {
      setStatus(
        updateFailureMessage([
          { url: feedUrl, title: feedUrl, error: String(e) },
        ]),
      );
      return false;
    }
    await refresh();
    expanded.add(feedUrl);
    expanded = expanded;
    return true;
  }

  async function confirmChoices() {
    const chosen = (addChoices ?? []).filter((f) => choiceSelected.has(f.url));
    addChoices = null;
    await run("Adding feeds…", async () => {
      let added = 0;
      for (const f of chosen) {
        if (await addAndUpdate(f.url)) added += 1;
      }
      if (added === chosen.length) setStatus(`Added ${added} feeds`);
      else if (added > 0) setStatus(`Added ${added} of ${chosen.length} feeds`);
      // If every feed failed, `addAndUpdate` already left the failure message
      // in the status bar.
    });
  }

  async function refresh() {
    await load();
  }

  async function updateAll() {
    if (!(await invoke<boolean>("has_feeds"))) {
      setStatus("No feeds to update");
      return;
    }
    await run("Updating feeds…", async () => {
      const report = await invoke<UpdateReport>("update_feeds", {
        scheduled: false,
      });
      await refresh();
      setStatus(
        report.failed > 0
          ? updateFailureMessage(report.failures)
          : "Feeds updated",
      );
    });
  }

  // Update feeds once on startup. This is the first update after the program
  // launches and honours the schedule, so feeds whose `update_after` is still
  // in the future are skipped.
  async function updateOnStartup() {
    if (!(await invoke<boolean>("has_feeds"))) return;
    await run("Updating feeds…", async () => {
      const report = await invoke<UpdateReport>("update_feeds", {
        scheduled: true,
      });
      await refresh();
      if (report.failed > 0) setStatus(updateFailureMessage(report.failures));
      else if (report.updated > 0) setStatus("Feeds updated");
    });
  }

  async function updateSingle(node: FeedNode) {
    await run(`Updating ${node.feed.title}…`, async () => {
      try {
        await invoke("update_feed", { url: node.feed.id });
      } catch (e) {
        setStatus(
          updateFailureMessage([
            { url: node.feed.id, title: node.feed.title, error: String(e) },
          ]),
        );
        return;
      }
      await refresh();
      setStatus("Feed updated");
    });
  }

  async function removeFeed(node: FeedNode) {
    const yes = await confirm(`Remove '${node.feed.title}'?`, { title: "Remove feed" });
    if (!yes) return;
    await run(`Removing ${node.feed.title}…`, async () => {
      await invoke("delete_feed", { url: node.feed.id });
      await refresh();
      setStatus("Feed removed");
    });
  }

  async function markAllRead(node: FeedNode) {
    await run("Marking all as read…", async () => {
      await invoke("mark_all_as_read", { feed: node.feed.id });
      await refresh();
      setStatus("All marked as read");
    });
  }

  function openPrune(node: FeedNode) {
    pruneDialog = node;
    pruneValue = 25;
  }

  async function doPrune() {
    const node = pruneDialog;
    pruneDialog = null;
    if (!node) return;
    const n = Math.max(1, Math.floor(pruneValue));
    const yes = await confirm(
      `Keep only the ${n} most recent entries in '${node.feed.title}'?`,
      { title: "Prune entries" }
    );
    if (!yes) return;
    await run(`Pruning ${node.feed.title}…`, async () => {
      await invoke("prune_feed", { feed: node.feed.id, n });
      await refresh();
      setStatus("Pruned");
    });
  }

  function openRename(node: FeedNode) {
    renameDialog = node;
    renameValue = node.feed.title;
  }

  async function doRename() {
    const node = renameDialog;
    renameDialog = null;
    const title = renameValue.trim();
    if (!node || !title) return;
    await run(`Renaming ${node.feed.title}…`, async () => {
      await invoke("rename_feed", { url: node.feed.id, title });
      await refresh();
      setStatus("Feed renamed");
    });
  }

  async function copy(text: string) {
    await writeText(text);
    setStatus("Copied to clipboard");
  }

  function openTagDialog(node: FeedNode) {
    tagDialog = {
      node,
      all: [...tagKeys],
      selected: new Set(node.tags),
      newTag: "",
    };
  }

  function addNewTag() {
    if (!tagDialog) return;
    const tag = tagDialog.newTag.trim();
    if (!tag || tagDialog.all.includes(tag)) return;
    tagDialog.all = [...tagDialog.all, tag];
    tagDialog.selected.add(tag);
    tagDialog.newTag = "";
    tagDialog = tagDialog;
    ensurePreviewColors([tag]);
  }

  async function saveTags() {
    const d = tagDialog;
    tagDialog = null;
    if (!d) return;
    await run("Saving tags…", async () => {
      await invoke("set_feed_tags", { feed: d.node.feed.id, tags: [...d.selected] });
      await loadSettings();
      await refresh();
      setStatus("Tags updated");
    });
  }

  async function openManageTags() {
    tagKeys = await invoke<string[]>("get_tag_keys");
    manageDialog = true;
  }

  async function renameTag(oldTag: string) {
    const value = prompt(`Rename '${oldTag}' to:`, oldTag);
    if (!value || value === oldTag) return;
    await invoke("rename_tag", { old: oldTag, new: value.trim() });
    await loadSettings();
    await refresh();
    tagKeys = await invoke<string[]>("get_tag_keys");
    setStatus("Tag renamed");
  }

  async function deleteTag(tag: string) {
    const yes = await confirm(`Remove tag '${tag}' from all feeds?`, { title: "Delete Tag" });
    if (!yes) return;
    await invoke("delete_tag", { tag });
    await loadSettings();
    await refresh();
    tagKeys = await invoke<string[]>("get_tag_keys");
    setStatus("Tag deleted");
  }

  // ── OPML & misc ────────────────────────────────────────────────────
  async function exportOpml() {
    const path = await saveDialog({
      title: "Export Feeds",
      defaultPath: "feeds.opml",
      filters: [{ name: "OPML", extensions: ["opml"] }],
    });
    if (!path) return;
    await run("Exporting feeds…", async () => {
      const xml = await invoke<string>("export_opml");
      await invoke("write_file", { path, contents: xml });
      setStatus(`Exported feeds to ${path}`);
    });
  }

  async function importOpml() {
    const path = await openDialog({
      title: "Import Feeds",
      multiple: false,
      filters: [{ name: "OPML", extensions: ["opml"] }],
    });
    if (!path || Array.isArray(path)) return;
    await run("Importing feeds…", async () => {
      const xml = await invoke<string>("read_file", { path });
      const n = await invoke<number>("import_opml", { xml });
      const report = await invoke<UpdateReport>("update_feeds", {
        scheduled: false,
      });
      await refresh();
      setStatus(
        report.failed > 0
          ? `Imported ${n} feeds. ${updateFailureMessage(report.failures)}`
          : `Imported ${n} feeds`,
      );
    });
  }

  function toggleSearch() {
    showSearch = !showSearch;
    if (!showSearch) {
      filterText = "";
      applyFilter();
    }
  }

  function toggleTagFilter() {
    showTagFilter = !showTagFilter;
    if (!showTagFilter) {
      tagFilter = "";
      refresh();
    }
  }

  async function zoom(delta: number | "reset") {
    const next = delta === "reset" ? 14 : Math.max(6, settings.font_size + delta);
    settings.font_size = await invoke<number>("set_font_size", { size: next });
    applyZoom();
  }

  function normalizeColor(value: string): string | null {
    const v = value.trim().toLowerCase();
    if (/^#[0-9a-f]{6}$/.test(v)) return v;
    if (/^#[0-9a-f]{3}$/.test(v)) {
      const [r, g, b] = v.slice(1).split("");
      return `#${r}${r}${g}${g}${b}${b}`;
    }
    return null;
  }

  function openColorDialog(tag: string) {
    colorTag = tag;
    colorValue = normalizeColor(settings.tag_colors[tag] || "") || "#888888";
    colorHex = colorValue;
    colorDialog = true;
  }

  function setColorFromHex(value: string) {
    const normalized = normalizeColor(value);
    if (normalized) colorValue = normalized;
  }

  async function applyTagColor() {
    const tag = colorTag;
    colorDialog = false;
    if (!tag) return;
    const normalized = normalizeColor(colorHex) || colorValue;
    await invoke("set_tag_color", { tag, color: normalized });
    settings.tag_colors[tag] = normalized;
    settings = settings;
    // The tag pills live in the feed tree; re-render them with the new color.
    nodes = nodes;
    setStatus("Tag color updated");
  }

  function onEntryChoiceChange(feedUrl: string, event: Event) {
    const checked = (event.currentTarget as HTMLInputElement).checked;
    if (checked) choiceSelected.add(feedUrl);
    else choiceSelected.delete(feedUrl);
    choiceSelected = choiceSelected;
  }

  function onTagToggle(tag: string, event: Event) {
    if (!tagDialog) return;
    const checked = (event.currentTarget as HTMLInputElement).checked;
    if (checked) tagDialog.selected.add(tag);
    else tagDialog.selected.delete(tag);
    tagDialog = tagDialog;
  }

  // ── Menus & keyboard ───────────────────────────────────────────────
  async function openContext(
    event: MouseEvent,
    kind: "feed" | "entry",
    node: FeedNode,
    entry?: Entry,
  ) {
    contextMenu = { x: event.clientX, y: event.clientY, kind, node, entry };
    // Let the menu render, then clamp it so it never overflows the window.
    await tick();
    const menu = contextMenu;
    if (!ctxEl || !menu) return;
    const margin = 4;
    const { width, height } = ctxEl.getBoundingClientRect();
    contextMenu = {
      ...menu,
      x: Math.max(margin, Math.min(menu.x, window.innerWidth - width - margin)),
      y: Math.max(margin, Math.min(menu.y, window.innerHeight - height - margin)),
    };
  }

  async function handleMenu(id: string) {
    switch (id) {
      case "add_feed":
        openAdd();
        break;
      case "update_feeds":
        await updateAll();
        break;
      case "export_opml":
        await exportOpml();
        break;
      case "import_opml":
        await importOpml();
        break;
      case "toggle_search":
        toggleSearch();
        break;
      case "toggle_tag_filter":
        toggleTagFilter();
        break;
      case "manage_tags":
        await openManageTags();
        break;
      case "zoom_in":
        await zoom(1);
        break;
      case "zoom_out":
        await zoom(-1);
        break;
      case "zoom_reset":
        await zoom("reset");
        break;
      case "report_issue":
        await openUrl("https://github.com/phagenlocher/feeds/issues");
        break;
      case "about":
        aboutDialog = true;
        break;
    }
  }

  function onKey(event: KeyboardEvent) {
    if ((event.ctrlKey || event.metaKey) && !event.altKey) {
      // Zoom shortcuts. "+" is Shift+"=" on most layouts, so accept both.
      if (event.key === "+" || event.key === "=") {
        event.preventDefault();
        void zoom(1);
        return;
      }
      if (event.key === "-" || event.key === "_") {
        event.preventDefault();
        void zoom(-1);
        return;
      }
      if (event.key === "0") {
        event.preventDefault();
        void zoom("reset");
        return;
      }
    }
    if (event.key === "Escape") {
      // Clear the active search first, then close any open menu or dialog.
      if (filterText) {
        filterText = "";
        applyFilter();
      }
      contextMenu = null;
      addDialog = false;
      addChoices = null;
      renameDialog = null;
      pruneDialog = null;
      tagDialog = null;
      manageDialog = false;
      aboutDialog = false;
      colorDialog = false;
    }
    if (event.key === "Enter" && selected?.entry) {
      const node = nodes.find((n) => n.feed.id === selected!.feed);
      const entry = node?.entries.find((e) => e.entry_id === selected!.entry);
      if (node && entry) openEntry(node, entry);
    }
  }

  onMount(() => {
    loadSettings()
      .then(load)
      .then(updateOnStartup);
    invoke<string>("app_version").then((v) => (version = v));
    const unlisten = listen<string>("menu", (e) => handleMenu(e.payload));
    window.addEventListener("keydown", onKey);
    return () => {
      unlisten.then((f) => f());
      window.removeEventListener("keydown", onKey);
    };
  });
</script>

<div class="app">
  {#if showSearch}
    <input
      class="search"
      placeholder="Filter entries…"
      bind:value={filterText}
      on:input={onFilterInput}
      autofocus
    />
  {/if}

  {#if showTagFilter}
    <select class="tag-filter" bind:value={tagFilter} on:change={() => refresh()}>
      <option value="">All tags</option>
      <option value={UNTAGGED}>Untagged</option>
      {#each tagKeys as tag (tag)}
        <option value={tag}>{tag}</option>
      {/each}
    </select>
  {/if}

  <div class="tree" on:scroll={() => (contextMenu = null)}>
    {#each visibleNodes as node (node.feed.id)}
      <div
        class="feed-row"
        class:selected={selected?.feed === node.feed.id && !selected?.entry}
        on:click={() => (selected = { feed: node.feed.id, entry: null })}
        on:dblclick={() => toggleFeed(node.feed.id)}
        on:contextmenu|preventDefault={(e) => openContext(e, "feed", node)}
      >
        <span
          class="disclosure"
          class:open={expanded.has(node.feed.id)}
          on:click|stopPropagation={() => toggleFeed(node.feed.id)}
        >
          <svg viewBox="0 0 10 10" aria-hidden="true"><path d="M3 2 L7 5 L3 8 Z" /></svg>
        </span>
        <span class="feed-title" class:bold={node.unread > 0}
          >{node.feed.title}{node.unread ? ` (${node.unread})` : ""}</span
        >
        {#each node.tags as tag (tag)}
          <span class="pill" style="--pill: {settings.tag_colors[tag] || previewColors[tag] || '#888'}">{tag}</span>
        {/each}
        <span class="spacer" />
        <span class="feed-date">{fmtDate(node.newest_date)}</span>
      </div>

      {#if expanded.has(node.feed.id)}
        {#each node.entries as entry (entry.entry_id)}
          <div
            class="entry-row"
            class:selected={selected?.feed === node.feed.id && selected?.entry === entry.entry_id}
            on:click={() => (selected = { feed: node.feed.id, entry: entry.entry_id })}
            on:dblclick={() => openEntry(node, entry)}
            on:contextmenu|preventDefault={(e) => openContext(e, "entry", node, entry)}
          >
            <span class="entry-title" class:bold={!entry.read}>{entry.title}</span>
            <span class="spacer" />
            <span class="entry-date">{fmtDate(entry.date)}</span>
          </div>
        {/each}
      {/if}
    {/each}
  </div>

  <div class="statusbar" class:busy>
    <span>{busy ? status || "Working…" : status}</span>
  </div>
</div>

{#if contextMenu}
  <div
    class="ctx"
    bind:this={ctxEl}
    style="left: {contextMenu.x}px; top: {contextMenu.y}px"
    on:mouseleave={() => (contextMenu = null)}
  >
    {#if contextMenu.kind === "feed"}
      <button on:click={() => { markAllRead(contextMenu.node); contextMenu = null; }}
        >Mark all as read</button
      >
      <button on:click={() => { removeFeed(contextMenu.node); contextMenu = null; }}
        >Remove feed</button
      >
      <hr />
      <button on:click={() => { openPrune(contextMenu.node); contextMenu = null; }}
        >Prune entries…</button
      >
      <hr />
      <button on:click={() => { openTagDialog(contextMenu.node); contextMenu = null; }}
        >Tag feed…</button
      >
      <button on:click={() => { openRename(contextMenu.node); contextMenu = null; }}
        >Rename</button
      >
      <button on:click={() => { copy(contextMenu.node.feed.id); contextMenu = null; }}
        >Copy URL</button
      >
      <button on:click={() => { updateSingle(contextMenu.node); contextMenu = null; }}
        >Update feed</button
      >
    {:else}
      {@const entry = contextMenu.entry}
      <button
        on:click={() => { markRead(contextMenu.node, entry, !entry.read); contextMenu = null; }}
        >{entry.read ? "Mark Unread" : "Mark Read"}</button
      >
      <hr />
      <button on:click={() => { copy(entry.url); contextMenu = null; }}>Copy URL</button>
    {/if}
  </div>
{/if}

<!-- Add feed dialog -->
{#if addDialog}
  <div class="backdrop" on:click={() => (addDialog = false)}>
    <div class="dialog" on:click|stopPropagation={() => {}}>
      <h2>Add Feed</h2>
      <label>Feed URL:</label>
      <input bind:value={addUrl} placeholder="https://example.com" on:keydown={(e) => e.key === "Enter" && submitAdd()} />
      <div class="buttons">
        <button on:click={() => (addDialog = false)}>Cancel</button>
        <button class="primary" disabled={!addUrl.trim()} on:click={submitAdd}>Add</button>
      </div>
    </div>
  </div>
{/if}

<!-- Feed choice dialog -->
{#if addChoices}
  <div class="backdrop">
    <div class="dialog">
      <h2>Choose feeds</h2>
      <p>Multiple feeds found. Select which to add:</p>
      <div class="choices">
        {#each addChoices as feed (feed.url)}
          <label class="choice">
            <input
              type="checkbox"
              checked={choiceSelected.has(feed.url)}
              on:change={(e) => onEntryChoiceChange(feed.url, e)}
            />
            <span><strong>{feed.title}</strong><br /><small>{feed.url}</small></span>
          </label>
        {/each}
      </div>
      <div class="buttons">
        <button on:click={() => (addChoices = null)}>Cancel</button>
        <button class="primary" disabled={choiceSelected.size === 0} on:click={confirmChoices}
          >Add Selected</button
        >
      </div>
    </div>
  </div>
{/if}

<!-- Rename dialog -->
{#if renameDialog}
  <div class="backdrop" on:click={() => (renameDialog = null)}>
    <div class="dialog" on:click|stopPropagation={() => {}}>
      <h2>Rename Feed</h2>
      <label>Feed title:</label>
      <input bind:value={renameValue} on:keydown={(e) => e.key === "Enter" && doRename()} />
      <div class="buttons">
        <button on:click={() => (renameDialog = null)}>Cancel</button>
        <button class="primary" disabled={!renameValue.trim()} on:click={doRename}>Rename</button>
      </div>
    </div>
  </div>
{/if}

<!-- Prune dialog -->
{#if pruneDialog}
  <div class="backdrop" on:click={() => (pruneDialog = null)}>
    <div class="dialog" on:click|stopPropagation={() => {}}>
      <h2>Prune entries</h2>
      <label>Number of entries to keep:</label>
      <input type="number" min="1" bind:value={pruneValue} />
      <div class="buttons">
        <button on:click={() => (pruneDialog = null)}>Cancel</button>
        <button class="primary" on:click={doPrune}>Prune</button>
      </div>
    </div>
  </div>
{/if}

<!-- Tag feed dialog -->
{#if tagDialog}
  <div class="backdrop" on:click={() => (tagDialog = null)}>
    <div class="dialog" on:click|stopPropagation={() => {}}>
      <h2>Tag Feed — {tagDialog.node.feed.title}</h2>
      <div class="tags">
        {#each tagDialog.all as tag (tag)}
          <label class="choice">
            <input
              type="checkbox"
              checked={tagDialog.selected.has(tag)}
              on:change={(e) => onTagToggle(tag, e)}
            />
            <span class="pill" style="--pill: {settings.tag_colors[tag] || previewColors[tag] || '#888'}">{tag}</span>
          </label>
        {/each}
      </div>
      <div class="row">
        <input bind:value={tagDialog.newTag} placeholder="New tag name…" on:keydown={(e) => e.key === "Enter" && addNewTag()} />
        <button disabled={!tagDialog.newTag.trim()} on:click={addNewTag}>Add</button>
      </div>
      <div class="buttons">
        <button on:click={() => (tagDialog = null)}>Cancel</button>
        <button class="primary" on:click={saveTags}>OK</button>
      </div>
    </div>
  </div>
{/if}

<!-- Manage tags dialog -->
{#if manageDialog}
  <div class="backdrop" on:click={() => (manageDialog = false)}>
    <div class="dialog" on:click|stopPropagation={() => {}}>
      <h2>Manage Tags</h2>
      {#if tagKeys.length === 0}
        <p>No tags defined.</p>
      {:else}
        <ul class="manage-list">
          {#each tagKeys as tag (tag)}
            <li>
              <span class="pill" style="--pill: {settings.tag_colors[tag] || previewColors[tag] || '#888'}">{tag}</span>
              <span class="spacer" />
              <button on:click={() => renameTag(tag)}>Rename…</button>
              <button on:click={() => openColorDialog(tag)}>Recolor…</button>
              <button on:click={() => deleteTag(tag)}>Delete</button>
            </li>
          {/each}
        </ul>
      {/if}
      <div class="buttons">
        <button class="primary" on:click={() => (manageDialog = false)}>Close</button>
      </div>
    </div>
  </div>
{/if}

<!-- Tag color dialog -->
{#if colorDialog}
  <div class="backdrop" on:click={() => (colorDialog = false)}>
    <div class="dialog" on:click|stopPropagation={() => {}}>
      <h2>Color for “{colorTag}”</h2>
      <label>Pick a color or enter a hex value:</label>
      <div class="row">
        <input
          type="color"
          bind:value={colorValue}
          on:input={() => (colorHex = colorValue)}
        />
        <input
          bind:value={colorHex}
          placeholder="#rrggbb"
          on:input={() => setColorFromHex(colorHex)}
          on:keydown={(e) => e.key === "Enter" && applyTagColor()}
        />
      </div>
      <div class="buttons">
        <button on:click={() => (colorDialog = false)}>Cancel</button>
        <button class="primary" on:click={applyTagColor}>OK</button>
      </div>
    </div>
  </div>
{/if}

<!-- About dialog -->
{#if aboutDialog}
  <div class="backdrop" on:click={() => (aboutDialog = false)}>
    <div class="dialog narrow" on:click|stopPropagation={() => {}}>
      <h2>feeds</h2>
      <p>An RSS/Atom feed indexer.</p>
      <p>Version {version}</p>
      <p>
        <a
          href="https://github.com/phagenlocher/feeds"
          on:click|preventDefault={() => openUrl("https://github.com/phagenlocher/feeds")}
          >Visit on GitHub</a
        >
      </p>
      <div class="buttons">
        <button class="primary" on:click={() => (aboutDialog = false)}>OK</button>
      </div>
    </div>
  </div>
{/if}

<style>
  :global(:root) {
    --font-size: 14px;
    --bg: Canvas;
    --fg: CanvasText;
    --muted: color-mix(in srgb, CanvasText 55%, Canvas);
    --border: color-mix(in srgb, CanvasText 15%, Canvas);
    --hover: color-mix(in srgb, CanvasText 8%, Canvas);
    --highlight: Highlight;
    --highlight-fg: HighlightText;
  }
  :global(body) {
    margin: 0;
    font-family: system-ui, sans-serif;
    font-size: var(--font-size);
    color: var(--fg);
    background: var(--bg);
  }
  .app {
    display: flex;
    flex-direction: column;
    height: 100vh;
    font-size: var(--font-size);
  }
  .search,
  .tag-filter {
    margin: 4px;
    padding: 4px 6px;
    font-size: inherit;
    background: var(--bg);
    color: var(--fg);
    border: 1px solid var(--border);
    border-radius: 4px;
  }
  .tree {
    flex: 1;
    overflow: auto;
  }
  .feed-row,
  .entry-row {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 8px;
    cursor: pointer;
    user-select: none;
    white-space: nowrap;
  }
  .feed-row {
    min-height: calc(var(--font-size) + 8px);
  }
  .entry-row {
    min-height: calc(var(--font-size) + 8px);
    padding-left: calc(var(--font-size) + 12px);
  }
  .feed-row:hover,
  .entry-row:hover {
    background: var(--hover);
  }
  .feed-row.selected,
  .entry-row.selected {
    background: var(--highlight);
    color: var(--highlight-fg);
  }
  .bold {
    font-weight: 600;
  }
  .disclosure {
    width: 1em;
    height: 1em;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    transform-origin: center;
    color: var(--muted);
  }
  .disclosure svg {
    width: 0.55em;
    height: 0.55em;
    display: block;
    fill: currentColor;
  }
  .selected .disclosure {
    color: var(--highlight-fg);
  }
  .disclosure.open {
    transform: rotate(90deg);
  }
  .feed-title {
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .entry-title {
    /* Shrink and ellipsize so the date on the right stays visible. */
    flex: 0 1 auto;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .entry-date,
  .feed-date {
    font-size: 0.8em;
    color: var(--muted);
    flex: 0 0 auto;
    white-space: nowrap;
  }
  .selected .entry-date,
  .selected .feed-date {
    color: var(--highlight-fg);
  }
  .spacer {
    flex: 1;
  }
  .pill {
    font-size: 0.75em;
    padding: 1px 6px;
    border: 1px solid var(--pill);
    border-radius: 6px;
    color: var(--pill);
    /* Opaque: mix with the surface colour, not `transparent`, so a selected
       (highlighted) row's background can't bleed through the pill. */
    background: color-mix(in srgb, var(--pill) 15%, var(--bg));
  }
  .statusbar {
    border-top: 1px solid var(--border);
    padding: 3px 8px;
    font-size: 0.85em;
    color: var(--muted);
    min-height: 1.2em;
  }
  .statusbar.busy {
    color: var(--fg);
  }
  .ctx {
    position: fixed;
    z-index: 50;
    background: var(--bg);
    color: var(--fg);
    border: 1px solid var(--border);
    border-radius: 6px;
    box-shadow: 0 6px 24px rgba(0, 0, 0, 0.25);
    padding: 4px;
    display: flex;
    flex-direction: column;
    min-width: 160px;
    max-height: calc(100vh - 8px);
    overflow: auto;
  }
  .ctx button {
    text-align: left;
    background: none;
    border: none;
    color: inherit;
    padding: 5px 8px;
    border-radius: 4px;
    font-size: inherit;
    cursor: pointer;
  }
  .ctx button:hover {
    background: var(--hover);
  }
  .ctx hr {
    border: none;
    border-top: 1px solid var(--border);
    margin: 4px 0;
  }
  .backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.4);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 100;
  }
  .dialog {
    background: var(--bg);
    color: var(--fg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px;
    min-width: 360px;
    max-width: 520px;
    max-height: 80vh;
    overflow: auto;
  }
  .dialog.narrow {
    min-width: 280px;
    text-align: center;
  }
  .dialog h2 {
    margin: 0 0 12px;
    font-size: 1.25em;
  }
  .dialog label {
    display: block;
    margin-bottom: 4px;
    color: var(--muted);
  }
  .dialog input[type="text"],
  .dialog input[type="number"],
  .dialog input:not([type]) {
    width: 100%;
    box-sizing: border-box;
    padding: 6px;
    font-size: inherit;
    background: var(--bg);
    color: var(--fg);
    border: 1px solid var(--border);
    border-radius: 4px;
  }
  /* Form controls don't inherit the page font by default, so set it
     explicitly and size the box in `em`: that makes checkboxes track the
     zoom-scaled `--font-size` instead of their fixed intrinsic size. */
  input[type="checkbox"] {
    font-size: inherit;
    width: 1.1em;
    height: 1.1em;
    flex: none;
    accent-color: var(--highlight);
  }
  .buttons {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    margin-top: 16px;
  }
  button {
    font-size: inherit;
    padding: 5px 12px;
    border-radius: 5px;
    border: 1px solid var(--border);
    background: var(--bg);
    color: var(--fg);
    cursor: pointer;
  }
  button:hover {
    background: var(--hover);
  }
  button.primary {
    background: var(--highlight);
    color: var(--highlight-fg);
    border-color: var(--highlight);
  }
  button:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .choices,
  .tags {
    display: flex;
    flex-direction: column;
    gap: 6px;
    max-height: 40vh;
    overflow: auto;
    margin: 8px 0;
  }
  .choice {
    display: flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
    padding: 2px 0;
  }
  .row {
    display: flex;
    gap: 8px;
    align-items: center;
  }
  .row input {
    flex: 1;
    padding: 6px;
    font-size: inherit;
    background: var(--bg);
    color: var(--fg);
    border: 1px solid var(--border);
    border-radius: 4px;
  }
  .row input[type="color"] {
    flex: 0 0 48px;
    height: 32px;
    padding: 2px;
    cursor: pointer;
  }
  .manage-list {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .manage-list li {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .manage-list button {
    padding: 3px 8px;
    font-size: 0.85em;
  }
</style>

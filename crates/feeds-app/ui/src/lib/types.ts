export interface Feed {
  id: string;
  title: string;
  last_updated: string | null;
  user_title: string | null;
}

export interface Entry {
  url: string;
  title: string;
  date: string | null;
  entry_id: string;
  feed_id: string;
  read: boolean;
  author: string;
}

export interface FeedNode {
  feed: Feed;
  unread: number;
  tags: string[];
  entries: Entry[];
  newest_date: string | null;
}

export interface UpdateFailure {
  url: string;
  title: string;
  error: string;
}

export interface UpdateReport {
  updated: number;
  new_entries: number;
  failed: number;
  failures: UpdateFailure[];
}

export interface Discovered {
  url: string;
  title: string;
}

export interface Settings {
  font_size: number;
  tag_colors: Record<string, string>;
}

export const UNTAGGED = "__untagged__";

"use client";

import type { Article, Feed } from "../lib/api";
import { ArticleRow } from "./ArticleRow";

type Props = {
  articles: Article[];
  /** false until the first article fetch resolves — suppresses the empty-state flash */
  loaded: boolean;
  queuedIds: Set<number>;
  unreadOnly: boolean;
  onUnreadOnly: (v: boolean) => void;
  search: string;
  onSearch: (v: string) => void;
  markReadOnExpand: boolean;
  onToggleQueue: (article: Article) => void;
  onRead: (article: Article) => void;
  currentFeed: Feed | null;
  currentGroup: { name: string } | null;
  lastPoll: string | null;
};

function hhmmss(iso: string | null): string {
  if (!iso) return "never";
  const d = new Date(iso);
  return d.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function ymd(): string {
  const d = new Date();
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, "0")}.${String(d.getDate()).padStart(2, "0")}`;
}

export function ArticleList({
  articles,
  loaded,
  queuedIds,
  unreadOnly,
  onUnreadOnly,
  search,
  onSearch,
  markReadOnExpand,
  onToggleQueue,
  onRead,
  currentFeed,
  currentGroup,
  lastPoll,
}: Props) {
  const title = currentFeed?.title ?? currentGroup?.name ?? "All dispatches";
  const total = articles.length;
  // The empty pane means different things — don't blame the user's setup when
  // they've just searched or read everything.
  const empty = search.trim()
    ? { head: "No matches", body: `Nothing matches “${search.trim()}”. Clear the search to see all.` }
    : unreadOnly
      ? { head: "All caught up", body: "Nothing unread here — switch off “Unread only” to see read articles." }
      : { head: "No dispatches yet", body: "Add a feed and refresh to populate the stream." };

  return (
    <div>
      <div className="content-head">
        <div>
          <span className="eyebrow">02 — Dispatch · {ymd()}</span>
          <h2 className="content-title">{title}</h2>
        </div>
        <div className="content-meta">
          <span>
            Count <strong>{String(total).padStart(3, "0")}</strong>
          </span>
          <span>
            Last poll <strong>{hhmmss(lastPoll)}</strong>
          </span>
        </div>
      </div>

      <div className="list-controls">
        <label className="filter-toggle">
          <input
            type="checkbox"
            className="checkbox"
            checked={unreadOnly}
            onChange={(e) => onUnreadOnly(e.target.checked)}
          />
          <span>Unread only</span>
        </label>
        <input
          type="search"
          className="search-input"
          placeholder="Search title / summary…"
          value={search}
          onChange={(e) => onSearch(e.target.value)}
          aria-label="Search articles"
        />
      </div>

      {!loaded ? (
        <p className="empty-state" aria-busy="true">
          Loading dispatches…
        </p>
      ) : articles.length === 0 ? (
        <p className="empty-state">
          {empty.head}
          <small>{empty.body}</small>
        </p>
      ) : (
        <div className="article-list">
          {articles.map((a, i) => (
            <ArticleRow
              key={a.id}
              article={a}
              index={i}
              total={total}
              queued={queuedIds.has(a.id)}
              markReadOnExpand={markReadOnExpand}
              onToggleQueue={() => onToggleQueue(a)}
              onRead={onRead}
            />
          ))}
        </div>
      )}
    </div>
  );
}

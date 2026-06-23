"use client";

import { useEffect, useRef, useState } from "react";
import type { Article, ArticleDetail, Feed } from "../lib/api";
import { api } from "../lib/api";
import { hostnameOf } from "../lib/url";
import { ArticleReaderDrawer } from "./ArticleReaderDrawer";
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

function plainSummary(raw: string | null): string {
  if (!raw) return "";
  const withoutTags = raw.replace(/<[^>]*>/g, " ");
  const decoded = withoutTags
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#(\d+);/g, (_, n) => String.fromCharCode(Number(n)));
  return decoded.replace(/\s+/g, " ").trim();
}

/** The triage reader: the same slide-over as the edition review, opened over
 * the current article list with prev/next across it. Loads full content on
 * open (fetching it on demand when it isn't cached) and marks the article seen
 * when configured — the behaviour the old inline expander had. */
function TriageReader({
  articles,
  index,
  onIndex,
  onClose,
  markReadOnExpand,
  onRead,
}: {
  articles: Article[];
  index: number;
  onIndex: (i: number) => void;
  onClose: () => void;
  markReadOnExpand: boolean;
  onRead: (article: Article) => void;
}) {
  const article = articles[index];
  const [detail, setDetail] = useState<ArticleDetail | null>(null);
  const [loading, setLoading] = useState(false);
  // Articles whose content we've already pulled this session — re-opening one
  // shouldn't re-fetch (and re-mark-read) it.
  const seen = useRef<Set<number>>(new Set());

  useEffect(() => {
    let live = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDetail(null);
    setLoading(true);

    if (markReadOnExpand && !article.read_at && !seen.current.has(article.id)) {
      api.markRead(article.id).then(onRead).catch(() => {});
    }
    seen.current.add(article.id);

    // Cached content comes straight back; uncached articles are fetched on
    // demand, falling back to whatever is stored if the live fetch fails.
    const load = article.has_full_content
      ? api.getArticle(article.id)
      : api.fetchArticle(article.id).catch(() => api.getArticle(article.id));
    load
      .then((d) => live && setDetail(d))
      .catch(() => live && setDetail(null))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
    // onRead is stable (useCallback in the parent); article identity drives this.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [article.id]);

  const hasContent = detail ? Boolean(detail.full_content) : article.has_full_content;
  return (
    <ArticleReaderDrawer
      eyebrow={`${hostnameOf(article.url)} · ${hasContent ? "Full" : "Summary"}`}
      title={article.title}
      url={article.url}
      index={index}
      count={articles.length}
      onIndex={onIndex}
      onClose={onClose}
      loading={loading}
      detail={detail}
      fallback={plainSummary(detail?.summary ?? article.summary) || "(no content available)"}
    />
  );
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
  // null = closed. A stale index (list shrank under an open reader) simply
  // renders nothing — guarded at the render site below.
  const [readIndex, setReadIndex] = useState<number | null>(null);

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
              onToggleQueue={() => onToggleQueue(a)}
              onOpen={() => setReadIndex(i)}
            />
          ))}
        </div>
      )}

      {readIndex !== null && readIndex < articles.length && (
        <TriageReader
          articles={articles}
          index={readIndex}
          onIndex={setReadIndex}
          onClose={() => setReadIndex(null)}
          markReadOnExpand={markReadOnExpand}
          onRead={onRead}
        />
      )}
    </div>
  );
}

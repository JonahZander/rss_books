"use client";

import { useEffect, useRef, useState } from "react";
import type { Article, ArticleDetail, Feed } from "../lib/api";
import { api } from "../lib/api";
import { hhmmss, plainSummary, ymd } from "../lib/format";
import { hostnameOf } from "../lib/url";
import { ArticleReaderDrawer } from "./ArticleReaderDrawer";
import { ArticleRow } from "./ArticleRow";

type Props = {
  articles: Article[];
  /** false until the first article fetch resolves; suppresses the empty-state flash */
  loaded: boolean;
  queuedIds: Set<number>;
  unreadOnly: boolean;
  onUnreadOnly: (v: boolean) => void;
  search: string;
  onSearch: (v: string) => void;
  markReadOnExpand: boolean;
  onToggleQueue: (article: Article) => void;
  onRead: (article: Article) => void;
  onToggleRead: (article: Article) => void;
  onMarkAllSeen: () => void;
  currentFeed: Feed | null;
  currentGroup: { name: string } | null;
  lastPoll: string | null;
  page: number;
  pageSize: number;
  hasNext: boolean;
  onPrev: () => void;
  onNext: () => void;
};

/** The triage reader: the same slide-over as the edition review, opened over
 * the current article list with prev/next across it. Loads full content on
 * open (fetching it on demand when it isn't cached) and marks the article seen
 * when configured, the behaviour the old inline expander had. */
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
  // Per-session content cache, keyed by article id. Re-opening an article we've
  // already pulled this session returns straight from here with no second fetch.
  const cache = useRef<Map<number, ArticleDetail>>(new Map());
  const [detail, setDetail] = useState<ArticleDetail | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let live = true;

    const cached = cache.current.get(article.id);
    if (cached) {
      // Already fetched this session: show it immediately, skip the network.
      setDetail(cached);
      setLoading(false);
      return;
    }

    setDetail(null);
    setLoading(true);

    if (markReadOnExpand && !article.read_at) {
      api.markRead(article.id).then(onRead).catch(() => {});
    }

    // Cached content comes straight back; uncached articles are fetched on
    // demand, falling back to whatever is stored if the live fetch fails.
    const load = article.has_full_content
      ? api.getArticle(article.id)
      : api.fetchArticle(article.id).catch(() => api.getArticle(article.id));
    load
      .then((d) => {
        if (!live) return;
        cache.current.set(article.id, d);
        setDetail(d);
      })
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
  onToggleRead,
  onMarkAllSeen,
  currentFeed,
  currentGroup,
  lastPoll,
  page,
  pageSize,
  hasNext,
  onPrev,
  onNext,
}: Props) {
  const title = currentFeed?.title ?? currentGroup?.name ?? "All dispatches";
  const total = articles.length;
  const searchActive = search.trim() !== "";
  const hasUnreadInView = articles.some((a) => !a.read_at);
  const numberOffset = page * pageSize;
  // null = closed. A stale index (list shrank under an open reader) simply
  // renders nothing; guarded at the render site below.
  const [readIndex, setReadIndex] = useState<number | null>(null);

  // Jump back to the top of the scroll column whenever the page turns.
  useEffect(() => {
    document.querySelector(".content")?.scrollTo({ top: 0 });
  }, [page]);

  // The empty pane means different things, so don't blame the user's setup when
  // they've just searched or read everything.
  const empty = search.trim()
    ? { head: "No matches", body: `Nothing matches “${search.trim()}”. Clear the search to see all.` }
    : unreadOnly
      ? { head: "All caught up", body: "Nothing unread here. Switch off “Unread only” to see read articles." }
      : { head: "No dispatches yet", body: "Add a feed and refresh to populate the stream." };

  return (
    <div>
      <div className="content-head">
        <div>
          <span className="eyebrow">Dispatch · {ymd()}</span>
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
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={onMarkAllSeen}
          disabled={searchActive || !hasUnreadInView}
          title={searchActive ? "Clear the search to mark all seen" : undefined}
        >
          <span>Mark all seen</span>
          <span className="btn-arrow">✓</span>
        </button>
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
              number={numberOffset + i + 1}
              queued={queuedIds.has(a.id)}
              onToggleQueue={() => onToggleQueue(a)}
              onToggleRead={() => onToggleRead(a)}
              onOpen={() => setReadIndex(i)}
            />
          ))}
        </div>
      )}

      {loaded && (page > 0 || hasNext) && (
        <div className="pager">
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={onPrev}
            disabled={page === 0}
          >
            <span className="btn-arrow">←</span>
            <span>Prev</span>
          </button>
          <span className="pager-label">Page {page + 1}</span>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={onNext}
            disabled={!hasNext}
          >
            <span>Next</span>
            <span className="btn-arrow">→</span>
          </button>
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

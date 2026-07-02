"use client";

import type { Article } from "../lib/api";
import { fmtTimestamp, plainSummary } from "../lib/format";
import { hostnameOf } from "../lib/url";

type Props = {
  article: Article;
  /** 1-based position in the overall list (absolute across pages). */
  number: number;
  queued: boolean;
  onToggleQueue: () => void;
  onOpen: () => void;
};

function pad(n: number, width: number): string {
  return String(n).padStart(width, "0");
}

type Lifecycle = "new" | "seen" | "queued" | "in_edition";

const LIFECYCLE_LABEL: Record<Lifecycle, string> = {
  new: "New",
  seen: "Seen",
  queued: "Queued",
  in_edition: "In edition",
};

/**
 * Resolve the effective lifecycle for display. `article.state` is authoritative
 * on load; `queued` is the optimistic overlay for the moment the box is ticked.
 * Precedence: in_edition > queued (local OR state) > seen > new.
 */
function lifecycleOf(article: Article, queued: boolean): Lifecycle {
  if (article.state === "in_edition") return "in_edition";
  if (queued || article.state === "queued") return "queued";
  if (article.state === "seen" || article.read_at) return "seen";
  return "new";
}

export function ArticleRow({ article, number, queued, onToggleQueue, onOpen }: Props) {
  const idx = pad(number, 2);
  const lifecycle = lifecycleOf(article, queued);

  return (
    <article
      className={`article-row ${queued ? "selected" : ""} state-${lifecycle}`}
      style={{ "--row-index": Math.min(number - 1, 12) } as React.CSSProperties}
      onClick={onOpen}
    >
      <header className="article-header">
        <span className="article-index">{idx}</span>
        <label className="checkbox-hit">
          <input
            type="checkbox"
            className="checkbox"
            checked={queued}
            onChange={onToggleQueue}
            onClick={(e) => e.stopPropagation()}
            aria-label={`Queue ${article.title}`}
          />
        </label>
        {/* Keep a real button for keyboard focus; clicking anywhere on the row
            also opens the reader (handled on the article element). */}
        <button type="button" className="article-title" onClick={onOpen}>
          <span>{article.title}</span>
        </button>
        {/* Lifecycle badge lives in a fixed right-hand column so every row's
            stamp sits in the same spot regardless of label length. */}
        <span className={`lifecycle-stamp lc-${lifecycle}`}>
          <span className="status-square" aria-hidden />
          {LIFECYCLE_LABEL[lifecycle]}
        </span>
      </header>

      <div className="article-meta">
        <a
          href={article.url}
          target="_blank"
          rel="noreferrer"
          onClick={(e) => e.stopPropagation()}
        >
          {hostnameOf(article.url)} ↗
        </a>
        {article.published_at && <span>{fmtTimestamp(article.published_at)}</span>}
      </div>

      {(() => {
        const text = plainSummary(article.summary);
        if (!text) return null;
        const trimmed = text.length > 220 ? text.slice(0, 220).trimEnd() + "…" : text;
        return <p className="article-summary">{trimmed}</p>;
      })()}
    </article>
  );
}

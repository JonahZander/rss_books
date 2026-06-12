"use client";

import { useState } from "react";
import type { Article, ArticleDetail } from "../lib/api";
import { api } from "../lib/api";

type Props = {
  article: Article;
  index: number;
  total: number;
  queued: boolean;
  markReadOnExpand: boolean;
  onToggleQueue: () => void;
  onRead: (article: Article) => void;
};

function hostnameOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function fmtTimestamp(iso: string): string {
  const d = new Date(iso);
  const date = `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, "0")}.${String(d.getDate()).padStart(2, "0")}`;
  const time = d.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  return `${date} · ${time}`;
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

function pad(n: number, width: number): string {
  return String(n).padStart(width, "0");
}

export function ArticleRow({
  article,
  index,
  total,
  queued,
  markReadOnExpand,
  onToggleQueue,
  onRead,
}: Props) {
  const [expanded, setExpanded] = useState(false);
  const [detail, setDetail] = useState<ArticleDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggle = async () => {
    const willExpand = !expanded;
    setExpanded(willExpand);
    if (!willExpand) return;

    if (markReadOnExpand && !article.read_at) {
      api
        .markRead(article.id)
        .then(onRead)
        .catch(() => {});
    }
    if (!detail) {
      setLoading(true);
      setError(null);
      try {
        const d = article.has_full_content
          ? await api.getArticle(article.id)
          : await api.fetchArticle(article.id);
        setDetail(d);
      } catch (e) {
        setError(e instanceof Error ? e.message : "failed to load");
        try {
          setDetail(await api.getArticle(article.id));
        } catch {
          // keep the error state
        }
      } finally {
        setLoading(false);
      }
    }
  };

  const width = String(total).length;
  const idx = pad(index + 1, Math.max(2, width));
  const totalStr = pad(total, Math.max(2, width));
  const read = Boolean(article.read_at);

  return (
    <article
      className={`article-row ${queued ? "selected" : ""} ${expanded ? "expanded" : ""} ${
        read ? "read" : ""
      }`}
      style={{ "--row-index": Math.min(index, 12) } as React.CSSProperties}
    >
      <header className="article-header">
        <span className="article-index">
          {idx}/{totalStr}
        </span>
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
        <button type="button" className="article-title" onClick={toggle} aria-expanded={expanded}>
          <span className="chev" aria-hidden>
            ›
          </span>
          <span>{article.title}</span>
        </button>
        <span className="article-status">
          <span className={`status-square ${article.has_full_content ? "filled" : ""}`} />
          {article.has_full_content ? "Cached" : "Summary"}
        </span>
      </header>

      <div className="article-meta">
        <a href={article.url} target="_blank" rel="noreferrer">
          {hostnameOf(article.url)} ↗
        </a>
        {article.published_at && <span>{fmtTimestamp(article.published_at)}</span>}
        {read && <span className="read-stamp">Read</span>}
      </div>

      {!expanded &&
        (() => {
          const text = plainSummary(article.summary);
          if (!text) return null;
          const trimmed = text.length > 220 ? text.slice(0, 220).trimEnd() + "…" : text;
          return <p className="article-summary">{trimmed}</p>;
        })()}

      {expanded && (
        <div className="article-body">
          <div className="article-body-label">
            <span className="stamp">Extract</span>
            <span>Trafilatura · {article.has_full_content ? "Cached" : "Fetched just now"}</span>
          </div>
          {loading && <p className="article-body-loading">Fetching full content</p>}
          {error && <p className="article-body-error">⚠ {error}</p>}
          {detail &&
            (detail.full_content ? (
              // full_content is sanitized server-side (nh3 allowlist)
              <div
                className="article-body-content prose"
                dangerouslySetInnerHTML={{ __html: detail.full_content }}
              />
            ) : (
              <div className="article-body-content plain">
                {plainSummary(detail.summary) || "(no content available)"}
              </div>
            ))}
        </div>
      )}
    </article>
  );
}

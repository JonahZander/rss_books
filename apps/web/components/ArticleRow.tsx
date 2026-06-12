"use client";

import { useState } from "react";
import type { Article, ArticleDetail } from "../lib/api";
import { api } from "../lib/api";

type Props = {
  article: Article;
  index: number;
  total: number;
  selected: boolean;
  onToggleSelect: () => void;
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

export function ArticleRow({ article, index, total, selected, onToggleSelect }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [detail, setDetail] = useState<ArticleDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggle = async () => {
    const willExpand = !expanded;
    setExpanded(willExpand);
    if (willExpand && !detail) {
      setLoading(true);
      setError(null);
      try {
        const d = article.has_full_content
          ? await api.getArticle(article.id)
          : await api.fetchArticle(article.id);
        setDetail(d);
      } catch (e) {
        setError(e instanceof Error ? e.message : "failed to load");
      } finally {
        setLoading(false);
      }
    }
  };

  const width = String(total).length;
  const idx = pad(index + 1, Math.max(2, width));
  const totalStr = pad(total, Math.max(2, width));

  return (
    <article className={`article-row ${selected ? "selected" : ""} ${expanded ? "expanded" : ""}`}>
      <header className="article-header">
        <span className="article-index">
          {idx}/{totalStr}
        </span>
        <input
          type="checkbox"
          className="checkbox"
          checked={selected}
          onChange={onToggleSelect}
          onClick={(e) => e.stopPropagation()}
          aria-label={`Select ${article.title}`}
        />
        <button type="button" className="article-title" onClick={toggle}>
          <span className="chev">›</span>
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

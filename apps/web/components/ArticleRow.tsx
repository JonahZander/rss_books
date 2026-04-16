"use client";

import { useState } from "react";
import type { Article, ArticleDetail } from "../lib/api";
import { api } from "../lib/api";

type Props = {
  article: Article;
  selected: boolean;
  onToggleSelect: () => void;
};

export function ArticleRow({ article, selected, onToggleSelect }: Props) {
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

  let hostname = "";
  try {
    hostname = new URL(article.url).hostname;
  } catch {
    hostname = article.url;
  }

  return (
    <article className={`article-row ${expanded ? "expanded" : ""}`}>
      <header className="article-header">
        <input
          type="checkbox"
          checked={selected}
          onChange={onToggleSelect}
          onClick={(e) => e.stopPropagation()}
        />
        <button className="article-toggle" onClick={toggle}>
          <span className="chevron">{expanded ? "▾" : "▸"}</span>
          <span className="title">{article.title}</span>
        </button>
      </header>
      <div className="article-meta">
        <a href={article.url} target="_blank" rel="noreferrer">
          {hostname}
        </a>
        {article.published_at && (
          <time dateTime={article.published_at}>
            {new Date(article.published_at).toLocaleString()}
          </time>
        )}
      </div>
      {!expanded && article.summary && (
        <p className="article-summary">{article.summary.slice(0, 200)}</p>
      )}
      {expanded && (
        <div className="article-body">
          {loading && <p>Loading…</p>}
          {error && <p className="error">{error}</p>}
          {detail && (
            <pre className="content">
              {detail.full_content || detail.summary || "(no content)"}
            </pre>
          )}
        </div>
      )}
    </article>
  );
}

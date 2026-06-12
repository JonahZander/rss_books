"use client";

import type { Article, Feed } from "../lib/api";
import { ArticleRow } from "./ArticleRow";

type Props = {
  articles: Article[];
  selectedIds: Set<number>;
  onToggle: (id: number) => void;
  currentFeed: Feed | null;
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

export function ArticleList({ articles, selectedIds, onToggle, currentFeed, lastPoll }: Props) {
  const title = currentFeed ? currentFeed.title : "All dispatches";
  const total = articles.length;

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
            Selected <strong>{String(selectedIds.size).padStart(2, "0")}</strong>
          </span>
          <span>
            Last poll <strong>{hhmmss(lastPoll)}</strong>
          </span>
        </div>
      </div>

      {articles.length === 0 ? (
        <p className="empty-state">
          No dispatches in queue
          <small>Add a feed and refresh to populate the stream.</small>
        </p>
      ) : (
        <div className="article-list">
          {articles.map((a, i) => (
            <ArticleRow
              key={a.id}
              article={a}
              index={i}
              total={total}
              selected={selectedIds.has(a.id)}
              onToggleSelect={() => onToggle(a.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

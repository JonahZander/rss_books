"use client";

import type { Article } from "../lib/api";
import { ArticleRow } from "./ArticleRow";

type Props = {
  articles: Article[];
  selectedIds: Set<number>;
  onToggle: (id: number) => void;
};

export function ArticleList({ articles, selectedIds, onToggle }: Props) {
  if (articles.length === 0) {
    return <p className="empty">No articles yet. Add a feed and click Refresh.</p>;
  }
  return (
    <div className="article-list">
      {articles.map((a) => (
        <ArticleRow
          key={a.id}
          article={a}
          selected={selectedIds.has(a.id)}
          onToggleSelect={() => onToggle(a.id)}
        />
      ))}
    </div>
  );
}

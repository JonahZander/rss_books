"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ArticleList } from "../components/ArticleList";
import { DigestQueue } from "../components/DigestQueue";
import { FeedSidebar } from "../components/FeedSidebar";
import { api, type Article, type Feed } from "../lib/api";

export default function Home() {
  const [feeds, setFeeds] = useState<Feed[]>([]);
  const [articles, setArticles] = useState<Article[]>([]);
  const [selectedFeedId, setSelectedFeedId] = useState<number | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

  const refreshFeeds = useCallback(async () => {
    setFeeds(await api.listFeeds());
  }, []);

  const refreshArticles = useCallback(async () => {
    setArticles(await api.listArticles(selectedFeedId ?? undefined));
  }, [selectedFeedId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refreshFeeds();
  }, [refreshFeeds]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refreshArticles();
  }, [refreshArticles]);

  const addFeed = async (url: string, title: string) => {
    await api.addFeed(url, title);
    await refreshFeeds();
  };

  const deleteFeed = async (id: number) => {
    await api.deleteFeed(id);
    await refreshFeeds();
    await refreshArticles();
  };

  const pollAll = async () => {
    await api.refreshAll();
    await refreshArticles();
  };

  const toggleSelect = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectedArticles = useMemo(
    () => articles.filter((a) => selectedIds.has(a.id)),
    [articles, selectedIds],
  );

  return (
    <main className="layout">
      <FeedSidebar
        feeds={feeds}
        selectedFeedId={selectedFeedId}
        onSelect={setSelectedFeedId}
        onAdd={addFeed}
        onDelete={deleteFeed}
        onRefresh={pollAll}
      />
      <section className="content">
        <ArticleList articles={articles} selectedIds={selectedIds} onToggle={toggleSelect} />
      </section>
      <DigestQueue selected={selectedArticles} onClear={() => setSelectedIds(new Set())} />
    </main>
  );
}

"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ArticleList } from "../components/ArticleList";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { DigestQueue } from "../components/DigestQueue";
import { FeedSidebar } from "../components/FeedSidebar";
import { Masthead } from "../components/Masthead";
import { useToast } from "../components/Toasts";
import {
  api,
  emailConfigured,
  type AppSettings,
  type Article,
  type Feed,
  type Group,
} from "../lib/api";

type MobilePanel = "feeds" | "articles" | "queue";

export default function Home() {
  const toast = useToast();
  const [feeds, setFeeds] = useState<Feed[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [articles, setArticles] = useState<Article[]>([]);
  const [queue, setQueue] = useState<Article[]>([]);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [selectedFeedId, setSelectedFeedId] = useState<number | null>(null);
  const [unreadOnly, setUnreadOnly] = useState(true);
  const [search, setSearch] = useState("");
  const [lastPoll, setLastPoll] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Feed | null>(null);
  const [mobilePanel, setMobilePanel] = useState<MobilePanel>("articles");

  const refreshFeeds = useCallback(async () => {
    const [feedList, groupList] = await Promise.all([api.listFeeds(), api.listGroups()]);
    setFeeds(feedList);
    setGroups(groupList);
  }, []);

  const refreshArticles = useCallback(async () => {
    setArticles(
      await api.listArticles({
        feedId: selectedFeedId ?? undefined,
        unread: unreadOnly,
        q: search || undefined,
      }),
    );
  }, [selectedFeedId, unreadOnly, search]);

  const refreshQueue = useCallback(async () => {
    setQueue(await api.getQueue());
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refreshFeeds();
    void refreshQueue();
    api.getSettings().then(setSettings, () => {});
  }, [refreshFeeds, refreshQueue]);

  useEffect(() => {
    const id = window.setTimeout(() => void refreshArticles(), search ? 250 : 0);
    return () => window.clearTimeout(id);
  }, [refreshArticles, search]);

  const addFeed = async (url: string, title: string) => {
    try {
      await api.addFeed(url, title);
      toast(`Feed “${title}” committed`);
      await refreshFeeds();
    } catch (e) {
      toast(e instanceof Error ? e.message : "could not add feed", "error");
    }
  };

  const deleteFeed = async () => {
    if (!deleteTarget) return;
    const feed = deleteTarget;
    setDeleteTarget(null);
    try {
      await api.deleteFeed(feed.id);
      toast(`Removed “${feed.title}”`);
      if (selectedFeedId === feed.id) setSelectedFeedId(null);
      await Promise.all([refreshFeeds(), refreshArticles(), refreshQueue()]);
    } catch (e) {
      toast(e instanceof Error ? e.message : "delete failed", "error");
    }
  };

  const pollAll = async () => {
    try {
      const r = await api.refreshAll();
      setLastPoll(new Date().toISOString());
      toast(
        r.errors > 0
          ? `${r.inserted} new · ${r.errors} feed${r.errors === 1 ? "" : "s"} failed`
          : `${r.inserted} new article${r.inserted === 1 ? "" : "s"}`,
        r.errors > 0 ? "error" : "ok",
      );
    } catch (e) {
      toast(e instanceof Error ? e.message : "refresh failed", "error");
    }
    await Promise.all([refreshArticles(), refreshFeeds()]);
  };

  const toggleQueue = async (article: Article) => {
    const queued = queue.some((a) => a.id === article.id);
    try {
      setQueue(
        queued ? await api.removeFromQueue(article.id) : await api.addToQueue(article.id),
      );
    } catch (e) {
      toast(e instanceof Error ? e.message : "queue update failed", "error");
    }
  };

  const onRead = useCallback((updated: Article) => {
    setArticles((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
    setFeeds((prev) =>
      prev.map((f) =>
        f.id === updated.feed_id ? { ...f, unread_count: Math.max(0, f.unread_count - 1) } : f,
      ),
    );
  }, []);

  const onCompiled = useCallback(async () => {
    await Promise.all([refreshQueue(), refreshArticles(), refreshFeeds()]);
  }, [refreshQueue, refreshArticles, refreshFeeds]);

  const queuedIds = useMemo(() => new Set(queue.map((a) => a.id)), [queue]);
  const currentFeed = useMemo(
    () => feeds.find((f) => f.id === selectedFeedId) ?? null,
    [feeds, selectedFeedId],
  );

  return (
    <div className="app">
      <Masthead
        readouts={{
          feedCount: feeds.length,
          articleCount: articles.length,
          queueCount: queue.length,
        }}
      />
      <nav className="mobile-tabs" aria-label="Panels">
        {(
          [
            ["feeds", `Feeds ${feeds.length}`],
            ["articles", `Articles ${articles.length}`],
            ["queue", `Queue ${queue.length}`],
          ] as [MobilePanel, string][]
        ).map(([panel, label]) => (
          <button
            key={panel}
            type="button"
            className={`mobile-tab ${mobilePanel === panel ? "active" : ""}`}
            onClick={() => setMobilePanel(panel)}
            aria-pressed={mobilePanel === panel}
          >
            {label}
          </button>
        ))}
      </nav>
      <main className={`layout panel-${mobilePanel}`}>
        <FeedSidebar
          feeds={feeds}
          selectedFeedId={selectedFeedId}
          onSelect={(id) => {
            setSelectedFeedId(id);
            setMobilePanel("articles");
          }}
          onAdd={addFeed}
          onDelete={setDeleteTarget}
          onRefresh={pollAll}
          onChanged={refreshFeeds}
        />
        <section className="content" aria-label="Articles">
          <ArticleList
            articles={articles}
            queuedIds={queuedIds}
            unreadOnly={unreadOnly}
            onUnreadOnly={setUnreadOnly}
            search={search}
            onSearch={setSearch}
            markReadOnExpand={settings?.mark_read_on_expand ?? true}
            onToggleQueue={toggleQueue}
            onRead={onRead}
            currentFeed={currentFeed}
            lastPoll={lastPoll}
          />
        </section>
        <DigestQueue
          queue={queue}
          emailConfigured={settings ? emailConfigured(settings) : false}
          groupsExist={groups.length > 0}
          onRemove={(a) => void toggleQueue(a)}
          onClear={() => {
            void api.replaceQueue([]).then(setQueue);
          }}
          onCompiled={onCompiled}
        />
      </main>
      <ConfirmDialog
        open={deleteTarget !== null}
        title={`Remove “${deleteTarget?.title ?? ""}”?`}
        body="The feed and all of its articles will be deleted. Articles already pressed into editions stay in those editions."
        confirmLabel="Remove feed"
        onConfirm={() => void deleteFeed()}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}

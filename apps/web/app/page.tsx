"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArticleList } from "../components/ArticleList";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { DigestQueue } from "../components/DigestQueue";
import { FeedSidebar } from "../components/FeedSidebar";
import { Masthead } from "../components/Masthead";
import { OnboardingChecklist } from "../components/OnboardingChecklist";
import { useToast } from "../components/Toasts";
import {
  api,
  defaultProfileName,
  emailConfigured,
  type AppSettings,
  type Article,
  type Feed,
  type Group,
} from "../lib/api";

type MobilePanel = "feeds" | "articles" | "queue";

const PAGE_SIZE = 200;

export default function Home() {
  const toast = useToast();
  const [feeds, setFeeds] = useState<Feed[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [articles, setArticles] = useState<Article[]>([]);
  const [articlesLoaded, setArticlesLoaded] = useState(false);
  const [queue, setQueue] = useState<Article[]>([]);
  const [digestsCount, setDigestsCount] = useState(0);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [selectedFeedId, setSelectedFeedId] = useState<number | null>(null);
  const [selectedGroupId, setSelectedGroupId] = useState<number | "none" | null>(null);
  const [unreadOnly, setUnreadOnly] = useState(true);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [hasNext, setHasNext] = useState(false);
  const [lastPoll, setLastPoll] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Feed | null>(null);
  const [deleteGroupTarget, setDeleteGroupTarget] = useState<Group | null>(null);
  const [mobilePanel, setMobilePanel] = useState<MobilePanel>("articles");
  // Bumped to signal FeedSidebar to open its add-feed form from outside (the
  // onboarding checklist's "Add a feed →"); see FeedSidebar's prop doc.
  const [openAddFeedSignal, setOpenAddFeedSignal] = useState(0);

  const refreshFeeds = useCallback(async () => {
    const [feedList, groupList] = await Promise.all([api.listFeeds(), api.listGroups()]);
    setFeeds(feedList);
    setGroups(groupList);
  }, []);

  // Guards against a slow, stale request clobbering a faster, newer one: each
  // call aborts its predecessor and stamps a sequence number, applying its
  // result only if nothing newer has started in the meantime.
  const articlesAbort = useRef<AbortController | null>(null);
  const articlesSeq = useRef(0);
  const refreshArticles = useCallback(async () => {
    articlesAbort.current?.abort();
    const controller = new AbortController();
    articlesAbort.current = controller;
    const seq = ++articlesSeq.current;
    try {
      const list = await api.listArticles(
        {
          feedId: selectedFeedId ?? undefined,
          groupId: selectedGroupId ?? undefined,
          unread: unreadOnly,
          q: search || undefined,
          limit: PAGE_SIZE,
          offset: page * PAGE_SIZE,
        },
        controller.signal,
      );
      if (seq !== articlesSeq.current) return; // a newer request has since started
      setArticles(list);
      // A full page implies there may be more; one short page ends the run.
      setHasNext(list.length === PAGE_SIZE);
      setArticlesLoaded(true);
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      if (seq !== articlesSeq.current) return;
      toast(e instanceof Error ? e.message : "could not load articles", "error");
    }
  }, [selectedFeedId, selectedGroupId, unreadOnly, search, page, toast]);

  const refreshQueue = useCallback(async () => {
    setQueue(await api.getQueue());
  }, []);

  // Only a count: the onboarding checklist needs a boolean ("an edition
  // exists"), and DigestQueue already owns the full, session-local digest
  // list — this avoids a second source of truth next to it.
  const refreshDigestsCount = useCallback(async () => {
    setDigestsCount((await api.listDigests()).length);
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refreshFeeds();
    void refreshQueue();
    void refreshDigestsCount();
    api.getSettings().then(setSettings, (e) => {
      toast(e instanceof Error ? e.message : "could not load settings", "error");
    });
  }, [refreshFeeds, refreshQueue, refreshDigestsCount, toast]);

  // Debounce only the search box; feed/group/unread switches should feel instant.
  const prevSearch = useRef(search);
  useEffect(() => {
    const searchChanged = prevSearch.current !== search;
    prevSearch.current = search;
    const id = window.setTimeout(() => void refreshArticles(), searchChanged ? 250 : 0);
    return () => window.clearTimeout(id);
  }, [refreshArticles, search]);

  const addFeed = async (url: string, title: string) => {
    try {
      await api.addFeed(url, title);
      toast(`Feed “${title}” added`);
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

  const deleteGroup = async () => {
    if (!deleteGroupTarget) return;
    const group = deleteGroupTarget;
    setDeleteGroupTarget(null);
    try {
      await api.deleteGroup(group.id);
      toast(`Group “${group.name}” dissolved, feeds kept`);
      if (selectedGroupId === group.id) setSelectedGroupId(null);
      await Promise.all([refreshFeeds(), refreshArticles()]);
    } catch (e) {
      toast(e instanceof Error ? e.message : "delete failed", "error");
    }
  };

  const selectFeed = useCallback((id: number | null) => {
    setSelectedFeedId(id);
    setSelectedGroupId(null);
    setPage(0);
    setMobilePanel("articles");
  }, []);

  const selectGroup = useCallback((id: number | "none" | null) => {
    setSelectedGroupId(id);
    setSelectedFeedId(null);
    setPage(0);
    setMobilePanel("articles");
  }, []);

  // Filter/search changes always return to the first page.
  const changeUnreadOnly = useCallback((v: boolean) => {
    setUnreadOnly(v);
    setPage(0);
  }, []);

  const changeSearch = useCallback((v: string) => {
    setSearch(v);
    setPage(0);
  }, []);

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
    const prev = queue;
    // Flip the checkbox immediately, then reconcile with the server's canonical
    // queue; roll back if the request fails.
    setQueue(queued ? prev.filter((a) => a.id !== article.id) : [...prev, article]);
    try {
      const next = queued
        ? await api.removeFromQueue(article.id)
        : await api.addToQueue(article.id);
      setQueue(next);
    } catch (e) {
      setQueue(prev);
      toast(e instanceof Error ? e.message : "queue update failed", "error");
    }
  };

  const reorderQueue = async (next: Article[]) => {
    const prev = queue;
    setQueue(next); // optimistic; reconciled with the server's canonical order below
    try {
      setQueue(await api.replaceQueue(next.map((a) => a.id)));
    } catch (e) {
      setQueue(prev);
      toast(e instanceof Error ? e.message : "reorder failed", "error");
    }
  };

  const addLink = async (url: string, title?: string) => {
    // The new article belongs to the hidden Saved-links feed, so it won't show
    // in the article list; reflecting it in the queue is enough.
    setQueue(await api.addLinkToQueue(url, title));
  };

  // Direction-aware: wasRead is the article's read state BEFORE this update,
  // so unread_count moves the opposite way (-1 marking read, +1 unmarking).
  const onArticleReadChange = useCallback((updated: Article, wasRead: boolean) => {
    setArticles((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
    setFeeds((prev) =>
      prev.map((f) =>
        f.id === updated.feed_id
          ? { ...f, unread_count: Math.max(0, f.unread_count + (wasRead ? 1 : -1)) }
          : f,
      ),
    );
  }, []);

  // TriageReader's mark-on-expand only ever marks read (wasRead is always
  // false there — it checks !article.read_at before calling this).
  const onRead = useCallback(
    (updated: Article) => onArticleReadChange(updated, false),
    [onArticleReadChange],
  );

  const toggleRead = async (article: Article) => {
    const wasRead = Boolean(article.read_at);
    try {
      const updated = wasRead ? await api.markUnread(article.id) : await api.markRead(article.id);
      onArticleReadChange(updated, wasRead);
    } catch (e) {
      toast(e instanceof Error ? e.message : "update failed", "error");
    }
  };

  const markAllSeen = async () => {
    try {
      const r = await api.markAllRead({
        feedId: selectedFeedId ?? undefined,
        groupId: selectedGroupId ?? undefined,
      });
      toast(`${r.updated} marked seen`);
      await Promise.all([refreshArticles(), refreshFeeds()]);
    } catch (e) {
      toast(e instanceof Error ? e.message : "mark all seen failed", "error");
    }
  };

  const onCompiled = useCallback(async () => {
    await Promise.all([refreshQueue(), refreshArticles(), refreshFeeds(), refreshDigestsCount()]);
  }, [refreshQueue, refreshArticles, refreshFeeds, refreshDigestsCount]);

  // Onboarding checklist actions: jump to the relevant mobile panel, then
  // hand off to the target — opening the add-feed form (FeedSidebar owns
  // that state) or scrolling the queue/compile panel into view.
  const focusAddFeed = useCallback(() => {
    setMobilePanel("feeds");
    setOpenAddFeedSignal((n) => n + 1);
  }, []);

  const goToQueue = useCallback(() => {
    setMobilePanel("queue");
    requestAnimationFrame(() => {
      document.querySelector(".digest-queue")?.scrollIntoView({ block: "start", behavior: "smooth" });
    });
  }, []);

  const queuedIds = useMemo(() => new Set(queue.map((a) => a.id)), [queue]);
  const currentFeed = useMemo(
    () => feeds.find((f) => f.id === selectedFeedId) ?? null,
    [feeds, selectedFeedId],
  );
  const currentGroup = useMemo(() => {
    if (selectedGroupId === "none") return { name: "Ungrouped" };
    return groups.find((g) => g.id === selectedGroupId) ?? null;
  }, [groups, selectedGroupId]);

  // a deleted/renamed-away group can't stay selected
  useEffect(() => {
    if (typeof selectedGroupId === "number" && !groups.some((g) => g.id === selectedGroupId)) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSelectedGroupId(null);
    }
  }, [groups, selectedGroupId]);

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
          groups={groups}
          selectedFeedId={selectedFeedId}
          selectedGroupId={selectedGroupId}
          onSelect={selectFeed}
          onSelectGroup={selectGroup}
          onAdd={addFeed}
          onDelete={setDeleteTarget}
          onDeleteGroup={setDeleteGroupTarget}
          onRefresh={pollAll}
          onChanged={refreshFeeds}
          defaultPollMinutes={settings?.default_poll_minutes ?? 30}
          openAddFeedSignal={openAddFeedSignal}
        />
        <section className="content" aria-label="Articles">
          <OnboardingChecklist
            hasFeeds={feeds.length > 0}
            hasQueuedEver={queue.length > 0 || digestsCount > 0}
            hasEdition={digestsCount > 0}
            deliveryReady={settings ? emailConfigured(settings) : false}
            onFocusAddFeed={focusAddFeed}
            onGoToQueue={goToQueue}
          />
          <ArticleList
            articles={articles}
            loaded={articlesLoaded}
            queuedIds={queuedIds}
            unreadOnly={unreadOnly}
            onUnreadOnly={changeUnreadOnly}
            search={search}
            onSearch={changeSearch}
            markReadOnExpand={settings?.mark_read_on_expand ?? true}
            onToggleQueue={toggleQueue}
            onRead={onRead}
            onToggleRead={(a) => void toggleRead(a)}
            onMarkAllSeen={() => void markAllSeen()}
            currentFeed={currentFeed}
            currentGroup={currentGroup}
            lastPoll={lastPoll}
            page={page}
            pageSize={PAGE_SIZE}
            hasNext={hasNext}
            onPrev={() => setPage((p) => Math.max(0, p - 1))}
            onNext={() => setPage((p) => p + 1)}
          />
        </section>
        <DigestQueue
          queue={queue}
          emailConfigured={settings ? emailConfigured(settings) : false}
          groupsExist={groups.length > 0}
          profiles={settings?.profiles.map((p) => p.name) ?? []}
          defaultProfile={settings ? defaultProfileName(settings) : null}
          onRemove={(a) => void toggleQueue(a)}
          onReorder={(next) => void reorderQueue(next)}
          onClear={() => {
            void api.replaceQueue([]).then(setQueue);
          }}
          onAddLink={addLink}
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
      <ConfirmDialog
        open={deleteGroupTarget !== null}
        title={`Dissolve “${deleteGroupTarget?.name ?? ""}”?`}
        body="Feeds in this group keep their subscriptions and articles; they just become ungrouped."
        confirmLabel="Dissolve group"
        onConfirm={() => void deleteGroup()}
        onCancel={() => setDeleteGroupTarget(null)}
      />
    </div>
  );
}

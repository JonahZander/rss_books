"use client";

import { useRef, useState } from "react";
import type { Feed } from "../lib/api";
import { api } from "../lib/api";
import { useToast } from "./Toasts";

type Props = {
  feeds: Feed[];
  selectedFeedId: number | null;
  onSelect: (id: number | null) => void;
  onAdd: (url: string, title: string) => Promise<void>;
  onDelete: (feed: Feed) => void;
  onRefresh: () => Promise<void>;
  onChanged: () => Promise<void>;
};

const pad2 = (n: number) => String(n).padStart(2, "0");

function hostnameOf(url: string | null): string {
  if (!url) return "";
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function relPoll(iso: string | null): string {
  if (!iso) return "never polled";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  const mins = Math.round((Date.now() - d.getTime()) / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export function FeedSidebar({
  feeds,
  selectedFeedId,
  onSelect,
  onAdd,
  onDelete,
  onRefresh,
  onChanged,
}: Props) {
  const toast = useToast();
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [renamingId, setRenamingId] = useState<number | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url || !title) return;
    setBusy(true);
    try {
      await onAdd(url, title);
      setUrl("");
      setTitle("");
    } finally {
      setBusy(false);
    }
  };

  const refresh = async () => {
    setRefreshing(true);
    try {
      await onRefresh();
    } finally {
      setRefreshing(false);
    }
  };

  const saveRename = async (feed: Feed) => {
    const next = renameValue.trim();
    setRenamingId(null);
    if (!next || next === feed.title) return;
    try {
      await api.patchFeed(feed.id, { title: next });
      await onChanged();
      toast(`Renamed to “${next}”`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "rename failed", "error");
    }
  };

  const refreshOne = async (feed: Feed) => {
    try {
      const r = await api.refreshFeed(feed.id);
      toast(`${feed.title}: ${r.inserted} new`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "refresh failed", "error");
    }
    await onChanged();
  };

  const importOpml = async (file: File) => {
    try {
      const r = await api.importOpml(file);
      toast(`OPML import: ${r.added} added, ${r.skipped} skipped`);
      await onChanged();
    } catch (e) {
      toast(e instanceof Error ? e.message : "import failed", "error");
    }
  };

  return (
    <aside className="feed-sidebar" aria-label="Feeds">
      <div className="section-head">
        <span className="eyebrow eyebrow-ink">00 — Index / Feeds</span>
        <span className="counter">{pad2(feeds.length)}</span>
      </div>

      <ul className="feed-list">
        <li>
          <button
            type="button"
            className={`feed-row all ${selectedFeedId === null ? "active" : ""}`}
            onClick={() => onSelect(null)}
          >
            <span className="feed-row-index">★</span>
            <span>
              <span className="feed-row-title">All dispatches</span>
              <span className="feed-row-sub">Unified stream · All feeds</span>
            </span>
          </button>
        </li>
        {feeds.map((f, i) => (
          <li key={f.id}>
            <div
              className={`feed-row ${selectedFeedId === f.id ? "active" : ""}`}
              onClick={() => onSelect(f.id)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelect(f.id);
                }
              }}
            >
              <span className="feed-row-index">{pad2(i + 1)}</span>
              {renamingId === f.id ? (
                <input
                  className="feed-rename-input"
                  value={renameValue}
                  autoFocus
                  onChange={(e) => setRenameValue(e.target.value)}
                  onClick={(e) => e.stopPropagation()}
                  onKeyDown={(e) => {
                    e.stopPropagation();
                    if (e.key === "Enter") void saveRename(f);
                    if (e.key === "Escape") setRenamingId(null);
                  }}
                  onBlur={() => void saveRename(f)}
                  aria-label={`Rename ${f.title}`}
                />
              ) : (
                <span>
                  <span className="feed-row-title">
                    {f.title}
                    {f.last_error && (
                      <span className="feed-error-badge" title={f.last_error}>
                        ▲
                      </span>
                    )}
                  </span>
                  <span className="feed-row-sub">
                    {hostnameOf(f.site_url ?? f.url)} · {relPoll(f.last_polled)}
                  </span>
                </span>
              )}
              <span className="feed-row-end">
                {f.unread_count > 0 && <span className="unread-badge">{f.unread_count}</span>}
                <span className="feed-row-tools">
                  <button
                    type="button"
                    className="feed-tool"
                    aria-label={`Refresh ${f.title}`}
                    title="Refresh now"
                    onClick={(e) => {
                      e.stopPropagation();
                      void refreshOne(f);
                    }}
                  >
                    ↻
                  </button>
                  <button
                    type="button"
                    className="feed-tool"
                    aria-label={`Rename ${f.title}`}
                    title="Rename"
                    onClick={(e) => {
                      e.stopPropagation();
                      setRenameValue(f.title);
                      setRenamingId(f.id);
                    }}
                  >
                    ✎
                  </button>
                  <button
                    type="button"
                    className="feed-tool danger"
                    aria-label={`Remove ${f.title}`}
                    title="Remove"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete(f);
                    }}
                  >
                    ×
                  </button>
                </span>
              </span>
            </div>
          </li>
        ))}
      </ul>

      <button
        type="button"
        className="btn btn-ghost"
        onClick={() => void refresh()}
        disabled={refreshing}
      >
        <span>{refreshing ? "Polling…" : "Refresh all"}</span>
        <span className="btn-arrow">↻</span>
      </button>

      <form onSubmit={submit} className="feed-form corner-marks">
        <span className="eyebrow eyebrow-ink">01 — Commit new feed</span>
        <div>
          <label className="feed-form-label" htmlFor="feed-url">
            URL
          </label>
          <input
            id="feed-url"
            placeholder="https://example.com/feed.xml"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            required
          />
        </div>
        <div>
          <label className="feed-form-label" htmlFor="feed-title">
            Title
          </label>
          <input
            id="feed-title"
            placeholder="Short label"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
          />
        </div>
        <button type="submit" className="btn" disabled={busy}>
          <span>{busy ? "Committing…" : "Commit feed"}</span>
          <span className="btn-arrow">→</span>
        </button>
      </form>

      <div className="opml-row">
        <input
          ref={fileRef}
          type="file"
          accept=".opml,.xml,text/xml"
          className="visually-hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void importOpml(file);
            e.target.value = "";
          }}
        />
        <button type="button" className="btn btn-ghost" onClick={() => fileRef.current?.click()}>
          <span>Import OPML</span>
          <span className="btn-arrow">↑</span>
        </button>
        <a className="btn btn-ghost" href={api.exportOpmlUrl()} download>
          <span>Export OPML</span>
          <span className="btn-arrow">↓</span>
        </a>
      </div>
    </aside>
  );
}
